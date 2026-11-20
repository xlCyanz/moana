"""Binary set algebra of canvas masks (MOANA.md section 11, ADR-022).

Masks are sets of canvas pixels, so the four operators are set operations:

* ``union``: pixels in at least one operand;
* ``intersect``: pixels in every operand;
* ``subtract``: pixels of the first operand in none of the others;
* ``xor``: pixels in an odd number of operands (n-ary parity).

``union``, ``intersect`` and ``xor`` are associative and commutative; ``subtract`` is
neither (``a - b - c == a - (b | c)``). Every result is clipped to the canvas, the
empty mask is the identity of ``union``/``xor``/``subtract`` and absorbs
``intersect``, and an empty result has no storage.

:func:`combined_box` computes the storage box of a result from the operand boxes
alone (pure arithmetic, shared with the cost plan through
:func:`moana.core.coordinates.combined_box`), so a caller can budget before
rasterising. A
:class:`MaskBuilder` folds operands one at a time into a single buffer of that box,
in place and without temporaries, so evaluating a node never holds more than its own
buffer plus the operand being folded.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final, Literal, get_args

import numpy as np

from moana.core.coordinates import Box, Dimensions
from moana.core.coordinates import combined_box as _core_combined_box
from moana.geometry.mask import Bits, Mask

__all__ = ["MASK_OPERATORS", "MaskBuilder", "MaskOperator", "combine_masks", "combined_box"]

MaskOperator = Literal["union", "intersect", "subtract", "xor"]
MASK_OPERATORS: Final[tuple[MaskOperator, ...]] = get_args(MaskOperator)
"""The binary operators, in specification order."""


def _check_operator(operator: object) -> MaskOperator:
    for known in MASK_OPERATORS:
        if operator == known and type(operator) is str:
            return known
    raise ValueError("operator must be union, intersect, subtract or xor")


def _check_dimensions(dimensions: object) -> Dimensions:
    if not isinstance(dimensions, Dimensions):
        raise TypeError("dimensions must be a Dimensions value")
    return dimensions


def combined_box(
    operator: MaskOperator, boxes: Sequence[Box | None], dimensions: Dimensions
) -> Box | None:
    """Storage box of ``operator`` over operands stored in ``boxes``, clipped to the canvas.

    ``None`` stands for an empty operand. The box bounds every pixel of the result:
    the hull of the operands for ``union`` and ``xor``, their common part for
    ``intersect`` and the first operand's box for ``subtract``. The arithmetic is
    :func:`moana.core.coordinates.combined_box`, shared with the cost plan; this
    entry point also checks the operator and the canvas.
    """
    return _core_combined_box(_check_operator(operator), boxes, _check_dimensions(dimensions))


def _window(bits: Bits, box: Box, part: Box) -> Bits:
    """View of ``bits`` (stored over ``box``) restricted to ``part``, a sub-box of it."""
    return bits[part.y0 - box.y0 : part.y1 - box.y0, part.x0 - box.x0 : part.x1 - box.x0]


def _clear_outside(bits: Bits, box: Box, keep: Box) -> None:
    """Set to ``False`` every pixel of ``bits`` (over ``box``) outside ``keep``."""
    top, bottom = keep.y0 - box.y0, keep.y1 - box.y0
    left, right = keep.x0 - box.x0, keep.x1 - box.x0
    bits[:top, :] = False
    bits[bottom:, :] = False
    bits[top:bottom, :left] = False
    bits[top:bottom, right:] = False


class MaskBuilder:
    """Fold the operands of one operator, in order, into a buffer over ``box``.

    ``box`` must be :func:`combined_box` of the operand boxes (it may be ``None``);
    pixels of an operand outside it are dropped, which is how results are clipped.
    The builder owns at most ``box.area`` bytes; each :meth:`add` works in place over
    the overlap of the operand with ``box``. :meth:`finish` returns the mask and
    closes the builder.
    """

    __slots__ = ("_bits", "_box", "_closed", "_count", "_operator")

    def __init__(self, operator: MaskOperator, box: Box | None) -> None:
        self._operator = _check_operator(operator)
        if box is not None and not isinstance(box, Box):
            raise TypeError("box must be a Box value or None")
        self._box = box
        self._bits: Bits | None = (
            None if box is None else np.zeros((box.height, box.width), dtype=np.bool_)
        )
        self._count = 0
        self._closed = False

    def add(self, mask: Mask) -> None:
        """Fold the next operand into the result."""
        if self._closed:
            raise RuntimeError("the mask builder is already finished")
        if not isinstance(mask, Mask):
            raise TypeError("mask must be a Mask value")
        first = self._count == 0
        self._count += 1
        box, bits = self._box, self._bits
        if box is None or bits is None:
            return
        storage = mask.box
        overlap = None if storage is None else storage.intersection(box)
        if storage is None or overlap is None:
            if self._operator == "intersect" and not first:
                bits[:, :] = False
            return
        target = _window(bits, box, overlap)
        source = _window(mask._bits, storage, overlap)
        if first or self._operator == "union":
            np.logical_or(target, source, out=target)
        elif self._operator == "xor":
            np.logical_xor(target, source, out=target)
        elif self._operator == "intersect":
            _clear_outside(bits, box, overlap)
            np.logical_and(target, source, out=target)
        else:  # subtract: keep target where the operand is unset (True > False)
            np.greater(target, source, out=target)

    def finish(self) -> Mask:
        """The folded mask (empty when no pixel is set); the builder cannot be reused."""
        if self._closed:
            raise RuntimeError("the mask builder is already finished")
        if self._count == 0:
            raise ValueError("a mask operator needs at least one operand")
        self._closed = True
        box, bits = self._box, self._bits
        self._bits = None
        if box is None or bits is None or not bits.any():
            return Mask.empty()
        return Mask._adopt(box, bits)


def combine_masks(operator: MaskOperator, masks: Sequence[Mask], dimensions: Dimensions) -> Mask:
    """Result of ``operator`` over ``masks`` (in order), clipped to ``dimensions``."""
    operator = _check_operator(operator)
    if isinstance(masks, str | bytes) or not isinstance(masks, Sequence):
        raise TypeError("masks must be a sequence of Mask values")
    for mask in masks:
        if not isinstance(mask, Mask):
            raise TypeError("masks must be a sequence of Mask values")
    builder = MaskBuilder(operator, combined_box(operator, [m.box for m in masks], dimensions))
    for mask in masks:
        builder.add(mask)
    return builder.finish()
