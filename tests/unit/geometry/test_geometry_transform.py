"""Pixel-perfect transformations on pixel indices (MOANA-008, ADR-016)."""

from __future__ import annotations

import tracemalloc

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from moanart.core.coordinates import MAX_COORDINATE, Box, Dimensions, Point
from moanart.core.errors import ValidationError
from moanart.geometry import (
    MAX_SCALE,
    Mask,
    Transform,
    rasterize_line,
    rasterize_pixel,
    rasterize_polygon,
    rasterize_rect,
    transform_box,
    transform_mask,
)

DIMS = Dimensions(12, 10)
BIG = Dimensions(64, 64)


def _mask(points: set[tuple[int, int]]) -> Mask:
    """A mask holding exactly ``points`` (test-only builder over the private adopter)."""
    if not points:
        return Mask.empty()
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    box = Box(min(xs), min(ys), max(xs) + 1, max(ys) + 1)
    bits = np.zeros((box.height, box.width), dtype=np.bool_)
    for x, y in points:
        bits[y - box.y0, x - box.x0] = True
    return Mask._adopt(box, bits)


def _padded_mask(points: set[tuple[int, int]]) -> Mask:
    """Like :func:`_mask` but stored in a box one pixel wider on every side."""
    if not points:
        return Mask.empty()
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    box = Box(min(xs) - 1, min(ys) - 1, max(xs) + 2, max(ys) + 2)
    bits = np.zeros((box.height, box.width), dtype=np.bool_)
    for x, y in points:
        bits[y - box.y0, x - box.x0] = True
    return Mask._adopt(box, bits)


def _pixels(mask: Mask) -> set[tuple[int, int]]:
    return {(p.x, p.y) for p in mask.points()}


def _grid(mask: Mask, dims: Dimensions) -> list[str]:
    return [
        "".join("#" if mask.contains(Point(x, y)) else "." for x in range(dims.width))
        for y in range(dims.height)
    ]


def _forward(points: set[tuple[int, int]], transform: Transform) -> set[tuple[int, int]]:
    """Forward map written from MOANART.md section 6, independently of the module.

    Mirror ``x -> -x``, then ``rotation / 90`` clockwise quarter turns ``(x, y) ->
    (-y, x)`` about the pivot, then each index becomes a ``k x k`` block, then the
    offset. No clipping.
    """
    k = transform.scale
    cx, cy = transform.pivot.x, transform.pivot.y
    result: set[tuple[int, int]] = set()
    for px, py in points:
        x, y = px - cx, py - cy
        if transform.mirror:
            x = -x
        for _ in range(transform.rotation // 90):
            x, y = -y, x
        bx, by = k * x + cx + transform.offset.x, k * y + cy + transform.offset.y
        result |= {(bx + i, by + j) for i in range(k) for j in range(k)}
    return result


def _oracle(
    points: set[tuple[int, int]], transform: Transform, dims: Dimensions
) -> set[tuple[int, int]]:
    """:func:`_forward` clipped to the canvas."""
    return {
        (x, y)
        for x, y in _forward(points, transform)
        if 0 <= x < dims.width and 0 <= y < dims.height
    }


# An asymmetric, non-square "L" with a gap: every symmetry would be visible.
L_SHAPE = {(2, 2), (2, 3), (2, 4), (3, 4), (4, 4), (4, 2)}


# --- Hand fixtures ---------------------------------------------------------------


def test_quarter_turn_clockwise_about_pivot_by_hand() -> None:
    # Pivot (3, 3): (2,2)->(4,2); (2,3)->(3,2); (2,4)->(2,2); (3,4)->(2,3);
    # (4,4)->(2,4); (4,2)->(4,4). Relative (x, y) -> (-y, x), y pointing down.
    rotated = transform_mask(_mask(L_SHAPE), Transform(pivot=Point(3, 3), rotation=90), DIMS)
    assert _grid(rotated, Dimensions(6, 6)) == [
        "......",
        "......",
        "..###.",
        "..#...",
        "..#.#.",
        "......",
    ]


def test_mirror_about_pivot_column_by_hand() -> None:
    mirrored = transform_mask(_mask(L_SHAPE), Transform(pivot=Point(5, 0), mirror=True), DIMS)
    # x -> 2*5 - x: columns 2, 3, 4 become 8, 7, 6.
    assert _pixels(mirrored) == {(8, 2), (8, 3), (8, 4), (7, 4), (6, 4), (6, 2)}


def test_rotation_180_and_270_by_hand() -> None:
    pixel = _mask({(5, 3)})
    pivot = Point(4, 4)  # relative (1, -1)
    assert _pixels(transform_mask(pixel, Transform(pivot=pivot, rotation=180), DIMS)) == {(3, 5)}
    assert _pixels(transform_mask(pixel, Transform(pivot=pivot, rotation=270), DIMS)) == {(3, 3)}


def test_translation_moves_every_pixel() -> None:
    moved = transform_mask(_mask(L_SHAPE), Transform(offset=Point(5, -2)), DIMS)
    assert _pixels(moved) == {(x + 5, y - 2) for x, y in L_SHAPE}


def test_ac2_scale_two_replicates_each_pixel_in_a_2x2_block() -> None:
    source = _mask({(1, 1), (2, 1), (1, 2)})
    scaled = transform_mask(source, Transform(pivot=Point(1, 1), scale=2), DIMS)
    assert _grid(scaled, Dimensions(6, 5)) == [
        "......",
        ".####.",
        ".####.",
        ".##...",
        ".##...",
    ]
    assert scaled.count == 4 * source.count


def test_scale_with_rotation_keeps_blocks_whole() -> None:
    # Pixel (1, 0) relative to pivot (0, 0) turns to (0, 1) and scales to [0,3) x [3,6).
    scaled = transform_mask(_mask({(1, 0)}), Transform(rotation=90, scale=3), DIMS)
    assert _pixels(scaled) == {(x, y) for x in range(3) for y in range(3, 6)}


# --- AC1 / AC2: identities --------------------------------------------------------


def test_ac1_four_quarter_turns_reconstruct_the_mask() -> None:
    source = _mask(L_SHAPE)
    turn = Transform(pivot=Point(4, 3), rotation=90)
    current = source
    for _ in range(4):
        current = transform_mask(current, turn, BIG)
    assert current == source
    assert _pixels(current) == L_SHAPE


def test_ac2_double_mirror_is_identity() -> None:
    source = _mask(L_SHAPE)
    mirror = Transform(pivot=Point(3, 0), mirror=True)
    once = transform_mask(source, mirror, BIG)
    assert once != source
    assert transform_mask(once, mirror, BIG) == source


def test_vertical_mirror_is_mirror_plus_half_turn() -> None:
    flipped = transform_mask(
        _mask(L_SHAPE), Transform(pivot=Point(0, 3), mirror=True, rotation=180), DIMS
    )
    assert _pixels(flipped) == {(x, 6 - y) for x, y in L_SHAPE}


# --- T1: composition and inverses on non-square masks and negative pivots ----------

coordinate = st.integers(-6, 18)
small_sets = st.sets(st.tuples(st.integers(0, 11), st.integers(0, 9)), max_size=14)
transforms = st.builds(
    Transform,
    pivot=st.builds(Point, coordinate, coordinate),
    mirror=st.booleans(),
    rotation=st.sampled_from([0, 90, 180, 270]),
    scale=st.integers(1, 3),
    offset=st.builds(Point, st.integers(-8, 8), st.integers(-8, 8)),
)


@given(points=small_sets, transform=transforms)
def test_t1_matches_independent_forward_oracle(
    points: set[tuple[int, int]], transform: Transform
) -> None:
    result = transform_mask(_mask(points), transform, DIMS)
    assert _pixels(result) == _oracle(points, transform, DIMS)


@given(points=small_sets, transform=transforms)
def test_t1_storage_wider_than_bounds_gives_the_same_image(
    points: set[tuple[int, int]], transform: Transform
) -> None:
    assert _pixels(transform_mask(_padded_mask(points), transform, DIMS)) == _oracle(
        points, transform, DIMS
    )


@given(points=small_sets, transform=transforms)
def test_t1_inverse_restores_unclipped_masks(
    points: set[tuple[int, int]], transform: Transform
) -> None:
    unscaled = Transform(
        pivot=transform.pivot,
        mirror=transform.mirror,
        rotation=transform.rotation,
        offset=transform.offset,
    )
    # Pivots in -6..18 and offsets in -8..8 move pixels at most ~40 away; shifting the
    # source by 100 keeps every image on the 256x256 canvas, so no example is vacuous.
    room = Dimensions(256, 256)
    points = {(x + 100, y + 100) for x, y in points}
    unscaled = Transform(
        pivot=Point(unscaled.pivot.x + 100, unscaled.pivot.y + 100),
        mirror=unscaled.mirror,
        rotation=unscaled.rotation,
        offset=unscaled.offset,
    )
    there = transform_mask(_mask(points), unscaled, room)
    assert there.count == len(points)
    assert _pixels(transform_mask(there, unscaled.inverse(), room)) == points


@given(
    points=small_sets,
    pivot=st.builds(Point, st.integers(-9, -1), st.integers(-9, -1)),
    first=st.sampled_from([0, 90, 180, 270]),
    second=st.sampled_from([0, 90, 180, 270]),
)
def test_t1_rotations_compose_additively_with_negative_pivot(
    points: set[tuple[int, int]], pivot: Point, first: int, second: int
) -> None:
    # T1 turns about a negative pivot c and moves by t onto the canvas; turning again
    # about the image of the pivot (c + t) equals one turn by the sum about c.
    room = Dimensions(128, 128)
    offset = Point(60, 60)
    source = _mask(points)
    once = transform_mask(source, Transform(pivot=pivot, rotation=first, offset=offset), room)
    assert once.count == len(points), "the offset keeps the image on the canvas"
    image_pivot = Point(pivot.x + offset.x, pivot.y + offset.y)
    twice = transform_mask(once, Transform(pivot=image_pivot, rotation=second), room)
    combined = Transform(pivot=pivot, rotation=(first + second) % 360, offset=offset)
    assert twice == transform_mask(source, combined, room)


def test_t1_translations_compose_and_mirror_plus_half_turn_is_vertical_mirror() -> None:
    room = Dimensions(32, 32)
    source = transform_mask(_mask(L_SHAPE), Transform(offset=Point(8, 8)), room)
    a, b = Transform(offset=Point(2, -1)), Transform(offset=Point(-5, 3))
    assert transform_mask(transform_mask(source, a, room), b, room) == transform_mask(
        source, Transform(offset=Point(-3, 2)), room
    )
    pivot = Point(-2, 13)  # negative pivot column; row 13 mirrors rows 10..12 to 14..16
    vertical = transform_mask(source, Transform(pivot=pivot, mirror=True, rotation=180), room)
    assert _pixels(vertical) == {(x, 2 * pivot.y - y) for x, y in _pixels(source)}
    centre = Point(12, 13)  # R(180) then mirror equals mirror then R(180): (x, y) -> (x, -y)
    turned_then_mirrored = transform_mask(
        transform_mask(source, Transform(pivot=centre, rotation=180), room),
        Transform(pivot=centre, mirror=True),
        room,
    )
    assert turned_then_mirrored == transform_mask(
        source, Transform(pivot=centre, mirror=True, rotation=180), room
    )


def test_t1_inverse_of_mirror_is_itself_and_of_turn_is_opposite_turn() -> None:
    turn = Transform(pivot=Point(-3, 2), rotation=90, offset=Point(4, -1))
    inverse = turn.inverse()
    assert (inverse.mirror, inverse.rotation, inverse.offset) == (False, 270, Point(-4, 1))
    assert inverse.pivot == Point(1, 1)
    reflection = Transform(pivot=Point(2, 2), mirror=True, rotation=90)
    assert reflection.inverse() == reflection
    assert Transform().inverse() == Transform()
    assert Transform().is_identity


def test_odd_and_even_sized_boxes_transform_as_pixel_sets() -> None:
    # A geometric rotation of corners would move a 3x2 box by half a pixel; the pixel
    # set rotation keeps the pivot pixel fixed and yields a 2x3 box.
    assert transform_box(Box(0, 0, 3, 2), Transform(rotation=90)) == Box(-1, 0, 1, 3)
    assert transform_box(Box(0, 0, 2, 2), Transform(rotation=90)) == Box(-1, 0, 1, 2)
    # x in {2, 3, 4} -> 6 - x and y in {1, 2, 3} -> 4 - y: the box maps onto itself.
    assert transform_box(Box(2, 1, 5, 4), Transform(pivot=Point(3, 2), rotation=180)) == Box(
        2, 1, 5, 4
    )
    assert transform_box(Box(2, 1, 5, 3), Transform(pivot=Point(3, 2), rotation=180)) == Box(
        2, 2, 5, 4
    )
    assert transform_box(Box(0, 0, 1, 1), Transform(scale=4, offset=Point(1, 1))) == Box(1, 1, 5, 5)


@given(box_corner=st.tuples(st.integers(-5, 5), st.integers(-5, 5)), transform=transforms)
def test_box_image_equals_bounds_of_transformed_pixels(
    box_corner: tuple[int, int], transform: Transform
) -> None:
    x0, y0 = box_corner
    box = Box(x0, y0, x0 + 3, y0 + 2)
    pixels = {(x, y) for x in range(box.x0, box.x1) for y in range(box.y0, box.y1)}
    expected = _forward(pixels, transform)
    xs = [x for x, _ in expected]
    ys = [y for _, y in expected]
    assert transform_box(box, transform) == Box(min(xs), min(ys), max(xs) + 1, max(ys) + 1)


# --- T2: clipping and rejection -------------------------------------------------


def test_t2_partially_off_canvas_is_clipped_without_wraparound() -> None:
    line = rasterize_line(Point(0, 0), Point(5, 0), DIMS)
    moved = transform_mask(line, Transform(offset=Point(-3, 0)), DIMS)
    assert _pixels(moved) == {(0, 0), (1, 0), (2, 0)}
    assert moved.box == Box(0, 0, 3, 1)
    turned = transform_mask(line, Transform(rotation=90), DIMS)  # into x = 0, y in 0..5
    assert _pixels(turned) == {(0, y) for y in range(6)}
    up = transform_mask(line, Transform(rotation=270), DIMS)  # y in -5..0: only the pivot
    assert _pixels(up) == {(0, 0)}


def test_t2_fully_off_canvas_is_empty_without_wraparound() -> None:
    rect = rasterize_rect(Box(0, 0, 4, 4), DIMS)
    for transform in (
        Transform(offset=Point(-4, 0)),
        Transform(offset=Point(DIMS.width, 0)),
        Transform(rotation=180, offset=Point(0, -1)),
        Transform(offset=Point(MAX_COORDINATE, MAX_COORDINATE)),
        Transform(pivot=Point(-MAX_COORDINATE, 0), scale=MAX_SCALE),
    ):
        result = transform_mask(rect, transform, DIMS)
        assert result.is_empty and result.box is None


def test_t2_large_scale_is_clipped_before_allocating() -> None:
    pixel = rasterize_pixel(Point(1, 1), DIMS)
    tracemalloc.start()
    try:
        result = transform_mask(pixel, Transform(scale=MAX_SCALE, pivot=Point(1, 1)), DIMS)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert result.box == Box(1, 1, DIMS.width, DIMS.height)
    assert result.count == (DIMS.width - 1) * (DIMS.height - 1)
    assert peak < 64 * 1024


def test_image_with_every_pixel_off_canvas_is_the_empty_mask() -> None:
    # The image box [-3, 8) overlaps the canvas but its two pixels land at x = -3 and 7.
    sparse = _mask({(0, 0), (10, 0)})
    result = transform_mask(sparse, Transform(offset=Point(-3, 0)), Dimensions(5, 5))
    assert result.is_empty and result.box is None


def test_empty_mask_stays_empty() -> None:
    assert transform_mask(Mask.empty(), Transform(rotation=90), DIMS).is_empty


@pytest.mark.parametrize(
    ("kwargs", "field_name", "reason"),
    [
        ({"rotation": 45}, "rotation", "arbitrary_rotation"),
        ({"rotation": 1}, "rotation", "arbitrary_rotation"),
        ({"rotation": 360}, "rotation", "out_of_range"),
        ({"rotation": -90}, "rotation", "out_of_range"),
        ({"rotation": 90.0}, "rotation", "not_integer"),
        ({"rotation": True}, "rotation", "not_integer"),
        ({"scale": 1.5}, "scale", "not_integer"),
        ({"scale": 2.0}, "scale", "not_integer"),
        ({"scale": True}, "scale", "not_integer"),
        ({"scale": 0}, "scale", "out_of_range"),
        ({"scale": -2}, "scale", "out_of_range"),
        ({"scale": MAX_SCALE + 1}, "scale", "out_of_range"),
        ({"mirror": 1}, "mirror", "not_boolean"),
    ],
)
def test_t2_rejects_arbitrary_rotation_and_non_integer_scale(
    kwargs: dict[str, object], field_name: str, reason: str
) -> None:
    with pytest.raises(ValidationError) as excinfo:
        Transform(**kwargs)  # type: ignore[arg-type]  # invalid on purpose
    assert excinfo.value.context["field"] == field_name
    assert excinfo.value.context["reason"] == reason


def test_scaled_transform_has_no_inverse() -> None:
    with pytest.raises(ValidationError) as excinfo:
        Transform(scale=2).inverse()
    assert excinfo.value.context["reason"] == "not_invertible"


def test_arguments_are_type_checked() -> None:
    with pytest.raises(TypeError):
        Transform(pivot=(0, 0))  # type: ignore[arg-type]  # deliberate misuse
    with pytest.raises(TypeError):
        Transform(offset=None)  # type: ignore[arg-type]  # deliberate misuse
    with pytest.raises(TypeError):
        transform_mask(L_SHAPE, Transform(), DIMS)  # type: ignore[arg-type]  # misuse
    with pytest.raises(TypeError):
        transform_mask(Mask.empty(), "rotate", DIMS)  # type: ignore[arg-type]  # misuse
    with pytest.raises(TypeError):
        transform_mask(Mask.empty(), Transform(), (4, 4))  # type: ignore[arg-type]  # misuse
    with pytest.raises(TypeError):
        transform_box((0, 0, 1, 1), Transform())  # type: ignore[arg-type]  # misuse


def test_inverse_pivot_out_of_range_is_not_invertible() -> None:
    far = Transform(pivot=Point(MAX_COORDINATE, 0), offset=Point(1, 0))
    with pytest.raises(ValidationError) as excinfo:
        far.inverse()
    assert excinfo.value.context == {"field": "pivot", "reason": "not_invertible"}


def test_rotation_errors_carry_type_and_allowed_values() -> None:
    with pytest.raises(ValidationError) as not_integer:
        Transform(rotation=90.0)  # type: ignore[arg-type]  # invalid on purpose
    assert not_integer.value.context["value_type"] == "float"
    with pytest.raises(ValidationError) as out_of_range:
        Transform(rotation=360)
    assert out_of_range.value.context["allowed"] == (0, 90, 180, 270)


def test_peak_memory_is_output_plus_one_source_copy() -> None:
    big = Dimensions(512, 512)
    full = rasterize_rect(Box(0, 0, 512, 512), big)
    tracemalloc.start()
    try:
        corner = transform_mask(full, Transform(offset=Point(511, 511)), big)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert corner.count == 1
    source_bytes = 513 * 513  # padded copy of the 512x512 storage
    assert peak <= source_bytes + 64 * 1024


def test_box_image_out_of_coordinate_range_is_a_validation_error() -> None:
    with pytest.raises(ValidationError):
        transform_box(Box(0, 0, 2, 2), Transform(offset=Point(MAX_COORDINATE, 0)))


def test_transform_is_immutable_and_hashable() -> None:
    transform = Transform(rotation=90)
    with pytest.raises(AttributeError):
        transform.rotation = 180  # type: ignore[misc]  # frozen on purpose
    assert hash(transform) == hash(Transform(rotation=90))


def test_polygon_rotation_preserves_count_inside_canvas() -> None:
    triangle = rasterize_polygon([Point(2, 2), Point(7, 2), Point(2, 6)], BIG)
    rotated = transform_mask(triangle, Transform(pivot=Point(20, 20), rotation=90), BIG)
    assert rotated.count == triangle.count
