"""Modular tiles and the meadow scene of ``examples/tiles`` (MOANA-034).

Oracles are independent of ``scripts/tiles.py``: ``numpy`` tiling and flips, the
Bayer 2 x 2 threshold of MOANART.md section 10 evaluated on canvas coordinates,
material classes read from palette IDs, boxes computed by hand from the documented
pivots, and the atlas pasted back with plain array slicing.
"""

from __future__ import annotations

import copy
import dataclasses
import json
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import pytest
from PIL import Image

from moanart.api import (
    Document,
    apply_edit,
    evaluate_quality,
    export_png,
    load_document,
    render,
    snapshot_digest,
)
from moanart.export import SheetFrame, export_spritesheet, load_spritesheet
from moanart.render import render_with_regions
from scripts.tiles import (
    ATLAS_COLUMNS,
    MAX_SOURCE_BYTES,
    TILES_DIR,
    Layout,
    LayoutError,
    Source,
    TransformName,
    Variant,
    atlas_frames,
    build_scene,
    check,
    check_layout,
    check_mirrors,
    format_document,
    load_layout,
    main,
    preview,
    variant_document,
)

type RGBA = npt.NDArray[np.uint8]

LAYOUT_PATH = TILES_DIR / "meadow.layout.json"
LAYOUT = load_layout(LAYOUT_PATH)
SCENE = load_document(LAYOUT.scene_path)
TILE = 16
BAYER_2 = ((0, 2), (3, 1))


def _pixels(document: Document) -> RGBA:
    result = render(document)
    return np.frombuffer(result.rgba, dtype=np.uint8).reshape(result.height, result.width, 4)


def _tree_pixels(tree: dict[str, Any]) -> RGBA:
    return _pixels(load_document(copy.deepcopy(tree)))


def _variant_pixels(layout: Layout, variant_id: str) -> RGBA:
    return _tree_pixels(variant_document(layout, variant_id))


def _rgba(hex_value: str) -> tuple[int, ...]:
    return tuple(bytes.fromhex(hex_value[1:]))


COLOURS = {colour.id: _rgba(colour.rgba) for colour in SCENE.palette.colors}


def _classes(image: RGBA) -> npt.NDArray[np.str_]:
    """Material class of every pixel: the palette ID before ``_`` (grass, dirt...)."""
    lookup = {rgba: colour_id.split("_")[0] for colour_id, rgba in COLOURS.items()}
    height, width = image.shape[:2]
    return np.array(
        [[lookup[tuple(int(v) for v in image[y, x])] for x in range(width)] for y in range(height)]
    )


def _profile(line: npt.NDArray[np.str_]) -> str:
    """Run-length profile ``grass*10+dirt*6`` of a row or column of classes."""
    runs: list[list[Any]] = []
    for value in line.tolist():
        if runs and runs[-1][0] == value:
            runs[-1][1] += 1
        else:
            runs.append([value, 1])
    return "+".join(f"{value}*{count}" for value, count in runs)


def _with_tree(layout: Layout, source_id: str, tree: dict[str, Any]) -> Layout:
    """``layout`` with the source ``source_id`` replaced by ``tree`` (and its variants)."""
    source = dataclasses.replace(layout.sources[source_id], tree=tree)
    sources = {**layout.sources, source_id: source}
    variants = {
        key: Variant(v.id, sources[v.source.id], v.transform) for key, v in layout.variants.items()
    }
    return dataclasses.replace(layout, sources=sources, variants=variants)


def _repeat(layout: Layout, variant_id: str, rows: int, columns: int) -> Layout:
    grid = tuple((variant_id,) * columns for _ in range(rows))
    return dataclasses.replace(layout, grid=grid, props=())


# T1: seams, mirrors and translation by multiples of the tile size.


@pytest.mark.parametrize(
    "variant_id", [v for v, x in LAYOUT.variants.items() if x.source.kind == "tile"]
)
def test_repeated_tile_equals_its_periodic_extension(variant_id: str) -> None:
    variant = LAYOUT.variants[variant_id]
    rows = 3 if variant.edge("n") == variant.edge("s") else 1
    columns = 3 if variant.edge("w") == variant.edge("e") else 1
    assert columns == 3  # every tile of the meadow repeats horizontally
    tile = _variant_pixels(LAYOUT, variant_id)
    repeated = _repeat(LAYOUT, variant_id, rows, columns)
    check_layout(repeated)

    composed = _tree_pixels(build_scene(repeated))

    # Each copy is the tile translated by a multiple of 16: the composition is the
    # periodic extension, so the horizontal (and, when it repeats, vertical) seams
    # continue exactly as the tile's opposite edges meet.
    assert np.array_equal(composed, np.tile(tile, (rows, columns, 1)))


def test_the_scene_cells_are_the_tiles_translated_by_whole_tiles() -> None:
    ground = _tree_pixels(build_scene(dataclasses.replace(LAYOUT, props=())))
    tiles = {variant_id: _variant_pixels(LAYOUT, variant_id) for variant_id in LAYOUT.variants}
    for r, row in enumerate(LAYOUT.grid):
        for c, variant_id in enumerate(row):
            cell = ground[r * TILE : (r + 1) * TILE, c * TILE : (c + 1) * TILE]
            assert np.array_equal(cell, tiles[variant_id]), (r, c)


def _assert_canvas_phase(tree: dict[str, Any], origin: tuple[int, int] = (0, 0)) -> RGBA:
    """Keep only the dithers of ``tree`` and check every painted pixel against the
    Bayer 2 x 2 threshold of MOANART.md section 10 on canvas coordinates."""
    tree = copy.deepcopy(tree)
    colour_a, colour_b = set(), set()
    for layer in tree["layers"]:
        dithers = [op for op in layer["operations"] if op["type"] == "dither"]
        for op in dithers:
            assert (op["size"], op["coverage"], op["origin"]) == (2, 2, list(origin))
            colour_a.add(COLOURS[op["color_a"]])
            colour_b.add(COLOURS[op["color_b"]])
        layer["operations"] = dithers
    tree["regions"] = []
    assert not colour_a & colour_b
    image = _tree_pixels(tree)
    ys, xs = np.nonzero(image[..., 3])
    assert ys.size > 0
    ox, oy = origin
    for y, x in zip(ys.tolist(), xs.tolist(), strict=True):
        # M[(y - oy) mod 2][(x - ox) mod 2] < coverage picks colour_b.
        picks_b = BAYER_2[(y - oy) % 2][(x - ox) % 2] < 2
        assert tuple(int(v) for v in image[y, x]) in (colour_b if picks_b else colour_a)
    return image


def test_dither_phase_belongs_to_the_canvas_across_every_seam() -> None:
    image = _assert_canvas_phase(build_scene(dataclasses.replace(LAYOUT, props=())))
    opaque = image[..., 3] > 0
    # Texture patches cross vertical seams (x = 16k - 1 | 16k) and stay in phase.
    assert any(opaque[:, 16 * k - 1].any() and opaque[:, 16 * k].any() for k in range(1, 8))
    crossing = [
        (y, k)
        for k in range(1, 8)
        for y in range(128)
        if opaque[y, 16 * k - 1] and opaque[y, 16 * k]
    ]
    assert crossing


@pytest.mark.parametrize(
    "variant_id", [v for v, x in LAYOUT.variants.items() if x.transform != "none"]
)
def test_mirrored_variant_is_the_flipped_source_geometry(variant_id: str) -> None:
    variant = LAYOUT.variants[variant_id]
    tree = copy.deepcopy(dict(variant.source.tree))
    for op in tree["layers"][0]["operations"]:
        if op["type"] == "dither":
            op["coverage"] = 4  # every masked pixel takes colour_b: phase-free geometry
    solid = _with_tree(LAYOUT, variant.source.id, tree)
    axis = 1 if variant.transform == "mirror_x" else 0

    assert np.array_equal(
        _variant_pixels(solid, variant_id), np.flip(_tree_pixels(tree), axis=axis)
    )


@pytest.mark.parametrize(
    "variant_id", [v for v, x in LAYOUT.variants.items() if x.transform != "none"]
)
def test_mirrored_variant_keeps_the_canvas_texture_phase(variant_id: str) -> None:
    frame = variant_document(LAYOUT, variant_id)
    if not any(op["type"] == "dither" for op in frame["layers"][0]["operations"]):
        pytest.skip("variant without texture")
    # The mirrored masks are filled with the canvas phase, not a flipped checker
    # (15 - x has the other parity, so a pixel flip would fail this oracle).
    _assert_canvas_phase(frame)


@pytest.mark.parametrize("source_id", [s for s, x in LAYOUT.sources.items() if x.kind == "tile"])
def test_documented_edges_match_the_rendered_tile(source_id: str) -> None:
    source = LAYOUT.sources[source_id]
    classes = _classes(_tree_pixels(dict(source.tree)))
    rendered = {
        "n": _profile(classes[0, :]),
        "s": _profile(classes[-1, :]),
        "w": _profile(classes[:, 0]),
        "e": _profile(classes[:, -1]),
    }
    assert rendered == dict(source.edges)


def test_scene_seams_keep_the_material_on_both_sides() -> None:
    classes = _classes(_tree_pixels(build_scene(dataclasses.replace(LAYOUT, props=()))))
    for k in range(1, 8):
        assert np.array_equal(classes[:, 16 * k - 1], classes[:, 16 * k]), f"column seam {k}"
        assert np.array_equal(classes[16 * k - 1, :], classes[16 * k, :]), f"row seam {k}"


@pytest.mark.parametrize("source_id", [s for s, x in LAYOUT.sources.items() if x.kind == "tile"])
def test_raw_tile_wraps_onto_itself(source_id: str) -> None:
    # Oracle on the source render alone (no generator): a tile that repeats along an
    # axis has the same material on its first and last pixel line of that axis.
    source = LAYOUT.sources[source_id]
    classes = _classes(_tree_pixels(dict(source.tree)))
    assert np.array_equal(classes[:, 0], classes[:, -1])  # every tile repeats sideways
    if source.edges["n"] == source.edges["s"]:
        assert np.array_equal(classes[0, :], classes[-1, :])


def test_tiles_keep_their_detail_off_the_edges() -> None:
    # Only the operations each tile declares in ``border_operations`` (fills, the
    # grass/dirt frontier) and the wrapping textures touch the border, so mirrors
    # and translations cannot cut a tuft or a pebble at a seam.
    for source in (s for s in LAYOUT.sources.values() if s.kind == "tile"):
        assert "fill" in source.border_operations
        for op in source.tree["layers"][0]["operations"]:
            if op["id"] in source.border_operations or op["type"] == "dither":
                continue
            boxes = [op["box"]] if "box" in op else []
            points = [op[k] for k in ("at", "start", "end") if k in op]
            boxes += [[x, y, x + 1, y + 1] for x, y in points]
            for x0, y0, x1, y1 in boxes:
                assert min(x0, y0) > 0 and max(x1, y1) < TILE, (source.id, op["id"])


# Negative and edge cases of the layout rules.


def test_grass_cannot_sit_on_top_of_dirt() -> None:
    grid = (("grass",), ("dirt",))
    with pytest.raises(LayoutError) as caught:
        check_layout(dataclasses.replace(LAYOUT, grid=grid, props=()))
    assert caught.value.reason == "edge_mismatch"


def test_side_seam_between_edge_and_grass_is_rejected() -> None:
    with pytest.raises(LayoutError) as caught:
        check_layout(dataclasses.replace(LAYOUT, grid=(("edge_n", "grass"),), props=()))
    assert caught.value.reason == "edge_mismatch"


@pytest.mark.parametrize(
    ("grid", "props", "reason"),
    [
        ((), (), "grid_shape"),
        ((("grass", "grass"), ("grass",)), (), "grid_shape"),
        ((("missing",),), (), "unknown_variant"),
        ((("rock",),), (), "wrong_kind"),
        ((("grass",),), (("prop_x", "grass", (8, 15)),), "wrong_kind"),
    ],
)
def test_layout_shape_errors(
    grid: tuple[tuple[str, ...], ...],
    props: tuple[tuple[str, str, tuple[int, int]], ...],
    reason: str,
) -> None:
    with pytest.raises(LayoutError) as caught:
        check_layout(dataclasses.replace(LAYOUT, grid=grid, props=props))
    assert caught.value.reason == reason


def test_prop_with_a_texture_must_keep_the_dither_phase() -> None:
    tree = copy.deepcopy(dict(LAYOUT.sources["rock"].tree))
    tree["layers"][0]["operations"].append(
        {
            "id": "lichen",
            "type": "dither",
            "size": 2,
            "coverage": 2,
            "origin": [0, 0],
            "color_a": "stone_1",
            "color_b": "stone_2",
            "mask_id": "body_m",
        }
    )
    layout = _with_tree(LAYOUT, "rock", tree)
    check_layout(dataclasses.replace(layout, props=(("prop_rock", "rock", (104, 25)),)))
    # Top-left (96, 11): y is odd, so the checker would start one phase late.
    with pytest.raises(LayoutError) as caught:
        check_layout(dataclasses.replace(layout, props=(("prop_rock", "rock", (104, 26)),)))
    assert caught.value.reason == "phase_mismatch"


def _write_layout(
    folder: Path, source: dict[str, Any], border: tuple[str, ...] = ("fill",), **changes: Any
) -> Path:
    (folder / "tile.moanart.json").write_text(json.dumps(source), encoding="utf-8")
    size = source["canvas"]["width"]
    layout = {
        "format": "moanart-tile-layout/1",
        "id": "mini",
        "scene": "mini.moanart.json",
        "document_id": "scene_mini",
        "seed": 1,
        "tile_size": [size, size],
        "pattern_origin": [0, 0],
        "sources": [
            {
                "id": "t",
                "kind": "tile",
                "path": "tile.moanart.json",
                "pivot": [0, 0],
                "edges": {side: f"grass*{size}" for side in "nesw"},
                "border_operations": border,
            }
        ],
        "variants": [{"id": "t", "source": "t", "transform": "none"}],
        "grid": [["t", "t"]],
        "props": [],
        "metadata": {"title": "mini"},
    }
    layout.update(changes)
    path = folder / "mini.layout.json"
    path.write_text(json.dumps(layout), encoding="utf-8")
    return path


def _mini_source(size: int, operations: list[dict[str, Any]]) -> dict[str, Any]:
    tree = copy.deepcopy(dict(LAYOUT.sources["grass"].tree))
    tree["canvas"] = {"width": size, "height": size, "profile": "strict"}
    tree["masks"] = [{"id": "all_m", "type": "rect", "box": [0, 0, size, size]}]
    tree["regions"] = []
    tree["layers"][0]["operations"] = [
        {"id": "fill", "type": "rect", "box": [0, 0, size, size], "color": "grass_1"},
        *operations,
    ]
    return tree


def _dither(size: int, origin: list[int]) -> dict[str, Any]:
    return {
        "id": "texture",
        "type": "dither",
        "size": size,
        "coverage": 2,
        "origin": origin,
        "color_a": "grass_1",
        "color_b": "grass_2",
        "mask_id": "all_m",
    }


@pytest.mark.parametrize(
    ("size", "operations", "changes", "reason"),
    [
        (6, [_dither(4, [0, 0])], {}, "period_mismatch"),
        (8, [_dither(2, [1, 0])], {}, "dither_origin"),
        (
            8,
            [{"id": "dot", "type": "polygon", "points": [[1, 1], [3, 1], [2, 3]], "color": "ink"}],
            {},
            "unsupported_operation",
        ),
        (8, [], {"format": "moanart-tile-layout/9"}, "unknown_format"),
        (8, [], {"tile_size": [16, 16]}, "size"),
        (
            8,
            [],
            {"variants": [{"id": "t", "source": "t", "transform": "rotate"}]},
            "invalid_layout",
        ),
        (8, [], {"variants": [{"id": "t", "source": "x", "transform": "none"}]}, "unknown_source"),
        (8, [], {"tile_size": [8]}, "invalid_layout"),
        (8, [], {"sources": 5}, "invalid_layout"),
        (8, [], {"seed": "1"}, "invalid_layout"),
        (8, [], {"grid": [["t", 3]]}, "invalid_layout"),
        (8, [], {"scene": "../mini.moanart.json"}, "invalid_layout"),
        (8, [], {"extra": True}, "invalid_layout"),
        (
            8,
            [],
            {
                "variants": [
                    {"id": "t", "source": "t", "transform": "none"},
                    {"id": "t", "source": "t", "transform": "mirror_x"},
                ]
            },
            "duplicate_id",
        ),
        (
            8,
            [],
            {"props": [{"id": "p", "variant": "t", "at": [1, 1]}] * 2},
            "duplicate_id",
        ),
        (
            8,
            [{"id": "dot", "type": "pixel", "at": [0, 3], "color": "ink"}],
            {},
            "detail_on_edge",
        ),
        (
            8,
            # Re-rasterised with mirrored endpoints, this line breaks its tie the other
            # way: {(7, 0), (6, 0), (5, 1)} instead of the flip {(7, 0), (6, 1), (5, 1)}.
            [{"id": "stroke", "type": "line", "start": [1, 1], "end": [3, 2], "color": "ink"}],
            {"variants": [{"id": "t", "source": "t", "transform": "mirror_x"}]},
            "mirror_asymmetry",
        ),
        (
            8,
            [],
            {"variants": [{"id": "t", "source": "t", "transform": "none"}], "grid": [[]]},
            "grid_shape",
        ),
    ],
)
def test_invalid_sources_and_layouts_are_rejected(
    tmp_path: Path,
    size: int,
    operations: list[dict[str, Any]],
    changes: dict[str, Any],
    reason: str,
) -> None:
    path = _write_layout(tmp_path, _mini_source(size, operations), **changes)
    with pytest.raises(LayoutError) as caught:
        load_layout(path)
    assert caught.value.reason == reason


def _with_source_entry(layout_path: Path, **entry: Any) -> None:
    layout = json.loads(layout_path.read_text(encoding="utf-8"))
    layout["sources"][0].update(entry)
    layout_path.write_text(json.dumps(layout), encoding="utf-8")


@pytest.mark.parametrize(
    ("relative", "reason"),
    [
        ("../tile.moanart.json", "path_escape"),
        ("tiles/../../tile.moanart.json", "path_escape"),
        ("/etc/passwd", "path_escape"),
        ("C:/tile.moanart.json", "path_escape"),
        ("missing.moanart.json", "not_found"),
    ],
)
def test_source_paths_stay_in_the_layout_folder(tmp_path: Path, relative: str, reason: str) -> None:
    folder = tmp_path / "layout"
    folder.mkdir()
    path = _write_layout(folder, _mini_source(8, []))
    (tmp_path / "tile.moanart.json").write_text("{}", encoding="utf-8")
    _with_source_entry(path, path=relative)
    with pytest.raises(LayoutError) as caught:
        load_layout(path)
    assert caught.value.reason == reason


def test_a_symlink_cannot_escape_the_layout_folder(tmp_path: Path) -> None:
    folder = tmp_path / "layout"
    folder.mkdir()
    path = _write_layout(folder, _mini_source(8, []))
    outside = tmp_path / "outside.moanart.json"
    outside.write_text(json.dumps(_mini_source(8, [])), encoding="utf-8")
    try:
        (folder / "link.moanart.json").symlink_to(outside)
    except OSError:
        pytest.skip("symlinks are not available")
    _with_source_entry(path, path="link.moanart.json")
    with pytest.raises(LayoutError) as caught:
        load_layout(path)
    assert caught.value.reason == "path_escape"


def test_oversized_and_invalid_sources_are_rejected_before_use(tmp_path: Path) -> None:
    path = _write_layout(tmp_path, _mini_source(8, []))
    big = tmp_path / "big.moanart.json"
    big.write_text(" " * (MAX_SOURCE_BYTES + 1), encoding="utf-8")
    _with_source_entry(path, path="big.moanart.json")
    with pytest.raises(LayoutError) as caught:
        load_layout(path)
    assert caught.value.reason == "too_large"

    bad = _mini_source(8, [])
    bad["seed"] = -1
    (tmp_path / "bad.moanart.json").write_text(json.dumps(bad), encoding="utf-8")
    _with_source_entry(path, path="bad.moanart.json")
    with pytest.raises(LayoutError) as caught:
        load_layout(path)
    assert caught.value.reason == "invalid_source"
    assert check(tmp_path)[0].startswith("mini.layout.json: source t is invalid")

    (tmp_path / "text.moanart.json").write_text("not json", encoding="utf-8")
    _with_source_entry(path, path="text.moanart.json")
    with pytest.raises(LayoutError) as caught:
        load_layout(path)
    assert caught.value.reason == "not_json"

    _with_source_entry(path, path="tile.moanart.json", border_operations=["fill", "nothing"])
    with pytest.raises(LayoutError) as caught:
        load_layout(path)
    assert caught.value.reason == "unknown_id"


def test_sources_must_share_one_palette(tmp_path: Path) -> None:
    tree = _mini_source(8, [])
    other = copy.deepcopy(tree)
    other["palette"]["colors"][0]["rgba"] = "#000000FF"
    (tmp_path / "other.moanart.json").write_text(json.dumps(other), encoding="utf-8")
    second = {
        "id": "u",
        "kind": "tile",
        "path": "other.moanart.json",
        "pivot": [0, 0],
        "edges": {side: "grass*8" for side in "nesw"},
        "border_operations": ["fill"],
    }
    path = _write_layout(tmp_path, tree)
    layout = json.loads(path.read_text(encoding="utf-8"))
    layout["sources"].append(second)
    path.write_text(json.dumps(layout), encoding="utf-8")
    with pytest.raises(LayoutError) as caught:
        load_layout(path)
    assert caught.value.reason == "palette_mismatch"


def test_check_reports_a_stale_scene_and_build_regenerates_it(tmp_path: Path) -> None:
    path = _write_layout(tmp_path, _mini_source(8, [_dither(2, [0, 0])]))
    assert check(tmp_path) == [
        "mini.layout.json: mini.moanart.json is stale; run scripts/tiles.py build"
    ]
    layout = load_layout(path)
    layout.scene_path.write_text(format_document(build_scene(layout)), encoding="utf-8")
    assert check(tmp_path) == []
    scene = load_document(layout.scene_path)
    assert (scene.canvas.width, scene.canvas.height) == (16, 8)


def test_versioned_scene_is_the_build_of_its_layout(capsys: pytest.CaptureFixture[str]) -> None:
    assert check() == []
    assert main(["check"]) == 0
    assert "Tiles OK" in capsys.readouterr().out
    assert LAYOUT.scene_path.read_text(encoding="utf-8") == format_document(build_scene(LAYOUT))


# T2: edit a prop by ID; native-scale legibility.


def _batch(document: Document, commands: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "base_revision": document.revision,
        "base_snapshot": snapshot_digest(document),
        "commands": commands,
    }


def _ids(document: Document) -> set[str]:
    ids = {node.id for node in (*document.masks, *document.regions, *document.layers)}
    ids.update(op.id for layer in document.layers for op in layer.operations)
    return ids


def _box_mask(shape: tuple[int, ...], box: tuple[int, int, int, int]) -> npt.NDArray[np.bool_]:
    mask = np.zeros(shape[:2], dtype=bool)
    x0, y0, x1, y1 = box
    mask[y0:y1, x0:x1] = True
    return mask


def test_recolouring_the_sign_board_by_id_changes_only_the_board() -> None:
    before = _pixels(SCENE)
    edited = apply_edit(
        SCENE,
        _batch(
            SCENE, [{"type": "set_color", "target_id": "prop_sign-board_face", "color": "dirt_1"}]
        ),
    )
    after = _pixels(edited)

    # Sign pivot (43, 46) - source pivot (8, 15) = top-left (35, 31); the source
    # board box [2, 3, 14, 8) is therefore [37, 34, 49, 39) in the scene. Only the
    # dirt_2 pixels left visible by later board operations change.
    board = _box_mask(before.shape, (37, 34, 49, 39))
    expected = board & (before == COLOURS["dirt_2"]).all(axis=2)
    changed = (before != after).any(axis=2)
    assert expected.sum() > 0
    assert np.array_equal(changed, expected)
    assert (after[changed] == COLOURS["dirt_1"]).all()
    _, regions = render_with_regions(SCENE, ["prop_sign-board"])
    region = np.zeros(changed.shape, dtype=bool)
    for point in regions["prop_sign-board"].points():
        region[point.y, point.x] = True
    assert not (changed & ~region).any()
    assert _ids(edited) == _ids(SCENE)
    assert edited.revision == SCENE.revision + 1
    untouched = [layer for layer in SCENE.layers if layer.id != "prop_sign"]
    assert [layer for layer in edited.layers if layer.id != "prop_sign"] == untouched


def test_moving_the_rock_by_id_touches_only_its_old_and_new_boxes() -> None:
    rock = next(layer for layer in SCENE.layers if layer.id == "prop_rock")
    leaves = [m.id for m in SCENE.masks if m.id.startswith("prop_rock-")]
    targets = [op.id for op in rock.operations if op.type != "outline"] + leaves
    dx, dy = -24, 16
    commands = [{"type": "translate", "target_id": t, "dx": dx, "dy": dy} for t in targets]
    before = _pixels(SCENE)
    after = _pixels(apply_edit(SCENE, _batch(SCENE, commands)))

    # Rock pivot (104, 25) - (8, 15): old box [96, 10, 112, 26), new box moved by
    # (-24, +16): [72, 26, 88, 42).
    old, new = (96, 10, 112, 26), (72, 26, 88, 42)
    changed = (before != after).any(axis=2)
    allowed = _box_mask(before.shape, old) | _box_mask(before.shape, new)
    assert changed.any()
    assert not (changed & ~allowed).any()
    frame = _variant_pixels(LAYOUT, "rock")
    opaque = frame[..., 3] > 0
    moved = after[new[1] : new[3], new[0] : new[2]]
    assert np.array_equal(moved[opaque], frame[opaque])


def test_scene_and_tiles_read_at_native_scale(tmp_path: Path) -> None:
    master = _pixels(SCENE)
    export_png(render(SCENE), tmp_path / "meadow-1x.png")
    export_png(render(SCENE), tmp_path / "meadow-4x.png", scale=4)
    with (
        Image.open(tmp_path / "meadow-1x.png") as one,
        Image.open(tmp_path / "meadow-4x.png") as four,
    ):
        assert np.array_equal(np.asarray(one.convert("RGBA")), master)
        enlarged = np.repeat(np.repeat(master, 4, axis=0), 4, axis=1)
        assert np.array_equal(np.asarray(four.convert("RGBA")), enlarged)

    documents = [SCENE, *(s.document for s in LAYOUT.sources.values())]
    documents += [load_document(variant_document(LAYOUT, v)) for v in LAYOUT.variants]
    for document in documents:
        report = evaluate_quality(document)
        assert report.passed_hard_checks, document.id
        # Recorded in examples/tiles/README.md: no warning and no suppression.
        assert report.findings == (), document.id
        assert report.metrics is not None and report.metrics.singletons == 0, document.id


# AC1: palette and editable IDs. AC2: atlas round trip.


def test_scene_keeps_the_shared_palette_and_editable_ids() -> None:
    for source in LAYOUT.sources.values():
        assert source.document.palette == SCENE.palette, source.id
    assert SCENE.canvas.profile == "strict"
    image = _pixels(SCENE)
    assert (image[..., 3] == 255).all()
    palette = {rgba for rgba in COLOURS.values()}
    assert {tuple(int(v) for v in pixel) for pixel in image.reshape(-1, 4)} <= palette

    layer_ids = [layer.id for layer in SCENE.layers]
    cells = [f"tile_r{r}_c{c}" for r in range(8) for c in range(8)]
    assert layer_ids == [*cells, "prop_rock", "prop_sign", "prop_bush_west", "prop_bush_east"]
    region_ids = {region.id for region in SCENE.regions}
    for prop_id, variant_id, _ in LAYOUT.props:
        source = LAYOUT.variants[variant_id].source
        assert {f"{prop_id}-{r['id']}" for r in source.tree["regions"]} <= region_ids
    assert "prop_sign-board" in region_ids and "prop_bush_west-berries" in region_ids
    assert evaluate_quality(SCENE).passed_hard_checks


def _atlas(layout: Layout, folder: Path) -> dict[str, SheetFrame]:
    frames = atlas_frames(layout)
    image, manifest = folder / "atlas.png", folder / "atlas.json"
    export_spritesheet(frames, image, manifest, columns=ATLAS_COLUMNS)
    return {frame.frame_id: frame for frame in load_spritesheet(image, manifest)}


def _frame(sheet: dict[str, SheetFrame], frame_id: str) -> RGBA:
    result = sheet[frame_id].result
    return np.frombuffer(result.rgba, dtype=np.uint8).reshape(result.height, result.width, 4)


def _rebuild(layout: Layout, sheet: dict[str, SheetFrame]) -> RGBA:
    """Paste the atlas frames by the documented grid and pivots (plain slicing)."""
    width, height = layout.canvas
    canvas = np.zeros((height, width, 4), dtype=np.uint8)
    for r, row in enumerate(layout.grid):
        for c, variant_id in enumerate(row):
            canvas[r * TILE : (r + 1) * TILE, c * TILE : (c + 1) * TILE] = _frame(sheet, variant_id)
    for _, variant_id, (ax, ay) in layout.props:
        pivot = sheet[variant_id].pivot
        x, y = ax - pivot.x, ay - pivot.y
        assert x >= 0 and y >= 0  # off-canvas props are rejected by the layout
        sprite = _frame(sheet, variant_id)
        target = canvas[y : y + TILE, x : x + TILE]
        assert target.shape == sprite.shape
        opaque = sprite[..., 3] == 255
        assert ((sprite[..., 3] == 0) | opaque).all()  # binary alpha: paste is "over"
        target[opaque] = sprite[opaque]
    return canvas


def test_atlas_rebuilds_the_scene_pixel_for_pixel(tmp_path: Path) -> None:
    sheet = _atlas(LAYOUT, tmp_path)
    assert list(sheet) == list(LAYOUT.variants)

    assert np.array_equal(_rebuild(LAYOUT, sheet), _pixels(SCENE))
    assert not np.array_equal(_frame(sheet, "grass"), _frame(sheet, "grass_mx"))
    assert (sheet["sign"].pivot.x, sheet["sign"].pivot.y) == (8, 15)


@pytest.mark.parametrize("origin", [(16, 0), (2, 2), (-4, 6)])
def test_atlas_rebuilds_the_scene_with_another_pattern_origin(
    tmp_path: Path, origin: tuple[int, int]
) -> None:
    layout = dataclasses.replace(LAYOUT, pattern_origin=origin)
    check_layout(layout)
    scene = build_scene(layout)
    sheet = _atlas(layout, tmp_path)
    for variant_id in ("grass", "edge_n"):
        assert (_frame(sheet, variant_id)[..., 3] == 255).all()  # never an empty frame
    assert np.array_equal(_rebuild(layout, sheet), _tree_pixels(scene))
    _assert_canvas_phase(build_scene(dataclasses.replace(layout, props=())), origin)


def test_odd_pattern_origin_breaks_the_phase_of_the_grid() -> None:
    with pytest.raises(LayoutError) as caught:
        check_layout(dataclasses.replace(LAYOUT, pattern_origin=(1, 0)))
    assert caught.value.reason == "phase_mismatch"


def test_scene_over_the_document_budget_is_rejected() -> None:
    grid = tuple(("grass",) * 12 for _ in range(12))  # 144 layers > MAX_LAYERS (128)
    layout = dataclasses.replace(LAYOUT, grid=grid, props=())
    check_layout(layout)
    with pytest.raises(LayoutError) as caught:
        build_scene(layout)
    assert caught.value.reason == "budget"


@pytest.mark.parametrize("at", [(4, 15), (8, 10), (124, 64), (64, 129)])
def test_props_must_fit_in_the_canvas(at: tuple[int, int]) -> None:
    with pytest.raises(LayoutError) as caught:
        check_layout(dataclasses.replace(LAYOUT, props=(("prop_rock", "rock", at),)))
    assert caught.value.reason == "off_canvas"


def test_props_touching_the_canvas_edge_are_kept_whole() -> None:
    corner = (("prop_rock", "rock", (8, 15)), ("prop_sign", "sign", (120, 127)))
    layout = dataclasses.replace(LAYOUT, grid=(("grass",) * 8,) * 8, props=corner)
    check_layout(layout)
    image = _tree_pixels(build_scene(layout))
    rock = _variant_pixels(LAYOUT, "rock")
    sign = _variant_pixels(LAYOUT, "sign")
    assert np.array_equal(image[:16, :16][rock[..., 3] > 0], rock[rock[..., 3] > 0])
    assert np.array_equal(image[-16:, -16:][sign[..., 3] > 0], sign[sign[..., 3] > 0])


def test_one_cell_grid_builds_and_renders() -> None:
    layout = dataclasses.replace(LAYOUT, grid=(("dirt_c",),), props=())
    check_layout(layout)
    image = _tree_pixels(build_scene(layout))
    assert image.shape == (TILE, TILE, 4)
    assert np.array_equal(image, _variant_pixels(LAYOUT, "dirt_c"))


def test_mirrored_prop_pivot_follows_the_mirror() -> None:
    source = LAYOUT.sources["bush"]
    assert Variant("b", source, "mirror_x").pivot == (16 - 8, 15)
    assert Variant("b", source, "mirror_y").pivot == (8, 16 - 15)
    assert isinstance(source, Source)


@pytest.mark.parametrize("transform", ["mirror_x", "mirror_y"])
def test_mirrored_props_are_pixel_mirrors(transform: TransformName) -> None:
    variants = {**LAYOUT.variants, "rock_m": Variant("rock_m", LAYOUT.sources["rock"], transform)}
    layout = dataclasses.replace(LAYOUT, variants=variants, props=(("prop_x", "rock_m", (40, 40)),))
    check_layout(layout)
    check_mirrors(layout)
    axis = 1 if transform == "mirror_x" else 0
    frame = _variant_pixels(layout, "rock_m")
    assert np.array_equal(frame, np.flip(_variant_pixels(LAYOUT, "rock"), axis=axis))
    px, py = variants["rock_m"].pivot
    image = _tree_pixels(build_scene(layout))
    box = image[40 - py : 40 - py + TILE, 40 - px : 40 - px + TILE]
    assert np.array_equal(box[frame[..., 3] > 0], frame[frame[..., 3] > 0])


def test_preview_writes_review_images_outside_the_sources(tmp_path: Path) -> None:
    written = preview(tmp_path)
    names = {path.name for path in written}
    assert {"meadow-1x.png", "meadow-4x.png", "meadow-atlas.png", "meadow-atlas.json"} <= names
    assert all(path.is_relative_to(tmp_path) for path in written)
    with Image.open(tmp_path / "meadow" / "variant-grass-3x3-8x.png") as image:
        assert image.size == (3 * TILE * 8, 3 * TILE * 8)
