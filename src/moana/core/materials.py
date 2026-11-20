"""Versioned material presets: pure data and cell arithmetic (MOANA.md section 10, ADR-030).

A material preset is a *recipe*, not a shader: a named, versioned row of this table
that fixes a texture pattern over integer cells, which ramp steps it may move a pixel
by, the allowed ranges of its two numeric parameters (``density`` and ``scale``) and
the provenance and licence of the recipe. Nothing in a document is executed: the
document names ``preset`` and ``version`` and gives integer parameters, and the
pattern code that a row names lives in :mod:`moana.techniques.materials`.

Pure data with no dependencies other than ``core``: ``schema`` (the grammar and the
ranges), ``techniques`` (the patterns) and the cost plan (``moana.render.budget``,
which imports no NumPy) all read the same rows and the same :func:`cell_span`.

**Cells.** A texture with ``scale`` ``s`` and ``origin`` ``(ox, oy)`` splits the
canvas into ``s x s`` cells; pixel ``(x, y)`` lies in cell
``((x - ox) // s, (y - oy) // s)`` (floor division, also for negative operands), so
the texture is anchored on ``origin`` and moving ``origin`` together with the
sprite moves the texture with it.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Literal, get_args

from moana.core.coordinates import MAX_DIMENSION, Box

__all__ = [
    "DENSITY_STEPS",
    "MATERIAL_PATTERNS",
    "MATERIAL_PRESETS",
    "MATERIAL_PRESET_NAMES",
    "MAX_MATERIAL_ORIGIN",
    "MAX_MATERIAL_SCALE",
    "MaterialPattern",
    "MaterialPreset",
    "PresetName",
    "cell_span",
    "preset",
]

PresetName = Literal["skin", "cloth", "metal", "wood", "stone"]
MATERIAL_PRESET_NAMES: Final[tuple[PresetName, ...]] = get_args(PresetName)
"""The five initial materials of MOANA.md section 10."""

MaterialPattern = Literal["pores", "weave", "streak", "grain", "speckle"]
MATERIAL_PATTERNS: Final[tuple[MaterialPattern, ...]] = get_args(MaterialPattern)
"""Integer cell patterns implemented by :mod:`moana.techniques.materials`."""

DENSITY_STEPS: Final = 64
"""``density`` is in sixty-fourths: a candidate cell is marked with probability
``density / 64`` (``cell_choice(..., 64) < density``)."""
MAX_MATERIAL_SCALE: Final = 8
"""Largest cell side of any preset (each row may allow less). No version 1 row goes
beyond 4: the schema-wide bound leaves room for future versions."""
MAX_MATERIAL_ORIGIN: Final = MAX_DIMENSION
"""Largest ``|ox|``/``|oy|`` of a texture origin: cells stay within the hash's
coordinate range for every pixel of every canvas."""


@dataclass(frozen=True, slots=True)
class MaterialPreset:
    """One versioned recipe.

    ``parts`` are the ramp-step offsets a pixel can take, ascending (``0`` is the
    band's own step; ``-1`` one step darker, ``+1`` one lighter); ``channels`` the
    hash draws per cell (1: the density gate; 2: the gate and a sign).
    ``max_density`` (in :data:`DENSITY_STEPS`) and ``max_scale`` bound the
    parameters (``density`` from 0, ``scale`` from 1).
    """

    name: PresetName
    version: int
    pattern: MaterialPattern
    parts: tuple[int, ...]
    channels: int
    max_density: int
    max_scale: int
    description: str
    provenance: str
    license: str


_PROVENANCE: Final = (
    "Recipe authored for Moana (MOANA-017, ADR-030) by an AI agent from MOANA.md "
    "section 10; no external asset, texture or palette was used."
)
_LICENSE: Final = "MIT (same licence as the Moana repository)."

_ROWS: Final = (
    MaterialPreset(
        "skin",
        1,
        "pores",
        (-1, 0),
        1,
        4,
        2,
        "Sparse darker pores on any cell; skin reads mostly smooth.",
        _PROVENANCE,
        _LICENSE,
    ),
    MaterialPreset(
        "cloth",
        1,
        "weave",
        (-1, 0),
        1,
        64,
        4,
        "Darker horizontal pairs of cells on every other row, alternating every two "
        "rows: a basket weave.",
        _PROVENANCE,
        _LICENSE,
    ),
    MaterialPreset(
        "metal",
        1,
        "streak",
        (0, 1),
        1,
        64,
        4,
        "Lighter diagonal streaks on every fourth cell diagonal: brushed sheen.",
        _PROVENANCE,
        _LICENSE,
    ),
    MaterialPreset(
        "wood",
        1,
        "grain",
        (-1, 0),
        1,
        64,
        4,
        "Darker horizontal grain on every third row of cells, broken by the gate.",
        _PROVENANCE,
        _LICENSE,
    ),
    MaterialPreset(
        "stone",
        1,
        "speckle",
        (-1, 0, 1),
        2,
        32,
        4,
        "Darker or lighter speckles on any cell, the sign drawn per cell.",
        _PROVENANCE,
        _LICENSE,
    ),
)

MATERIAL_PRESETS: Final[MappingProxyType[tuple[str, int], MaterialPreset]] = MappingProxyType(
    {(row.name, row.version): row for row in _ROWS}
)
"""Every recipe, keyed by ``(name, version)``. A new version adds a row; a released
row never changes, so a document that names it renders the same."""


def preset(name: str, version: int) -> MaterialPreset | None:
    """The recipe ``(name, version)``, or ``None`` when the table has no such row."""
    if type(name) is not str or type(version) is not int:
        return None
    return MATERIAL_PRESETS.get((name, version))


def cell_span(box: Box, scale: int, origin: tuple[int, int]) -> Box:
    """Cells, as a box of cell indexes, that cover every pixel of ``box``.

    Cell ``(cx, cy)`` holds pixels ``ox + s·cx .. ox + s·cx + s - 1`` (and the same
    in ``y``); floor division keeps cells aligned also left of or above ``origin``.
    """
    ox, oy = origin
    return Box(
        (box.x0 - ox) // scale,
        (box.y0 - oy) // scale,
        (box.x1 - 1 - ox) // scale + 1,
        (box.y1 - 1 - oy) // scale + 1,
    )
