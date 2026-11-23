"""Limit configuration: contract maxima, lowering only, strict integer fields."""

import pytest

from moanart.core import (
    DEFAULT_GEOMETRY_LIMITS,
    MAX_AREA,
    MAX_COORDINATE,
    MAX_DIMENSION,
    Box,
    Dimensions,
    GeometryLimits,
    OutOfBoundsError,
    Point,
    ValidationError,
)


def test_contract_constants_match_moanart_section_5() -> None:
    assert (MAX_DIMENSION, MAX_AREA, MAX_COORDINATE) == (2048, 4_194_304, 1_048_576)
    assert GeometryLimits(2048, 4_194_304, 1_048_576) == DEFAULT_GEOMETRY_LIMITS


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_dimension": 2049},
        {"max_area": MAX_AREA + 1},
        {"max_coordinate": MAX_COORDINATE + 1},
        {"max_dimension": 0},
        {"max_area": 0},
        {"max_coordinate": -1},
        {"max_dimension": True},
        {"max_area": 10.0},
    ],
)
def test_limits_cannot_exceed_contract_or_be_invalid(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        GeometryLimits(**kwargs)  # type: ignore[arg-type]


def test_lowered_limits_apply_to_dimensions_and_boxes() -> None:
    limits = GeometryLimits(max_dimension=128, max_area=128 * 64, max_coordinate=256)
    limits.check_dimensions(Dimensions(128, 64))
    with pytest.raises(ValidationError) as dimension:
        limits.check_dimensions(Dimensions(129, 1))
    assert dimension.value.context["field"] == "width"
    with pytest.raises(ValidationError) as area:
        limits.check_dimensions(Dimensions(128, 65))
    assert area.value.context["field"] == "area"
    limits.check_box(Box(-256, -256, 256, 256))
    with pytest.raises(ValidationError):
        limits.check_box(Box(-257, 0, 0, 1))
    limits.check_point(Point(256, -256))
    with pytest.raises(ValidationError):
        limits.check_point(Point(0, 257))


def test_area_limit_independent_of_axis_limit() -> None:
    limits = GeometryLimits(max_area=100)
    limits.check_dimensions(Dimensions(100, 1))
    with pytest.raises(ValidationError):
        limits.check_dimensions(Dimensions(11, 10))


def test_pixel_access_outside_canvas_raises_bounds_error() -> None:
    canvas = Dimensions(128, 128)
    canvas.check_pixel(Point(0, 0))
    canvas.check_pixel(Point(127, 127))
    for outside in (Point(-1, 0), Point(0, -1), Point(128, 0), Point(0, 128)):
        with pytest.raises(OutOfBoundsError):
            canvas.check_pixel(outside)


def test_lowered_box_limit_allows_excluded_edge_plus_one() -> None:
    limits = GeometryLimits(max_coordinate=0)
    limits.check_box(Box(0, 0, 1, 1))
    with pytest.raises(ValidationError) as caught:
        limits.check_box(Box(0, 0, 2, 1))
    assert caught.value.context["field"] == "x1"


def test_pixel_bounds_on_extreme_canvases() -> None:
    Dimensions(1, 1).check_pixel(Point(0, 0))
    Dimensions(2048, 2048).check_pixel(Point(2047, 2047))
    with pytest.raises(OutOfBoundsError) as caught:
        Dimensions(1, 1).check_pixel(Point(1, 0))
    assert caught.value.code == "OUT_OF_BOUNDS"
    assert caught.value.context == {"x": 1, "y": 0, "width": 1, "height": 1}
