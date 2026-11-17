"""Palettes, colours and ramps referenced by stable IDs (MOANA.md section 9, ADR-014).

``palette`` depends only on ``core`` (MOANA.md section 3) and loads no graphics
library: values are plain integers. ``moana.editing`` may not import it; the ID
and colour languages it checks are owned by ``moana.core.ids``.
"""

from moana.palette.colors import (
    LINEAR_SCALE,
    LUMINANCE_SCALE,
    PROFILE_MAX_COLORS,
    PROFILES,
    SRGB_TO_LINEAR,
    TRANSPARENT,
    ColorProfile,
    Rgba,
)
from moana.palette.table import (
    MIN_RAMP_LENGTH,
    RAMP_LUMINANCE_NOT_INCREASING,
    RAMP_PARTIAL_ALPHA_STEP,
    RAMP_TRANSPARENT_STEP,
    ColorRemap,
    Palette,
    PaletteColor,
    PaletteWarning,
    Ramp,
)

__all__ = [
    "LINEAR_SCALE",
    "LUMINANCE_SCALE",
    "MIN_RAMP_LENGTH",
    "PROFILES",
    "PROFILE_MAX_COLORS",
    "RAMP_LUMINANCE_NOT_INCREASING",
    "RAMP_PARTIAL_ALPHA_STEP",
    "RAMP_TRANSPARENT_STEP",
    "SRGB_TO_LINEAR",
    "TRANSPARENT",
    "ColorProfile",
    "ColorRemap",
    "Palette",
    "PaletteColor",
    "PaletteWarning",
    "Ramp",
    "Rgba",
]
