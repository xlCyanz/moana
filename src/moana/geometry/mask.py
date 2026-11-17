"""Immutable binary masks produced by the integer rasterisers (ADR-015).

A :class:`Mask` stores one byte per pixel of its :attr:`Mask.box`, the operation
bounds already clipped to the canvas, so its memory is exactly the mask term of the
``budget-v1`` estimator. The bit array is private, read-only and never shared:
:meth:`Mask.to_array` returns a copy for internal adapters (compositor, quality).
Equality and hashing compare the *set of pixels*: the storage box and the shape of
:meth:`Mask.to_array` are not part of the value. The hash derives from ``hash(bytes)``,
which varies between processes; it must never order or seed rendering (section 14).
Copies return the same object and pickling rebuilds a read-only mask after
validating the state.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Final, final

import numpy as np
import numpy.typing as npt

from moana.core.coordinates import Box, Point
from moana.core.errors import ValidationError

__all__ = ["Mask"]

Bits = npt.NDArray[np.bool_]
_NO_BITS: Final = (0, 0)


@final
class Mask:
    """Set of canvas pixels covered by a primitive; empty masks have no storage."""

    __slots__ = ("_bits", "_box")

    _box: Box | None
    _bits: Bits

    def __init__(self) -> None:
        """Direct construction is closed: masks come from ``moana.geometry`` functions."""
        raise TypeError("masks are produced by the moana.geometry rasterisers")

    @classmethod
    def _adopt(cls, box: Box, bits: Bits) -> Mask:
        """Wrap ``bits`` (shape ``box.height x box.width``) that nobody else references."""
        bits.flags.writeable = False
        mask = cls.__new__(cls)
        mask._box = box
        mask._bits = bits
        return mask

    @classmethod
    def empty(cls) -> Mask:
        """A mask without pixels or storage (geometry clipped away entirely)."""
        mask = cls.__new__(cls)
        mask._box = None
        mask._bits = np.zeros(_NO_BITS, dtype=np.bool_)
        mask._bits.flags.writeable = False
        return mask

    @property
    def box(self) -> Box | None:
        """Region the stored bits cover: the clipped operation bounds, or ``None``."""
        return self._box

    @property
    def count(self) -> int:
        """Number of pixels in the mask."""
        return int(np.count_nonzero(self._bits))

    @property
    def is_empty(self) -> bool:
        """Whether the mask contains no pixel."""
        return not bool(self._bits.any())

    @property
    def bounds(self) -> Box | None:
        """Tightest box holding every pixel of the mask, or ``None`` if empty."""
        if self._box is None or not self._bits.any():
            return None
        rows = np.flatnonzero(self._bits.any(axis=1))
        columns = np.flatnonzero(self._bits.any(axis=0))
        x0, y0 = self._box.x0, self._box.y0
        return Box(
            x0 + int(columns[0]),
            y0 + int(rows[0]),
            x0 + int(columns[-1]) + 1,
            y0 + int(rows[-1]) + 1,
        )

    def contains(self, point: Point) -> bool:
        """Whether ``point`` belongs to the mask; points off the storage box do not."""
        if not isinstance(point, Point):
            raise TypeError("point must be a Point value")
        if self._box is None or not self._box.contains(point):
            return False
        return bool(self._bits[point.y - self._box.y0, point.x - self._box.x0])

    def points(self) -> Iterator[Point]:
        """Pixels of the mask in row-major order (``y`` then ``x``)."""
        if self._box is None:
            return
        x0, y0 = self._box.x0, self._box.y0
        for row in range(self._box.height):
            for column in np.flatnonzero(self._bits[row]):
                yield Point(x0 + int(column), y0 + row)

    def to_array(self) -> Bits:
        """Independent writable copy of the bits over :attr:`box` (``(0, 0)`` if none)."""
        return self._bits.copy(order="C")

    def _trimmed(self) -> tuple[Box | None, bytes]:
        bounds = self.bounds
        if bounds is None or self._box is None:
            return None, b""
        x0, y0 = self._box.x0, self._box.y0
        window = self._bits[
            bounds.y0 - y0 : bounds.y1 - y0,
            bounds.x0 - x0 : bounds.x1 - x0,
        ]
        return bounds, window.tobytes()

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Mask):
            return NotImplemented
        return self._trimmed() == other._trimmed()

    def __hash__(self) -> int:
        return hash(self._trimmed())

    def __copy__(self) -> Mask:
        return self

    def __deepcopy__(self, memo: dict[int, object]) -> Mask:
        return self

    def __reduce__(self) -> tuple[object, tuple[Box | None, tuple[int, int], bytes]]:
        height, width = (int(n) for n in self._bits.shape)
        return _restore, (self._box, (height, width), self._bits.tobytes())

    def __repr__(self) -> str:
        return f"Mask(box={self._box!r}, count={self.count})"


def _invalid_state(reason: str) -> ValidationError:
    return ValidationError(
        "mask state is inconsistent", context={"field": "mask", "reason": reason}
    )


def _restore(box: object, shape: object, data: object) -> Mask:
    """Rebuild a pickled mask, validating box, shape and bytes before adopting them."""
    if box is not None and not isinstance(box, Box):
        raise _invalid_state("not_box")
    expected = _NO_BITS if box is None else (box.height, box.width)
    if type(shape) is not tuple or shape != expected:
        raise _invalid_state("shape_mismatch")
    if type(data) is not bytes or len(data) != expected[0] * expected[1]:
        raise _invalid_state("size_mismatch")
    if box is None:
        return Mask.empty()
    raw = np.frombuffer(data, dtype=np.uint8).reshape(expected)
    if bool((raw > 1).any()):
        raise _invalid_state("not_binary")
    return Mask._adopt(box, raw.astype(np.bool_))
