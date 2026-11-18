"""Shared arithmetic of bounded binary morphology (MOANA.md section 8, ADR-027).

Pure values with no NumPy: :mod:`moana.geometry.morphology` (the operators) and the
cost plan (:mod:`moana.render.budget`, which imports no NumPy) read the memory bound
from here, so there is exactly one definition of it.
"""

from __future__ import annotations

from typing import Final

from moana.core.coordinates import Box

__all__ = [
    "COUNT_BYTES",
    "MORPHOLOGY_FIXED_BYTES",
    "UFUNC_BUFFER_ITEMS",
    "morphology_bytes",
]

COUNT_BYTES: Final = 4
"""Bytes of one prefix sum or window count (``int32``)."""
MORPHOLOGY_FIXED_BYTES: Final = 4096
"""Fixed overhead of one morphology call (array headers and views)."""
UFUNC_BUFFER_ITEMS: Final = 8192
"""Items of one NumPy iteration buffer (``NPY_BUFSIZE``).

Window counts subtract two strided views of the prefix sums; NumPy iterates them
through buffers of at most this many items per operand.
"""
_BUFFERED_OPERANDS: Final = 3


def morphology_bytes(box: Box | None, radius: int) -> int:
    """Upper bound of the bytes one dilation or erosion of ``radius`` holds over ``box``.

    ``box`` is the box the operator works on (the grown box of a dilation, the mask
    box of an erosion); ``None`` costs nothing. With ``P = (W + 2r + 1)·(H + 2r + 1)``:
    source and result bits (``2·area``), the prefix sums of either pass (``4·P``
    bounds both), one ``int32`` window count per pixel (``4·area``), the NumPy
    iteration buffers of the strided subtraction (``12·min(P, 8192)``: three
    ``int32`` operands of at most :data:`UFUNC_BUFFER_ITEMS` items) and
    :data:`MORPHOLOGY_FIXED_BYTES`.
    """
    if box is None:
        return 0
    side = 2 * radius + 1
    padded = (box.width + side) * (box.height + side)
    buffers = _BUFFERED_OPERANDS * COUNT_BYTES * min(padded, UFUNC_BUFFER_ITEMS)
    return (
        2 * box.area
        + COUNT_BYTES * padded
        + COUNT_BYTES * box.area
        + buffers
        + MORPHOLOGY_FIXED_BYTES
    )
