"""Bounded binary morphology of canvas masks (MOANART.md section 8, ADR-027).

Both operators use the Chebyshev neighbourhood: the square of side ``2r + 1``
centred on the pixel, which is ``r`` repetitions of the 3 x 3 neighbourhood of
section 8. Masks live in canvas coordinates with a **transparent exterior**: a
pixel off the canvas never belongs to a mask, and nothing wraps around.

* :func:`dilate`: pixel ``p`` of the canvas is in the result when some pixel of the
  mask lies within Chebyshev distance ``r`` of ``p``. The result is stored over the
  mask's storage box grown by ``r`` per side and clipped to the canvas
  (:func:`moanart.core.coordinates.grown_box`), so the canvas clip happens before
  anything is allocated.
* :func:`erode`: pixel ``p`` is in the result when *every* pixel within Chebyshev
  distance ``r`` of ``p`` is in the mask. Pixels off the canvas count as outside,
  so a mask touching the canvas edge erodes from that edge too. The result is
  stored over the mask's own box.

The square is separable: each operator runs one pass per axis over a prefix sum of
the row or column (``int32``, at most 2048 + 33 per line), so the work is linear in
the box area whatever ``r``. One pass over a ``W x H`` box holds the source bits,
the prefix sums of ``(W + 2r + 1) x H`` (or ``W x (H + 2r + 1)``) entries, one
``int32`` window count per pixel for an erosion and the result bits;
:func:`moanart.core.morphology.morphology_bytes` (re-exported here) is the bound the
cost plan uses. Pure integer arithmetic: no floats, hashes or set order decide a
pixel.
"""

from __future__ import annotations

from typing import Final, Literal

import numpy as np
import numpy.typing as npt

from moanart.core.coordinates import Box, Dimensions, grown_box, require_int
from moanart.core.limits import MAX_MORPHOLOGY_RADIUS
from moanart.core.morphology import MORPHOLOGY_FIXED_BYTES, morphology_bytes
from moanart.geometry.algebra import _window
from moanart.geometry.mask import Bits, Mask

__all__ = [
    "MAX_MORPHOLOGY_RADIUS",
    "MORPHOLOGY_FIXED_BYTES",
    "dilate",
    "erode",
    "morphology_bytes",
]

_COUNT: Final = np.int32

Counts = npt.NDArray[np.int32]


def _check(mask: object, radius: object, dimensions: object) -> tuple[Mask, int, Dimensions]:
    if not isinstance(mask, Mask):
        raise TypeError("mask must be a Mask value")
    if not isinstance(dimensions, Dimensions):
        raise TypeError("dimensions must be a Dimensions value")
    checked = require_int(radius, "radius", minimum=1, maximum=MAX_MORPHOLOGY_RADIUS)
    return mask, checked, dimensions


def _window_counts(bits: Bits, radius: int, axis: Literal[0, 1]) -> tuple[Counts, Counts]:
    """``(high, low)`` prefix-sum views whose difference counts each window along ``axis``.

    For a line of ``n`` bits, the prefix ``P`` has ``n + 2r + 1`` entries with
    ``P[k] = sum(bits[: clamp(k - r, 0, n)])``; the window ``[i - r, i + r]`` (bits
    outside the line count as unset) holds ``P[i + 2r + 1] - P[i]`` set bits.
    """
    n = bits.shape[axis]
    shape = list(bits.shape)
    shape[axis] = n + 2 * radius + 1
    prefix = np.zeros(tuple(shape), dtype=_COUNT)
    body = [slice(None), slice(None)]
    body[axis] = slice(radius + 1, radius + 1 + n)
    view = prefix[tuple(body)]
    view[...] = bits  # accumulate in place: no temporary of the line sums
    np.cumsum(view, axis=axis, out=view)
    tail, last = [slice(None), slice(None)], [slice(None), slice(None)]
    tail[axis] = slice(radius + 1 + n, None)
    last[axis] = slice(radius + n, radius + n + 1)
    # Copy the last sums first: broadcasting from an overlapping view of ``prefix``
    # would make NumPy copy the whole padded tail.
    prefix[tuple(tail)] = prefix[tuple(last)].copy()
    high, low = [slice(None), slice(None)], [slice(None), slice(None)]
    high[axis] = slice(2 * radius + 1, 2 * radius + 1 + n)
    low[axis] = slice(0, n)
    return prefix[tuple(high)], prefix[tuple(low)]


def _dilate_axis(bits: Bits, radius: int, axis: Literal[0, 1]) -> Bits:
    high, low = _window_counts(bits, radius, axis)
    return np.not_equal(high, low)  # at least one set bit in the window


def _erode_axis(bits: Bits, radius: int, axis: Literal[0, 1]) -> Bits:
    high, low = _window_counts(bits, radius, axis)
    counts = np.subtract(high, low)
    return np.equal(counts, 2 * radius + 1)  # every bit of the window set


def _adopt(box: Box, bits: Bits) -> Mask:
    if not bits.any():
        return Mask.empty()
    return Mask._adopt(box, np.ascontiguousarray(bits))


def dilate(mask: Mask, radius: int, dimensions: Dimensions) -> Mask:
    """Chebyshev dilation of ``mask`` by ``radius`` (``1..MAX_MORPHOLOGY_RADIUS``).

    Raises ``ValidationError`` (``field: radius``, ``not_integer`` or
    ``out_of_range``) for another radius. The result is clipped to ``dimensions``.
    """
    mask, radius, dimensions = _check(mask, radius, dimensions)
    storage = mask.box
    part = None if storage is None else storage.clip_to(dimensions)
    box = grown_box(part, radius, dimensions)
    if storage is None or part is None or box is None:
        return Mask.empty()
    source = np.zeros((box.height, box.width), dtype=np.bool_)
    _window(source, box, part)[...] = _window(mask._bits, storage, part)
    rows = _dilate_axis(source, radius, 1)
    del source
    return _adopt(box, _dilate_axis(rows, radius, 0))


def erode(mask: Mask, radius: int, dimensions: Dimensions) -> Mask:
    """Chebyshev erosion of ``mask`` by ``radius``, with a transparent exterior.

    Same radius contract as :func:`dilate`. Pixels within ``radius`` of the canvas
    edge or of a pixel outside the mask are removed; the result is a subset of
    ``mask`` stored over its box (or empty).
    """
    mask, radius, dimensions = _check(mask, radius, dimensions)
    storage = mask.box
    part = None if storage is None else storage.clip_to(dimensions)
    if storage is None or part is None:
        return Mask.empty()
    rows = _erode_axis(_window(mask._bits, storage, part), radius, 1)
    return _adopt(part, _erode_axis(rows, radius, 0))
