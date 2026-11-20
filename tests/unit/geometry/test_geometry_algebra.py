"""T1 (MOANA-013): binary set algebra of canvas masks (MOANA.md section 11, ADR-022).

Oracles are Python sets of ``(x, y)`` pixels written by hand; masks are built from
raw bits (``_restore``), never from the algebra under test. Fixtures hold 1, 8 and
128 pixels, plus empty masks and masks reaching outside the canvas.
"""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from moana.core.coordinates import Box, Dimensions
from moana.geometry import (
    MASK_OPERATORS,
    Mask,
    MaskBuilder,
    MaskOperator,
    combine_masks,
    combined_box,
    rasterize_rect,
)
from moana.geometry.mask import _restore

Pixels = frozenset[tuple[int, int]]
DIMS = Dimensions(16, 16)

ONE: Pixels = frozenset({(3, 3)})
# Eight pixels: the ring around (3, 3).
EIGHT: Pixels = frozenset((x, y) for x in range(2, 5) for y in range(2, 5) if (x, y) != (3, 3))
# 128 pixels: the top half of the canvas (16 x 8).
HALF: Pixels = frozenset((x, y) for x in range(16) for y in range(8))
EMPTY: Pixels = frozenset()


def mask_of(pixels: Iterable[tuple[int, int]]) -> Mask:
    """A mask holding exactly ``pixels``, stored over their bounding box."""
    points = sorted(pixels)
    if not points:
        return Mask.empty()
    x0 = min(x for x, _ in points)
    y0 = min(y for _, y in points)
    x1 = max(x for x, _ in points) + 1
    y1 = max(y for _, y in points) + 1
    bits = np.zeros((y1 - y0, x1 - x0), dtype=np.uint8)
    for x, y in points:
        bits[y - y0, x - x0] = 1
    return _restore(Box(x0, y0, x1, y1), (y1 - y0, x1 - x0), bits.tobytes())


def pixels_of(mask: Mask) -> Pixels:
    return frozenset((point.x, point.y) for point in mask.points())


def oracle(operator: MaskOperator, sets: list[Pixels]) -> Pixels:
    first, rest = sets[0], sets[1:]
    if operator == "union":
        return first.union(*rest)
    if operator == "intersect":
        return first.intersection(*rest)
    if operator == "subtract":
        return first.difference(*rest)
    result = set(first)
    for other in rest:
        result ^= other
    return frozenset(result)


FIXTURES = {"one": ONE, "eight": EIGHT, "half": HALF, "empty": EMPTY}


def test_fixtures_have_the_documented_sizes() -> None:
    assert (len(ONE), len(EIGHT), len(HALF), len(EMPTY)) == (1, 8, 128, 0)


@pytest.mark.parametrize("operator", MASK_OPERATORS)
@pytest.mark.parametrize("left", sorted(FIXTURES))
@pytest.mark.parametrize("right", sorted(FIXTURES))
def test_t1_binary_operators_match_set_oracle(
    operator: MaskOperator, left: str, right: str
) -> None:
    sets = [FIXTURES[left], FIXTURES[right]]
    result = combine_masks(operator, [mask_of(s) for s in sets], DIMS)
    assert pixels_of(result) == oracle(operator, sets)
    assert result.count == len(oracle(operator, sets))


def test_t1_hand_results_on_the_fixtures() -> None:
    ring_and_centre = combine_masks("union", [mask_of(ONE), mask_of(EIGHT)], DIMS)
    assert pixels_of(ring_and_centre) == {(x, y) for x in range(2, 5) for y in range(2, 5)}
    assert ring_and_centre.box == Box(2, 2, 5, 5)
    # The ring and the top half share every ring pixel (rows 2..4 < 8).
    assert pixels_of(combine_masks("intersect", [mask_of(EIGHT), mask_of(HALF)], DIMS)) == EIGHT
    # Half minus ring: 128 - 8 = 120 pixels, the centre (3, 3) stays.
    cut = combine_masks("subtract", [mask_of(HALF), mask_of(EIGHT)], DIMS)
    assert cut.count == 120 and (3, 3) in pixels_of(cut) and (2, 2) not in pixels_of(cut)
    # xor of centre and ring is the full 3 x 3 block; xor with itself is empty.
    assert combine_masks("xor", [mask_of(ONE), mask_of(EIGHT)], DIMS).count == 9
    self_xor = combine_masks("xor", [mask_of(EIGHT), mask_of(EIGHT)], DIMS)
    assert self_xor.is_empty and self_xor.box is None


@pytest.mark.parametrize("operator", ["union", "intersect", "xor"])
def test_t1_associative_and_commutative_operators(operator: MaskOperator) -> None:
    a, b, c = mask_of(ONE), mask_of(EIGHT), mask_of(HALF | {(15, 15)})
    left = combine_masks(operator, [combine_masks(operator, [a, b], DIMS), c], DIMS)
    right = combine_masks(operator, [a, combine_masks(operator, [b, c], DIMS)], DIMS)
    flat = combine_masks(operator, [a, b, c], DIMS)
    swapped = combine_masks(operator, [c, a, b], DIMS)
    assert left == right == flat == swapped


def test_t1_subtract_is_left_fold_and_not_commutative() -> None:
    a, b, c = mask_of(HALF), mask_of(EIGHT), mask_of(ONE | {(0, 0)})
    folded = combine_masks("subtract", [a, b, c], DIMS)
    assert folded == combine_masks("subtract", [a, combine_masks("union", [b, c], DIMS)], DIMS)
    assert pixels_of(folded) == HALF - EIGHT - ONE - {(0, 0)}
    assert combine_masks("subtract", [b, a], DIMS).is_empty  # the ring lies in the half


def test_t1_empty_mask_identities() -> None:
    a, empty = mask_of(EIGHT), Mask.empty()
    assert combine_masks("union", [a, empty], DIMS) == a
    assert combine_masks("xor", [empty, a], DIMS) == a
    assert combine_masks("subtract", [a, empty], DIMS) == a
    for operator in MASK_OPERATORS:
        assert combine_masks(operator, [empty, empty], DIMS).box is None
    assert combine_masks("intersect", [a, empty], DIMS).box is None
    assert combine_masks("subtract", [empty, a], DIMS).is_empty
    # Disjoint operands: the intersection has no common box at all.
    assert combine_masks("intersect", [mask_of(ONE), mask_of({(9, 9)})], DIMS).box is None


def test_t1_results_are_clipped_to_the_canvas() -> None:
    big = Dimensions(32, 32)
    outside = rasterize_rect(Box(12, 12, 30, 30), big)  # reaches beyond 16 x 16
    corner = {(x, y) for x in range(12, 16) for y in range(12, 16)}
    clipped = combine_masks("union", [outside, mask_of(ONE)], DIMS)
    assert pixels_of(clipped) == corner | ONE
    assert clipped.box == Box(3, 3, 16, 16)
    far = rasterize_rect(Box(20, 20, 30, 30), big)  # entirely off the 16 x 16 canvas
    assert combine_masks("union", [far, far], DIMS).is_empty
    assert combine_masks("xor", [far, mask_of(ONE)], DIMS) == mask_of(ONE)


def test_combined_box_is_pure_box_arithmetic() -> None:
    a, b = Box(0, 0, 4, 4), Box(2, 3, 10, 6)
    assert combined_box("union", [a, None, b], DIMS) == Box(0, 0, 10, 6)
    assert combined_box("xor", [None, None], DIMS) is None
    assert combined_box("intersect", [a, b], DIMS) == Box(2, 3, 4, 4)
    assert combined_box("intersect", [a, None], DIMS) is None
    assert combined_box("intersect", [None, a], DIMS) is None
    assert combined_box("subtract", [b, a], DIMS) == b
    assert combined_box("subtract", [None, a], DIMS) is None
    assert combined_box("union", [Box(10, 10, 40, 40)], DIMS) == Box(10, 10, 16, 16)


@settings(max_examples=80, deadline=None)
@given(
    operator=st.sampled_from(MASK_OPERATORS),
    sets=st.lists(
        st.frozensets(st.tuples(st.integers(0, 7), st.integers(0, 7)), max_size=20),
        min_size=2,
        max_size=5,
    ),
)
def test_t1_property_matches_python_sets(operator: MaskOperator, sets: list[Pixels]) -> None:
    result = combine_masks(operator, [mask_of(s) for s in sets], Dimensions(8, 8))
    assert pixels_of(result) == oracle(operator, sets)
    assert result.box == (_storage_box(operator, sets) if result.count else None)


def _bounds(pixels: Iterable[tuple[int, int]]) -> tuple[int, int, int, int] | None:
    """Half-open bounding box of a pixel set, independent of the code under test."""
    points = list(pixels)
    if not points:
        return None
    xs, ys = [x for x, _ in points], [y for _, y in points]
    return (min(xs), min(ys), max(xs) + 1, max(ys) + 1)


def _storage_box(operator: MaskOperator, sets: list[Pixels]) -> Box | None:
    """Expected storage box from the pixel sets: the rectangle of every pixel that
    lies in the bounds of all operands (intersect), of the first (subtract) or of any
    (union, xor)."""
    rects = [_bounds(s) for s in sets]
    if operator == "subtract":
        chosen = rects[0]
    elif operator == "intersect":
        if any(r is None for r in rects):
            return None
        cells = set.intersection(
            *({(x, y) for x in range(r[0], r[2]) for y in range(r[1], r[3])} for r in rects if r)
        )
        chosen = _bounds(cells)
    else:
        chosen = _bounds(set().union(*sets))
    return None if chosen is None else Box(*chosen)


def test_builder_folds_into_an_arbitrary_box_and_closes() -> None:
    # A box larger than the operands: intersect must clear what later operands miss.
    builder = MaskBuilder("intersect", Box(0, 0, 16, 16))
    builder.add(mask_of(HALF))
    builder.add(mask_of(EIGHT | {(10, 12)}))
    builder.add(Mask.empty())  # nothing in common with an empty operand
    assert builder.finish().is_empty
    builder = MaskBuilder("intersect", Box(0, 0, 16, 16))
    builder.add(mask_of(HALF))
    builder.add(mask_of(EIGHT | {(10, 12)}))
    result = builder.finish()
    assert pixels_of(result) == EIGHT and result.box == Box(0, 0, 16, 16)
    with pytest.raises(RuntimeError, match="finished"):
        builder.add(mask_of(ONE))
    with pytest.raises(RuntimeError, match="finished"):
        builder.finish()
    empty_builder = MaskBuilder("union", None)
    empty_builder.add(mask_of(ONE))  # nothing can be stored without a box
    assert empty_builder.finish().is_empty


def test_builder_and_combine_reject_misuse() -> None:
    with pytest.raises(ValueError, match="operator"):
        MaskBuilder("or", None)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="operator"):
        combined_box(True, [None], DIMS)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="box"):
        MaskBuilder("union", (0, 0, 1, 1))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="at least one"):
        MaskBuilder("union", None).finish()
    with pytest.raises(TypeError, match="Mask"):
        MaskBuilder("union", None).add(ONE)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="at least one"):
        combined_box("union", [], DIMS)
    with pytest.raises(TypeError, match="Box"):
        combined_box("union", [(0, 0, 1, 1)], DIMS)  # type: ignore[list-item]
    with pytest.raises(TypeError, match="Dimensions"):
        combined_box("union", [None], (16, 16))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="sequence"):
        combine_masks("union", mask_of(ONE), DIMS)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="sequence"):
        combine_masks("union", [mask_of(ONE), "x"], DIMS)  # type: ignore[list-item]


def test_results_are_immutable_masks() -> None:
    result = combine_masks("union", [mask_of(ONE), mask_of(EIGHT)], DIMS)
    with pytest.raises(ValueError, match="read-only"):
        result._bits[0, 0] = False
