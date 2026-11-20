"""T1 (MOANA-014): bounded Chebyshev dilation and erosion (MOANA.md section 8, ADR-027).

Oracles are Python sets of ``(x, y)`` pixels: hand-written masks for the fixtures and
the literal definitions (``max(|dx|, |dy|) <= r``, exterior transparent) for the
property test. Masks are built from raw bits (``_restore``), never from the operators
under test.
"""

from __future__ import annotations

import tracemalloc
from collections.abc import Callable, Iterable
from functools import partial

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from moana.core.coordinates import Box, Dimensions, grown_box
from moana.core.errors import ValidationError
from moana.core.limits import MAX_MORPHOLOGY_RADIUS
from moana.core.morphology import MORPHOLOGY_FIXED_BYTES, morphology_bytes
from moana.geometry import Mask, dilate, erode
from moana.geometry.mask import _restore

Pixels = frozenset[tuple[int, int]]


def mask_of(pixels: Iterable[tuple[int, int]], box: Box | None = None) -> Mask:
    """A mask holding exactly ``pixels``, stored over ``box`` or their bounding box."""
    points = sorted(pixels)
    if not points:
        return Mask.empty()
    if box is None:
        box = Box(
            min(x for x, _ in points),
            min(y for _, y in points),
            max(x for x, _ in points) + 1,
            max(y for _, y in points) + 1,
        )
    bits = np.zeros((box.height, box.width), dtype=np.uint8)
    for x, y in points:
        bits[y - box.y0, x - box.x0] = 1
    return _restore(box, (box.height, box.width), bits.tobytes())


def pixels_of(mask: Mask) -> Pixels:
    return frozenset((point.x, point.y) for point in mask.points())


def dilation_oracle(pixels: Pixels, radius: int, width: int, height: int) -> Pixels:
    return frozenset(
        (x, y)
        for x in range(width)
        for y in range(height)
        if any(max(abs(x - a), abs(y - b)) <= radius for a, b in pixels)
    )


def erosion_oracle(pixels: Pixels, radius: int, width: int, height: int) -> Pixels:
    window = range(-radius, radius + 1)
    return frozenset(
        (x, y)
        for x in range(width)
        for y in range(height)
        if all((x + i, y + j) in pixels for i in window for j in window)
    )


# --- hand fixtures ------------------------------------------------------------------------


def test_dilating_one_pixel_gives_the_chebyshev_square() -> None:
    dims = Dimensions(9, 9)
    result = dilate(mask_of({(4, 4)}), 2, dims)
    assert pixels_of(result) == {(x, y) for x in range(2, 7) for y in range(2, 7)}
    assert result.box == Box(2, 2, 7, 7)


def test_radius_r_equals_r_repetitions_of_the_3x3_neighbourhood() -> None:
    dims = Dimensions(12, 12)
    source = mask_of({(3, 4), (7, 6), (8, 8)})
    twice = dilate(dilate(source, 1, dims), 1, dims)
    assert pixels_of(dilate(source, 2, dims)) == pixels_of(twice)
    assert pixels_of(erode(erode(dilate(source, 3, dims), 1, dims), 1, dims)) == pixels_of(
        erode(dilate(source, 3, dims), 2, dims)
    )


def test_dilation_clips_to_the_canvas_without_wraparound() -> None:
    dims = Dimensions(5, 4)
    result = dilate(mask_of({(0, 0), (4, 3)}), 1, dims)
    assert pixels_of(result) == {(0, 0), (1, 0), (0, 1), (1, 1), (3, 2), (4, 2), (3, 3), (4, 3)}
    assert result.box == Box(0, 0, 5, 4)  # the grown box, clipped before allocation


def test_erosion_treats_the_off_canvas_exterior_as_transparent() -> None:
    dims = Dimensions(6, 5)
    full = {(x, y) for x in range(6) for y in range(5)}
    eroded = erode(mask_of(full), 1, dims)
    assert pixels_of(eroded) == {(x, y) for x in range(1, 5) for y in range(1, 4)}
    assert erode(mask_of(full), 2, dims).is_empty is False
    assert pixels_of(erode(mask_of(full), 2, dims)) == {(2, 2), (3, 2)}


def test_a_hole_shrinks_under_dilation_and_grows_under_erosion() -> None:
    dims = Dimensions(9, 9)
    ring = {(x, y) for x in range(1, 8) for y in range(1, 8)} - {(4, 4)}
    assert (4, 4) in pixels_of(dilate(mask_of(ring), 1, dims))
    eroded = pixels_of(erode(mask_of(ring), 1, dims))
    hole_neighbours = {(x, y) for x in range(3, 6) for y in range(3, 6)}
    assert eroded == {(x, y) for x in range(2, 7) for y in range(2, 7)} - hole_neighbours


def test_corner_contact_and_diagonal() -> None:
    dims = Dimensions(6, 6)
    diagonal = {(i, i) for i in range(6)}
    assert erode(mask_of(diagonal), 1, dims).is_empty
    assert pixels_of(dilate(mask_of(diagonal), 1, dims)) == dilation_oracle(
        frozenset(diagonal), 1, 6, 6
    )


def test_empty_and_off_canvas_masks_give_empty_results() -> None:
    dims = Dimensions(4, 4)
    assert dilate(Mask.empty(), 1, dims).is_empty
    assert erode(Mask.empty(), 1, dims).is_empty
    far = mask_of({(10, 10)})  # stored entirely outside this canvas
    assert dilate(far, 2, dims).is_empty and erode(far, 1, dims).is_empty
    assert erode(mask_of({(1, 1)}), 1, dims).is_empty


def test_mask_stored_partly_off_a_smaller_canvas_is_clipped_first() -> None:
    pixels = {(x, y) for x in range(8) for y in range(8)}
    small = Dimensions(5, 5)
    assert pixels_of(erode(mask_of(pixels), 1, small)) == erosion_oracle(
        frozenset(p for p in pixels if p[0] < 5 and p[1] < 5), 1, 5, 5
    )
    assert pixels_of(dilate(mask_of(pixels), 1, small)) == {
        (x, y) for x in range(5) for y in range(5)
    }


def test_results_keep_storage_boxes_and_dilation_supersets() -> None:
    dims = Dimensions(10, 10)
    source = mask_of({(4, 4), (5, 5)}, box=Box(3, 3, 7, 7))  # stored over a wider box
    assert dilate(source, 1, dims).box == Box(2, 2, 8, 8)
    assert erode(mask_of({(x, y) for x in range(3, 7) for y in range(3, 7)}), 1, dims).box == (
        Box(3, 3, 7, 7)
    )


# --- negatives ----------------------------------------------------------------------------


@pytest.mark.parametrize("radius", [0, -1, MAX_MORPHOLOGY_RADIUS + 1])
def test_radius_out_of_range(radius: int) -> None:
    for operator in (dilate, erode):
        with pytest.raises(ValidationError) as raised:
            operator(mask_of({(1, 1)}), radius, Dimensions(4, 4))
        assert raised.value.context["field"] == "radius"
        assert raised.value.context["reason"] == "out_of_range"


@pytest.mark.parametrize("radius", [True, 1.0, "1"])
def test_radius_must_be_a_real_int(radius: object) -> None:
    with pytest.raises(ValidationError) as raised:
        dilate(mask_of({(1, 1)}), radius, Dimensions(4, 4))  # type: ignore[arg-type]  # invalid on purpose
    assert raised.value.context["reason"] == "not_integer"


def test_wrong_types_are_type_errors() -> None:
    with pytest.raises(TypeError, match="Mask"):
        dilate("mask", 1, Dimensions(4, 4))  # type: ignore[arg-type]  # invalid on purpose
    with pytest.raises(TypeError, match="Dimensions"):
        erode(Mask.empty(), 1, (4, 4))  # type: ignore[arg-type]  # invalid on purpose


def test_grown_box_contract() -> None:
    dims = Dimensions(10, 8)
    assert grown_box(Box(2, 2, 4, 4), 3, dims) == Box(0, 0, 7, 7)
    assert grown_box(Box(2, 2, 4, 4), 0, dims) == Box(2, 2, 4, 4)
    assert grown_box(Box(-5, -5, 12, 9), 0, dims) == Box(0, 0, 10, 8)
    assert grown_box(None, 2, dims) is None
    assert grown_box(Box(20, 20, 21, 21), 2, dims) is None  # clipped before growing
    with pytest.raises(ValidationError):
        grown_box(Box(0, 0, 1, 1), -1, dims)
    with pytest.raises(TypeError):
        grown_box((0, 0, 1, 1), 1, dims)  # type: ignore[arg-type]  # invalid on purpose


# --- properties against the set oracle -----------------------------------------------------

pixel_sets = st.frozensets(st.tuples(st.integers(0, 8), st.integers(0, 8)), max_size=20)


@settings(max_examples=150, deadline=None)
@given(
    pixels=pixel_sets,
    radius=st.integers(1, 3),
    width=st.integers(1, 9),
    height=st.integers(1, 9),
)
def test_operators_match_the_set_oracle(
    pixels: Pixels, radius: int, width: int, height: int
) -> None:
    on_canvas = frozenset((x, y) for x, y in pixels if x < width and y < height)
    dims = Dimensions(width, height)
    source = mask_of(on_canvas)
    assert pixels_of(dilate(source, radius, dims)) == dilation_oracle(
        on_canvas, radius, width, height
    )
    assert pixels_of(erode(source, radius, dims)) == erosion_oracle(
        on_canvas, radius, width, height
    )


# --- memory ---------------------------------------------------------------------------------


def traced_peak(operator: Callable[[], Mask]) -> tuple[Mask, int]:
    tracemalloc.start()
    try:
        result = operator()
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return result, peak


@pytest.mark.parametrize("radius", [1, 3, MAX_MORPHOLOGY_RADIUS])
@pytest.mark.parametrize(
    "size", [(1, 1), (8, 8), (40, 80), (100, 100), (2048, 1), (1, 2048), (300, 300)]
)
def test_peak_memory_stays_within_morphology_bytes(size: tuple[int, int], radius: int) -> None:
    """Full and sparse boxes of many shapes; the strided NumPy buffers are in the bound."""
    width, height = size
    dims = Dimensions(2048, 2048)
    box = Box(0, 0, width, height)
    full = _restore(box, (height, width), bytes([1]) * box.area)
    bits = np.zeros((height, width), dtype=np.uint8)
    bits[::3, ::2] = 1
    sparse = _restore(box, (height, width), bits.tobytes())
    grown = grown_box(box, radius, dims)
    for source in (full, sparse):
        for operator, work in ((dilate, grown), (erode, box)):
            result, peak = traced_peak(partial(operator, source, radius, dims))
            assert result.box is None or result.box == work
            assert peak <= morphology_bytes(work, radius)


def test_peak_memory_of_an_inner_mask_stored_off_its_origin() -> None:
    dims = Dimensions(300, 260)
    bits = np.zeros((200, 220), dtype=np.uint8)
    bits[::3, ::2] = 1
    source = _restore(Box(40, 30, 260, 230), (200, 220), bits.tobytes())
    for radius in (1, 2, MAX_MORPHOLOGY_RADIUS):
        grown = grown_box(source.box, radius, dims)
        for operator, box in ((dilate, grown), (erode, source.box)):
            _, peak = traced_peak(partial(operator, source, radius, dims))
            assert peak <= morphology_bytes(box, radius)


def test_morphology_bytes_formula() -> None:
    assert morphology_bytes(None, 3) == 0
    # 4 x 2 box, radius 1: P = (4+3)*(2+3) = 35;
    # 2*8 bits + 4*35 prefix + 4*8 counts + 12*min(35, 8192) buffers + fixed
    assert morphology_bytes(Box(0, 0, 4, 2), 1) == 16 + 140 + 32 + 420 + MORPHOLOGY_FIXED_BYTES
    # 300 x 300 box, radius 16: P = 333 * 333 = 110889 > 8192, so the buffers are capped
    assert morphology_bytes(Box(0, 0, 300, 300), 16) == (
        2 * 90_000 + 4 * 110_889 + 4 * 90_000 + 12 * 8192 + MORPHOLOGY_FIXED_BYTES
    )


def test_width_16_matches_the_set_oracle_on_explicit_masks() -> None:
    """The largest radius against the literal definitions, holes and the canvas edge."""
    dims = Dimensions(40, 36)
    ring = frozenset(
        (x, y) for x in range(2, 38) for y in range(1, 35) if not (12 <= x < 28 and 10 <= y < 26)
    )
    for pixels in (frozenset({(20, 18)}), ring, frozenset({(0, 0), (39, 35)})):
        source = mask_of(pixels)
        assert pixels_of(dilate(source, MAX_MORPHOLOGY_RADIUS, dims)) == dilation_oracle(
            pixels, MAX_MORPHOLOGY_RADIUS, 40, 36
        )
        assert pixels_of(erode(source, MAX_MORPHOLOGY_RADIUS, dims)) == erosion_oracle(
            pixels, MAX_MORPHOLOGY_RADIUS, 40, 36
        )
    full = frozenset((x, y) for x in range(40) for y in range(36))
    assert pixels_of(erode(mask_of(full), MAX_MORPHOLOGY_RADIUS, dims)) == frozenset(
        (x, y) for x in range(16, 24) for y in range(16, 20)
    )
