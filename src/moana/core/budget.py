"""Request budgets of MOANA.md section 20 and the cooperative deadline (ADR-012).

:class:`RenderLimits` holds the per-request resource budgets: estimated buffer bytes
(temporaries included), estimated pixel visits and accumulated frame pixels, plus the
operation/layer counts and the :class:`~moana.core.limits.GeometryLimits` it
composes. Callers may lower any value. Raising a budget above the section 20 default
requires ``host_override=True``, an explicit decision of the hosting application;
documents never carry limits. Counts and geometry can never exceed the format
contract, even with an override.

:class:`Deadline` is a *cooperative* check between units of work. It cannot stop a
native call that is already running; a service exposed to untrusted input must still
isolate rendering in a process with operating-system limits.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Final

from moana.core.coordinates import require_int
from moana.core.errors import BudgetExceeded
from moana.core.limits import DEFAULT_GEOMETRY_LIMITS, MAX_LAYERS, MAX_OPERATIONS, GeometryLimits

__all__ = [
    "DEFAULT_MAX_BUFFER_BYTES",
    "DEFAULT_MAX_FRAME_PIXELS",
    "DEFAULT_MAX_PIXEL_VISITS",
    "DEFAULT_RENDER_LIMITS",
    "Deadline",
    "RenderLimits",
]

DEFAULT_MAX_BUFFER_BYTES: Final = 256 * 1024 * 1024
DEFAULT_MAX_PIXEL_VISITS: Final = 100_000_000
DEFAULT_MAX_FRAME_PIXELS: Final = 16_777_216

# Largest value a host override may request; far beyond any real machine, it only
# keeps budgets finite and representable.
_OVERRIDE_CEILING: Final = 2**62


@dataclass(frozen=True, slots=True)
class RenderLimits:
    """Per-request budgets; lower freely, raise only with ``host_override=True``."""

    geometry: GeometryLimits = field(default=DEFAULT_GEOMETRY_LIMITS)
    max_buffer_bytes: int = DEFAULT_MAX_BUFFER_BYTES
    max_pixel_visits: int = DEFAULT_MAX_PIXEL_VISITS
    max_frame_pixels: int = DEFAULT_MAX_FRAME_PIXELS
    max_operations: int = MAX_OPERATIONS
    max_layers: int = MAX_LAYERS
    host_override: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.geometry, GeometryLimits):
            raise TypeError("geometry must be a GeometryLimits instance")
        if type(self.host_override) is not bool:
            raise TypeError("host_override must be a bool")
        budgets = (
            ("max_buffer_bytes", self.max_buffer_bytes, DEFAULT_MAX_BUFFER_BYTES),
            ("max_pixel_visits", self.max_pixel_visits, DEFAULT_MAX_PIXEL_VISITS),
            ("max_frame_pixels", self.max_frame_pixels, DEFAULT_MAX_FRAME_PIXELS),
        )
        for name, value, default in budgets:
            ceiling = _OVERRIDE_CEILING if self.host_override else default
            require_int(value, name, minimum=1, maximum=ceiling)
        require_int(self.max_operations, "max_operations", minimum=0, maximum=MAX_OPERATIONS)
        require_int(self.max_layers, "max_layers", minimum=0, maximum=MAX_LAYERS)


DEFAULT_RENDER_LIMITS: Final = RenderLimits()


class Deadline:
    """Cooperative time budget checked between units of work.

    Time only decides whether work continues; it never influences pixels, ordering
    or seeds (MOANA.md section 14). ``clock`` must be monotonic and return seconds.
    """

    __slots__ = ("_clock", "_expires_at", "_milliseconds")

    def __init__(self, milliseconds: int, *, clock: Callable[[], float] = time.monotonic) -> None:
        """Start a deadline of ``milliseconds`` (at least 1) from now."""
        require_int(milliseconds, "milliseconds", minimum=1, maximum=_OVERRIDE_CEILING)
        if not callable(clock):
            raise TypeError("clock must be callable")
        self._clock = clock
        self._milliseconds = milliseconds
        self._expires_at = clock() + milliseconds / 1000

    @property
    def milliseconds(self) -> int:
        """The configured budget."""
        return self._milliseconds

    def expired(self) -> bool:
        """Whether the budget is used up."""
        return self._clock() >= self._expires_at

    def checkpoint(self, stage: str) -> None:
        """Raise :class:`BudgetExceeded` (resource ``time``) once the deadline passed.

        ``stage`` is a fixed name chosen by the caller (for example ``"layer"``),
        never document content.
        """
        if not isinstance(stage, str):
            raise TypeError("stage must be a str")
        if self.expired():
            raise BudgetExceeded(
                "cooperative deadline expired",
                context={
                    "resource": "time",
                    "limit": self._milliseconds,
                    "unit": "ms",
                    "stage": stage,
                },
            )
