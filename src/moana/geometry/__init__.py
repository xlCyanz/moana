"""Integer masks of primitives and bounded flood fill (MOANA.md section 6, ADR-015).

``geometry`` depends only on ``core`` (MOANA.md section 3). NumPy is an internal
detail: rasterisers return immutable :class:`Mask` values and never expose a shared
array. Pixel-perfect transformations (mirror, quarter turns, integer scale, translation)
act on pixel indices about a pivot pixel (ADR-016). Paths and stroke widths are out
of scope (later issues).
"""

from moana.geometry.fill import FLOOD_FILL_BYTES_PER_PIXEL, flood_fill, flood_fill_cost
from moana.geometry.mask import Mask
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
    "FLOOD_FILL_BYTES_PER_PIXEL",
    "MAX_SCALE",
    "MIN_POLYGON_VERTICES",
    "QUARTER_TURNS",
    "Mask",
    "Transform",
    "flood_fill",
    "flood_fill_cost",
    "rasterize_ellipse",
    "rasterize_line",
    "rasterize_pixel",
    "rasterize_polygon",
    "rasterize_rect",
    "transform_box",
    "transform_mask",
]
