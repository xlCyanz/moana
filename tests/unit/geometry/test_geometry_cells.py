"""Selection by a grid of cells anchored on the canvas (``select_cells``, ADR-030)."""

from __future__ import annotations

import pytest

from moanart.core.coordinates import Box, Dimensions, Point
from moanart.core.errors import ValidationError
from moanart.geometry import rasterize_ellipse, rasterize_rect, select_cells

CANVAS = Dimensions(20, 12)


def oracle(
    pixels: set[tuple[int, int]],
    cells: bytes,
    span: Box,
    scale: int,
    origin: tuple[int, int],
    value: int,
) -> set[tuple[int, int]]:
    def cell(x: int, y: int) -> int:
        cx = (x - origin[0]) // scale - span.x0
        cy = (y - origin[1]) // scale - span.y0
        return cells[cy * span.width + cx]

    return {(x, y) for x, y in pixels if cell(x, y) == value}


def test_selection_uses_floor_division_with_negative_cells() -> None:
    mask = rasterize_ellipse(Box(-3, -2, 15, 9), CANVAS)
    pixels = {(p.x, p.y) for p in mask.points()}
    for scale, origin in ((1, (0, 0)), (2, (1, 1)), (3, (-4, 5)), (8, (7, -9))):
        box = mask.box
        assert box is not None
        x0, y0 = (box.x0 - origin[0]) // scale, (box.y0 - origin[1]) // scale
        x1, y1 = (box.x1 - 1 - origin[0]) // scale + 1, (box.y1 - 1 - origin[1]) // scale + 1
        span = Box(x0 - 1, y0, x1, y1 + 2)  # a larger grid is fine
        cells = bytes((i * 7 + i // 3) % 3 for i in range(span.area))
        for value in range(3):
            selected = select_cells(mask, cells, span, scale, Point(*origin), value)
            got = {(p.x, p.y) for p in selected.points()}
            assert got == oracle(pixels, cells, span, scale, origin, value)
            assert selected.is_empty or selected.box == mask.box


def test_empty_mask_and_empty_selection() -> None:
    empty = rasterize_rect(Box(30, 30, 31, 31), CANVAS)
    assert select_cells(empty, b"\x00", Box(0, 0, 1, 1), 1, Point(0, 0), 0).is_empty
    one = rasterize_rect(Box(0, 0, 1, 1), CANVAS)
    assert select_cells(one, b"\x01", Box(0, 0, 1, 1), 1, Point(0, 0), 0).is_empty
    assert select_cells(one, b"\x01", Box(0, 0, 1, 1), 1, Point(0, 0), 1).count == 1


def test_grid_must_cover_the_mask_and_match_its_size() -> None:
    mask = rasterize_rect(Box(0, 0, 4, 4), CANVAS)
    for span in (Box(1, 0, 4, 4), Box(0, 1, 4, 4), Box(0, 0, 3, 4), Box(0, 0, 4, 3)):
        with pytest.raises(ValidationError) as raised:
            select_cells(mask, bytes(span.area), span, 1, Point(0, 0), 0)
        assert raised.value.context == {"field": "cells", "reason": "grid_too_small"}
    with pytest.raises(ValidationError) as raised:
        select_cells(mask, b"\x00", Box(0, 0, 4, 4), 1, Point(0, 0), 0)
    assert raised.value.context["reason"] == "size_mismatch"
    with pytest.raises(ValidationError):
        select_cells(mask, bytes(16), Box(0, 0, 4, 4), 9, Point(0, 0), 0)
    with pytest.raises(ValidationError):
        select_cells(mask, bytes(16), Box(0, 0, 4, 4), 1, Point(0, 0), 256)


def test_type_checks() -> None:
    mask = rasterize_rect(Box(0, 0, 1, 1), CANVAS)
    span = Box(0, 0, 1, 1)
    with pytest.raises(TypeError, match="mask"):
        select_cells(object(), b"\x00", span, 1, Point(0, 0), 0)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="span"):
        select_cells(mask, b"\x00", (0, 0, 1, 1), 1, Point(0, 0), 0)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="origin"):
        select_cells(mask, b"\x00", span, 1, (0, 0), 0)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="cells"):
        select_cells(mask, bytearray(1), span, 1, Point(0, 0), 0)  # type: ignore[arg-type]
