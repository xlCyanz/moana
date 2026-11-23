"""Shared constants of ordered dithering (MOANART.md section 10, ADR-025).

Pure data with no dependencies: ``schema`` (the ``size`` grammar), ``techniques``
(the Bayer matrices), ``geometry`` (the periodic selection) and the cost plan
(``moanart.render.budget``, which imports no NumPy) all read these values from here,
so there is exactly one definition of each.
"""

from __future__ import annotations

from typing import Final

__all__ = ["DITHER_SIZES", "PATTERN_INDEX_BYTES"]

DITHER_SIZES: Final = (2, 4)
"""Supported Bayer matrix sides ``N`` of a ``dither`` operation."""
PATTERN_INDEX_BYTES: Final = 8
"""Bytes per row or column index (``int64``) of a periodic selection."""
