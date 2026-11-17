"""Geometric contract limits of MOANA.md section 5, separate from where they apply.

:class:`GeometryLimits` holds the canvas and coordinate maxima of the format. A host
may lower them for a request but never raise them above the contract, and an
untrusted document cannot supply them. Raisable resource budgets of section 20
(bytes, pixel visits, frames) belong to ``RenderLimits`` (MOANA-003), which composes
these limits instead of extending them (ADR-010).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from moana.core.coordinates import (
    MAX_AREA,
    MAX_COORDINATE,
    MAX_DIMENSION,
    Box,
    Dimensions,
    Point,
    check_box_corners,
    require_int,
)
from moana.core.errors import ValidationError

__all__ = [
    "DEFAULT_GEOMETRY_LIMITS",
    "MAX_COLORS_RGBA",
    "MAX_COLORS_STRICT",
    "MAX_LAYERS",
    "MAX_OPERATIONS",
    "MAX_VERTICES",
    "GeometryLimits",
]

# Document cardinality limits of MOANA.md section 20, shared by schema, palette and
# render. Byte, depth and node limits of the reader live in ``moana.schema``.
MAX_LAYERS: Final = 128
MAX_OPERATIONS: Final = 10_000
MAX_VERTICES: Final = 4096
MAX_COLORS_STRICT: Final = 256
MAX_COLORS_RGBA: Final = 4096


@dataclass(frozen=True, slots=True)
class GeometryLimits:
    """Upper bounds for canvas axes, canvas area and absolute pixel coordinates."""

    max_dimension: int = MAX_DIMENSION
    max_area: int = MAX_AREA
    max_coordinate: int = MAX_COORDINATE

    def __post_init__(self) -> None:
        require_int(self.max_dimension, "max_dimension", minimum=1, maximum=MAX_DIMENSION)
        require_int(self.max_area, "max_area", minimum=1, maximum=MAX_AREA)
        require_int(self.max_coordinate, "max_coordinate", minimum=0, maximum=MAX_COORDINATE)

    def check_dimensions(self, dimensions: Dimensions) -> None:
        """Reject a canvas whose axes or area exceed these limits."""
        for field, value in (("width", dimensions.width), ("height", dimensions.height)):
            require_int(value, field, minimum=1, maximum=self.max_dimension)
        if dimensions.area > self.max_area:
            raise ValidationError(
                "canvas area exceeds the configured limit",
                context={"field": "area", "reason": "out_of_range", "maximum": self.max_area},
            )

    def check_point(self, point: Point) -> None:
        """Reject a pixel whose coordinates exceed ``±max_coordinate``."""
        for field, value in (("x", point.x), ("y", point.y)):
            require_int(value, field, minimum=-self.max_coordinate, maximum=self.max_coordinate)

    def check_box(self, box: Box) -> None:
        """Reject a box outside the range; its excluded edge may reach ``max + 1``."""
        check_box_corners(box.x0, box.y0, box.x1, box.y1, max_coordinate=self.max_coordinate)


DEFAULT_GEOMETRY_LIMITS: Final = GeometryLimits()
