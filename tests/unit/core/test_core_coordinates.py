"""Points, dimensions and half-open boxes (MOANA.md section 5).

Oracles are independent of the implementation: hand-computed boxes and, for the
intersection properties, explicit pixel sets enumerated from the half-open rule.
"""

from fractions import Fraction

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from moana.core import (
    MAX_COORDINATE,
    Box,
    Dimensions,
    MoanaError,
    Point,
    ValidationError,
)

# --- T1: range extremes, negative boxes, edges and canvas sizes -----------------


@pytest.mark.parametrize("size", [1, 128, 2048])
def test_valid_square_canvas_sizes(size: int) -> None:
    dimensions = Dimensions(size, size)
    assert (dimensions.width, dimensions.height, dimensions.area) == (size, size, size * size)


def test_default_canvas_is_128() -> None:
    assert Dimensions.default() == Dimensions(128, 128)


@pytest.mark.parametrize(
    ("width", "height", "field"),
    [
        (0, 1, "width"),
        (1, 0, "height"),
        (-5, 10, "width"),
        (2049, 1, "width"),
        (1, 2049, "height"),
    ],
)
def test_dimensions_out_of_range_fail(width: int, height: int, field: str) -> None:
    with pytest.raises(ValidationError) as caught:
        Dimensions(width, height)
    assert caught.value.code == "VALIDATION_ERROR"
    assert caught.value.context["field"] == field


@pytest.mark.parametrize(
    "value", [True, False, 1.0, Fraction(1), "1", None, np.int64(1), np.uint8(1)]
)
def test_only_real_python_ints_are_coordinates(value: object) -> None:
    for build in (
        lambda: Point(value, 0),  # type: ignore[arg-type]
        lambda: Dimensions(4, value),  # type: ignore[arg-type]
        lambda: Box(0, 0, value, 4),  # type: ignore[arg-type]
    ):
        with pytest.raises(ValidationError) as caught:
            build()
        assert caught.value.context["reason"] == "not_integer"
        assert caught.value.context["value_type"] == type(value).__name__


@pytest.mark.parametrize("coordinate", [-MAX_COORDINATE, 0, MAX_COORDINATE])
def test_coordinate_extremes_are_accepted(coordinate: int) -> None:
    assert Point(coordinate, coordinate).x == coordinate


@pytest.mark.parametrize("coordinate", [-MAX_COORDINATE - 1, MAX_COORDINATE + 1, 10**30])
def test_coordinates_beyond_absolute_range_fail(coordinate: int) -> None:
    with pytest.raises(ValidationError) as caught:
        Point(0, coordinate)
    assert caught.value.context == {
        "field": "y",
        "reason": "out_of_range",
        "minimum": -MAX_COORDINATE,
        "maximum": MAX_COORDINATE,
    }


def test_negative_box_is_valid_and_measured() -> None:
    box = Box(-10, -4, -2, 3)
    assert (box.width, box.height, box.area) == (8, 7, 56)


@pytest.mark.parametrize(
    "corners",
    [(5, 0, 5, 1), (0, 5, 1, 5), (6, 0, 5, 1), (0, 6, 1, 5), (0, 0, 0, 0)],
)
def test_empty_or_inverted_box_fails(corners: tuple[int, int, int, int]) -> None:
    with pytest.raises(ValidationError) as caught:
        Box(*corners)
    assert caught.value.context["reason"] == "empty_or_inverted"


def test_unit_box_contains_exactly_one_pixel() -> None:
    box = Box(3, 7, 4, 8)
    assert (box.width, box.height, box.area) == (1, 1, 1)
    inside = [Point(x, y) for x in range(0, 10) for y in range(0, 10) if box.contains(Point(x, y))]
    assert inside == [Point(3, 7)]
    assert Box.from_point(Point(3, 7)) == box


def test_half_open_edges() -> None:
    box = Box(0, 0, 4, 2)
    assert box.contains(Point(0, 0)) and box.contains(Point(3, 1))
    assert not box.contains(Point(4, 0))
    assert not box.contains(Point(0, 2))
    assert not box.contains(Point(-1, 0))


def test_canvas_box_and_clipping() -> None:
    canvas = Dimensions(128, 128)
    assert Box.from_dimensions(canvas) == Box(0, 0, 128, 128)
    assert Box(-10, -10, 5, 200).clip_to(canvas) == Box(0, 0, 5, 128)
    assert Box(0, 0, 128, 128).clip_to(canvas) == Box(0, 0, 128, 128)
    # Fully outside, touching the right edge, or above the canvas: empty clip is None.
    assert Box(128, 0, 140, 5).clip_to(canvas) is None
    assert Box(-5, -5, 0, 0).clip_to(canvas) is None
    assert Box(10, -3, 12, 0).clip_to(canvas) is None


def test_intersection_of_touching_boxes_is_none() -> None:
    assert Box(0, 0, 2, 2).intersection(Box(2, 0, 4, 2)) is None
    assert Box(0, 0, 2, 2).intersection(Box(1, 1, 3, 3)) == Box(1, 1, 2, 2)


def test_values_are_immutable_and_hashable() -> None:
    box = Box(0, 0, 1, 1)
    with pytest.raises(AttributeError):
        setattr(box, "x0", 5)  # noqa: B010 - bypass static checks to prove immutability
    assert len({Box(0, 0, 1, 1), Box(0, 0, 1, 1), Point(0, 0)}) == 2


def test_errors_are_domain_errors() -> None:
    with pytest.raises(MoanaError):
        Point(True, 0)


# --- T2: intersection properties against an explicit pixel-set oracle ----------

small = st.integers(min_value=-6, max_value=6)


@st.composite
def boxes(draw: st.DrawFn) -> Box:
    x0, y0 = draw(small), draw(small)
    return Box(x0, y0, x0 + draw(st.integers(1, 5)), y0 + draw(st.integers(1, 5)))


def pixels(box: Box | None) -> set[tuple[int, int]]:
    if box is None:
        return set()
    return {(x, y) for x in range(box.x0, box.x1) for y in range(box.y0, box.y1)}


@given(boxes(), boxes())
def test_intersection_matches_pixel_set_oracle(first: Box, second: Box) -> None:
    assert pixels(first.intersection(second)) == pixels(first) & pixels(second)


@given(boxes(), boxes())
def test_intersection_is_commutative(first: Box, second: Box) -> None:
    assert first.intersection(second) == second.intersection(first)


@given(boxes(), boxes())
def test_intersection_is_contained_and_never_expands(first: Box, second: Box) -> None:
    result = first.intersection(second)
    if result is None:
        return
    assert pixels(result) <= pixels(first) and pixels(result) <= pixels(second)
    assert result.area <= min(first.area, second.area)
    assert result.intersection(first) == result


@given(boxes())
def test_intersection_is_idempotent(box: Box) -> None:
    assert box.intersection(box) == box


@given(boxes(), st.integers(1, 8), st.integers(1, 8))
def test_clip_matches_canvas_pixel_oracle(box: Box, width: int, height: int) -> None:
    canvas = Dimensions(width, height)
    canvas_pixels = {(x, y) for x in range(width) for y in range(height)}
    assert pixels(box.clip_to(canvas)) == pixels(box) & canvas_pixels


# --- Review follow-ups: extremes of the absolute range and non-square canvases --


@pytest.mark.parametrize("size", [(2048, 1), (1, 2048)])
def test_non_square_extreme_canvases(size: tuple[int, int]) -> None:
    assert Dimensions(*size).area == 2048


@pytest.mark.parametrize("coordinate", [-MAX_COORDINATE, MAX_COORDINATE])
def test_every_valid_pixel_has_a_unit_box(coordinate: int) -> None:
    box = Box.from_point(Point(coordinate, coordinate))
    assert box.area == 1 and box.contains(Point(coordinate, coordinate))


@pytest.mark.parametrize(
    ("corners", "field"),
    [
        ((MAX_COORDINATE + 1, 0, MAX_COORDINATE + 2, 1), "x0"),
        ((0, 0, MAX_COORDINATE + 2, 1), "x1"),
        ((0, -MAX_COORDINATE - 1, 1, 0), "y0"),
        ((0, 0, 1, -MAX_COORDINATE), "y1"),
    ],
)
def test_box_corner_ranges(corners: tuple[int, int, int, int], field: str) -> None:
    with pytest.raises(ValidationError) as caught:
        Box(*corners)
    assert caught.value.context["field"] == field


def test_huge_box_clips_to_largest_canvas() -> None:
    huge = Box(-MAX_COORDINATE, -MAX_COORDINATE, MAX_COORDINATE + 1, MAX_COORDINATE + 1)
    assert huge.clip_to(Dimensions(2048, 2048)) == Box(0, 0, 2048, 2048)
    far = Box(MAX_COORDINATE, MAX_COORDINATE, MAX_COORDINATE + 1, MAX_COORDINATE + 1)
    assert far.clip_to(Dimensions(2048, 2048)) is None
    assert huge.intersection(far) == far


def test_require_int_rejects_inverted_bounds_as_programming_error() -> None:
    from moana.core import require_int

    with pytest.raises(ValueError, match="invalid bounds"):
        require_int(5, "field", minimum=10, maximum=0)


edge = st.integers(min_value=MAX_COORDINATE - 6, max_value=MAX_COORDINATE)


@st.composite
def edge_boxes(draw: st.DrawFn) -> Box:
    x0, y0 = draw(edge), draw(edge)
    return Box(x0, y0, x0 + draw(st.integers(1, 1)), y0 + draw(st.integers(1, 1)))


@given(edge_boxes(), edge_boxes())
def test_intersection_oracle_near_maximum(first: Box, second: Box) -> None:
    assert pixels(first.intersection(second)) == pixels(first) & pixels(second)
