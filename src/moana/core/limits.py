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
    "MAX_GROUP_DEPTH",
    "MAX_LAYERS",
    "MAX_MASKS",
    "MAX_MASK_DEPTH",
    "MAX_MASK_OPERANDS",
    "MAX_OPERATIONS",
    "MAX_PATH_CELLS",
    "MAX_PATH_COMMANDS",
    "MAX_PATH_CURVE_SEGMENTS",
    "MAX_PATH_SEGMENTS",
    "MAX_RAMP_ENTRIES",
    "MAX_REGIONS",
    "MAX_VERTICES",
    "GeometryLimits",
]

# Document cardinality limits of MOANA.md section 20, shared by schema, palette and
# render. Byte, depth and node limits of the reader live in ``moana.schema``.
MAX_LAYERS: Final = 128
# Nesting of groups in the layer tree (MOANA.md section 11).
MAX_GROUP_DEPTH: Final = 16
MAX_OPERATIONS: Final = 10_000
MAX_VERTICES: Final = 4096
MAX_COLORS_STRICT: Final = 256
MAX_COLORS_RGBA: Final = 4096
# Total colour references across all ramps of a palette. A schema document cannot
# reach it (its reader admits at most 20 000 JSON nodes); it bounds the cost of
# palettes built outside the schema reader (ADR-014).
MAX_RAMP_ENTRIES: Final = 20_000
# Semantic masks and regions (MOANA.md section 11, ADR-022): node counts, operands of
# one boolean node and the longest chain of mask references (a leaf has depth 1).
MAX_MASKS: Final = 1024
MAX_MASK_OPERANDS: Final = 64
MAX_MASK_DEPTH: Final = 16
MAX_REGIONS: Final = 1024
# Fixed-point paths (MOANA.md section 6, ADR-023): commands of one path, line segments
# after flattening its curves (closing edges included), segments of one flattened
# curve, and the coverage cells AggDraw may accumulate for one path. The cell bound is
# an engine limit, not a request budget: AGG keeps at most 4 194 304 cells and drops
# the rest silently, so a path whose conservative cell bound exceeds half of that is
# rejected before the adapter instead of being rendered wrong; the factor 2 also covers
# the extra cells of the grown outline's joins. The JSON reader counts at most 20 000
# nodes per document (each command is an array plus its items), so 4096 commands are
# only reachable through the reader with paths made almost only of ``M``/``L``.
MAX_PATH_COMMANDS: Final = 4096
MAX_PATH_SEGMENTS: Final = 65_536
MAX_PATH_CURVE_SEGMENTS: Final = 64
MAX_PATH_CELLS: Final = 2_097_152


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
