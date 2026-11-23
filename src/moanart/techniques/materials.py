"""Material textures of the versioned presets (MOANART.md sections 10 and 14, ADR-030).

A material shades its bands exactly like ``shade`` (:func:`band_index`, ADR-028)
and then moves some pixels of each band by one ramp step, never by a computed
colour: a pixel takes ``ramp[clamp(band step + offset)]`` with ``offset`` one of the
preset's ``parts`` (``-1``, ``0`` or ``+1``). Which pixels move is the *texture*:

* the canvas is split into ``scale x scale`` cells anchored on ``origin``
  (:func:`moanart.core.materials.cell_span`); every pixel of a cell gets the same
  offset, so a texture is made of clusters of at least ``scale x scale`` pixels;
* a cell is a *candidate* by the preset's integer pattern: ``pores`` and
  ``speckle`` every cell, ``weave`` the cells of a basket weave (``cy mod 2 = 0``
  and ``(cx div 2 + cy div 2) mod 2 = 0``: horizontal pairs of cells on every other
  row, alternating every two rows), ``streak`` cells with ``(cx - cy) mod 4 = 0``
  and ``grain`` cells with ``cy mod 3 = 0``;
* a candidate is *marked* when ``cell_choice(seed, operation_id, cx, cy, 0, 64) <
  density`` (MOANART.md section 14: SHA-256 of ``[seed, operation_id, cx, cy, 0,
  "cell-sha256-v1"]``), so ``density`` is in sixty-fourths and ``density = 64``
  marks every candidate;
* a marked cell takes the preset's sign: ``-1`` for ``pores``, ``weave`` and
  ``grain``, ``+1`` for ``streak``, and for ``speckle`` ``-1`` when
  ``cell_choice(..., 1, 2) = 0`` and ``+1`` otherwise. Unmarked cells take ``0``.

The texture depends only on the document seed, the operation's own ID, the cell and
the recipe: adding, removing or reordering other operations never changes it, the
same seed always gives the same texture and no frame enters the key (the texture
has no temporal variation, so it never flickers). No RNG, clock, ``hash()`` or float
is involved.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from moanart.core.budget import Deadline
from moanart.core.coordinates import Box, Point, require_int
from moanart.core.errors import ValidationError
from moanart.core.ids import check_id
from moanart.core.materials import (
    DENSITY_STEPS,
    MATERIAL_PRESET_NAMES,
    MATERIAL_PRESETS,
    MAX_MATERIAL_ORIGIN,
    MaterialPattern,
    MaterialPreset,
    PresetName,
    cell_span,
    preset,
)
from moanart.core.procedural import MAX_SEED, cell_choice, cell_choices
from moanart.geometry import Mask, select_cells

__all__ = [
    "DENSITY_STEPS",
    "MATERIAL_PRESETS",
    "MATERIAL_PRESET_NAMES",
    "MaterialPreset",
    "MaterialTexture",
    "PresetName",
    "is_candidate",
    "split_texture",
    "texture_cells",
    "texture_mask",
    "texture_step",
]

GATE_CHANNEL: Final = 0
"""Hash channel of the density gate."""
SIGN_CHANNEL: Final = 1
"""Hash channel of the ``speckle`` sign."""
_SIGNS: Final[MappingProxyType[MaterialPattern, int]] = MappingProxyType(
    {"pores": -1, "weave": -1, "streak": 1, "grain": -1}
)


@dataclass(frozen=True, slots=True)
class MaterialTexture:
    """The texture parameters of one material operation.

    ``(preset, version)`` must name a row of :data:`MATERIAL_PRESETS`
    (``field: preset``, ``unknown_preset``); ``density`` is an ``int`` in
    ``0..max_density`` and ``scale`` in ``1..max_scale`` of that row; ``origin`` a
    :class:`Point` with ``|x|, |y| <= 2048``; ``seed`` in ``0..2**64 - 1``;
    ``operation_id`` a document ID (the hash key, MOANART.md section 14).
    """

    preset: PresetName
    version: int
    density: int
    scale: int
    origin: Point
    seed: int
    operation_id: str

    def __post_init__(self) -> None:
        row = preset(self.preset, self.version)
        if row is None:
            raise ValidationError(
                "preset and version do not name a material recipe",
                context={"field": "preset", "reason": "unknown_preset"},
            )
        require_int(self.density, "density", minimum=0, maximum=row.max_density)
        require_int(self.scale, "scale", minimum=1, maximum=row.max_scale)
        if not isinstance(self.origin, Point):
            raise TypeError("origin must be a Point value")
        for value in (self.origin.x, self.origin.y):
            require_int(value, "origin", minimum=-MAX_MATERIAL_ORIGIN, maximum=MAX_MATERIAL_ORIGIN)
        require_int(self.seed, "seed", minimum=0, maximum=MAX_SEED)
        check_id(self.operation_id)

    @property
    def spec(self) -> MaterialPreset:
        """The recipe row this texture follows."""
        return MATERIAL_PRESETS[(self.preset, self.version)]


def _check_texture(texture: object) -> MaterialTexture:
    if not isinstance(texture, MaterialTexture):
        raise TypeError("texture must be a MaterialTexture value")
    return texture


def is_candidate(pattern: MaterialPattern, cx: int, cy: int) -> bool:
    """Whether cell ``(cx, cy)`` can be marked by ``pattern`` (module rules)."""
    if pattern == "weave":  # basket weave: pairs of cells, alternating every two rows
        return cy % 2 == 0 and (cx // 2 + cy // 2) % 2 == 0
    if pattern == "streak":
        return (cx - cy) % 4 == 0
    if pattern == "grain":
        return cy % 3 == 0
    return True  # pores, speckle


def _cell_step(texture: MaterialTexture, cx: int, cy: int) -> int:
    spec = texture.spec
    if not is_candidate(spec.pattern, cx, cy):
        return 0
    key = (texture.seed, texture.operation_id, cx, cy)
    if cell_choice(*key, GATE_CHANNEL, DENSITY_STEPS) >= texture.density:
        return 0
    if spec.pattern == "speckle":
        return -1 if cell_choice(*key, SIGN_CHANNEL, 2) == 0 else 1
    return _SIGNS[spec.pattern]


def texture_step(texture: MaterialTexture, point: Point) -> int:
    """Ramp-step offset of the canvas pixel ``point``: one of the preset's ``parts``.

    The scalar definition of the module rules, one :func:`cell_choice` at a time.
    """
    texture = _check_texture(texture)
    if not isinstance(point, Point):
        raise TypeError("point must be a Point value")
    ox, oy = texture.origin.x, texture.origin.y
    return _cell_step(texture, (point.x - ox) // texture.scale, (point.y - oy) // texture.scale)


def texture_cells(
    texture: MaterialTexture, span: Box, *, deadline: Deadline | None = None
) -> bytes:
    """``offset + 1`` of every cell of ``span``, row-major, one byte per cell.

    Equal cell by cell to :func:`texture_step`; the hashes come from
    :func:`moanart.core.procedural.cell_choices` (``deadline`` checked between rows).
    """
    texture = _check_texture(texture)
    spec = texture.spec
    key = (texture.seed, texture.operation_id, span)
    gates = cell_choices(*key, GATE_CHANNEL, DENSITY_STEPS, deadline=deadline)
    signs = (
        cell_choices(*key, SIGN_CHANNEL, 2, deadline=deadline) if spec.pattern == "speckle" else b""
    )
    fixed = _SIGNS.get(spec.pattern, 0)
    values = bytearray(span.area)
    position = 0
    for cy in range(span.y0, span.y1):
        for cx in range(span.x0, span.x1):
            if gates[position] < texture.density and is_candidate(spec.pattern, cx, cy):
                step = (-1 if signs[position] == 0 else 1) if signs else fixed
                values[position] = step + 1
            else:
                values[position] = 1
            position += 1
    return bytes(values)


def texture_mask(
    mask: Mask, texture: MaterialTexture, part: int, *, deadline: Deadline | None = None
) -> Mask:
    """Pixels of ``mask`` whose texture offset is ``part`` (one of the preset's parts).

    The parts of one mask are disjoint and their union is the mask. Raises
    ``ValidationError`` (``field: part``, ``unknown_part``) for an offset the preset
    never produces.
    """
    if not isinstance(mask, Mask):
        raise TypeError("mask must be a Mask value")
    texture = _check_texture(texture)
    if type(part) is not int or part not in texture.spec.parts:
        raise ValidationError(
            "part is not an offset of this preset",
            context={"field": "part", "reason": "unknown_part"},
        )
    box = mask.box
    if box is None:
        return Mask.empty()
    span = cell_span(box, texture.scale, (texture.origin.x, texture.origin.y))
    cells = texture_cells(texture, span, deadline=deadline)
    return select_cells(mask, cells, span, texture.scale, texture.origin, part + 1)


def split_texture(mask: Mask, texture: MaterialTexture) -> tuple[Mask, ...]:
    """:func:`texture_mask` of every part of the preset, in the order of ``parts``."""
    texture = _check_texture(texture)
    return tuple(texture_mask(mask, texture, part) for part in texture.spec.parts)
