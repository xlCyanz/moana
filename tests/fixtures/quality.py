"""Synthetic quality corpus (MOANA-026 T1): small sprites with one known defect each.

Every case pairs a *defect* grid with its *corrected* grid and the finding the defect
must produce, written by hand (boxes are half-open ``[x0, y0, x1, y1)``). Grids are
character rows; ``.`` is transparent. The corrected grid fixes only that defect (the
``noise`` one keeps its eight singletons over a larger opaque area), so the rule of
the case must report nothing on it. Timeline cases list frames.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from moanart.core.coordinates import Dimensions
from moanart.palette import Palette, PaletteColor, Rgba
from moanart.quality import QUALITY_RULES

RGBA = tuple[int, int, int, int]
COLORS: dict[str, RGBA] = {
    ".": (0, 0, 0, 0),
    "k": (27, 26, 46, 255),  # ink
    "s": (90, 160, 80, 255),  # slime
    "l": (150, 210, 120, 255),  # light
    "x": (255, 0, 255, 255),  # not in the palette
    "h": (90, 160, 80, 128),  # slime RGB, partial alpha: not in a strict palette
    "g": (10, 20, 30, 0),  # transparent pixel that keeps RGB: not normalised
}
PALETTE = Palette(
    "pal",
    "strict",
    tuple(
        PaletteColor(name, Rgba(*COLORS[key]))
        for name, key in (("ink", "k"), ("slime", "s"), ("light", "l"))
    ),
)
RGBA_PALETTE = Palette("pal", "rgba", PALETTE.colors)


@dataclass(frozen=True, slots=True)
class Raster:
    """A still image with the fields of ``RenderResult`` that quality reads."""

    width: int
    height: int
    rgba: bytes


@dataclass(frozen=True, slots=True)
class Frame:
    """A timeline frame with the fields of ``FrameRender`` that quality reads."""

    frame_id: str
    result: Raster


def raster(rows: list[str]) -> Raster:
    """Image of a character grid (rows of equal length)."""
    data = b"".join(bytes(COLORS[c]) for row in rows for c in row)
    return Raster(len(rows[0]), len(rows), data)


def frames(grids: list[list[str]]) -> tuple[Frame, ...]:
    """Frames ``f0``, ``f1``... of character grids."""
    return tuple(Frame(f"f{index}", raster(rows)) for index, rows in enumerate(grids))


CANVAS = Dimensions(6, 6)
BODY = [
    "......",
    ".kkkk.",
    ".kssk.",
    ".kssk.",
    ".kkkk.",
    "......",
]


def _with(grid: list[str], x: int, y: int, char: str) -> list[str]:
    rows = list(grid)
    rows[y] = rows[y][:x] + char + rows[y][x + 1 :]
    return rows


@dataclass(frozen=True, slots=True)
class Case:
    """One known defect: grids (or frames), its rule, expected box and evidence."""

    name: str
    rule: str
    defect: list[str]
    fixed: list[str]
    box: tuple[int, int, int, int]
    evidence: dict[str, int | str]
    config: dict[str, object] = field(default_factory=dict)
    defect_frames: list[list[str]] = field(default_factory=list)
    fixed_frames: list[list[str]] = field(default_factory=list)


SPECKLED = [
    "lklklk",
    "kkkkkk",
    "lklklk",
    "kkkkkk",
    "lklkkk",
    "kkkkkk",
]  # eight light pixels two apart: 8 singletons over 36 opaque pixels (222 per mille)


def speckled_field(size: int) -> list[str]:
    """``size`` x ``size`` ink field with the eight light pixels of :data:`SPECKLED`."""
    rows = [row + "k" * (size - len(row)) for row in SPECKLED]
    return rows + ["k" * size] * (size - len(rows))


SPECKLED_FIELD = speckled_field(14)  # same 8 singletons over 196 pixels: 40 per mille
STAIR = [
    "kk......",
    "..k.....",
    "...kkkk.",
    ".......k",
    "........",
]  # steps 2, 1, 4, 1: interior pair (1, 4) jumps by 3
STRAIGHT = [
    "kk......",
    "..kk....",
    "....kk..",
    "......kk",
    "........",
]

CASES: tuple[Case, ...] = (
    Case(
        "off_palette",
        "palette_strict",
        _with(BODY, 3, 2, "x"),
        BODY,
        (3, 2, 4, 3),
        {"color": "#FF00FFFF", "first_x": 3, "first_y": 2, "pixels": 1},
    ),
    Case(
        "partial_alpha_in_strict",
        "palette_strict",
        _with(_with(BODY, 2, 2, "h"), 3, 3, "h"),
        BODY,
        (2, 2, 4, 4),
        {"color": "#5AA05080", "first_x": 2, "first_y": 2, "pixels": 2},
    ),
    Case(
        "alpha_not_normalised",
        "alpha_normalized",
        _with(BODY, 0, 5, "g"),
        BODY,
        (0, 5, 1, 6),
        {"first_x": 0, "first_y": 5, "pixels": 1},
    ),
    Case(
        "singleton",
        "singleton",
        _with(BODY, 2, 2, "l"),
        _with(_with(BODY, 2, 2, "l"), 3, 2, "l"),
        (2, 2, 3, 3),
        {"area": 1, "color": "#96D278FF"},
    ),
    Case(
        "irregular_steps",
        "irregular_steps",
        STAIR,
        STRAIGHT,
        (2, 1, 7, 3),
        {
            "color": "#1B1A2EFF",
            "first_length": 1,
            "second_length": 4,
            "step": 1,
            "steps": 4,
        },
    ),
    Case(
        "color_excess",
        "color_excess",
        _with(BODY, 2, 2, "l"),
        BODY,
        (1, 1, 5, 5),
        {"distinct_colors": 3, "max_colors": 2},
        config={"max_colors": 2},
    ),
    Case(
        "noise",
        "noise",
        SPECKLED,
        SPECKLED_FIELD,
        (0, 0, 5, 5),
        {
            "max_singleton_permille": 50,
            "opaque_area": 36,
            "singleton_permille": 222,  # floor(1000 * 8 / 36)
            "singletons": 8,
        },
    ),
    Case(
        "outside_mask",
        "outside_mask",
        _with(BODY, 5, 5, "k"),
        BODY,
        (5, 5, 6, 6),
        {"first_x": 5, "first_y": 5, "pixels": 1, "regions": "body"},
        config={"containment": ("body",)},
    ),
    Case(
        "temporal_flicker",
        "temporal_flicker",
        BODY,
        BODY,
        (2, 2, 3, 3),
        {"first_x": 2, "first_y": 2, "pixels": 1},
        defect_frames=[BODY, _with(BODY, 2, 2, "l"), BODY],
        fixed_frames=[BODY, _with(BODY, 2, 2, "l"), _with(BODY, 2, 2, "l")],
    ),
    Case(
        "temporal_change",
        "temporal_change",
        BODY,
        BODY,
        (0, 0, 6, 6),
        {
            "changed_permille": 1000,  # 28 changed of 28 opaque in either frame
            "changed_pixels": 28,
            "max_changed_permille": 900,
            "opaque_union": 28,
            "previous_frame_id": "f0",
        },
        config={"rules": QUALITY_RULES},
        defect_frames=[
            BODY,
            ["kk..kk", "k....k", "......", "......", "k....k", "kk..kk"],
        ],
        fixed_frames=[BODY, _with(BODY, 2, 2, "l")],
    ),
)
