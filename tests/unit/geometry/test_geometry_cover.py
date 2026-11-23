"""MaskCover: which masks hold every pixel of some boxes (ADR-027).

Masks are built from raw bits; the oracle is a Python set of pixels per mask.
"""

from __future__ import annotations

import itertools
import tracemalloc
from collections.abc import Iterator

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from moanart.core.budget import Deadline
from moanart.core.coordinates import Box, Dimensions
from moanart.core.errors import BudgetExceeded, ValidationError
from moanart.core.limits import MAX_CLUSTER_EXCEPTIONS
from moanart.geometry import MAX_COVER_MASKS, Mask, MaskCover, cover_bytes
from moanart.geometry.mask import _restore

Pixels = frozenset[tuple[int, int]]


def mask_of(pixels: Pixels, box: Box | None = None) -> Mask:
    if not pixels:
        return Mask.empty()
    if box is None:
        xs, ys = [x for x, _ in pixels], [y for _, y in pixels]
        box = Box(min(xs), min(ys), max(xs) + 1, max(ys) + 1)
    bits = np.zeros((box.height, box.width), dtype=np.uint8)
    for x, y in pixels:
        bits[y - box.y0, x - box.x0] = 1
    return _restore(box, (box.height, box.width), bits.tobytes())


def box_pixels(box: Box) -> Pixels:
    return frozenset(itertools.product(range(box.x0, box.x1), range(box.y0, box.y1)))


def oracle(masks: list[Pixels], boxes: list[Box]) -> int:
    wanted = frozenset().union(*(box_pixels(box) for box in boxes))
    return sum(1 << i for i, pixels in enumerate(masks) if wanted <= pixels)


def test_common_answers_every_box_and_drops_off_canvas_pixels() -> None:
    dims = Dimensions(6, 4)
    left = frozenset(itertools.product(range(3), range(4)))
    everything = frozenset(itertools.product(range(6), range(4)))
    stored_off = mask_of(everything, Box(-2, -1, 8, 5))  # stored past the canvas edges
    cover = MaskCover.build([mask_of(left), Mask.empty(), stored_off], dims)
    assert cover.count == 3
    assert cover.common([Box(0, 0, 1, 1)]) == 0b101
    assert cover.common([Box(0, 0, 3, 4), Box(1, 1, 2, 2)]) == 0b101
    assert cover.common([Box(0, 0, 4, 1)]) == 0b100
    assert cover.common([Box(5, 3, 7, 4)]) == 0  # reaches off the canvas
    assert cover.common([Box(3, 0, 4, 1), Box(0, 0, 1, 1)]) == 0b100
    assert MaskCover.build([], dims).common([Box(0, 0, 1, 1)]) == 0


def test_capacity_matches_the_exception_limit() -> None:
    assert MAX_CLUSTER_EXCEPTIONS <= MAX_COVER_MASKS == 64
    dims = Dimensions(2, 2)
    dot = mask_of(frozenset({(1, 1)}))
    cover = MaskCover.build([dot] * MAX_COVER_MASKS, dims)
    assert cover.common([Box(1, 1, 2, 2)]) == (1 << 64) - 1
    with pytest.raises(ValidationError) as raised:
        MaskCover.build([dot] * (MAX_COVER_MASKS + 1), dims)
    assert raised.value.context["reason"] == "too_many_masks"


def test_masks_are_consumed_one_at_a_time() -> None:
    read: list[int] = []

    def stream() -> Iterator[Mask]:
        for i in range(3):
            read.append(i)
            yield mask_of(frozenset({(i, 0)}))

    cover = MaskCover.build(stream(), Dimensions(3, 1))
    assert read == [0, 1, 2]
    assert [cover.common([Box(i, 0, i + 1, 1)]) for i in range(3)] == [1, 2, 4]


def test_types_closed_constructor_and_deadline() -> None:
    dims = Dimensions(2, 2)
    with pytest.raises(TypeError):
        MaskCover()
    with pytest.raises(TypeError):
        MaskCover.build([object()], dims)  # type: ignore[list-item]  # invalid on purpose
    with pytest.raises(TypeError):
        MaskCover.build([], (2, 2))  # type: ignore[arg-type]  # invalid on purpose
    with pytest.raises(TypeError):
        MaskCover.build([], dims, deadline=1)  # type: ignore[arg-type]  # invalid on purpose
    with pytest.raises(TypeError):
        MaskCover.build([], dims).common([(0, 0, 1, 1)])  # type: ignore[list-item]  # invalid on purpose
    with pytest.raises(TypeError):
        cover_bytes((2, 2))  # type: ignore[arg-type]  # invalid on purpose
    ticks = itertools.count()
    expired = Deadline(1000, clock=lambda: float(next(ticks)))
    with pytest.raises(BudgetExceeded) as raised:
        MaskCover.build([Mask.empty()] * 3, dims, deadline=expired)
    assert raised.value.context["stage"] == "mask_cover"


def test_memory_is_the_cover_whatever_the_masks() -> None:
    dims = Dimensions(200, 150)
    full = mask_of(frozenset(itertools.product(range(200), range(150))))
    tracemalloc.start()
    try:
        MaskCover.build([full] * 8, dims)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert cover_bytes(dims) == 8 * 200 * 150
    assert peak <= cover_bytes(dims) + 4096


cell = st.tuples(st.integers(0, 5), st.integers(0, 4))


@settings(max_examples=100, deadline=None)
@given(
    masks=st.lists(st.frozensets(cell, max_size=20), max_size=5),
    boxes=st.lists(
        st.tuples(st.integers(-1, 5), st.integers(-1, 4), st.integers(1, 3), st.integers(1, 3)),
        min_size=1,
        max_size=3,
    ),
)
def test_common_matches_the_set_oracle(
    masks: list[Pixels], boxes: list[tuple[int, int, int, int]]
) -> None:
    dims = Dimensions(6, 5)
    shapes = [Box(x, y, x + w, y + h) for x, y, w, h in boxes]
    cover = MaskCover.build([mask_of(pixels) for pixels in masks], dims)
    assert cover.common(shapes) == oracle(masks, shapes)
