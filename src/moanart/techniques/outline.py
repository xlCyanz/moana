"""Outer and inner outlines of a mask (MOANART.md section 8, ADR-027).

Normative rule of section 8, with the Chebyshev 3 x 3 neighbourhood repeated
``width`` times and a transparent exterior:

* outer outline of width ``n``: ``dilate(mask, n) - mask``;
* inner outline of width ``n``: ``mask - erode(mask, n)``.

Holes are part of the exterior, so each hole gets its own outer outline (inside the
hole) and its own inner outline (around it). The outer outline is clipped to the
canvas; the inner outline of a mask that touches the canvas edge runs along that
edge, because pixels off the canvas are outside every mask. The outline is a subset
of the canvas, disjoint from the mask (outer) or contained in it (inner).
"""

from __future__ import annotations

from typing import Final, Literal, get_args

from moanart.core.coordinates import Dimensions, require_int
from moanart.core.errors import ValidationError
from moanart.geometry import MAX_MORPHOLOGY_RADIUS, Mask, combine_masks, dilate, erode

__all__ = [
    "MAX_OUTLINE_WIDTH",
    "OUTLINE_SIDES",
    "OutlineSide",
    "outline_mask",
]

OutlineSide = Literal["outer", "inner"]
OUTLINE_SIDES: Final[tuple[OutlineSide, ...]] = get_args(OutlineSide)
"""``outer``: ring outside the mask; ``inner``: ring inside it."""
MAX_OUTLINE_WIDTH: Final = MAX_MORPHOLOGY_RADIUS
"""Largest outline width: the morphology radius limit of ``moanart.core.limits``."""


def _check_side(side: object) -> OutlineSide:
    for known in OUTLINE_SIDES:
        if side == known and type(side) is str:
            return known
    raise ValidationError(
        "side must be outer or inner", context={"field": "side", "reason": "unknown_side"}
    )


def outline_mask(mask: Mask, width: int, side: OutlineSide, dimensions: Dimensions) -> Mask:
    """Outline of ``mask`` of ``width`` pixels (``1..MAX_OUTLINE_WIDTH``) on ``side``.

    Raises ``ValidationError`` (``field: width``, ``not_integer``/``out_of_range``;
    ``field: side``, ``unknown_side``). The result is stored over the mask's storage
    box grown by ``width`` and clipped (outer) or over the clipped mask box (inner),
    :func:`moanart.core.coordinates.grown_box` with ``width`` or ``0``; or it is empty.
    """
    if not isinstance(mask, Mask):
        raise TypeError("mask must be a Mask value")
    require_int(width, "width", minimum=1, maximum=MAX_OUTLINE_WIDTH)
    if _check_side(side) == "outer":
        return combine_masks("subtract", [dilate(mask, width, dimensions), mask], dimensions)
    return combine_masks("subtract", [mask, erode(mask, width, dimensions)], dimensions)
