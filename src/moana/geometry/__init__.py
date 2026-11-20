"""Integer masks of primitives and bounded flood fill (MOANA.md section 6, ADR-015).

``geometry`` depends only on ``core`` (MOANA.md section 3). NumPy is an internal
detail: rasterisers return immutable :class:`Mask` values and never expose a shared
array. Pixel-perfect transformations (mirror, quarter turns, integer scale, translation)
act on pixel indices about a pivot pixel (ADR-016). Fixed-point paths
come from the AggDraw adapter :mod:`moana.geometry.paths` (backend ``aggdraw-v1``,
ADR-023), which imports AggDraw only when a path is rasterised or the backend is
probed; stroke widths are out of scope. Masks combine through the set algebra of
:mod:`moana.geometry.algebra` (union, intersect, subtract, xor; ADR-022). A periodic
cell table anchored on the canvas selects mask pixels with the mathematical modulo
(:func:`select_periodic`, ADR-025), the geometry under ordered dithering. Bounded
Chebyshev dilation and erosion with a transparent exterior (:func:`dilate`,
:func:`erode`, ADR-027) are the geometry under outlines. A grid of one-byte cells
anchored on the canvas selects mask pixels by cell value (:func:`select_cells`,
ADR-030), the geometry under material textures.
"""

from moana.geometry.algebra import (
    MASK_OPERATORS,
    MaskBuilder,
    MaskOperator,
    combine_masks,
    combined_box,
)
from moana.geometry.cover import (
    COVER_BYTES_PER_PIXEL,
    MAX_COVER_MASKS,
    MaskCover,
    cover_bytes,
)
from moana.geometry.fill import FLOOD_FILL_BYTES_PER_PIXEL, flood_fill, flood_fill_cost
from moana.geometry.mask import Mask
from moana.geometry.morphology import (
    MAX_MORPHOLOGY_RADIUS,
    MORPHOLOGY_FIXED_BYTES,
    dilate,
    erode,
    morphology_bytes,
)
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
from moana.geometry.pattern import (
    MAX_PATTERN_SIZE,
    PATTERN_INDEX_BYTES,
    CellTable,
    select_cells,
    select_periodic,
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
    "COVER_BYTES_PER_PIXEL",
    "FLOOD_FILL_BYTES_PER_PIXEL",
    "MASK_OPERATORS",
    "MAX_COVER_MASKS",
    "MAX_MORPHOLOGY_RADIUS",
    "MAX_PATTERN_SIZE",
    "MAX_SCALE",
    "MIN_POLYGON_VERTICES",
    "MORPHOLOGY_FIXED_BYTES",
    "PATH_BUFFER_MARGIN",
    "PATTERN_INDEX_BYTES",
    "QUARTER_TURNS",
    "TESTED_AGGDRAW_VERSIONS",
    "CellTable",
    "Mask",
    "MaskBuilder",
    "MaskCover",
    "MaskOperator",
    "PathBackend",
    "Transform",
    "backend_unavailable_error",
    "combine_masks",
    "combined_box",
    "cover_bytes",
    "dilate",
    "erode",
    "flood_fill",
    "flood_fill_cost",
    "morphology_bytes",
    "path_backend",
    "path_buffer_box",
    "path_mask_box",
    "rasterize_ellipse",
    "rasterize_line",
    "rasterize_path",
    "rasterize_pixel",
    "rasterize_polygon",
    "rasterize_rect",
    "select_cells",
    "select_periodic",
    "transform_box",
    "transform_mask",
]
