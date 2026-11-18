"""Pixel-art techniques over masks and palette colours (MOANA.md sections 7-10).

``techniques`` depends on ``core``, ``geometry`` and ``palette`` (MOANA.md section 3).
It currently holds ordered Bayer dithering only (MOANA-016, ADR-025): integer
coverage, an explicit canvas anchor with the mathematical modulo and clipping by a
mask, split into the pixels of colour A and of colour B.
"""

from moana.techniques.dither import (
    BAYER_2X2,
    BAYER_4X4,
    DITHER_PARTS,
    DITHER_SIZES,
    DitherPart,
    OrderedDither,
    bayer_matrix,
    dither_cells,
    dither_mask,
    split_dither,
)

__all__ = [
    "BAYER_2X2",
    "BAYER_4X4",
    "DITHER_PARTS",
    "DITHER_SIZES",
    "DitherPart",
    "OrderedDither",
    "bayer_matrix",
    "dither_cells",
    "dither_mask",
    "split_dither",
]
