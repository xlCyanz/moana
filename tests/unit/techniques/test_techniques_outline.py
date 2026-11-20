"""AC1/T1/T2 (MOANA-014): outer and inner outlines of masks (MOANA.md section 8, ADR-027).

Expected pixels are written by hand (rings, holes, canvas corners) or computed from
section 8 with Python sets: outer = ``{p : 0 < d(p, mask) <= w}`` with the Chebyshev
distance ``d``, inner = ``{p in mask : some q with d(p, q) <= w is outside}`` where
pixels off the canvas are outside. Masks are built from raw bits, never from the
operators under test.
"""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from moana.core.coordinates import Box, Dimensions
from moana.core.errors import ValidationError
from moana.geometry import Mask
from moana.geometry.mask import _restore
from moana.techniques import MAX_OUTLINE_WIDTH, OUTLINE_SIDES, outline_mask

Pixels = frozenset[tuple[int, int]]


def mask_of(pixels: Iterable[tuple[int, int]]) -> Mask:
    """A mask holding exactly ``pixels`` over their bounding box, built from raw bits."""
    points = sorted(pixels)
    if not points:
        return Mask.empty()
    x0, y0 = min(x for x, _ in points), min(y for _, y in points)
    x1, y1 = max(x for x, _ in points) + 1, max(y for _, y in points) + 1
    bits = np.zeros((y1 - y0, x1 - x0), dtype=np.uint8)
    for x, y in points:
        bits[y - y0, x - x0] = 1
    return _restore(Box(x0, y0, x1, y1), (y1 - y0, x1 - x0), bits.tobytes())


def pixels_of(mask: Mask) -> frozenset[tuple[int, int]]:
    return frozenset((point.x, point.y) for point in mask.points())


def square(x0: int, y0: int, x1: int, y1: int) -> set[tuple[int, int]]:
    return {(x, y) for x in range(x0, x1) for y in range(y0, y1)}


def outer_oracle(pixels: Pixels, width: int, w: int, h: int) -> Pixels:
    return frozenset(
        (x, y)
        for x in range(w)
        for y in range(h)
        if (x, y) not in pixels and any(max(abs(x - a), abs(y - b)) <= width for a, b in pixels)
    )


def inner_oracle(pixels: Pixels, width: int) -> Pixels:
    span = range(-width, width + 1)
    return frozenset(
        (x, y) for x, y in pixels if any((x + i, y + j) not in pixels for i in span for j in span)
    )


# --- AC1 / T1: width, holes, corners, diagonals and canvas edges ---------------------------


def test_ac1_outer_width_1_rings_the_square_and_fills_its_hole() -> None:
    dims = Dimensions(10, 10)
    hole = square(4, 4, 6, 6)
    shape = square(2, 2, 8, 8) - hole
    ring = square(1, 1, 9, 9) - square(2, 2, 8, 8)  # 28 pixels around the square
    result = outline_mask(mask_of(shape), 1, "outer", dims)
    assert pixels_of(result) == ring | hole
    assert len(ring) == 28 and result.count == 32
    assert result.box == Box(1, 1, 9, 9)


def test_ac1_inner_width_1_follows_the_border_and_the_hole() -> None:
    dims = Dimensions(10, 10)
    hole = square(4, 4, 6, 6)
    shape = square(2, 2, 8, 8) - hole
    border = square(2, 2, 8, 8) - square(3, 3, 7, 7)  # 20 pixels
    around_hole = square(3, 3, 7, 7) - hole  # 12 pixels
    result = outline_mask(mask_of(shape), 1, "inner", dims)
    assert pixels_of(result) == border | around_hole
    assert result.count == 32


def test_ac1_width_2_doubles_the_ring_on_both_sides() -> None:
    dims = Dimensions(16, 16)
    shape = square(4, 4, 12, 12)
    assert pixels_of(outline_mask(mask_of(shape), 2, "outer", dims)) == square(2, 2, 14, 14) - shape
    assert pixels_of(outline_mask(mask_of(shape), 2, "inner", dims)) == shape - square(6, 6, 10, 10)


def test_ac1_inner_width_2_around_a_single_pixel_hole() -> None:
    dims = Dimensions(16, 16)
    shape = square(1, 1, 15, 15) - {(7, 7)}
    expected = (square(1, 1, 15, 15) - square(3, 3, 13, 13)) | (square(5, 5, 10, 10) - {(7, 7)})
    assert pixels_of(outline_mask(mask_of(shape), 2, "inner", dims)) == expected


def test_ac1_clipping_at_the_canvas_corner() -> None:
    dims = Dimensions(8, 8)
    corner = square(0, 0, 4, 4)
    outer = outline_mask(mask_of(corner), 1, "outer", dims)
    assert pixels_of(outer) == square(0, 0, 5, 5) - corner  # 9 pixels, no wraparound
    assert outer.box == Box(0, 0, 5, 5)
    # the exterior beyond the canvas is transparent: the edge pixels are outline
    inner = outline_mask(mask_of(corner), 1, "inner", dims)
    assert pixels_of(inner) == corner - square(1, 1, 3, 3)
    assert {(0, 0), (0, 3), (3, 0)} <= pixels_of(inner)


def test_t1_full_canvas_has_no_outer_outline_and_an_edge_inner_one() -> None:
    dims = Dimensions(5, 4)
    full = square(0, 0, 5, 4)
    assert outline_mask(mask_of(full), 1, "outer", dims).is_empty
    assert pixels_of(outline_mask(mask_of(full), 1, "inner", dims)) == full - square(1, 1, 4, 3)


def test_t1_corner_contact_fills_the_notches() -> None:
    dims = Dimensions(7, 7)
    shape = square(1, 1, 3, 3) | square(3, 3, 5, 5)  # touching only at a corner
    outer = pixels_of(outline_mask(mask_of(shape), 1, "outer", dims))
    assert {(3, 2), (2, 3)} <= outer  # the two notch pixels belong to both rings
    assert outer == (square(0, 0, 4, 4) | square(2, 2, 6, 6)) - shape
    assert pixels_of(outline_mask(mask_of(shape), 1, "inner", dims)) == shape


def test_t1_diagonal_line() -> None:
    dims = Dimensions(6, 6)
    diagonal = {(i, i) for i in range(6)}
    assert pixels_of(outline_mask(mask_of(diagonal), 1, "inner", dims)) == diagonal
    outer = pixels_of(outline_mask(mask_of(diagonal), 1, "outer", dims))
    # by hand: every pixel one or two columns off the diagonal
    assert outer == {(x, y) for x in range(6) for y in range(6) if 1 <= abs(x - y) <= 2}
    assert outer == outer_oracle(frozenset(diagonal), 1, 6, 6)
    assert (5, 0) not in outer and (1, 0) in outer and (2, 0) in outer


def test_t2_outline_is_disjoint_from_or_inside_the_mask() -> None:
    dims = Dimensions(12, 9)
    shape = square(2, 1, 9, 7) - {(5, 4)}
    outer = pixels_of(outline_mask(mask_of(shape), 1, "outer", dims))
    inner = pixels_of(outline_mask(mask_of(shape), 1, "inner", dims))
    assert not outer & shape and inner <= shape


def test_empty_mask_has_no_outline() -> None:
    for side in OUTLINE_SIDES:
        assert outline_mask(Mask.empty(), 1, side, Dimensions(4, 4)).is_empty


# --- negatives --------------------------------------------------------------------------


@pytest.mark.parametrize("width", [0, MAX_OUTLINE_WIDTH + 1, True])
def test_width_out_of_range(width: int) -> None:
    with pytest.raises(ValidationError) as raised:
        outline_mask(mask_of({(1, 1)}), width, "outer", Dimensions(4, 4))
    assert raised.value.context["field"] == "width"


@pytest.mark.parametrize("side", ["both", "OUTER", 1])
def test_unknown_side(side: object) -> None:
    with pytest.raises(ValidationError) as raised:
        outline_mask(mask_of({(1, 1)}), 1, side, Dimensions(4, 4))  # type: ignore[arg-type]  # invalid on purpose
    assert raised.value.context == {"field": "side", "reason": "unknown_side"}


def test_mask_type_is_checked() -> None:
    with pytest.raises(TypeError, match="Mask"):
        outline_mask({(1, 1)}, 1, "outer", Dimensions(4, 4))  # type: ignore[arg-type]  # invalid on purpose


# --- property against the set oracle ----------------------------------------------------


@settings(max_examples=150, deadline=None)
@given(
    pixels=st.frozensets(st.tuples(st.integers(0, 9), st.integers(0, 9)), max_size=30),
    width=st.integers(1, 3),
    side=st.sampled_from(OUTLINE_SIDES),
    w=st.integers(1, 10),
    h=st.integers(1, 10),
)
def test_outline_matches_the_set_oracle(
    pixels: Pixels, width: int, side: str, w: int, h: int
) -> None:
    inside = frozenset((x, y) for x, y in pixels if x < w and y < h)
    dims = Dimensions(w, h)
    result = pixels_of(outline_mask(mask_of(inside), width, side, dims))  # type: ignore[arg-type]  # sampled side
    if side == "outer":
        assert result == outer_oracle(inside, width, w, h)
    else:
        assert result == inner_oracle(inside, width)
