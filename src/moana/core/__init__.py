"""Core contracts: integer coordinates, canvas limits and the domain error hierarchy.

``moana.core`` imports no other Moana module, NumPy or Pillow (MOANA.md section 3).
"""

from moana.core.coordinates import (
    DEFAULT_SIZE,
    MAX_AREA,
    MAX_COORDINATE,
    MAX_DIMENSION,
    MIN_DIMENSION,
    Box,
    Dimensions,
    Point,
    require_int,
)
from moana.core.errors import (
    BudgetExceeded,
    EditConflict,
    ErrorDetail,
    ExportError,
    MoanaError,
    OutOfBoundsError,
    ReferenceError,
    UnsupportedOperation,
    UnsupportedVersion,
    ValidationError,
)
from moana.core.limits import (
    DEFAULT_GEOMETRY_LIMITS,
    MAX_COLORS_RGBA,
    MAX_COLORS_STRICT,
    MAX_LAYERS,
    MAX_OPERATIONS,
    MAX_VERTICES,
    GeometryLimits,
)

__all__ = [
    "DEFAULT_GEOMETRY_LIMITS",
    "DEFAULT_SIZE",
    "MAX_AREA",
    "MAX_COLORS_RGBA",
    "MAX_COLORS_STRICT",
    "MAX_COORDINATE",
    "MAX_DIMENSION",
    "MAX_LAYERS",
    "MAX_OPERATIONS",
    "MAX_VERTICES",
    "MIN_DIMENSION",
    "Box",
    "BudgetExceeded",
    "Dimensions",
    "EditConflict",
    "ErrorDetail",
    "ExportError",
    "GeometryLimits",
    "MoanaError",
    "OutOfBoundsError",
    "Point",
    "ReferenceError",
    "UnsupportedOperation",
    "UnsupportedVersion",
    "ValidationError",
    "require_int",
]
