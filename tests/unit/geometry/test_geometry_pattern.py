"""Periodic selection anchored on the canvas (``select_periodic``, ADR-025)."""

from __future__ import annotations

import tracemalloc
from typing import Any

import pytest

from moana.core.coordinates import Box, Dimensions, Point
from moana.core.errors import ValidationError
from moana.geometry import (
    MAX_PATTERN_SIZE,
    PATTERN_INDEX_BYTES,
    rasterize_ellipse,
    rasterize_rect,
    select_periodic,
)

CANVAS = Dimensions(20, 12)
CHECKER = ((True, False), (False, True))


def oracle(box: Box, cells: Any, origin: tuple[int, int]) -> set[tuple[int, int]]:
    height, width = len(cells), len(cells[0])
    return {
        (x, y)
        for y in range(box.y0, box.y1)
        for x in range(box.x0, box.x1)
        if cells[(y - origin[1]) % height][(x - origin[0]) % width]
    }


def test_selection_follows_the_floor_modulo_with_negative_origins() -> None:
    cells = ((True, False, False), (False, False, True))  # 2 rows x 3 columns
    mask = rasterize_rect(Box(0, 0, 20, 12), CANVAS)
    for origin in ((0, 0), (-1, -1), (-7, 4), (5, -3), (-1_048_576, 1_048_576)):
        selected = select_periodic(mask, cells, Point(*origin))
        got = {(p.x, p.y) for p in selected.points()}
        assert got == oracle(Box(0, 0, 20, 12), cells, origin)
        assert selected.box == mask.box


def test_selection_never_leaves_the_mask() -> None:
    mask = rasterize_ellipse(Box(-3, -2, 15, 9), CANVAS)
    inside = {(p.x, p.y) for p in mask.points()}
    selected = select_periodic(mask, CHECKER, Point(1, 0))
    got = {(p.x, p.y) for p in selected.points()}
    assert got <= inside
    assert got == inside & oracle(Box(0, 0, 20, 12), CHECKER, (1, 0))


def test_empty_inputs_and_results_have_no_storage() -> None:
    empty = rasterize_rect(Box(30, 30, 31, 31), CANVAS)
    assert select_periodic(empty, CHECKER, Point(0, 0)).box is None
    one = rasterize_rect(Box(0, 0, 1, 1), CANVAS)
    assert select_periodic(one, CHECKER, Point(1, 0)).box is None  # cell (0, 1) is False
    assert select_periodic(one, ((True,),), Point(0, 0)).count == 1


@pytest.mark.parametrize(
    ("cells", "reason"),
    [
        ("ab", "not_sequence"),
        (5, "not_sequence"),
        ((b"ab",), "not_sequence"),
        ((7,), "not_sequence"),
        (((1, 0),), "not_boolean"),
        ((), "bad_size"),
        (((),), "bad_size"),
        (((True,) * (MAX_PATTERN_SIZE + 1),), "bad_size"),
        (((True, False), (True,)), "not_rectangular"),
    ],
)
def test_invalid_cell_tables_are_domain_errors(cells: Any, reason: str) -> None:
    mask = rasterize_rect(Box(0, 0, 2, 2), CANVAS)
    with pytest.raises(ValidationError) as raised:
        select_periodic(mask, cells, Point(0, 0))
    assert raised.value.context == {"field": "cells", "reason": reason}


def test_wrong_argument_types_are_rejected() -> None:
    mask = rasterize_rect(Box(0, 0, 2, 2), CANVAS)
    with pytest.raises(TypeError):
        select_periodic(None, CHECKER, Point(0, 0))  # type: ignore[arg-type]  # not a Mask
    with pytest.raises(TypeError):
        select_periodic(mask, CHECKER, (0, 0))  # type: ignore[arg-type]  # not a Point


def test_peak_memory_is_the_result_plus_indexes_and_period_rows() -> None:
    dimensions = Dimensions(512, 384)
    mask = rasterize_rect(Box(0, 0, 512, 384), dimensions)
    box = mask.box
    assert box is not None
    tracemalloc.start()
    try:
        select_periodic(mask, CHECKER, Point(-3, 1))
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    rows = len(CHECKER) * box.width  # one box-wide row per cell row
    assert peak <= box.area + PATTERN_INDEX_BYTES * (box.width + box.height) + rows + 4096
