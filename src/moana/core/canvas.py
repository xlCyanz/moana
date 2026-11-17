"""Owned RGBA canvas buffer (MOANA.md section 5, ADR-013).

The buffer is a C-contiguous ``uint8`` NumPy array of shape ``(height, width, 4)``
holding straight (non-premultiplied) sRGB-encoded RGBA, indexed ``array[y, x, c]``.
:class:`Canvas` owns it exclusively: arrays never cross the boundary by reference.
Imports copy, exports copy, and every pixel whose alpha is zero is stored as
``(0, 0, 0, 0)``.

Buffers are reserved only after checking the request budget (:class:`RenderLimits`,
ADR-012): the canvas bytes and the host geometry limits are verified before NumPy
allocates anything, with the same ``BudgetExceeded`` resources as the cost plan.

This module is the NumPy adapter of ``core``; ``import moana.core`` does not load it.
"""

from __future__ import annotations

import hashlib
from typing import Final

import numpy as np
import numpy.typing as npt

from moana.core.budget import RenderLimits
from moana.core.coordinates import MAX_DIMENSION, MIN_DIMENSION, Dimensions, Point, require_int
from moana.core.errors import BudgetExceeded, ErrorDetail, ValidationError

__all__ = ["CHANNELS", "RGBA", "Canvas", "check_canvas_budget"]

CHANNELS: Final = 4
RGBA = tuple[int, int, int, int]
"""A straight RGBA colour with each channel in ``0..255``."""

_TRANSPARENT: Final[RGBA] = (0, 0, 0, 0)


def check_canvas_budget(dimensions: Dimensions, limits: RenderLimits) -> None:
    """Raise :class:`BudgetExceeded` unless a canvas of ``dimensions`` fits ``limits``.

    Checks the host geometry limits and ``4 * width * height`` buffer bytes, before
    any allocation. Resources match :func:`moana.render.plan_budget`.
    """
    geometry = limits.geometry
    details: list[ErrorDetail] = []

    def exceeded(resource: str, limit: int, estimated: int) -> None:
        details.append(
            ErrorDetail(
                BudgetExceeded.code,
                f"canvas {resource} exceed the request budget",
                context={"resource": resource, "limit": limit, "estimated": estimated},
            )
        )

    for value in (dimensions.width, dimensions.height):
        if value > geometry.max_dimension:
            exceeded("canvas_dimension", geometry.max_dimension, value)
    if dimensions.area > geometry.max_area:
        exceeded("canvas_area", geometry.max_area, dimensions.area)
    size = CHANNELS * dimensions.area
    if size > limits.max_buffer_bytes:
        exceeded("buffer_bytes", limits.max_buffer_bytes, size)
    if details:
        raise BudgetExceeded(
            "canvas exceeds the request budget",
            context=dict(details[0].context),
            details=details,
        )


def _normalize_transparent(pixels: npt.NDArray[np.uint8]) -> None:
    """Set RGB to zero wherever alpha is zero, in place.

    ``copyto`` with a broadcast ``where`` mask needs only ``A`` bytes; boolean
    indexing would materialise int64 indices (up to ``16 * A`` bytes).
    """
    np.copyto(pixels, np.uint8(0), where=pixels[:, :, 3:4] == 0)


def _require_point(point: object) -> Point:
    if not isinstance(point, Point):
        raise TypeError("point must be a Point value")
    return point


def _check_rgba(value: object) -> RGBA:
    if type(value) is not tuple or len(value) != CHANNELS:
        raise ValidationError(
            "color must be a tuple of four channels",
            context={"field": "rgba", "reason": "not_rgba_tuple"},
        )
    channels = tuple(
        require_int(channel, name, minimum=0, maximum=255)
        for name, channel in zip(("r", "g", "b", "a"), value, strict=True)
    )
    r, g, b, a = channels
    return _TRANSPARENT if a == 0 else (r, g, b, a)


class Canvas:
    """Mutable RGBA canvas that exclusively owns its pixel buffer."""

    __slots__ = ("_dimensions", "_pixels")
    __hash__ = None  # type: ignore[assignment]  # mutable value: equality only

    _dimensions: Dimensions
    _pixels: npt.NDArray[np.uint8]

    def __init__(self) -> None:
        """Direct construction is closed: use :meth:`blank` or :meth:`from_array`."""
        raise TypeError("use Canvas.blank or Canvas.from_array")

    @classmethod
    def _adopt(cls, dimensions: Dimensions, pixels: npt.NDArray[np.uint8]) -> Canvas:
        """Wrap a buffer this module just created and nobody else references."""
        canvas = cls.__new__(cls)
        canvas._dimensions = dimensions
        canvas._pixels = pixels
        return canvas

    @classmethod
    def blank(cls, dimensions: Dimensions, *, limits: RenderLimits) -> Canvas:
        """A fully transparent canvas, allocated only after the budget check."""
        if not isinstance(dimensions, Dimensions):
            raise TypeError("dimensions must be a Dimensions value")
        check_canvas_budget(dimensions, limits)
        pixels = np.zeros((dimensions.height, dimensions.width, CHANNELS), dtype=np.uint8)
        return cls._adopt(dimensions, pixels)

    @classmethod
    def from_array(cls, array: object, *, limits: RenderLimits) -> Canvas:
        """Copy an ``(height, width, 4)`` ``uint8`` array; zero-alpha pixels normalised.

        Shape and dtype are checked before copying; the caller's array is never
        retained or modified.
        """
        if type(array) is not np.ndarray:  # subclasses (masked arrays) could drop data
            raise ValidationError(
                "canvas source must be a plain NumPy array",
                context={"field": "array", "reason": "not_ndarray"},
            )
        if array.dtype != np.uint8:
            raise ValidationError(
                "canvas array must have dtype uint8",
                context={"field": "array", "reason": "wrong_dtype", "dtype": str(array.dtype)},
            )
        if array.ndim != 3 or array.shape[2] != CHANNELS:
            raise ValidationError(
                "canvas array must have shape (height, width, 4)",
                context={
                    "field": "array",
                    "reason": "wrong_shape",
                    "shape": tuple(int(n) for n in array.shape),
                },
            )
        height, width = int(array.shape[0]), int(array.shape[1])
        for name, value in (("width", width), ("height", height)):
            require_int(value, name, minimum=MIN_DIMENSION, maximum=MAX_DIMENSION)
        dimensions = Dimensions(width, height)
        check_canvas_budget(dimensions, limits)
        pixels = np.array(array, dtype=np.uint8, order="C", copy=True)
        _normalize_transparent(pixels)
        return cls._adopt(dimensions, pixels)

    @property
    def dimensions(self) -> Dimensions:
        """Canvas size."""
        return self._dimensions

    @property
    def width(self) -> int:
        """Number of columns."""
        return self._dimensions.width

    @property
    def height(self) -> int:
        """Number of rows."""
        return self._dimensions.height

    def get_pixel(self, point: Point) -> RGBA:
        """RGBA at ``point``; :class:`OutOfBoundsError` outside, never wrapping."""
        self._dimensions.check_pixel(_require_point(point))
        r, g, b, a = (int(channel) for channel in self._pixels[point.y, point.x])
        return (r, g, b, a)

    def set_pixel(self, point: Point, rgba: RGBA) -> None:
        """Write ``rgba`` at ``point``; zero alpha is stored as ``(0, 0, 0, 0)``."""
        self._dimensions.check_pixel(_require_point(point))
        self._pixels[point.y, point.x] = _check_rgba(rgba)

    def to_array(self) -> npt.NDArray[np.uint8]:
        """An independent, writable, C-contiguous copy of the pixels."""
        return self._pixels.copy(order="C")

    def to_bytes(self) -> bytes:
        """Row-major RGBA bytes (``height * width * 4``)."""
        return self._pixels.tobytes(order="C")

    def copy(self) -> Canvas:
        """An independent canvas with the same pixels."""
        return Canvas._adopt(self._dimensions, self._pixels.copy(order="C"))

    def __copy__(self) -> Canvas:
        return self.copy()

    def __deepcopy__(self, memo: dict[int, object]) -> Canvas:
        return self.copy()

    def visual_digest(self) -> str:
        """``sha256:<hex>`` of width and height (uint32 big-endian) + RGBA (section 14)."""
        digest = hashlib.sha256(self.width.to_bytes(4, "big") + self.height.to_bytes(4, "big"))
        digest.update(self._pixels.data)  # C-contiguous: hashed without a copy
        return "sha256:" + digest.hexdigest()

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Canvas):
            return NotImplemented
        return self._dimensions == other._dimensions and bool(
            np.array_equal(self._pixels, other._pixels)
        )

    def __repr__(self) -> str:
        return f"Canvas(width={self.width}, height={self.height})"
