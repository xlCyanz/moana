"""Which of a few masks cover each canvas pixel (MOANART.md section 19, ADR-027).

A :class:`MaskCover` folds up to :data:`MAX_COVER_MASKS` masks into one ``uint64``
per canvas pixel: bit ``i`` is set when mask ``i`` (in the order given) holds the
pixel. :meth:`MaskCover.common` then answers "which masks hold *every* pixel of
these boxes" with one vectorised reduction per box, so checking many findings
against many regions costs the pixels of the findings, not findings x regions.

The masks are consumed one at a time from an iterable and never retained: the
cover holds :func:`cover_bytes` (``8·area``) whatever the masks are. Building it
visits each mask's clipped box once, without temporaries. Pixels off the canvas
belong to no mask.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Final, final

import numpy as np
import numpy.typing as npt

from moanart.core.budget import Deadline
from moanart.core.coordinates import Box, Dimensions
from moanart.core.errors import ValidationError
from moanart.geometry.algebra import _window
from moanart.geometry.mask import Mask

__all__ = ["COVER_BYTES_PER_PIXEL", "MAX_COVER_MASKS", "MaskCover", "cover_bytes"]

MAX_COVER_MASKS: Final = 64
"""Masks one cover can hold: the bits of one ``uint64`` per pixel."""
COVER_BYTES_PER_PIXEL: Final = 8

Cover = npt.NDArray[np.uint64]


def cover_bytes(dimensions: Dimensions) -> int:
    """Bytes a :class:`MaskCover` of ``dimensions`` holds: ``8·area``."""
    if not isinstance(dimensions, Dimensions):
        raise TypeError("dimensions must be a Dimensions value")
    return COVER_BYTES_PER_PIXEL * dimensions.area


@final
class MaskCover:
    """Immutable per-pixel bitset of the masks that hold each canvas pixel."""

    __slots__ = ("_bits", "_count", "_dimensions")

    _bits: Cover
    _count: int
    _dimensions: Dimensions

    def __init__(self) -> None:
        """Direct construction is closed: use :meth:`build`."""
        raise TypeError("mask covers are produced by MaskCover.build")

    @classmethod
    def build(
        cls,
        masks: Iterable[Mask],
        dimensions: Dimensions,
        *,
        deadline: Deadline | None = None,
    ) -> MaskCover:
        """Fold ``masks`` (at most :data:`MAX_COVER_MASKS`, in order) into a cover.

        Each mask is read once and dropped. More masks raise ``ValidationError``
        (``field: masks``, ``too_many_masks``) before the extra one is used; the
        ``deadline`` is checked before each mask.
        """
        if not isinstance(dimensions, Dimensions):
            raise TypeError("dimensions must be a Dimensions value")
        if deadline is not None and not isinstance(deadline, Deadline):
            raise TypeError("deadline must be a Deadline or None")
        bits: Cover = np.zeros((dimensions.height, dimensions.width), dtype=np.uint64)
        count = 0
        for mask in masks:
            if count == MAX_COVER_MASKS:
                raise ValidationError(
                    "too many masks for one cover",
                    context={"field": "masks", "reason": "too_many_masks"},
                )
            if not isinstance(mask, Mask):
                raise TypeError("masks must be Mask values")
            if deadline is not None:
                deadline.checkpoint("mask_cover")
            _add(bits, mask, count, dimensions)
            count += 1
        bits.flags.writeable = False
        cover = cls.__new__(cls)
        cover._bits, cover._count, cover._dimensions = bits, count, dimensions
        return cover

    @property
    def count(self) -> int:
        """Number of masks folded into the cover."""
        return self._count

    def common(self, boxes: Sequence[Box]) -> int:
        """Bitset of the masks holding every pixel of every box in ``boxes``.

        Bit ``i`` stands for the ``i``-th mask given to :meth:`build`. A box reaching
        off the canvas holds pixels of no mask, so the result is then ``0``.
        """
        result = (1 << self._count) - 1
        for box in boxes:
            if not isinstance(box, Box):
                raise TypeError("boxes must be Box values")
            if result == 0:
                break
            if box.clip_to(self._dimensions) != box:
                return 0
            window = self._bits[box.y0 : box.y1, box.x0 : box.x1]
            result &= int(np.bitwise_and.reduce(window, axis=None))
        return result


def _add(bits: Cover, mask: Mask, index: int, dimensions: Dimensions) -> None:
    """Set bit ``index`` of ``bits`` on every canvas pixel of ``mask``, in place."""
    storage = mask.box
    part = None if storage is None else storage.clip_to(dimensions)
    if storage is None or part is None:
        return
    target = bits[part.y0 : part.y1, part.x0 : part.x1]  # the canvas starts at (0, 0)
    np.bitwise_or(
        target, np.uint64(1 << index), out=target, where=_window(mask._bits, storage, part)
    )
