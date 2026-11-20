"""Ordered Bayer dithering of ``moana.techniques`` (MOANA-016, MOANA.md section 10).

Oracles are independent of the implementation: the threshold matrices are written
out literally from MOANA.md section 10 and every expected pixel is computed here with
Python's floor modulo over those literals, never from the module under test.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from moana.core.coordinates import Box, Dimensions, Point
from moana.core.errors import ValidationError
from moana.geometry import (
    Mask,
    combine_masks,
    rasterize_ellipse,
    rasterize_polygon,
    rasterize_rect,
)
from moana.techniques import (
    BAYER_2X2,
    BAYER_4X4,
    DITHER_PARTS,
    DITHER_SIZES,
    OrderedDither,
    bayer_matrix,
    dither_cells,
    dither_mask,
    split_dither,
)

TECHNIQUES = Path(__file__).resolve().parents[3] / "src/moana/techniques"

# Literal oracles from MOANA.md section 10 (row index first).
SPEC_2 = [[0, 2], [3, 1]]
SPEC_4 = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]
SPEC = {2: SPEC_2, 4: SPEC_4}
CANVAS = Dimensions(32, 24)


def oracle_threshold(size: int, x: int, y: int, ox: int, oy: int) -> int:
    """``M[(y - oy) mod N][(x - ox) mod N]`` with Python's floor modulo."""
    return SPEC[size][(y - oy) % size][(x - ox) % size]


def oracle_parts(
    pixels: set[tuple[int, int]], size: int, coverage: int, ox: int, oy: int
) -> tuple[set[tuple[int, int]], set[tuple[int, int]]]:
    b = {(x, y) for x, y in pixels if oracle_threshold(size, x, y, ox, oy) < coverage}
    return pixels - b, b


def pixels_of(mask: Mask) -> set[tuple[int, int]]:
    return {(point.x, point.y) for point in mask.points()}


# --- T1: thresholds, coverages and positions of the period -------------------------------


def test_matrices_are_the_normative_ones() -> None:
    assert [list(row) for row in BAYER_2X2] == SPEC_2
    assert [list(row) for row in BAYER_4X4] == SPEC_4
    assert DITHER_SIZES == (2, 4)
    for size in DITHER_SIZES:
        assert bayer_matrix(size) == tuple(tuple(row) for row in SPEC[size])
        flat = sorted(value for row in SPEC[size] for value in row)
        assert flat == list(range(size * size))  # every threshold exactly once


@pytest.mark.parametrize("size", [2, 4])
def test_t1_every_threshold_position_and_coverage(size: int) -> None:
    """All coverages 0..N^2 and every cell of the period, against the literal matrix."""
    for coverage in range(size * size + 1):
        dither = OrderedDither(size, coverage, Point(0, 0))
        b_count = 0
        for y in range(size):
            for x in range(size):
                threshold = SPEC[size][y][x]
                assert dither.threshold(Point(x, y)) == threshold
                expected = "b" if threshold < coverage else "a"
                assert dither.part(Point(x, y)) == expected
                b_count += expected == "b"
        assert b_count == coverage  # exactly c B cells per period
        cells_b = dither_cells(dither, "b")
        cells_a = dither_cells(dither, "a")
        assert sum(cell for row in cells_b for cell in row) == coverage
        for row_b, row_a in zip(cells_b, cells_a, strict=True):
            assert all(b is not a for b, a in zip(row_b, row_a, strict=True))


@pytest.mark.parametrize("size", [2, 4])
@pytest.mark.parametrize("origin", [(0, 0), (1, 3), (-1, -1), (-7, 5), (-1_048_576, 1_048_575)])
def test_t1_every_coverage_on_a_full_canvas_period_counts(
    size: int, origin: tuple[int, int]
) -> None:
    ox, oy = origin
    full = rasterize_rect(Box(0, 0, CANVAS.width, CANVAS.height), CANVAS)
    every = pixels_of(full)
    for coverage in range(size * size + 1):
        dither = OrderedDither(size, coverage, Point(ox, oy))
        a, b = split_dither(full, dither)
        expected_a, expected_b = oracle_parts(every, size, coverage, ox, oy)
        assert pixels_of(a) == expected_a
        assert pixels_of(b) == expected_b
        # Each aligned N x N window of the canvas holds exactly ``coverage`` B pixels.
        for wy in range(0, CANVAS.height - size + 1, size):
            for wx in range(0, CANVAS.width - size + 1, size):
                window = {(wx + i, wy + j) for i in range(size) for j in range(size)}
                assert len(window & pixels_of(b)) == coverage


# --- AC1: coverage 0 is only A and N^2 only B, inside the mask ---------------------------


def _shapes() -> dict[str, Mask]:
    ellipse = rasterize_ellipse(Box(2, 1, 19, 14), CANVAS)
    polygon = rasterize_polygon([Point(20, 0), Point(31, 9), Point(14, 23)], CANVAS)
    hole = rasterize_ellipse(Box(6, 4, 12, 10), CANVAS)
    combined = combine_masks(
        "xor", [combine_masks("subtract", [ellipse, hole], CANVAS), polygon], CANVAS
    )
    return {"ellipse": ellipse, "polygon": polygon, "combined": combined}


@pytest.mark.parametrize("name", ["ellipse", "polygon", "combined"])
@pytest.mark.parametrize("size", [2, 4])
def test_ac1_extreme_coverages_inside_non_rectangular_masks(name: str, size: int) -> None:
    mask = _shapes()[name]
    inside = pixels_of(mask)
    assert inside
    empty_a, all_b = split_dither(mask, OrderedDither(size, size * size, Point(-3, 2)))
    all_a, empty_b = split_dither(mask, OrderedDither(size, 0, Point(-3, 2)))
    assert pixels_of(all_a) == inside and empty_b.box is None
    assert pixels_of(all_b) == inside and empty_a.box is None


@pytest.mark.parametrize("name", ["ellipse", "polygon", "combined"])
@pytest.mark.parametrize("size", [2, 4])
def test_t2_non_rectangular_masks_split_exactly(name: str, size: int) -> None:
    mask = _shapes()[name]
    inside = pixels_of(mask)
    for coverage in range(size * size + 1):
        a, b = split_dither(mask, OrderedDither(size, coverage, Point(5, -9)))
        expected_a, expected_b = oracle_parts(inside, size, coverage, 5, -9)
        assert pixels_of(a) == expected_a and pixels_of(b) == expected_b
        assert not (pixels_of(a) | pixels_of(b)) - inside  # nothing outside the mask
        for part in (a, b):
            assert part.box is None or part.box == mask.box  # clipped like the mask


# --- AC2: negative origins and translations by the period -------------------------------


@pytest.mark.parametrize("size", [2, 4])
@pytest.mark.parametrize("coverage_ratio", [1, 2, 3])
def test_ac2_negative_origin_and_period_translations_match(size: int, coverage_ratio: int) -> None:
    coverage = coverage_ratio * size * size // 4
    mask = _shapes()["combined"]
    reference = split_dither(mask, OrderedDither(size, coverage, Point(1, 2)))
    for kx in (-262_144, -3, -1, 0, 1, 5):
        for ky in (-2, -1, 0, 7):
            origin = Point(1 + kx * size, 2 + ky * size)
            assert split_dither(mask, OrderedDither(size, coverage, origin)) == reference


def test_ac2_negative_origin_uses_the_floor_modulo() -> None:
    """With C's truncated remainder, (-1 - 0) % 2 would be -1: column 1 by floor mod."""
    dither = OrderedDither(2, 1, Point(1, 1))
    assert dither.threshold(Point(0, 0)) == SPEC_2[1][1] == 1
    dither = OrderedDither(4, 1, Point(-5, -6))
    assert dither.threshold(Point(0, 0)) == SPEC_4[6 % 4][5 % 4]


# --- T2: seams between tiles and repetition without flicker -----------------------------


@pytest.mark.parametrize("size", [2, 4])
def test_t2_adjacent_tiles_with_a_shared_anchor_have_no_seam(size: int) -> None:
    """Dithering tiles separately equals dithering their union (any cut position)."""
    origin = Point(-11, 3)
    for coverage in range(size * size + 1):
        dither = OrderedDither(size, coverage, origin)
        whole = split_dither(rasterize_rect(Box(0, 0, 32, 24), CANVAS), dither)
        for cut in (1, 5, 13, 17):
            left = split_dither(rasterize_rect(Box(0, 0, cut, 24), CANVAS), dither)
            right = split_dither(rasterize_rect(Box(cut, 0, 32, 24), CANVAS), dither)
            for index in (0, 1):
                joined = pixels_of(left[index]) | pixels_of(right[index])
                assert joined == pixels_of(whole[index])


def test_t2_repeated_dithering_is_identical() -> None:
    mask = _shapes()["combined"]
    dither = OrderedDither(4, 7, Point(-2, -3))
    first = split_dither(mask, dither)
    for _ in range(5):
        again = split_dither(mask, OrderedDither(4, 7, Point(-2, -3)))
        assert again == first
        assert [m.to_array().tobytes() for m in again] == [m.to_array().tobytes() for m in first]


@settings(max_examples=60, deadline=None)
@given(
    size=st.sampled_from([2, 4]),
    data=st.data(),
    box=st.tuples(st.integers(-4, 30), st.integers(-4, 22), st.integers(1, 12), st.integers(1, 12)),
    origin=st.tuples(st.integers(-50, 50), st.integers(-50, 50)),
)
def test_property_parts_partition_the_mask_like_the_oracle(
    size: int, data: Any, box: tuple[int, int, int, int], origin: tuple[int, int]
) -> None:
    coverage = data.draw(st.integers(0, size * size))
    x, y, w, h = box
    mask = rasterize_ellipse(Box(x, y, x + w, y + h), CANVAS)
    a, b = split_dither(mask, OrderedDither(size, coverage, Point(*origin)))
    expected_a, expected_b = oracle_parts(pixels_of(mask), size, coverage, *origin)
    assert (pixels_of(a), pixels_of(b)) == (expected_a, expected_b)


def test_empty_mask_gives_empty_parts() -> None:
    empty = rasterize_rect(Box(100, 100, 104, 104), CANVAS)
    assert empty.box is None
    assert all(part.box is None for part in split_dither(empty, OrderedDither(2, 2, Point(0, 0))))


# --- Negative cases --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("size", "coverage", "field", "reason"),
    [
        (3, 1, "size", "unsupported_size"),
        (8, 1, "size", "unsupported_size"),
        (0, 0, "size", "unsupported_size"),
        (True, 1, "size", "not_integer"),
        (2.0, 1, "size", "not_integer"),
        (2, -1, "coverage", "out_of_range"),
        (2, 5, "coverage", "out_of_range"),
        (4, 17, "coverage", "out_of_range"),
        (4, True, "coverage", "not_integer"),
        (4, 1.0, "coverage", "not_integer"),
    ],
)
def test_invalid_parameters_raise_domain_errors(
    size: Any, coverage: Any, field: str, reason: str
) -> None:
    with pytest.raises(ValidationError) as raised:
        OrderedDither(size, coverage, Point(0, 0))
    assert raised.value.context["field"] == field
    assert raised.value.context["reason"] == reason


def test_bayer_matrix_rejects_unsupported_sizes() -> None:
    with pytest.raises(ValidationError) as raised:
        bayer_matrix(3)
    assert raised.value.context["reason"] == "unsupported_size"


def test_unknown_part_and_wrong_types() -> None:
    dither = OrderedDither(2, 1, Point(0, 0))
    mask = rasterize_rect(Box(0, 0, 2, 2), CANVAS)
    assert DITHER_PARTS == ("a", "b")
    for part in ("c", "A", b"a", None):
        with pytest.raises(ValidationError) as raised:
            dither_mask(mask, dither, part)  # type: ignore[arg-type]  # invalid on purpose
        assert raised.value.context["reason"] == "unknown_part"
    with pytest.raises(TypeError):
        OrderedDither(2, 1, (0, 0))  # type: ignore[arg-type]  # not a Point
    with pytest.raises(TypeError):
        dither.threshold((0, 0))  # type: ignore[arg-type]  # not a Point
    with pytest.raises(TypeError):
        dither_cells("bayer", "a")  # type: ignore[arg-type]  # not an OrderedDither
    with pytest.raises(TypeError):
        dither_mask(None, dither, "a")  # type: ignore[arg-type]  # not a Mask


# --- Architecture -----------------------------------------------------------------------


def _imports(path: Path) -> list[str]:
    names: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
        elif isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
    return names


def test_techniques_imports_only_core_geometry_palette_and_stdlib() -> None:
    """MOANA.md section 3: techniques depends on core, geometry and palette."""
    paths = sorted(TECHNIQUES.glob("*.py"))
    assert paths
    allowed = ("moana.core", "moana.geometry", "moana.palette", "moana.techniques")
    for path in paths:
        for name in _imports(path):
            root = name.split(".")[0]
            assert root in sys.stdlib_module_names or name.startswith(allowed), (
                f"{path.name} imports {name}"
            )
            assert name != "moana.core.pillow_adapter"


def test_importing_techniques_loads_neither_pillow_nor_pydantic() -> None:
    probe = (
        "import sys, moana.techniques; "
        "heavy = {'PIL', 'aggdraw', 'pydantic'}; "
        "print(sorted(heavy & {name.split('.')[0] for name in sys.modules}))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, check=True, text=True
    )
    assert completed.stdout.strip() == "[]"
