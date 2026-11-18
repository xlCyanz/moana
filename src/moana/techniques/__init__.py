"""Pixel-art techniques over masks and palette colours (MOANA.md sections 7-10).

``techniques`` depends on ``core``, ``geometry`` and ``palette`` (MOANA.md section 3).
It holds ordered Bayer dithering (MOANA-016, ADR-025): integer coverage, an
explicit canvas anchor with the mathematical modulo and clipping by a mask, split
into the pixels of colour A and of colour B. MOANA-014 (ADR-027) adds outer and inner
outlines (:func:`outline_mask`, Chebyshev morphology of section 8) and the cluster
analysis of an RGBA image (:func:`analyze_clusters`): connected components of equal
colour with explicit 4/8 connectivity, singleton and irregular-step warnings and
region exceptions (:func:`check_cluster_settings`, :func:`cluster_bytes` bound its
memory). The analysis never modifies anything and never cleans up. MOANA-015
(ADR-028) adds band shading: a discrete :class:`ShadeLight`, authored facings
(:func:`exposure`, :func:`band_level`), the clamped ramp index of a band
(:func:`band_index`) and last-listed-wins priority (:func:`last_wins`,
:func:`resolve_bands`). No normal is inferred and no colour is computed.
"""

from moana.techniques.clusters import (
    CLUSTER_FIXED_BYTES,
    CLUSTER_RULES,
    CLUSTER_RUN_BYTES,
    CONNECTIVITIES,
    Cluster,
    ClusterException,
    ClusterFinding,
    ClusterReport,
    ClusterRule,
    Connectivity,
    Severity,
    analyze_clusters,
    check_cluster_settings,
    cluster_bytes,
)
from moana.techniques.dither import (
    BAYER_2X2,
    BAYER_4X4,
    DITHER_PARTS,
    DITHER_SIZES,
    DitherPart,
    OrderedDither,
    bayer_matrix,
    dither_cells,
    dither_mask,
    split_dither,
)
from moana.techniques.outline import (
    MAX_OUTLINE_WIDTH,
    OUTLINE_SIDES,
    OutlineSide,
    outline_mask,
)
from moana.techniques.shading import (
    COSINE,
    EXPOSURE_SCALE,
    FACINGS,
    LIGHT_DIRECTIONS,
    MAX_LIGHT_HEIGHT,
    MAX_RAMP_STEP,
    MAX_SHADE_BANDS,
    Facing,
    LightDirection,
    ShadeLight,
    band_index,
    band_level,
    exposure,
    last_wins,
    ramp_index,
    resolve_bands,
)

__all__ = [
    "BAYER_2X2",
    "BAYER_4X4",
    "CLUSTER_FIXED_BYTES",
    "CLUSTER_RULES",
    "CLUSTER_RUN_BYTES",
    "CONNECTIVITIES",
    "COSINE",
    "DITHER_PARTS",
    "DITHER_SIZES",
    "EXPOSURE_SCALE",
    "FACINGS",
    "LIGHT_DIRECTIONS",
    "MAX_LIGHT_HEIGHT",
    "MAX_OUTLINE_WIDTH",
    "MAX_RAMP_STEP",
    "MAX_SHADE_BANDS",
    "OUTLINE_SIDES",
    "Cluster",
    "ClusterException",
    "ClusterFinding",
    "ClusterReport",
    "ClusterRule",
    "Connectivity",
    "DitherPart",
    "Facing",
    "LightDirection",
    "OrderedDither",
    "OutlineSide",
    "Severity",
    "ShadeLight",
    "analyze_clusters",
    "band_index",
    "band_level",
    "bayer_matrix",
    "check_cluster_settings",
    "cluster_bytes",
    "dither_cells",
    "dither_mask",
    "exposure",
    "last_wins",
    "outline_mask",
    "ramp_index",
    "resolve_bands",
    "split_dither",
]
