"""Pixel-perfect transformations of pixel sets (MOANART.md section 6, ADR-016).

Transformations act on pixel *indices*, never on geometric corners: a pixel is an
integer point and the pivot is a pixel. A :class:`Transform` applies, in this fixed
order and relative to its ``pivot`` ``c``:

1. ``mirror``: horizontal mirror about the pivot column, ``(x, y) -> (-x, y)``;
2. ``rotation``: 0/90/180/270 degrees clockwise on screen (``y`` grows downwards),
   one quarter turn being ``(x, y) -> (-y, x)``;
3. ``scale``: integer nearest-neighbour scale ``k``; index ``q`` becomes the
   ``k x k`` block ``[k q, k q + k)``;
4. ``offset``: explicit integer translation ``t``.

So pixel ``p`` maps to the block whose top-left pixel is ``k R (p - c) + c + t``,
where ``R`` is the mirror/rotation matrix. The pivot pixel stays fixed when ``k = 1``
and ``t = 0``; a vertical mirror is ``mirror`` plus a 180 degree rotation. Boxes are
transformed as pixel sets, so their image is the box of the transformed pixels.

Masks are produced by inverse gathering over the output box clipped to the canvas:
each output row and column maps back to one source column or row, so the work and
memory are bounded by the clipped output plus one zero-padded copy of the source
storage.
Arbitrary rotations and fractional scales are rejected (they fall outside the strict
profile and no other profile implements them).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
import numpy.typing as npt

from moanart.core.coordinates import (
    MAX_COORDINATE,
    MAX_DIMENSION,
    Box,
    Dimensions,
    Point,
    require_int,
)
from moanart.core.errors import ValidationError
from moanart.geometry.mask import Mask

__all__ = ["MAX_SCALE", "QUARTER_TURNS", "Transform", "transform_box", "transform_mask"]

MAX_SCALE: Final = MAX_DIMENSION
"""Largest scale factor: one pixel scaled by it already covers the widest canvas."""

QUARTER_TURNS: Final = (0, 90, 180, 270)
"""Admitted clockwise rotations in degrees; anything else is not pixel-perfect."""

_ORIGIN: Final = Point(0, 0)

# 2x2 integer matrix ((a, b), (c, d)) acting as (x, y) -> (a x + b y, c x + d y).
_Matrix = tuple[int, int, int, int]
_IDENTITY: Final[_Matrix] = (1, 0, 0, 1)
_MIRROR: Final[_Matrix] = (-1, 0, 0, 1)
_QUARTER: Final[_Matrix] = (0, -1, 1, 0)

_Indices = npt.NDArray[np.int64]


def _multiply(left: _Matrix, right: _Matrix) -> _Matrix:
    a, b, c, d = left
    e, f, g, h = right
    return (a * e + b * g, a * f + b * h, c * e + d * g, c * f + d * h)


def _invalid(field_name: str, reason: str, message: str) -> ValidationError:
    return ValidationError(message, context={"field": field_name, "reason": reason})


@dataclass(frozen=True, slots=True)
class Transform:
    """Mirror, quarter-turn rotation, integer scale and translation about a pivot pixel.

    Equality is structural: two transforms describing the same mapping with different
    fields (for example any pivot of an identity) are not ``==``; use
    :attr:`is_identity` or compare images instead.
    """

    pivot: Point = _ORIGIN
    mirror: bool = False
    rotation: int = 0
    scale: int = 1
    offset: Point = _ORIGIN

    def __post_init__(self) -> None:
        for name in ("pivot", "offset"):
            if not isinstance(getattr(self, name), Point):
                raise TypeError(f"{name} must be a Point value")
        if type(self.mirror) is not bool:
            raise _invalid("mirror", "not_boolean", "mirror must be a boolean")
        if type(self.rotation) is not int:
            raise ValidationError(
                "rotation must be an integer",
                context={
                    "field": "rotation",
                    "reason": "not_integer",
                    "value_type": type(self.rotation).__name__,
                },
            )
        if self.rotation % 90 != 0:
            raise _invalid(
                "rotation",
                "arbitrary_rotation",
                "only rotations by quarter turns are pixel-perfect",
            )
        if self.rotation not in QUARTER_TURNS:
            raise ValidationError(
                "rotation must be 0, 90, 180 or 270",
                context={"field": "rotation", "reason": "out_of_range", "allowed": QUARTER_TURNS},
            )
        require_int(self.scale, "scale", minimum=1, maximum=MAX_SCALE)

    @property
    def _matrix(self) -> _Matrix:
        """The mirror-then-rotation matrix ``R`` as ``(a, b, c, d)`` (internal)."""
        result = _MIRROR if self.mirror else _IDENTITY
        for _ in range(self.rotation // 90):
            result = _multiply(_QUARTER, result)
        return result

    @property
    def is_identity(self) -> bool:
        """Whether every pixel maps to itself."""
        return not self.mirror and self.rotation == 0 and self.scale == 1 and self.offset == _ORIGIN

    def inverse(self) -> Transform:
        """The transform undoing this one; only unscaled transforms are invertible.

        The inverse pivots on ``pivot + offset`` and translates by ``-offset``. A scaled
        transform, or one whose ``pivot + offset`` leaves the coordinate range, raises
        ``ValidationError`` with reason ``not_invertible``.
        """
        if self.scale != 1:
            raise _invalid("scale", "not_invertible", "a scaled transform has no inverse")
        x, y = self.pivot.x + self.offset.x, self.pivot.y + self.offset.y
        if max(abs(x), abs(y)) > MAX_COORDINATE:
            raise _invalid("pivot", "not_invertible", "the inverse pivot is out of range")
        rotation = self.rotation if self.mirror else (360 - self.rotation) % 360
        return Transform(
            pivot=Point(x, y),
            mirror=self.mirror,
            rotation=rotation,
            offset=Point(-self.offset.x, -self.offset.y),
        )

    def _image_corners(self, box: Box) -> tuple[int, int, int, int]:
        """Half-open bounds of the pixel set ``box`` once transformed (Python ints)."""
        a, b, c, d = self._matrix
        k, cx, cy = self.scale, self.pivot.x, self.pivot.y
        xs = (box.x0 - cx, box.x1 - 1 - cx)
        ys = (box.y0 - cy, box.y1 - 1 - cy)
        qx = [a * x + b * y for x in xs for y in ys]
        qy = [c * x + d * y for x in xs for y in ys]
        ox, oy = cx + self.offset.x, cy + self.offset.y
        return (
            k * min(qx) + ox,
            k * min(qy) + oy,
            k * max(qx) + k + ox,
            k * max(qy) + k + oy,
        )


def _require(value: object, kind: type, name: str) -> None:
    if not isinstance(value, kind):
        raise TypeError(f"{name} must be a {kind.__name__} value")


def transform_box(box: Box, transform: Transform) -> Box:
    """Box of the transformed pixels of ``box``; ``ValidationError`` if out of range."""
    _require(box, Box, "box")
    _require(transform, Transform, "transform")
    return Box(*transform._image_corners(box))


def _source_indices(
    output: _Indices, *, origin: int, scale: int, factor: int, pivot: int, start: int, size: int
) -> _Indices:
    """Source index for each output coordinate, or ``size`` (zero padding) if outside.

    ``q = (output - origin) // scale`` undoes the translation and the scale; the source
    coordinate is ``factor * q + pivot`` (``factor`` is the non-zero entry of the
    transposed matrix, so ``R^-1 = R^T`` picks one axis).
    """
    source = factor * ((output - origin) // scale) + pivot - start
    return np.where((source >= 0) & (source < size), source, size)


def transform_mask(mask: Mask, transform: Transform, dimensions: Dimensions) -> Mask:
    """Image of ``mask`` under ``transform``, clipped to the canvas without wraparound."""
    _require(mask, Mask, "mask")
    _require(transform, Transform, "transform")
    _require(dimensions, Dimensions, "dimensions")
    bounds, storage = mask.bounds, mask.box
    if bounds is None or storage is None:
        return Mask.empty()
    x0, y0, x1, y1 = transform._image_corners(bounds)
    ox0, oy0 = max(x0, 0), max(y0, 0)
    ox1, oy1 = min(x1, dimensions.width), min(y1, dimensions.height)
    if ox0 >= ox1 or oy0 >= oy1:
        return Mask.empty()
    out = Box(ox0, oy0, ox1, oy1)

    height, width = storage.height, storage.width
    padded = np.zeros((height + 1, width + 1), dtype=np.bool_)
    padded[:height, :width] = mask._bits  # read-only source; the only copy is ``padded``

    a, b, c, d = transform._matrix
    k, cx, cy = transform.scale, transform.pivot.x, transform.pivot.y
    origin_x, origin_y = cx + transform.offset.x, cy + transform.offset.y
    columns = np.arange(ox0, ox1, dtype=np.int64)
    rows = np.arange(oy0, oy1, dtype=np.int64)
    # R^-1 = R^T: source x = a qx + c qy, source y = b qx + d qy.
    if a != 0:  # axes kept: source x from output columns, source y from output rows
        src_x = _source_indices(
            columns, origin=origin_x, scale=k, factor=a, pivot=cx, start=storage.x0, size=width
        )
        src_y = _source_indices(
            rows, origin=origin_y, scale=k, factor=d, pivot=cy, start=storage.y0, size=height
        )
        bits = padded[np.ix_(src_y, src_x)]
    else:  # axes swapped: source x from output rows, source y from output columns
        src_x = _source_indices(
            rows, origin=origin_y, scale=k, factor=c, pivot=cx, start=storage.x0, size=width
        )
        src_y = _source_indices(
            columns, origin=origin_x, scale=k, factor=b, pivot=cy, start=storage.y0, size=height
        )
        bits = padded.T[np.ix_(src_x, src_y)]
    if not bits.any():  # the image box is visible but every set pixel fell off the canvas
        return Mask.empty()
    return Mask._adopt(out, np.ascontiguousarray(bits))
