"""Bounded, iterative 4-connected flood fill over an RGBA snapshot (ADR-015).

The fill reads a *snapshot* :class:`~moana.core.canvas.Canvas` (the previous state
of the layer, MOANA.md section 6) and returns a :class:`Mask`; it never writes the
canvas. Colours match by exact RGBA equality; the canvas already stores every
zero-alpha pixel as ``(0, 0, 0, 0)``, so transparent pixels match each other.

Work and memory are checked against :class:`RenderLimits` before anything is
copied: at most ``A = width * height`` pixel visits (each pixel is classified once
and claimed at most once) and :data:`FLOOD_FILL_BYTES_PER_PIXEL` bytes per canvas
pixel. The algorithm is a scanline fill whose stack holds one ``int32`` per pending
run; no Python recursion, no per-pixel Python objects.
"""

from __future__ import annotations

from array import array
from typing import Final

import numpy as np

from moana.core.budget import RenderLimits
from moana.core.canvas import Canvas
from moana.core.coordinates import Box, Point
from moana.core.errors import BudgetExceeded, ErrorDetail
from moana.geometry.mask import Mask

__all__ = ["FLOOD_FILL_BYTES_PER_PIXEL", "flood_fill", "flood_fill_cost"]

# Peak working set per canvas pixel: 4 (snapshot copy) + 1 (colour match) while
# classifying, then 1 (match) + 1 (filled mask) + at most ~2.25 (run stack).
FLOOD_FILL_BYTES_PER_PIXEL: Final = 8


def flood_fill_cost(snapshot: Canvas) -> tuple[int, int]:
    """Upper bound ``(pixel_visits, buffer_bytes)`` of a fill on ``snapshot``."""
    area = snapshot.dimensions.area
    return area, FLOOD_FILL_BYTES_PER_PIXEL * area


def _check_budget(snapshot: Canvas, limits: RenderLimits) -> None:
    visits, size = flood_fill_cost(snapshot)
    details = [
        ErrorDetail(
            BudgetExceeded.code,
            f"flood fill {resource} exceed the request budget",
            context={"resource": resource, "limit": limit, "estimated": estimated},
        )
        for resource, limit, estimated in (
            ("pixel_visits", limits.max_pixel_visits, visits),
            ("buffer_bytes", limits.max_buffer_bytes, size),
        )
        if estimated > limit
    ]
    if details:
        raise BudgetExceeded(
            "flood fill exceeds the request budget",
            context=dict(details[0].context),
            details=details,
        )


def _match_bytes(snapshot: Canvas, seed: Point) -> bytearray:
    """One byte per pixel: 1 where the RGBA equals the seed's, written in place."""
    height, width = snapshot.height, snapshot.width
    pixels = snapshot.to_array()  # independent C-contiguous (h, w, 4) uint8 copy
    packed = pixels.view(np.uint32).reshape(height, width)
    match = bytearray(height * width)
    target = np.frombuffer(match, dtype=np.bool_).reshape(height, width)
    np.equal(packed, packed[seed.y, seed.x], out=target)
    return match


def flood_fill(snapshot: Canvas, seed: Point, *, limits: RenderLimits) -> Mask:
    """Pixels 4-connected to ``seed`` with exactly the seed's RGBA.

    Raises :class:`BudgetExceeded` (``pixel_visits``, ``buffer_bytes``) before any
    copy when the worst case exceeds ``limits``. A seed off the canvas yields an
    empty mask, like any other clipped geometry. ``snapshot`` is never modified.
    """
    if not isinstance(snapshot, Canvas):
        raise TypeError("snapshot must be a Canvas")
    if not isinstance(seed, Point):
        raise TypeError("seed must be a Point value")
    if not isinstance(limits, RenderLimits):
        raise TypeError("limits must be a RenderLimits value")
    _check_budget(snapshot, limits)
    canvas = Box.from_dimensions(snapshot.dimensions)
    if not canvas.contains(seed):
        return Mask.empty()
    width = snapshot.width
    match = _match_bytes(snapshot, seed)
    filled = _scanline_fill(match, width, seed.y * width + seed.x)
    bits = np.frombuffer(filled, dtype=np.bool_).reshape(snapshot.height, width)
    return Mask._adopt(canvas, bits)


def _scanline_fill(match: bytearray, width: int, seed: int) -> bytearray:
    """Claim the maximal match runs connected to flat index ``seed``.

    Runs are claimed (marked in ``filled``) when pushed, so each run enters the stack
    once and the stack never exceeds the number of runs (``<= (width + 1) // 2`` per
    row). Run ends are found with ``bytearray.find`` at C speed.
    """
    size = len(match)
    filled = bytearray(size)
    stack = array("i")
    _claim(match, filled, stack, seed, width)
    while stack:
        start = stack.pop()
        row = start - start % width
        end = _run_end(match, start, row + width)
        for neighbour in (row - width, row + width):
            if 0 <= neighbour < size:
                _scan(match, filled, stack, neighbour + start - row, neighbour + end - row, width)
    return filled


def _run_end(match: bytearray, index: int, row_end: int) -> int:
    end = match.find(0, index, row_end)
    return row_end if end < 0 else end


def _claim(match: bytearray, filled: bytearray, stack: array[int], index: int, width: int) -> int:
    """Mark the whole run holding ``index``, push its start and return its end."""
    row = index - index % width
    gap = match.rfind(0, row, index)
    start = row if gap < 0 else gap + 1
    end = _run_end(match, index, row + width)
    filled[start:end] = b"\x01" * (end - start)
    stack.append(start)
    return end


def _scan(
    match: bytearray, filled: bytearray, stack: array[int], a: int, b: int, width: int
) -> None:
    """Claim every unclaimed match run overlapping columns ``[a, b)`` of one row."""
    index = a
    while True:
        index = match.find(1, index, b)
        if index < 0:
            return
        if filled[index]:
            # A claimed run is a whole match run: skip to its end within [a, b).
            index = filled.find(0, index, b)
            if index < 0:
                return
            continue
        index = _claim(match, filled, stack, index, width)
