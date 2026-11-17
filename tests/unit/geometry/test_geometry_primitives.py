"""Hand-written oracles for the integer rasterisers of MOANA.md section 6 (MOANA-006).

Expected masks are literal grids or point lists derived by hand from the normative
rules; ``#`` marks a pixel of the mask. Property tests compare the row-span
implementation with a literal per-pixel evaluation of the same formulas.
"""

from __future__ import annotations

import itertools
from collections.abc import Sequence
from fractions import Fraction
from typing import overload

import pytest
from hypothesis import given
from hypothesis import strategies as st

from moana.core.coordinates import Box, Dimensions, Point
from moana.core.errors import ValidationError
from moana.core.limits import MAX_VERTICES
from moana.geometry import (
    Mask,
    rasterize_ellipse,
    rasterize_line,
    rasterize_pixel,
    rasterize_polygon,
    rasterize_rect,
)


def grid(mask: Mask, width: int, height: int) -> list[str]:
    return [
        "".join("#" if mask.contains(Point(x, y)) else "." for x in range(width))
        for y in range(height)
    ]


def pts(*pairs: tuple[int, int]) -> list[Point]:
    return [Point(x, y) for x, y in pairs]


NINE = Dimensions(9, 9)

# --- pixel ---------------------------------------------------------------------------


def test_pixel_is_exactly_one_pixel() -> None:
    mask = rasterize_pixel(Point(2, 1), Dimensions(4, 3))
    assert grid(mask, 4, 3) == ["....", "..#.", "...."]
    assert mask.box == Box(2, 1, 3, 2)


@pytest.mark.parametrize("at", [(-1, 0), (0, -1), (4, 0), (0, 3), (-1_048_576, 1_048_576)])
def test_pixel_off_canvas_is_empty_without_wraparound(at: tuple[int, int]) -> None:
    mask = rasterize_pixel(Point(*at), Dimensions(4, 3))
    assert mask.is_empty and mask.box is None


# --- line: T1 octants, degenerate, axis-aligned ----------------------------------------

# From (4, 4) to each octant; derived by hand with the section 6 recurrence.
OCTANTS = {
    (8, 6): [(4, 4), (5, 5), (6, 5), (7, 6), (8, 6)],
    (6, 8): [(4, 4), (5, 5), (5, 6), (6, 7), (6, 8)],
    (2, 8): [(2, 8), (3, 7), (3, 6), (4, 5), (4, 4)],
    (0, 6): [(0, 6), (1, 5), (2, 5), (3, 4), (4, 4)],
    (0, 2): [(0, 2), (1, 3), (2, 3), (3, 4), (4, 4)],
    (2, 0): [(2, 0), (3, 1), (3, 2), (4, 3), (4, 4)],
    (6, 0): [(4, 4), (5, 3), (5, 2), (6, 1), (6, 0)],
    (8, 2): [(4, 4), (5, 3), (6, 3), (7, 2), (8, 2)],
}


@pytest.mark.parametrize("end", sorted(OCTANTS))
def test_line_octants_match_hand_oracle(end: tuple[int, int]) -> None:
    mask = rasterize_line(Point(4, 4), Point(*end), NINE)
    assert sorted((p.x, p.y) for p in mask.points()) == sorted(OCTANTS[end])


@pytest.mark.parametrize("end", sorted(OCTANTS))
def test_ac1_reversed_line_gives_identical_mask(end: tuple[int, int]) -> None:
    forward = rasterize_line(Point(4, 4), Point(*end), NINE)
    backward = rasterize_line(Point(*end), Point(4, 4), NINE)
    assert forward == backward
    assert forward.contains(Point(4, 4)) and forward.contains(Point(*end))


def test_line_tie_breaking_on_shallow_slope() -> None:
    # dx=4, dy=-1, err=3: y steps only when e2 <= dx, at the second step (e2 = 4).
    mask = rasterize_line(Point(0, 0), Point(4, 1), Dimensions(5, 2))
    assert grid(mask, 5, 2) == ["##...", "..###"]


def test_degenerate_line_is_one_pixel() -> None:
    mask = rasterize_line(Point(3, 3), Point(3, 3), NINE)
    assert list(mask.points()) == [Point(3, 3)]


def test_horizontal_vertical_and_diagonal_lines() -> None:
    dims = Dimensions(6, 4)
    assert grid(rasterize_line(Point(5, 1), Point(1, 1), dims), 6, 4) == [
        "......",
        ".#####",
        "......",
        "......",
    ]
    assert grid(rasterize_line(Point(2, 3), Point(2, 0), dims), 6, 4) == [
        "..#...",
        "..#...",
        "..#...",
        "..#...",
    ]
    assert grid(rasterize_line(Point(0, 3), Point(3, 0), dims), 6, 4) == [
        "...#..",
        "..#...",
        ".#....",
        "#.....",
    ]


def test_line_partially_off_canvas_is_clipped_without_wraparound() -> None:
    # Diagonal from (-2, -2) to (5, 5) on 4x4: only (0,0)..(3,3) remain.
    mask = rasterize_line(Point(-2, -2), Point(5, 5), Dimensions(4, 4))
    assert grid(mask, 4, 4) == ["#...", ".#..", "..#.", "...#"]
    assert mask.box == Box(0, 0, 4, 4)


def test_line_entirely_off_canvas_or_beside_it_is_empty() -> None:
    dims = Dimensions(4, 4)
    assert rasterize_line(Point(-5, -1), Point(-1, -1), dims).is_empty
    assert rasterize_line(Point(-1_048_576, 2), Point(-10, 2), dims).box is None
    # Bounding box overlaps the canvas but the path stays outside it.
    corner = rasterize_line(Point(-3, 2), Point(2, -3), dims)
    assert corner.box == Box(0, 0, 3, 3) and corner.is_empty


coordinate = st.integers(min_value=-12, max_value=20)


@given(coordinate, coordinate, coordinate, coordinate)
def test_line_properties(x0: int, y0: int, x1: int, y1: int) -> None:
    dims = Dimensions(9, 7)
    mask = rasterize_line(Point(x0, y0), Point(x1, y1), dims)
    assert mask == rasterize_line(Point(x1, y1), Point(x0, y0), dims)
    canvas = Box.from_dimensions(dims)
    for end in (Point(x0, y0), Point(x1, y1)):
        assert mask.contains(end) == canvas.contains(end)
    points = list(mask.points())
    assert all(canvas.contains(p) for p in points)
    if all(canvas.contains(p) for p in (Point(x0, y0), Point(x1, y1))):
        assert len(points) == max(abs(x1 - x0), abs(y1 - y0)) + 1
        # One pixel per major-axis step, 8-connected.
        shallow = abs(x1 - x0) >= abs(y1 - y0)
        major = sorted(points, key=lambda p: (p.x, p.y) if shallow else (p.y, p.x))
        for a, b in itertools.pairwise(major):
            assert max(abs(a.x - b.x), abs(a.y - b.y)) == 1


# --- rect ----------------------------------------------------------------------------


def test_rect_is_half_open() -> None:
    mask = rasterize_rect(Box(1, 1, 4, 3), Dimensions(5, 4))
    assert grid(mask, 5, 4) == [".....", ".###.", ".###.", "....."]


def test_rect_partially_off_canvas_and_negative() -> None:
    mask = rasterize_rect(Box(-2, -1, 2, 2), Dimensions(4, 4))
    assert grid(mask, 4, 4) == ["##..", "##..", "....", "...."]
    assert mask.box == Box(0, 0, 2, 2)


@pytest.mark.parametrize(
    "box",
    [Box(-3, -3, -1, -1), Box(4, 0, 6, 2), Box(-2, 0, 0, 4), Box(0, 4, 4, 5)],
)
def test_rect_fully_off_canvas_is_empty_without_wraparound(box: Box) -> None:
    assert rasterize_rect(box, Dimensions(4, 4)) == Mask.empty()


# --- ellipse -------------------------------------------------------------------------


def test_ellipse_5x3_by_pixel_centres() -> None:
    # w=5, h=3: rows B=-2,0,2 admit |A| <= 3, 5, 3 (A even: -4..4).
    mask = rasterize_ellipse(Box(0, 0, 5, 3), Dimensions(5, 3))
    assert grid(mask, 5, 3) == [".###.", "#####", ".###."]


def test_ellipse_4x4_circle() -> None:
    mask = rasterize_ellipse(Box(1, 1, 5, 5), Dimensions(6, 6))
    assert grid(mask, 6, 6) == [
        "......",
        "..##..",
        ".####.",
        ".####.",
        "..##..",
        "......",
    ]


def test_ellipse_small_boxes_fill_completely() -> None:
    assert grid(rasterize_ellipse(Box(0, 0, 1, 1), Dimensions(1, 1)), 1, 1) == ["#"]
    assert grid(rasterize_ellipse(Box(0, 0, 2, 1), Dimensions(2, 1)), 2, 1) == ["##"]
    assert grid(rasterize_ellipse(Box(0, 0, 2, 2), Dimensions(2, 2)), 2, 2) == ["##", "##"]


def test_ellipse_7x1_includes_the_whole_row() -> None:
    # h=1: B=0 and A^2 <= w^2 for every A in -6..6.
    mask = rasterize_ellipse(Box(0, 0, 7, 1), Dimensions(7, 1))
    assert grid(mask, 7, 1) == ["#######"]


def test_ellipse_partially_and_fully_off_canvas() -> None:
    clipped = rasterize_ellipse(Box(-2, -2, 2, 2), Dimensions(3, 3))
    # The 4x4 circle shifted by -2: only its lower-right quadrant remains.
    assert grid(clipped, 3, 3) == ["##.", "#..", "..."]
    assert rasterize_ellipse(Box(-5, -5, -1, -1), Dimensions(3, 3)).box is None


def _ellipse_reference(box: Box, x: int, y: int) -> bool:
    w, h = box.width, box.height
    a = 2 * x + 1 - box.x0 - box.x1
    b = 2 * y + 1 - box.y0 - box.y1
    return a * a * h * h + b * b * w * w <= w * w * h * h


@given(
    st.integers(-6, 8),
    st.integers(-6, 8),
    st.integers(1, 14),
    st.integers(1, 14),
)
def test_ellipse_matches_literal_per_pixel_formula(x0: int, y0: int, w: int, h: int) -> None:
    box = Box(x0, y0, x0 + w, y0 + h)
    mask = rasterize_ellipse(box, Dimensions(10, 9))
    for y in range(9):
        for x in range(10):
            expected = box.contains(Point(x, y)) and _ellipse_reference(box, x, y)
            assert mask.contains(Point(x, y)) == expected


# --- polygon: even-odd ---------------------------------------------------------------


def test_integer_rectangle_polygon_equals_half_open_rect() -> None:
    mask = rasterize_polygon(pts((1, 1), (4, 1), (4, 3), (1, 3)), Dimensions(5, 4))
    assert mask == rasterize_rect(Box(1, 1, 4, 3), Dimensions(5, 4))


def test_triangle_by_pixel_centres() -> None:
    # Right triangle (0,0),(4,0),(0,4): crossings c = 0 and c = 4 - (y + 1/2). A centre
    # on the hypotenuse (x + y + 1 == 4) has no crossing strictly to its right: outside.
    mask = rasterize_polygon(pts((0, 0), (4, 0), (0, 4)), Dimensions(4, 4))
    assert grid(mask, 4, 4) == ["###.", "##..", "#...", "...."]


def test_t3_bow_tie_with_zero_signed_area_is_not_empty() -> None:
    points = pts((0, 0), (4, 4), (4, 0), (0, 4))
    edges = zip(points, points[1:] + points[:1], strict=True)
    signed = sum(a.x * b.y - b.x * a.y for a, b in edges)
    assert signed == 0  # shoelace cancels, yet the even-odd interior is two triangles
    mask = rasterize_polygon(points, Dimensions(4, 4))
    assert grid(mask, 4, 4) == ["...#", "#.##", "#.##", "...#"]
    assert mask.count == 8


def test_t1_self_intersection_leaves_even_odd_hole() -> None:
    # Edges (6,4)-(2,4) and (4,2)-(4,6) cross at (4,4); rows 2-3 see four crossings.
    points = pts((0, 0), (6, 0), (6, 4), (2, 4), (2, 2), (4, 2), (4, 6), (0, 6))
    mask = rasterize_polygon(points, Dimensions(6, 6))
    assert grid(mask, 6, 6) == [
        "######",
        "######",
        "##..##",
        "##..##",
        "####..",
        "####..",
    ]


def test_polygon_repeated_vertices_and_orientation_do_not_matter() -> None:
    square = pts((1, 1), (4, 1), (4, 3), (1, 3))
    repeated = pts((1, 1), (1, 1), (4, 1), (4, 3), (4, 3), (1, 3))
    dims = Dimensions(5, 4)
    assert rasterize_polygon(repeated, dims) == rasterize_polygon(square, dims)
    assert rasterize_polygon(square[::-1], dims) == rasterize_polygon(square, dims)


def test_degenerate_polygons_are_empty() -> None:
    dims = Dimensions(5, 5)
    assert rasterize_polygon(pts((0, 0), (4, 0), (2, 0)), dims).box is None
    collinear = rasterize_polygon(pts((0, 0), (2, 2), (4, 4)), dims)
    assert collinear.is_empty and collinear.box == Box(0, 0, 4, 4)


def test_polygon_off_canvas_and_negative_coordinates() -> None:
    dims = Dimensions(4, 4)
    clipped = rasterize_polygon(pts((-2, -2), (2, -2), (2, 2), (-2, 2)), dims)
    assert grid(clipped, 4, 4) == ["##..", "##..", "....", "...."]
    assert rasterize_polygon(pts((-6, -6), (-2, -6), (-2, -2)), dims).box is None


def test_polygon_rejects_bad_vertex_counts_and_types() -> None:
    dims = Dimensions(4, 4)
    with pytest.raises(ValidationError) as too_few:
        rasterize_polygon(pts((0, 0), (1, 1)), dims)
    assert too_few.value.context["reason"] == "out_of_range"
    with pytest.raises(ValidationError):
        rasterize_polygon([Point(i % 3, i % 2) for i in range(MAX_VERTICES + 1)], dims)
    with pytest.raises(TypeError):
        rasterize_polygon("abc", dims)  # type: ignore[arg-type]  # deliberate misuse
    with pytest.raises(TypeError):
        rasterize_polygon([(0, 0), (1, 0), (0, 1)], dims)  # type: ignore[list-item]  # misuse


def _polygon_reference(points: list[Point], x: int, y: int) -> bool:
    """Section 6 literally: count crossings strictly right of the centre, as rationals."""
    px, py = Fraction(2 * x + 1, 2), Fraction(2 * y + 1, 2)
    crossings = 0
    for a, b in zip(points, points[1:] + points[:1], strict=True):
        if a.y == b.y or not min(a.y, b.y) <= py < max(a.y, b.y):
            continue
        cx = a.x + (b.x - a.x) * (py - a.y) / (b.y - a.y)
        crossings += cx > px
    return crossings % 2 == 1


vertex = st.builds(Point, st.integers(-3, 11), st.integers(-3, 10))


@given(st.lists(vertex, min_size=3, max_size=8))
def test_polygon_matches_literal_even_odd_rule(points: list[Point]) -> None:
    mask = rasterize_polygon(points, Dimensions(9, 8))
    for y in range(8):
        for x in range(9):
            assert mask.contains(Point(x, y)) == _polygon_reference(points, x, y)


# --- argument checking ---------------------------------------------------------------


def test_rasterisers_reject_wrong_argument_types() -> None:
    dims = Dimensions(2, 2)
    with pytest.raises(TypeError):
        rasterize_pixel((0, 0), dims)  # type: ignore[arg-type]  # deliberate misuse
    with pytest.raises(TypeError):
        rasterize_rect(Box(0, 0, 1, 1), (2, 2))  # type: ignore[arg-type]  # misuse
    with pytest.raises(TypeError):
        rasterize_line(Point(0, 0), (1, 1), dims)  # type: ignore[arg-type]  # misuse
    with pytest.raises(TypeError):
        rasterize_ellipse((0, 0, 1, 1), dims)  # type: ignore[arg-type]  # misuse


class _HugeSequence(Sequence[Point]):
    """Claims ten million vertices but must never be iterated."""

    def __len__(self) -> int:
        return 10**7

    @overload
    def __getitem__(self, index: int) -> Point: ...
    @overload
    def __getitem__(self, index: slice) -> Sequence[Point]: ...
    def __getitem__(self, index: int | slice) -> Point | Sequence[Point]:
        raise AssertionError("polygon vertices iterated before the count check")


def test_polygon_vertex_count_is_checked_before_iterating() -> None:
    with pytest.raises(ValidationError) as excinfo:
        rasterize_polygon(_HugeSequence(), Dimensions(4, 4))
    assert excinfo.value.context["maximum"] == MAX_VERTICES


def _bresenham_reference(x0: int, y0: int, x1: int, y1: int) -> set[tuple[int, int]]:
    """Section 6 written out independently: sort endpoints, then the plain recurrence."""
    if (x1, y1) < (x0, y0):
        x0, y0, x1, y1 = x1, y1, x0, y0
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    err = dx + dy
    points = set()
    while True:
        points.add((x0, y0))
        if (x0, y0) == (x1, y1):
            return points
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


@given(coordinate, coordinate, coordinate, coordinate)
def test_line_matches_literal_recurrence(x0: int, y0: int, x1: int, y1: int) -> None:
    dims = Dimensions(9, 7)
    canvas = Box.from_dimensions(dims)
    expected = {p for p in _bresenham_reference(x0, y0, x1, y1) if canvas.contains(Point(*p))}
    mask = rasterize_line(Point(x0, y0), Point(x1, y1), dims)
    assert {(p.x, p.y) for p in mask.points()} == expected


def test_one_by_one_canvas_cases() -> None:
    one = Dimensions(1, 1)
    assert grid(rasterize_line(Point(-3, -3), Point(3, 3), one), 1, 1) == ["#"]
    assert rasterize_line(Point(-3, 3), Point(3, 3), one).is_empty
    assert grid(rasterize_polygon(pts((0, 0), (1, 0), (1, 1), (0, 1)), one), 1, 1) == ["#"]
    assert grid(rasterize_polygon(pts((-5, -5), (5, -5), (0, 5)), one), 1, 1) == ["#"]
    assert grid(rasterize_ellipse(Box(0, 0, 1, 1), one), 1, 1) == ["#"]
