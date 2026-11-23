"""Band shading with a discrete light and authored facings (MOANART.md sections 9-10, ADR-028).

No normal is ever inferred from pixels. The author supplies, per band, a mask and a
*facing*: the discrete orientation of that part of the volume (one of the eight
picture-plane directions, ``front`` towards the viewer, or ``none``). The light is
discrete too: a direction (the same eight plus ``front``), a height ``h`` in ``0..3``,
an ``intensity`` and an ``ambient`` ramp step. Everything is integer arithmetic.

**Exposure** of a facing ``F`` under the light, an integer in ``-6..6``
(:data:`EXPOSURE_SCALE` = 6). With ``d`` the angular distance between two planar
directions in 45 degree steps (``0..4``) and ``COSINE = (2, 1, 0, -1, -2)``:

==================  =====================  ==================
facing \\ light      planar direction ``L``  ``front``
==================  =====================  ==================
planar ``F``        ``(3 - h) * COSINE[d]``  ``0``
``front``           ``2 * h``              ``6``
``none``            ``0``                  ``0``
==================  =====================  ==================

So a low light (``h = 0``) gives full contrast between opposite sides and leaves a
front-facing plane at the ambient step; a high light (``h = 3``) flattens the sides
and fully lights the front, exactly like a ``front`` light (whose height is unused).

**Ramp index** of a band with integer ``offset``::

    level = round_half_away(intensity * exposure / 6)      # in -intensity..intensity
    index = clamp(ambient + level + offset, 0, len(ramp) - 1)

``round_half_away`` rounds ``n / 6`` to the nearest integer, halves away from zero,
so opposite facings get opposite levels. The clamp keeps every colour inside the
ramp: no colour is ever computed, multiplied or blended.

**Priority**: bands are listed in order and, where they overlap, the last listed
band wins (section 10). :func:`last_wins` keeps the pixels of one band that no later
band covers, so the visible parts of the bands are disjoint and their union is the
union of the band masks; painting them in any order gives the same pixels.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Final

from moanart.core.coordinates import require_int
from moanart.core.errors import ValidationError
from moanart.core.limits import MAX_COLORS_RGBA
from moanart.core.shading import (
    FACINGS,
    LIGHT_DIRECTIONS,
    MAX_LIGHT_HEIGHT,
    MAX_RAMP_STEP,
    MAX_SHADE_BANDS,
    PLANAR_DIRECTIONS,
    Facing,
    LightDirection,
)
from moanart.geometry import Mask, MaskBuilder

__all__ = [
    "COSINE",
    "EXPOSURE_SCALE",
    "FACINGS",
    "LIGHT_DIRECTIONS",
    "MAX_LIGHT_HEIGHT",
    "MAX_RAMP_STEP",
    "MAX_SHADE_BANDS",
    "Facing",
    "LightDirection",
    "ShadeLight",
    "band_index",
    "band_level",
    "exposure",
    "last_wins",
    "ramp_index",
    "resolve_bands",
]

COSINE: Final = (2, 1, 0, -1, -2)
"""Twice the cosine of ``d x 45`` degrees, rounded to an integer (``d`` in ``0..4``)."""
EXPOSURE_SCALE: Final = 2 * MAX_LIGHT_HEIGHT
"""Largest exposure: a facing that looks straight at the light."""


def _literal[T: str](value: object, known: tuple[T, ...], field: str, reason: str) -> T:
    for item in known:
        if value == item and type(value) is str:
            return item
    raise ValidationError(
        f"{field} must be one of {', '.join(known)}", context={"field": field, "reason": reason}
    )


@dataclass(frozen=True, slots=True)
class ShadeLight:
    """A discrete artistic light (MOANART.md section 9).

    ``direction`` is one of :data:`LIGHT_DIRECTIONS` (``unknown_direction``);
    ``height`` an ``int`` in ``0..3``; ``intensity`` and ``ambient`` ``int`` ramp steps
    in ``0..MAX_RAMP_STEP`` (``not_integer``/``out_of_range``).
    """

    direction: LightDirection
    height: int
    intensity: int
    ambient: int

    def __post_init__(self) -> None:
        _literal(self.direction, LIGHT_DIRECTIONS, "direction", "unknown_direction")
        require_int(self.height, "height", minimum=0, maximum=MAX_LIGHT_HEIGHT)
        require_int(self.intensity, "intensity", minimum=0, maximum=MAX_RAMP_STEP)
        require_int(self.ambient, "ambient", minimum=0, maximum=MAX_RAMP_STEP)


def _check_light(light: object) -> ShadeLight:
    if not isinstance(light, ShadeLight):
        raise TypeError("light must be a ShadeLight value")
    return light


def exposure(facing: Facing, light: ShadeLight) -> int:
    """Exposure of ``facing`` under ``light``, an ``int`` in ``-6..6`` (module table).

    Raises ``ValidationError`` (``field: facing``, ``unknown_facing``).
    """
    facing = _literal(facing, FACINGS, "facing", "unknown_facing")
    light = _check_light(light)
    if facing == "none":
        return 0
    if facing == "front":
        return EXPOSURE_SCALE if light.direction == "front" else 2 * light.height
    if light.direction == "front":
        return 0
    turn = PLANAR_DIRECTIONS.index(facing) - PLANAR_DIRECTIONS.index(light.direction)
    distance = min(turn % 8, -turn % 8)
    return (MAX_LIGHT_HEIGHT - light.height) * COSINE[distance]


def band_level(facing: Facing, light: ShadeLight) -> int:
    """``round_half_away(intensity x exposure / 6)``: ramp steps above the ambient."""
    product = _check_light(light).intensity * exposure(facing, light)
    magnitude = (2 * abs(product) + EXPOSURE_SCALE) // (2 * EXPOSURE_SCALE)
    return magnitude if product >= 0 else -magnitude


def ramp_index(step: int, length: int) -> int:
    """``step`` clamped to the indexes ``0..length - 1`` of a ramp of ``length`` colours."""
    require_int(length, "length", minimum=1, maximum=MAX_COLORS_RGBA)
    if type(step) is not int:
        raise ValidationError(
            "step must be an integer",
            context={"field": "step", "reason": "not_integer", "value_type": type(step).__name__},
        )
    return min(max(step, 0), length - 1)


def band_index(facing: Facing, offset: int, light: ShadeLight, length: int) -> int:
    """Ramp index of a band: ``clamp(ambient + level + offset, 0, length - 1)``.

    ``offset`` is an ``int`` in ``-MAX_RAMP_STEP..MAX_RAMP_STEP``.
    """
    require_int(offset, "offset", minimum=-MAX_RAMP_STEP, maximum=MAX_RAMP_STEP)
    light = _check_light(light)
    return ramp_index(light.ambient + band_level(facing, light) + offset, length)


def last_wins(masks: Iterable[Mask]) -> Mask:
    """Pixels of the first mask that none of the following masks covers.

    The masks are consumed one at a time: the result buffer (the first mask's box)
    is the only one kept while each later mask is folded and released, and nothing
    after the first mask is read when it is empty. The result never grows past the
    first mask; it may be empty.
    """
    iterator = iter(masks)
    first = next(iterator, None)
    if not isinstance(first, Mask):
        raise TypeError("masks must start with a Mask value")
    if first.box is None:
        return first
    builder = MaskBuilder("subtract", first.box)
    builder.add(first)
    del first
    for later in iterator:
        if not isinstance(later, Mask):
            raise TypeError("masks must be Mask values")
        builder.add(later)
        del later  # release each operand before the next one is built
    return builder.finish()


def resolve_bands(masks: Sequence[Mask]) -> tuple[Mask, ...]:
    """Visible part of each band mask, in order: ``masks[i]`` minus every later mask.

    The parts are disjoint and their union is the union of ``masks``. At most
    :data:`MAX_SHADE_BANDS` bands (``field: bands``, ``out_of_range``).
    """
    if isinstance(masks, str | bytes) or not isinstance(masks, Sequence):
        raise TypeError("masks must be a sequence of Mask values")
    require_int(len(masks), "bands", minimum=0, maximum=MAX_SHADE_BANDS)
    return tuple(last_wins(masks[index:]) for index in range(len(masks)))
