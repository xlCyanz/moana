"""Periodic selection of mask pixels anchored on the canvas (MOANA.md section 10, ADR-025).

A *cell table* is a rectangular tuple of rows of booleans, ``cells[row][column]``,
1 to :data:`MAX_PATTERN_SIZE` cells per axis. Tiled over the canvas with its cell
``(0, 0)`` on the pixel ``origin``, the table selects pixel ``(x, y)`` when::

    cells[(y - origin.y) mod height][(x - origin.x) mod width]

``mod`` is the mathematical modulo (the result is in ``[0, n)`` also for negative
operands, Python's ``%`` and NumPy's ``remainder`` on integers), never C's truncated
remainder. So the phase depends only on canvas coordinates and on ``origin``: moving
``origin`` by a multiple of the period selects exactly the same pixels, and two masks
that tile the canvas with the same ``origin`` meet without seams.

:func:`select_periodic` keeps the pixels of a mask that the table selects. It works
on the mask's storage box only (the clipped geometry): the result has the same box,
one byte per pixel, plus the ``int64`` row and column indexes
(:data:`PATTERN_INDEX_BYTES` ``x (width + height)``) and one box-wide row per cell
row (at most ``64 x width`` bytes). Plain ``take`` copies, no buffered fancy
indexing. Pure integer arithmetic; no floats, hashes or set order decide a pixel.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

import numpy as np

from moana.core.coordinates import Point
from moana.core.dither import PATTERN_INDEX_BYTES
from moana.core.errors import ValidationError
from moana.geometry.mask import Mask

__all__ = ["MAX_PATTERN_SIZE", "PATTERN_INDEX_BYTES", "CellTable", "select_periodic"]

MAX_PATTERN_SIZE: Final = 64
"""Largest cell table side: patterns are small authored periods, not images."""

CellTable = tuple[tuple[bool, ...], ...]
"""Rectangular rows of booleans; ``True`` selects the pixel."""


def _invalid(message: str, reason: str) -> ValidationError:
    return ValidationError(message, context={"field": "cells", "reason": reason})


def _check_cells(cells: object) -> CellTable:
    """``cells`` as a validated rectangular table of 1 to 64 booleans per axis."""
    if isinstance(cells, str | bytes) or not isinstance(cells, Sequence):
        raise _invalid("cells must be a sequence of rows", "not_sequence")
    rows: list[tuple[bool, ...]] = []
    for row in cells:
        if isinstance(row, str | bytes) or not isinstance(row, Sequence):
            raise _invalid("every row of cells must be a sequence", "not_sequence")
        if any(type(cell) is not bool for cell in row):
            raise _invalid("cells must be booleans", "not_boolean")
        rows.append(tuple(row))
    height = len(rows)
    width = len(rows[0]) if rows else 0
    if not (1 <= height <= MAX_PATTERN_SIZE and 1 <= width <= MAX_PATTERN_SIZE):
        raise _invalid(f"cells must have 1 to {MAX_PATTERN_SIZE} rows and columns", "bad_size")
    if any(len(row) != width for row in rows):
        raise _invalid("cells must be rectangular", "not_rectangular")
    return tuple(rows)


def select_periodic(mask: Mask, cells: Sequence[Sequence[bool]], origin: Point) -> Mask:
    """Pixels of ``mask`` that ``cells``, tiled from ``origin``, selects.

    ``origin`` may lie anywhere, also off the canvas or at negative coordinates.
    Raises ``ValidationError`` (``field: cells``) for a table that is not a
    rectangular sequence of 1 to 64 boolean rows and columns.
    """
    if not isinstance(mask, Mask):
        raise TypeError("mask must be a Mask value")
    if not isinstance(origin, Point):
        raise TypeError("origin must be a Point value")
    table = np.array(_check_cells(cells), dtype=np.bool_)
    box = mask.box
    if box is None:
        return Mask.empty()
    height, width = table.shape
    rows = np.remainder(np.arange(box.y0, box.y1, dtype=np.int64) - origin.y, height)
    columns = np.remainder(np.arange(box.x0, box.x1, dtype=np.int64) - origin.x, width)
    periods = np.take(table, columns, axis=1)  # one canvas-wide row per cell row
    bits = np.take(periods, rows, axis=0)
    np.logical_and(bits, mask._bits, out=bits)
    if not bits.any():
        return Mask.empty()
    return Mask._adopt(box, np.ascontiguousarray(bits))
