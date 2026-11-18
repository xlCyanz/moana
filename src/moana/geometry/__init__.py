"""Integer masks of primitives and bounded flood fill (MOANA.md section 6, ADR-015).

``geometry`` depends only on ``core`` (MOANA.md section 3). NumPy is an internal
detail: rasterisers return immutable :class:`Mask` values and never expose a shared
array. Pixel-perfect transformations (mirror, quarter turns, integer scale, translation)
act on pixel indices about a pivot pixel (ADR-016). Fixed-point paths
come from the AggDraw adapter :mod:`moana.geometry.paths` (backend ``aggdraw-v1``,
ADR-023), which imports AggDraw only when a path is rasterised or the backend is
probed; stroke widths are out of scope. Masks combine through the set algebra of
:mod:`moana.geometry.algebra` (union, intersect, subtract, xor; ADR-022).
"""

from moana.geometry.algebra import (
    MASK_OPERATORS,
    MaskBuilder,
    MaskOperator,
    combine_masks,
    combined_box,
)
from moana.geometry.fill import FLOOD_FILL_BYTES_PER_PIXEL, flood_fill, flood_fill_cost
from moana.geometry.mask import Mask
from moana.geometry.paths import (
    AGGDRAW_BACKEND,
    COVERAGE_THRESHOLD,
    PATH_BUFFER_MARGIN,
    TESTED_AGGDRAW_VERSIONS,
    PathBackend,
    backend_unavailable_error,
    path_backend,
    path_buffer_box,
    path_mask_box,
    rasterize_path,
)
from moana.geometry.primitives import (
    MIN_POLYGON_VERTICES,
    rasterize_ellipse,
    rasterize_line,
    rasterize_pixel,
    rasterize_polygon,
    rasterize_rect,
)
from moana.geometry.transform import (
    MAX_SCALE,
    QUARTER_TURNS,
    Transform,
    transform_box,
    transform_mask,
)

__all__ = [
    "AGGDRAW_BACKEND",
    "COVERAGE_THRESHOLD",
    "FLOOD_FILL_BYTES_PER_PIXEL",
    "MASK_OPERATORS",
    "MAX_SCALE",
    "MIN_POLYGON_VERTICES",
    "PATH_BUFFER_MARGIN",
    "QUARTER_TURNS",
    "TESTED_AGGDRAW_VERSIONS",
    "Mask",
    "MaskBuilder",
    "MaskOperator",
    "PathBackend",
    "Transform",
    "backend_unavailable_error",
    "combine_masks",
    "combined_box",
    "flood_fill",
    "flood_fill_cost",
    "path_backend",
    "path_buffer_box",
    "path_mask_box",
    "rasterize_ellipse",
    "rasterize_line",
    "rasterize_path",
    "rasterize_pixel",
    "rasterize_polygon",
    "rasterize_rect",
    "transform_box",
    "transform_mask",
]
