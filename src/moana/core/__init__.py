"""Core contracts: integer coordinates, canvas limits and the domain error hierarchy.

``moana.core`` imports no other Moana module (MOANA.md section 3), and importing the
package loads neither NumPy nor Pillow. The canvas buffer and its adapters are the
explicit submodules ``moana.core.canvas`` and ``moana.core.pillow_adapter`` (ADR-013).
"""

from moana.core.budget import (
    DEFAULT_MAX_BUFFER_BYTES,
    DEFAULT_MAX_FRAME_PIXELS,
    DEFAULT_MAX_PIXEL_VISITS,
    DEFAULT_RENDER_LIMITS,
    Deadline,
    RenderLimits,
)
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
    detail_sort_key,
)
from moana.core.ids import (
    ID_PATTERN,
    ID_REGEX,
    RGBA_HEX_PATTERN,
    RGBA_HEX_REGEX,
    check_id,
    is_id,
    is_rgba_hex,
)
from moana.core.limits import (
    DEFAULT_GEOMETRY_LIMITS,
    MAX_COLORS_RGBA,
    MAX_COLORS_STRICT,
    MAX_LAYERS,
    MAX_OPERATIONS,
    MAX_RAMP_ENTRIES,
    MAX_VERTICES,
    GeometryLimits,
)

__all__ = [
    "DEFAULT_GEOMETRY_LIMITS",
    "DEFAULT_MAX_BUFFER_BYTES",
    "DEFAULT_MAX_FRAME_PIXELS",
    "DEFAULT_MAX_PIXEL_VISITS",
    "DEFAULT_RENDER_LIMITS",
    "DEFAULT_SIZE",
    "ID_PATTERN",
    "ID_REGEX",
    "MAX_AREA",
    "MAX_COLORS_RGBA",
    "MAX_COLORS_STRICT",
    "MAX_COORDINATE",
    "MAX_DIMENSION",
    "MAX_LAYERS",
    "MAX_OPERATIONS",
    "MAX_RAMP_ENTRIES",
    "MAX_VERTICES",
    "MIN_DIMENSION",
    "RGBA_HEX_PATTERN",
    "RGBA_HEX_REGEX",
    "Box",
    "BudgetExceeded",
    "Deadline",
    "Dimensions",
    "EditConflict",
    "ErrorDetail",
    "ExportError",
    "GeometryLimits",
    "MoanaError",
    "OutOfBoundsError",
    "Point",
    "ReferenceError",
    "RenderLimits",
    "UnsupportedOperation",
    "UnsupportedVersion",
    "ValidationError",
    "check_id",
    "detail_sort_key",
    "is_id",
    "is_rgba_hex",
    "require_int",
]
