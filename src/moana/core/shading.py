"""Shared constants of band shading and discrete lights (MOANA.md sections 9-10, ADR-028).

Pure data with no dependencies: ``schema`` (the ``shade`` grammar and its limits)
and ``techniques`` (the exposure table and the ramp index rule) read these values
from here, so there is exactly one definition of each. The cost plan
(``moana.render.budget``) does not need them: a band's cost depends only on its
mask, never on its light or ramp step.
"""

from __future__ import annotations

from typing import Final, Literal, get_args

__all__ = [
    "FACINGS",
    "LIGHT_DIRECTIONS",
    "MAX_LIGHT_HEIGHT",
    "MAX_RAMP_STEP",
    "MAX_SHADE_BANDS",
    "PLANAR_DIRECTIONS",
    "RAMP_ORDERS",
    "Facing",
    "LightDirection",
    "RampOrder",
]

LightDirection = Literal["n", "ne", "e", "se", "s", "sw", "w", "nw", "front"]
LIGHT_DIRECTIONS: Final[tuple[LightDirection, ...]] = get_args(LightDirection)
"""Eight picture-plane orientations, clockwise from north (up), then ``front``."""
PLANAR_DIRECTIONS: Final = LIGHT_DIRECTIONS[:8]
"""The eight picture-plane orientations; position ``k`` is ``k x 45`` degrees."""

Facing = Literal["n", "ne", "e", "se", "s", "sw", "w", "nw", "front", "none"]
FACINGS: Final[tuple[Facing, ...]] = get_args(Facing)
"""Authored orientation of a band: a light direction, or ``none`` (no exposure)."""

RampOrder = Literal["monotonic", "stylized"]
RAMP_ORDERS: Final[tuple[RampOrder, ...]] = get_args(RampOrder)
"""``monotonic``: warn when the ramp luminance does not grow; ``stylized``: do not."""

MAX_LIGHT_HEIGHT: Final = 3
"""Discrete light height ``0..3``: 0 grazes the picture plane, 3 faces the viewer."""
MAX_RAMP_STEP: Final = 4095
"""Largest ``intensity``, ``ambient`` and absolute ``offset``: a ramp has at most 4096
colours (``MAX_COLORS_RGBA``), so larger steps would always be clamped."""
MAX_SHADE_BANDS: Final = 64
"""Bands of one ``shade`` operation; each band is one fill of the compositor."""
