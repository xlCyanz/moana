"""T1/T2/AC2 (MOANA-017): versioned material presets and their seeded cell textures.

Oracles are independent of :mod:`moana.techniques.materials`: grids at the maximum
density are written by hand from the pattern rules of ADR-030 (the gate always
passes when ``density = 64``), and seeded cells are recomputed here with
``hashlib`` and ``json`` from the key of MOANA.md section 14. Masks come from raw
bits, never from the operators under test.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from moana.core.coordinates import Box, Point
from moana.core.errors import ValidationError
from moana.core.materials import (
    MATERIAL_PATTERNS,
    MAX_MATERIAL_ORIGIN,
    MAX_MATERIAL_SCALE,
    cell_span,
    preset,
)
from moana.geometry import Mask
from moana.geometry.mask import _restore
from moana.techniques import (
    DENSITY_STEPS,
    MATERIAL_PRESET_NAMES,
    MATERIAL_PRESETS,
    MaterialTexture,
    is_candidate,
    split_texture,
    texture_cells,
    texture_mask,
    texture_step,
)

SEED = 1234


def mask_of(pixels: Iterable[tuple[int, int]]) -> Mask:
    points = sorted(pixels)
    if not points:
        return Mask.empty()
    x0, y0 = min(x for x, _ in points), min(y for _, y in points)
    x1, y1 = max(x for x, _ in points) + 1, max(y for _, y in points) + 1
    bits = np.zeros((y1 - y0, x1 - x0), dtype=np.uint8)
    for x, y in points:
        bits[y - y0, x - x0] = 1
    return _restore(Box(x0, y0, x1, y1), (y1 - y0, x1 - x0), bits.tobytes())


def square(x0: int, y0: int, x1: int, y1: int) -> set[tuple[int, int]]:
    return {(x, y) for x in range(x0, x1) for y in range(y0, y1)}


def pixels_of(mask: Mask) -> frozenset[tuple[int, int]]:
    return frozenset((point.x, point.y) for point in mask.points())


def oracle_choice(seed: int, op: str, x: int, y: int, channel: int, n: int) -> int:
    """MOANA.md section 14, recomputed from scratch."""
    key = json.dumps([seed, op, x, y, channel, "cell-sha256-v1"], separators=(",", ":"))
    u = int.from_bytes(hashlib.sha256(key.encode("utf-8")).digest()[:8], "big")
    return u * n // 2**64


def oracle_step(
    name: str, density: int, scale: int, origin: tuple[int, int], op: str, x: int, y: int
) -> int:
    """The rules of ADR-030 restated: candidate, gate (channel 0), sign (channel 1)."""
    cx, cy = (x - origin[0]) // scale, (y - origin[1]) // scale
    candidate = {
        "skin": True,
        "stone": True,
        "cloth": cy % 2 == 0 and (cx // 2 + cy // 2) % 2 == 0,
        "metal": (cx - cy) % 4 == 0,
        "wood": cy % 3 == 0,
    }[name]
    if not candidate or oracle_choice(SEED, op, cx, cy, 0, 64) >= density:
        return 0
    if name == "stone":
        return -1 if oracle_choice(SEED, op, cx, cy, 1, 2) == 0 else 1
    return 1 if name == "metal" else -1


def texture(
    name: str, density: int, scale: int = 1, origin: tuple[int, int] = (0, 0), op: str = "mat"
) -> MaterialTexture:
    return MaterialTexture(name, 1, density, scale, Point(*origin), SEED, op)  # type: ignore[arg-type]


def grid(tex: MaterialTexture, width: int, height: int) -> list[str]:
    symbols = {-1: "-", 0: ".", 1: "+"}
    return [
        "".join(symbols[texture_step(tex, Point(x, y))] for x in range(width))
        for y in range(height)
    ]


# --- the table --------------------------------------------------------------------------


def test_five_versioned_presets_with_ranges_and_provenance() -> None:
    assert MATERIAL_PRESET_NAMES == ("skin", "cloth", "metal", "wood", "stone")
    assert set(MATERIAL_PRESETS) == {(name, 1) for name in MATERIAL_PRESET_NAMES}
    rows = {name: MATERIAL_PRESETS[(name, 1)] for name in MATERIAL_PRESET_NAMES}
    assert {name: row.pattern for name, row in rows.items()} == {
        "skin": "pores",
        "cloth": "weave",
        "metal": "streak",
        "wood": "grain",
        "stone": "speckle",
    }
    assert {name: row.parts for name, row in rows.items()} == {
        "skin": (-1, 0),
        "cloth": (-1, 0),
        "metal": (0, 1),
        "wood": (-1, 0),
        "stone": (-1, 0, 1),
    }
    assert {name: (row.max_density, row.max_scale) for name, row in rows.items()} == {
        "skin": (4, 2),
        "cloth": (64, 4),
        "metal": (64, 4),
        "wood": (64, 4),
        "stone": (32, 4),
    }
    for row in rows.values():
        assert row.version == 1 and row.channels == (2 if row.name == "stone" else 1)
        assert 0 < row.max_density <= DENSITY_STEPS and 1 <= row.max_scale <= MAX_MATERIAL_SCALE
        assert "no external asset" in row.provenance and row.license and row.description
        assert row.pattern in MATERIAL_PATTERNS
    assert preset("stone", 1) is rows["stone"]
    assert preset("stone", 2) is None and preset("lava", 1) is None
    assert preset("stone", True) is None and preset(1, 1) is None  # type: ignore[arg-type]


def test_cell_span_uses_floor_division_around_the_origin() -> None:
    assert cell_span(Box(0, 0, 4, 4), 2, (0, 0)) == Box(0, 0, 2, 2)
    assert cell_span(Box(0, 0, 5, 3), 2, (1, 1)) == Box(-1, -1, 2, 1)
    assert cell_span(Box(-3, 2, -1, 3), 4, (0, 0)) == Box(-1, 0, 0, 1)
    assert cell_span(Box(0, 0, 1, 1), 1, (-2048, 2048)) == Box(2048, -2048, 2049, -2047)


# --- T1: fixtures per material at the density limits (hand-written) ----------------------


def test_t1_cloth_full_density_is_a_basket_weave() -> None:
    assert grid(texture("cloth", 64), 6, 4) == ["--..--", "......", "..--..", "......"]
    assert grid(texture("cloth", 64, 2), 6, 4) == ["----..", "----..", "......", "......"]


def test_t1_metal_full_density_is_a_diagonal_streak_every_fourth_cell() -> None:
    assert grid(texture("metal", 64), 8, 4) == [
        "+...+...",
        ".+...+..",
        "..+...+.",
        "...+...+",
    ]
    assert grid(texture("metal", 64, 1, (1, 0)), 5, 2) == [".+...", "..+.."]


def test_t1_wood_full_density_is_horizontal_grain_every_third_row() -> None:
    assert grid(texture("wood", 64), 4, 7) == [
        "----",
        "....",
        "....",
        "----",
        "....",
        "....",
        "----",
    ]
    assert grid(texture("wood", 64, 2), 2, 7) == ["--", "--", "..", "..", "..", "..", "--"]


def test_t1_zero_density_never_moves_a_pixel() -> None:
    for name in MATERIAL_PRESET_NAMES:
        assert set("".join(grid(texture(name, 0), 9, 9))) == {"."}


@pytest.mark.parametrize("name", MATERIAL_PRESET_NAMES)
def test_t1_every_preset_matches_the_independent_hash_oracle(name: str) -> None:
    row = MATERIAL_PRESETS[(name, 1)]
    for density in (1, row.max_density // 2, row.max_density):
        for scale in sorted({1, row.max_scale}):
            tex = texture(name, density, scale, (3, -2))
            for y in range(-4, 12):
                for x in range(-4, 12):
                    expected = oracle_step(name, density, scale, (3, -2), "mat", x, y)
                    assert texture_step(tex, Point(x, y)) == expected, (name, x, y)


@pytest.mark.parametrize("name", MATERIAL_PRESET_NAMES)
def test_t1_limits_of_density_and_scale(name: str) -> None:
    row = MATERIAL_PRESETS[(name, 1)]
    texture(name, row.max_density, row.max_scale)  # inclusive limits
    texture(name, 0, 1)
    for density, scale in ((row.max_density + 1, 1), (-1, 1), (0, 0), (0, row.max_scale + 1)):
        with pytest.raises(ValidationError) as raised:
            texture(name, density, scale)
        assert raised.value.context["reason"] == "out_of_range"
        assert raised.value.context["field"] in {"density", "scale"}


def test_t1_marked_fraction_follows_the_density() -> None:
    """Over 64 x 64 cells, every marked pores cell is a hash below the density: the count
    is exactly the oracle's, and it grows with the density."""
    counts = []
    for density in range(5):
        tex = texture("skin", density)
        cells = texture_cells(tex, Box(0, 0, 64, 64))
        marked = sum(1 for value in cells if value == 0)
        expected = sum(
            1
            for cy in range(64)
            for cx in range(64)
            if oracle_choice(SEED, "mat", cx, cy, 0, 64) < density
        )
        assert marked == expected
        counts.append(marked)
    assert counts[0] == 0 and counts == sorted(counts)
    assert 4096 * 4 // 64 - 96 <= counts[4] <= 4096 * 4 // 64 + 96  # about 1/16


@settings(max_examples=40, deadline=None)
@given(
    name=st.sampled_from(MATERIAL_PRESET_NAMES),
    density=st.integers(0, 63),
    x=st.integers(-50, 50),
    y=st.integers(-50, 50),
)
def test_t1_a_cell_marked_at_one_density_stays_marked_above_it(
    name: str, density: int, x: int, y: int
) -> None:
    row = MATERIAL_PRESETS[(name, 1)]
    density = min(density, row.max_density - 1)
    low = texture_step(texture(name, density), Point(x, y))
    high = texture_step(texture(name, density + 1), Point(x, y))
    assert low == 0 or low == high


@settings(max_examples=40, deadline=None)
@given(
    name=st.sampled_from(MATERIAL_PRESET_NAMES),
    scale=st.integers(1, 4),
    ox=st.integers(-9, 9),
    oy=st.integers(-9, 9),
    cx=st.integers(-6, 6),
    cy=st.integers(-6, 6),
)
def test_t1_every_pixel_of_a_cell_shares_its_offset(
    name: str, scale: int, ox: int, oy: int, cx: int, cy: int
) -> None:
    row = MATERIAL_PRESETS[(name, 1)]
    tex = texture(name, row.max_density, min(scale, row.max_scale), (ox, oy))
    s = tex.scale
    values = {
        texture_step(tex, Point(ox + s * cx + dx, oy + s * cy + dy))
        for dx in range(s)
        for dy in range(s)
    }
    assert len(values) == 1


# --- AC2 / T2: same seed, same texture; other operations never change it -----------------


def test_ac2_same_seed_same_texture_and_the_key_is_the_operation() -> None:
    first = texture_cells(texture("stone", 32, 1, op="rock"), Box(-5, -5, 20, 20))
    again = texture_cells(texture("stone", 32, 1, op="rock"), Box(-5, -5, 20, 20))
    other_id = texture_cells(texture("stone", 32, 1, op="pebble"), Box(-5, -5, 20, 20))
    other_seed = MaterialTexture("stone", 1, 32, 1, Point(0, 0), SEED + 1, "rock")
    assert first == again
    assert first != other_id
    assert first != texture_cells(other_seed, Box(-5, -5, 20, 20))


@settings(max_examples=40, deadline=None)
@given(
    name=st.sampled_from(MATERIAL_PRESET_NAMES),
    dx=st.integers(-40, 40),
    dy=st.integers(-40, 40),
    x=st.integers(-20, 20),
    y=st.integers(-20, 20),
)
def test_t2_texture_follows_its_origin(name: str, dx: int, dy: int, x: int, y: int) -> None:
    """A frame that moves the sprite and its origin together keeps every texel."""
    row = MATERIAL_PRESETS[(name, 1)]
    here = texture(name, row.max_density // 2, row.max_scale, (1, 2))
    moved = texture(name, row.max_density // 2, row.max_scale, (1 + dx, 2 + dy))
    assert texture_step(here, Point(x, y)) == texture_step(moved, Point(x + dx, y + dy))


@pytest.mark.parametrize("name", MATERIAL_PRESET_NAMES)
def test_texture_cells_equal_the_scalar_definition(name: str) -> None:
    row = MATERIAL_PRESETS[(name, 1)]
    tex = texture(name, row.max_density, row.max_scale, (-3, 5))
    span = Box(-4, -3, 6, 4)
    cells = texture_cells(tex, span)
    s = tex.scale
    expected = [
        texture_step(tex, Point(-3 + s * cx, 5 + s * cy)) + 1
        for cy in range(span.y0, span.y1)
        for cx in range(span.x0, span.x1)
    ]
    assert list(cells) == expected


@pytest.mark.parametrize("name", MATERIAL_PRESET_NAMES)
def test_parts_are_disjoint_cover_the_mask_and_stay_inside_it(name: str) -> None:
    row = MATERIAL_PRESETS[(name, 1)]
    tex = texture(name, row.max_density, row.max_scale, (2, 1))
    pixels = square(1, 2, 13, 11) - square(4, 4, 7, 7) | {(20, 20)}
    parts = split_texture(mask_of(pixels), tex)
    assert len(parts) == len(row.parts)
    union: set[tuple[int, int]] = set()
    for part, offset in zip(parts, row.parts, strict=True):
        got = pixels_of(part)
        assert not got & union
        assert got == {(x, y) for x, y in pixels if texture_step(tex, Point(x, y)) == offset}
        union |= got
    assert union == pixels


def test_empty_mask_and_invalid_inputs() -> None:
    tex = texture("stone", 8)
    assert texture_mask(Mask.empty(), tex, 0).is_empty
    with pytest.raises(ValidationError) as raised:
        texture_mask(mask_of({(0, 0)}), tex, 2)
    assert raised.value.context == {"field": "part", "reason": "unknown_part"}
    with pytest.raises(ValidationError):
        texture_mask(mask_of({(0, 0)}), texture("metal", 8), -1)
    with pytest.raises(ValidationError):
        texture_mask(mask_of({(0, 0)}), tex, True)
    with pytest.raises(TypeError, match="mask"):
        texture_mask(object(), tex, 0)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="texture"):
        texture_mask(mask_of({(0, 0)}), object(), 0)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="texture"):
        texture_step(object(), Point(0, 0))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="point"):
        texture_step(tex, (0, 0))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="texture"):
        split_texture(mask_of({(0, 0)}), object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="texture"):
        texture_cells(object(), Box(0, 0, 1, 1))  # type: ignore[arg-type]


def test_material_texture_validates_every_member() -> None:
    with pytest.raises(ValidationError) as raised:
        MaterialTexture("lava", 1, 0, 1, Point(0, 0), 0, "mat")  # type: ignore[arg-type]
    assert raised.value.context == {"field": "preset", "reason": "unknown_preset"}
    with pytest.raises(ValidationError):
        MaterialTexture("stone", 2, 0, 1, Point(0, 0), 0, "mat")
    with pytest.raises(TypeError, match="origin"):
        MaterialTexture("stone", 1, 0, 1, (0, 0), 0, "mat")  # type: ignore[arg-type]
    edge = MAX_MATERIAL_ORIGIN
    MaterialTexture("stone", 1, 0, 1, Point(-edge, edge), 2**64 - 1, "mat")
    with pytest.raises(ValidationError):
        MaterialTexture("stone", 1, 0, 1, Point(edge + 1, 0), 0, "mat")
    with pytest.raises(ValidationError):
        MaterialTexture("stone", 1, 0, 1, Point(0, 0), 2**64, "mat")
    with pytest.raises(ValidationError):
        MaterialTexture("stone", 1, 0, 1, Point(0, 0), 0, "Not an ID")
    assert texture("wood", 3).spec is MATERIAL_PRESETS[("wood", 1)]


def test_is_candidate_rules() -> None:
    assert is_candidate("pores", 7, -3) and is_candidate("speckle", -1, 9)
    assert is_candidate("weave", 1, 0) and is_candidate("weave", 2, 2)
    assert not is_candidate("weave", 1, 1) and not is_candidate("weave", 2, 0)
    assert is_candidate("streak", 5, 1) and not is_candidate("streak", 5, 2)
    assert is_candidate("grain", 2, -3) and not is_candidate("grain", 2, -2)
