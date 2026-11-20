"""Modular tiles and scenes from instanced Moana documents (MOANA-034).

A *layout* (``examples/tiles/<scene>.layout.json``, format ``moana-tile-layout/1``)
names editable source documents (16 x 16 tiles and props that share one palette), the
*variants* of each source (``none``, ``mirror_x`` or ``mirror_y``), a grid of tile
variants and prop placements by pivot. The scene document is derived from them: each
placement becomes one layer whose operations, masks and regions are the source's,
with IDs prefixed by the instance (``tile_r3_c2-lip_1``, ``prop_sign-board``) and the
geometry moved and mirrored with :func:`moana.geometry.transform_box`. Nothing new
enters the document format: no instancing node, tile map or engine; the scene is an
ordinary schema 1.0 document that renders, validates and edits by ID like any other.

Rules that keep the seams invisible (README of ``examples/tiles``):

* every ``dither`` keeps the *pattern origin* of the layout: textures belong to the
  canvas, not to the tile, so they are never mirrored and their phase only depends on
  canvas coordinates (MOANA.md section 10). A placement must start at the pattern
  origin modulo every dither period of its source; a tile side must be a multiple of
  every period of its sources;
* each tile declares the material profile of its four edges (``edges``), read in
  increasing coordinate, and adjacent cells must present equal profiles once the
  variant's mirror is applied (``edge_mismatch`` otherwise).

Subcommands (none touches anything but the paths below):

``check``
    Load and validate every layout, rebuild its scene and compare it byte for byte
    with the versioned ``<scene>.moana.json``. Exit code 1 on any difference.
``build``
    Rewrite the versioned scene documents from their layouts.
``preview [--out DIR]``
    Write review images under ``artifacts/tiles`` (ignored by Git): scene at 1x and
    4x, every variant repeated 3 x 3 at 8x, the atlas and its manifest.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Annotated, Any, Final, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field
from pydantic import ValidationError as PydanticValidationError

from moana.api import Document, export_png, load_document, render
from moana.core.coordinates import Box, Point
from moana.core.errors import MoanaError
from moana.core.limits import MAX_LAYERS, MAX_MASKS, MAX_OPERATIONS, MAX_REGIONS
from moana.export import SheetFrame, export_spritesheet
from moana.export.spritesheet import FramePixels
from moana.geometry import Transform, transform_box

ROOT: Final = Path(__file__).resolve().parents[1]
TILES_DIR: Final = ROOT / "examples" / "tiles"
PREVIEW_DIR: Final = ROOT / "artifacts" / "tiles"
LAYOUT_FORMAT: Final = "moana-tile-layout/1"
TRANSFORMS: Final = ("none", "mirror_x", "mirror_y")
SIDES: Final = ("n", "e", "s", "w")
SHAPE_OPERATIONS: Final = frozenset({"rect", "ellipse", "pixel", "line"})
MASK_OPERATIONS: Final = frozenset({"dither", "outline"})
SHAPE_MASKS: Final = frozenset({"rect", "ellipse", "pixel", "line"})
COMBINATION_MASKS: Final = frozenset({"union", "intersect", "subtract", "xor"})
MAX_LAYOUT_BYTES: Final = 256 * 1024
"""Largest layout file read (checked with ``stat`` before reading)."""
MAX_SOURCE_BYTES: Final = 1024 * 1024
"""Largest source document read (checked with ``stat`` before reading)."""
ATLAS_COLUMNS: Final = 5
ATLAS_FRAME_MS: Final = 100
"""Duration written for every atlas frame: the manifest needs one; tiles are static."""

type JsonObject = dict[str, Any]
type TransformName = Literal["none", "mirror_x", "mirror_y"]
type Kind = Literal["tile", "prop"]
type RGBA = np.ndarray[Any, np.dtype[np.uint8]]


class LayoutError(ValueError):
    """An invalid layout; ``reason`` is a stable machine-readable code."""

    def __init__(self, message: str, reason: str) -> None:
        super().__init__(message)
        self.reason = reason


class _Entry(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


_Pair = Annotated[list[int], Field(min_length=2, max_length=2)]
_Name = Annotated[str, Field(min_length=1, max_length=64)]


class _SourceEntry(_Entry):
    id: _Name
    kind: Literal["tile", "prop"]
    path: Annotated[str, Field(min_length=1, max_length=256)]
    pivot: _Pair
    edges: dict[str, str] = {}
    border_operations: list[_Name] = []


class _VariantEntry(_Entry):
    id: _Name
    source: _Name
    transform: Literal["none", "mirror_x", "mirror_y"]


class _PropEntry(_Entry):
    id: _Name
    variant: _Name
    at: _Pair


class _LayoutEntry(_Entry):
    format: str
    id: _Name
    scene: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9-]*\.moana\.json$")]
    document_id: _Name
    seed: Annotated[int, Field(ge=0)]
    tile_size: _Pair
    pattern_origin: _Pair
    sources: Annotated[list[_SourceEntry], Field(min_length=1)]
    variants: list[_VariantEntry]
    grid: list[list[_Name]]
    props: list[_PropEntry]
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class Source:
    """One editable source document: its raw JSON tree and its validated model.

    ``border_operations`` are the shape operations allowed to touch the tile border
    (fills, the grass/dirt frontier); every other detail stays one pixel inside.
    """

    id: str
    kind: Kind
    path: str
    pivot: tuple[int, int]
    edges: Mapping[str, str]
    tree: Mapping[str, Any]
    document: Document
    border_operations: tuple[str, ...] = ()

    @property
    def size(self) -> tuple[int, int]:
        return self.document.canvas.width, self.document.canvas.height

    @property
    def dither_periods(self) -> tuple[int, ...]:
        layer = self.tree["layers"][0]
        return tuple(sorted({op["size"] for op in layer["operations"] if op["type"] == "dither"}))


@dataclass(frozen=True, slots=True)
class Variant:
    """A source drawn with one mirror; its pivot and edges follow the mirror."""

    id: str
    source: Source
    transform: TransformName

    @property
    def pivot(self) -> tuple[int, int]:
        """The source pivot (pixel-edge coordinates) after the mirror."""
        (px, py), (w, h) = self.source.pivot, self.source.size
        if self.transform == "mirror_x":
            return w - px, py
        if self.transform == "mirror_y":
            return px, h - py
        return px, py

    def edge(self, side: str) -> str:
        """The material profile of ``side`` after the mirror (read in increasing coordinate)."""
        edges = self.source.edges
        if self.transform == "mirror_x":
            return {"w": edges["e"], "e": edges["w"]}.get(side) or _reverse(edges[side])
        if self.transform == "mirror_y":
            return {"n": edges["s"], "s": edges["n"]}.get(side) or _reverse(edges[side])
        return edges[side]


@dataclass(frozen=True, slots=True)
class Placement:
    """One instance: its scene ID, its variant and the top-left pixel of its box."""

    id: str
    variant: Variant
    origin: tuple[int, int]


@dataclass(frozen=True, slots=True)
class Layout:
    """A validated layout with its sources, variants, grid and props."""

    path: Path
    id: str
    scene: str
    document_id: str
    seed: int
    tile_size: tuple[int, int]
    pattern_origin: tuple[int, int]
    sources: Mapping[str, Source]
    variants: Mapping[str, Variant]
    grid: tuple[tuple[str, ...], ...]
    props: tuple[tuple[str, str, tuple[int, int]], ...]
    metadata: Mapping[str, Any]

    @property
    def columns(self) -> int:
        return len(self.grid[0])

    @property
    def rows(self) -> int:
        return len(self.grid)

    @property
    def canvas(self) -> tuple[int, int]:
        return self.columns * self.tile_size[0], self.rows * self.tile_size[1]

    @property
    def scene_path(self) -> Path:
        return self.path.parent / self.scene


def _reverse(profile: str) -> str:
    """``grass*10+dirt*6`` read from the other end: ``dirt*6+grass*10``."""
    return "+".join(reversed(profile.split("+")))


def _unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    keys = [key for key, _ in pairs]
    duplicates = sorted({key for key in keys if keys.count(key) > 1})
    if duplicates:
        raise LayoutError(f"duplicate JSON key {duplicates[0]!r}", "duplicate_key")
    return dict(pairs)


def _read_json(path: Path, limit: int) -> JsonObject:
    """A JSON object of at most ``limit`` bytes (``stat`` first; repeated keys rejected)."""
    if not path.is_file():
        raise LayoutError(f"{path.name} is not a regular file", "not_found")
    if path.stat().st_size > limit:
        raise LayoutError(f"{path.name} is larger than {limit} bytes", "too_large")
    try:
        tree = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise LayoutError(f"{path.name} is not UTF-8 JSON: {error}", "not_json") from None
    if not isinstance(tree, dict):
        raise LayoutError(f"{path.name} must hold a JSON object", "not_object")
    return tree


def confined(folder: Path, relative: str) -> Path:
    """``folder / relative`` if it stays inside ``folder`` (also through symlinks)."""
    posix, windows = PurePosixPath(relative), PureWindowsPath(relative)
    if posix.is_absolute() or windows.is_absolute() or windows.drive or ".." in windows.parts:
        raise LayoutError(f"source path {relative!r} leaves the layout folder", "path_escape")
    base = folder.resolve()
    target = (base / relative).resolve()
    if not target.is_relative_to(base):
        raise LayoutError(f"source path {relative!r} leaves the layout folder", "path_escape")
    return target


def _check_source_document(source_id: str, document: Document) -> None:
    """One plain layer, supported types and canvas-anchored textures at ``[0, 0]``."""
    if document.animations or len(document.layers) != 1:
        raise LayoutError(f"source {source_id} must have exactly one layer", "not_single_layer")
    layer = document.layers[0]
    if not layer.visible or layer.opacity != 255 or layer.mask_id is not None:
        raise LayoutError(f"source {source_id} must have a plain visible layer", "layer_settings")
    for operation in layer.operations:
        if operation.type not in SHAPE_OPERATIONS | MASK_OPERATIONS:
            raise LayoutError(
                f"operation {operation.id} of {source_id} cannot be instanced",
                "unsupported_operation",
            )
        if operation.type == "dither" and tuple(operation.origin) != (0, 0):
            raise LayoutError(
                f"dither {operation.id} of {source_id} must use origin [0, 0]", "dither_origin"
            )
    for mask in document.masks:
        if mask.type not in SHAPE_MASKS | COMBINATION_MASKS:
            raise LayoutError(
                f"mask {mask.id} of {source_id} cannot be instanced", "unsupported_mask"
            )


def operation_box(operation: Mapping[str, Any]) -> tuple[int, int, int, int] | None:
    """Half-open box of a shape operation's geometry; ``None`` for mask operations."""
    if "box" in operation:
        x0, y0, x1, y1 = operation["box"]
        return x0, y0, x1, y1
    points = [operation[key] for key in ("at", "start", "end") if key in operation]
    if not points:
        return None
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return min(xs), min(ys), max(xs) + 1, max(ys) + 1


def _check_border(source: Source) -> None:
    """Only the declared ``border_operations`` may touch the tile border."""
    operations = {op["id"]: op for op in source.tree["layers"][0]["operations"]}
    unknown = sorted(set(source.border_operations) - set(operations))
    if unknown:
        raise LayoutError(f"{source.id} lists unknown border operation {unknown[0]}", "unknown_id")
    if source.kind != "tile":
        return
    w, h = source.size
    for op_id, operation in operations.items():
        box = operation_box(operation)
        if box is None or op_id in source.border_operations:
            continue
        x0, y0, x1, y1 = box
        if x0 <= 0 or y0 <= 0 or x1 >= w or y1 >= h:
            raise LayoutError(f"{op_id} of {source.id} touches the tile border", "detail_on_edge")


def _load_source(folder: Path, entry: _SourceEntry, tile_size: tuple[int, int]) -> Source:
    tree = _read_json(confined(folder, entry.path), MAX_SOURCE_BYTES)
    try:
        document = load_document(copy.deepcopy(tree))
    except MoanaError as error:
        raise LayoutError(f"source {entry.id} is invalid: {error}", "invalid_source") from None
    _check_source_document(entry.id, document)
    if entry.kind == "tile" and set(entry.edges) != set(SIDES):
        raise LayoutError(f"tile {entry.id} must declare its four edges", "missing_edges")
    source = Source(
        entry.id,
        entry.kind,
        entry.path,
        (entry.pivot[0], entry.pivot[1]),
        dict(entry.edges),
        tree,
        document,
        tuple(entry.border_operations),
    )
    if source.size != tile_size:
        raise LayoutError(f"source {entry.id} is not {tile_size[0]}x{tile_size[1]}", "size")
    for period in source.dither_periods:
        if tile_size[0] % period or tile_size[1] % period:
            raise LayoutError(
                f"the tile side is not a multiple of the dither period {period}",
                "period_mismatch",
            )
    _check_border(source)
    return source


def _check_palettes(sources: Mapping[str, Source]) -> None:
    palettes = {source.document.palette for source in sources.values()}
    if len(palettes) != 1:
        raise LayoutError("every source must share one palette", "palette_mismatch")


def _unique(ids: Sequence[str], what: str) -> None:
    seen: set[str] = set()
    for item in ids:
        if item in seen:
            raise LayoutError(f"duplicate {what} ID {item}", "duplicate_id")
        seen.add(item)


def _parse_layout(tree: JsonObject) -> _LayoutEntry:
    if tree.get("format") != LAYOUT_FORMAT:
        raise LayoutError(f"layout format must be {LAYOUT_FORMAT}", "unknown_format")
    try:
        return _LayoutEntry.model_validate(tree)
    except PydanticValidationError as error:
        first = error.errors(include_url=False)[0]
        where = "/".join(str(part) for part in first["loc"])
        raise LayoutError(f"invalid layout at {where}: {first['msg']}", "invalid_layout") from None


def load_layout(path: Path) -> Layout:
    """Read and validate a layout and its sources; ``LayoutError`` on any rule."""
    entry = _parse_layout(_read_json(path, MAX_LAYOUT_BYTES))
    tile_size = (entry.tile_size[0], entry.tile_size[1])
    _unique([source.id for source in entry.sources], "source")
    _unique([variant.id for variant in entry.variants], "variant")
    _unique([prop.id for prop in entry.props], "prop")
    sources = {source.id: _load_source(path.parent, source, tile_size) for source in entry.sources}
    _check_palettes(sources)
    variants: dict[str, Variant] = {}
    for item in entry.variants:
        if item.source not in sources:
            raise LayoutError(f"variant {item.id} names an unknown source", "unknown_source")
        variants[item.id] = Variant(item.id, sources[item.source], item.transform)
    layout = Layout(
        path=path,
        id=entry.id,
        scene=entry.scene,
        document_id=entry.document_id,
        seed=entry.seed,
        tile_size=tile_size,
        pattern_origin=(entry.pattern_origin[0], entry.pattern_origin[1]),
        sources=sources,
        variants=variants,
        grid=tuple(tuple(row) for row in entry.grid),
        props=tuple((p.id, p.variant, (p.at[0], p.at[1])) for p in entry.props),
        metadata=entry.metadata,
    )
    check_layout(layout)
    check_mirrors(layout)
    return layout


def check_layout(layout: Layout) -> None:
    """Grid shape, kinds, matching edges, dither phase and props inside the canvas."""
    _check_grid(layout)
    width, height = layout.canvas
    for placement in placements(layout):
        _check_phase(layout, placement)
        (x, y), (w, h) = placement.origin, placement.variant.source.size
        if x < 0 or y < 0 or x + w > width or y + h > height:
            raise LayoutError(f"{placement.id} does not fit in the canvas", "off_canvas")


def _solid(tree: Mapping[str, Any]) -> JsonObject:
    """``tree`` with every dither at full coverage: its geometry without a phase."""
    solid = copy.deepcopy(dict(tree))
    for operation in solid["layers"][0]["operations"]:
        if operation["type"] == "dither":
            operation["coverage"] = operation["size"] * operation["size"]
    return solid


def rgba(document: Document) -> RGBA:
    """The rendered pixels as a ``(height, width, 4)`` array."""
    result = render(document)
    pixels = np.frombuffer(result.rgba, dtype=np.uint8)
    return pixels.reshape(result.height, result.width, 4).copy()


def check_mirrors(layout: Layout) -> None:
    """Every mirrored variant must equal the flipped source pixels (``mirror_asymmetry``).

    Re-rasterising mirrored geometry can differ from flipping its pixels (a line's
    tie-breaking follows its direction), so each mirror is checked, with the
    dithers at full coverage (phase-free), against ``numpy.flip`` of the source.
    """
    for variant in layout.variants.values():
        if variant.transform == "none":
            continue
        tree = _solid(variant.source.tree)
        source = rgba(load_document(copy.deepcopy(tree)))
        item = (variant.id, variant.source.id, tree, placement_transform(variant, (0, 0)))
        mirrored = rgba(
            load_document(_compose(layout, "mirror_check", variant.source.size, [item]))
        )
        axis = 1 if variant.transform == "mirror_x" else 0
        if not np.array_equal(mirrored, np.flip(source, axis=axis)):
            raise LayoutError(
                f"variant {variant.id} is not the pixel mirror of {variant.source.id}",
                "mirror_asymmetry",
            )


def _variant(layout: Layout, variant_id: str, kind: Kind) -> Variant:
    variant = layout.variants.get(variant_id)
    if variant is None:
        raise LayoutError(f"unknown variant {variant_id}", "unknown_variant")
    if variant.source.kind != kind:
        raise LayoutError(f"variant {variant_id} is not a {kind}", "wrong_kind")
    return variant


def _check_grid(layout: Layout) -> None:
    """Rectangular grid of tile variants whose neighbouring edges match."""
    if not layout.grid or not layout.grid[0] or any(len(r) != layout.columns for r in layout.grid):
        raise LayoutError("the grid must be a non-empty rectangle", "grid_shape")
    for r, row in enumerate(layout.grid):
        for c, variant_id in enumerate(row):
            variant = _variant(layout, variant_id, "tile")
            if c + 1 < layout.columns:
                right = _variant(layout, row[c + 1], "tile")
                if variant.edge("e") != right.edge("w"):
                    raise LayoutError(f"seam between r{r}c{c} and r{r}c{c + 1}", "edge_mismatch")
            if r + 1 < layout.rows:
                below = _variant(layout, layout.grid[r + 1][c], "tile")
                if variant.edge("s") != below.edge("n"):
                    raise LayoutError(f"seam between r{r}c{c} and r{r + 1}c{c}", "edge_mismatch")


def _check_phase(layout: Layout, placement: Placement) -> None:
    ox, oy = layout.pattern_origin
    x, y = placement.origin
    for period in placement.variant.source.dither_periods:
        if (x - ox) % period or (y - oy) % period:
            raise LayoutError(
                f"{placement.id} breaks the dither phase of period {period}", "phase_mismatch"
            )


def placements(layout: Layout) -> list[Placement]:
    """Every instance in paint order: tiles row by row, then props as listed."""
    w, h = layout.tile_size
    result = [
        Placement(f"tile_r{r}_c{c}", _variant(layout, variant_id, "tile"), (c * w, r * h))
        for r, row in enumerate(layout.grid)
        for c, variant_id in enumerate(row)
    ]
    for prop_id, variant_id, (ax, ay) in layout.props:
        variant = _variant(layout, variant_id, "prop")
        px, py = variant.pivot
        result.append(Placement(prop_id, variant, (ax - px, ay - py)))
    return result


def placement_transform(variant: Variant, origin: tuple[int, int]) -> Transform:
    """Pixel mapping of a source into the scene: mirror about the box, then move."""
    (x, y), (w, h) = origin, variant.source.size
    if variant.transform == "mirror_x":
        return Transform(mirror=True, offset=Point(x + w - 1, y))
    if variant.transform == "mirror_y":
        return Transform(mirror=True, rotation=180, offset=Point(x, y + h - 1))
    return Transform(offset=Point(x, y))


def _box(value: Sequence[int], transform: Transform) -> list[int]:
    box = transform_box(Box(*value), transform)
    return [box.x0, box.y0, box.x1, box.y1]


def _point(value: Sequence[int], transform: Transform) -> list[int]:
    x, y = value
    return _box((x, y, x + 1, y + 1), transform)[:2]


def _geometry(node: Mapping[str, Any], transform: Transform) -> JsonObject:
    """``node`` with its geometric members mapped (shape operations and shape masks)."""
    moved = dict(node)
    if "box" in node:
        moved["box"] = _box(node["box"], transform)
    for member in ("at", "start", "end"):
        if member in node:
            moved[member] = _point(node[member], transform)
    return moved


def instance(
    tree: Mapping[str, Any], prefix: str, transform: Transform, origin: tuple[int, int]
) -> tuple[list[JsonObject], list[JsonObject], list[JsonObject]]:
    """Operations, masks and regions of ``tree`` placed with ``transform``.

    IDs and references gain ``<prefix>-``; colours are kept (shared palette);
    textures keep the canvas pattern ``origin`` instead of being moved.
    """

    def ref(local: str) -> str:
        return f"{prefix}-{local}"

    operations = []
    for operation in tree["layers"][0]["operations"]:
        moved = _geometry(operation, transform)
        moved["id"] = ref(operation["id"])
        if "mask_id" in operation:
            moved["mask_id"] = ref(operation["mask_id"])
        if operation["type"] == "dither":
            moved["origin"] = list(origin)
        operations.append(moved)
    masks = []
    for mask in tree.get("masks", []):
        moved = _geometry(mask, transform)
        moved["id"] = ref(mask["id"])
        if "masks" in mask:
            moved["masks"] = [ref(item) for item in mask["masks"]]
        masks.append(moved)
    regions = [
        {
            "id": ref(region["id"]),
            "mask_id": ref(region["mask_id"]),
            "operation_ids": [ref(item) for item in region.get("operation_ids", [])],
        }
        for region in tree.get("regions", [])
    ]
    return operations, masks, regions


def _palette(layout: Layout) -> Any:
    return copy.deepcopy(next(iter(layout.sources.values())).tree["palette"])


type _Item = tuple[str, str, Mapping[str, Any], Transform]
"""Layer ID, source ID, source tree and transform of one placed instance."""


def _check_budget(layers: int, operations: int, masks: int, regions: int) -> None:
    for name, count, limit in (
        ("layers", layers, MAX_LAYERS),
        ("operations", operations, MAX_OPERATIONS),
        ("masks", masks, MAX_MASKS),
        ("regions", regions, MAX_REGIONS),
    ):
        if count > limit:
            raise LayoutError(f"the scene needs {count} {name}; at most {limit}", "budget")


def _compose(
    layout: Layout,
    document_id: str,
    canvas: tuple[int, int],
    items: Sequence[_Item],
    metadata: Mapping[str, Any] | None = None,
) -> JsonObject:
    layers, masks, regions = [], [], []
    for layer_id, source_id, tree, transform in items:
        operations, placed_masks, placed_regions = instance(
            tree, layer_id, transform, layout.pattern_origin
        )
        layers.append({"id": layer_id, "name": source_id, "operations": operations})
        masks.extend(placed_masks)
        regions.extend(placed_regions)
    total = sum(len(layer["operations"]) for layer in layers)
    _check_budget(len(layers), total, len(masks), len(regions))
    return {
        "schema_version": "1.0",
        "id": document_id,
        "revision": 0,
        "seed": layout.seed,
        "canvas": {"width": canvas[0], "height": canvas[1], "profile": "strict"},
        "palette": _palette(layout),
        "masks": masks,
        "regions": regions,
        "layers": layers,
        "metadata": dict(metadata or {"title": document_id}),
    }


def _item(placement: Placement) -> _Item:
    variant = placement.variant
    name = f"{variant.source.id} ({variant.transform})"
    return placement.id, name, variant.source.tree, placement_transform(variant, placement.origin)


def build_scene(layout: Layout) -> JsonObject:
    """The scene document of ``layout`` as a JSON tree (revision 0)."""
    items = [_item(placement) for placement in placements(layout)]
    return _compose(layout, layout.document_id, layout.canvas, items, layout.metadata)


def variant_document(layout: Layout, variant_id: str) -> JsonObject:
    """One variant alone on a tile-sized canvas with its box at ``(0, 0)``: its atlas frame.

    The dithers keep the layout's pattern origin. Every cell starts at that origin
    modulo each period (checked by ``check_layout``, and cell ``(0, 0)`` exists), so
    the frame has the phase of every placement of the variant.
    """
    variant = layout.variants[variant_id]
    document_id = f"{layout.id}_{variant_id}".replace("-", "_")
    title = f"{variant.source.id} ({variant.transform})"
    item = _item(Placement(variant_id, variant, (0, 0)))
    return _compose(layout, document_id, layout.tile_size, [item], {"title": title})


def _line(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def _items(key: str, values: Sequence[object], indent: str) -> Iterator[str]:
    if not values:
        yield f'{indent}"{key}": [],'
        return
    yield f'{indent}"{key}": ['
    body = ",\n".join(f"{indent}  {_line(value)}" for value in values)
    yield body
    yield f"{indent}],"


def format_document(tree: Mapping[str, Any]) -> str:
    """Deterministic JSON text: one mask, region and operation per line."""
    lines = ["{"]
    for key in ("schema_version", "id", "revision", "seed", "canvas", "palette"):
        lines.append(f'  "{key}": {_line(tree[key])},')
    lines.extend(_items("masks", tree["masks"], "  "))
    lines.extend(_items("regions", tree["regions"], "  "))
    lines.append('  "layers": [')
    layer_texts = []
    for layer in tree["layers"]:
        head = f'    {{"id": {_line(layer["id"])}, "name": {_line(layer["name"])}, "operations": ['
        body = ",\n".join(f"      {_line(op)}" for op in layer["operations"])
        layer_texts.append(f"{head}\n{body}\n    ]}}")
    lines.append(",\n".join(layer_texts))
    lines.append("  ],")
    lines.append(f'  "metadata": {_line(tree["metadata"])}')
    lines.append("}")
    return "\n".join(lines) + "\n"


def layout_paths(root: Path = TILES_DIR) -> list[Path]:
    """Every layout of ``root``, sorted."""
    return sorted(root.glob("*.layout.json"))


def atlas_frames(layout: Layout) -> list[SheetFrame]:
    """One frame per variant, in layout order, with the variant pivot."""
    frames = []
    for variant_id, variant in layout.variants.items():
        result = render(load_document(variant_document(layout, variant_id)))
        pixels = FramePixels(result.width, result.height, result.rgba)
        frames.append(SheetFrame(variant_id, ATLAS_FRAME_MS, Point(*variant.pivot), pixels))
    return frames


def check(root: Path = TILES_DIR) -> list[str]:
    """Problems of every layout of ``root``: invalid layouts or stale scenes."""
    errors = []
    for path in layout_paths(root):
        try:
            layout = load_layout(path)
            expected = format_document(build_scene(layout))
            load_document(json.loads(expected))
        except (LayoutError, MoanaError) as error:
            errors.append(f"{path.name}: {error}")
            continue
        actual = (
            layout.scene_path.read_text(encoding="utf-8") if layout.scene_path.exists() else None
        )
        if actual != expected:
            errors.append(f"{path.name}: {layout.scene} is stale; run scripts/tiles.py build")
    return errors


def build(root: Path = TILES_DIR) -> list[Path]:
    """Rewrite every scene document of ``root`` from its layout."""
    written = []
    for path in layout_paths(root):
        layout = load_layout(path)
        layout.scene_path.write_text(format_document(build_scene(layout)), encoding="utf-8")
        written.append(layout.scene_path)
    return written


def _scaled(image: np.ndarray[Any, np.dtype[np.uint8]], factor: int) -> Any:
    return np.repeat(np.repeat(image, factor, axis=0), factor, axis=1)


def preview(out: Path, root: Path = TILES_DIR) -> list[Path]:
    """Write the review images of every layout under ``out`` (overwriting them)."""
    from PIL import Image

    written = []
    for path in layout_paths(root):
        layout = load_layout(path)
        folder = out / layout.id
        folder.mkdir(parents=True, exist_ok=True)
        scene = load_document(build_scene(layout))
        for factor in (1, 4):
            target = folder / f"{layout.id}-{factor}x.png"
            export_png(render(scene), target, scale=factor, overwrite=True)
            written.append(target)
        for variant_id in layout.variants:
            tile = rgba(load_document(variant_document(layout, variant_id)))
            target = folder / f"variant-{variant_id}-3x3-8x.png"
            Image.fromarray(_scaled(np.tile(tile, (3, 3, 1)), 8)).save(target)
            written.append(target)
        image, manifest = folder / f"{layout.id}-atlas.png", folder / f"{layout.id}-atlas.json"
        export_spritesheet(
            atlas_frames(layout), image, manifest, columns=ATLAS_COLUMNS, overwrite=True
        )
        written.extend((image, manifest))
    return written


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check", help="validate layouts and compare the versioned scenes")
    commands.add_parser("build", help="rewrite the versioned scenes from their layouts")
    preview_parser = commands.add_parser("preview", help="write review images to artifacts")
    preview_parser.add_argument("--out", type=Path, default=PREVIEW_DIR)
    args = parser.parse_args(argv)
    if args.command == "build":
        for path in build():
            print(f"wrote {path.relative_to(ROOT)}")
        return 0
    if args.command == "preview":
        for path in preview(args.out):
            print(f"wrote {path}")
        return 0
    errors = check()
    for error in errors:
        print(error)
    if not errors:
        print(f"Tiles OK: {len(layout_paths())} layouts")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
