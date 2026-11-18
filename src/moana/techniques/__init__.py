"""Pixel-art techniques over masks and palette colours (MOANA.md sections 7-10).

``techniques`` depends on ``core``, ``geometry`` and ``palette`` (MOANA.md section 3).
It holds ordered Bayer dithering (MOANA-016, ADR-025): integer coverage, an
explicit canvas anchor with the mathematical modulo and clipping by a mask, split
into the pixels of colour A and of colour B. MOANA-014 (ADR-027) adds outer and inner
outlines (:func:`outline_mask`, Chebyshev morphology of section 8) and the cluster
analysis of an RGBA image (:func:`analyze_clusters`): connected components of equal
colour with explicit 4/8 connectivity, singleton and irregular-step warnings and
region exceptions (:func:`check_cluster_settings`, :func:`cluster_bytes` bound its
memory). The analysis never modifies anything and never cleans up.
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

__all__ = [
    "BAYER_2X2",
    "BAYER_4X4",
    "CLUSTER_FIXED_BYTES",
    "CLUSTER_RULES",
    "CLUSTER_RUN_BYTES",
    "CONNECTIVITIES",
    "DITHER_PARTS",
    "DITHER_SIZES",
    "MAX_OUTLINE_WIDTH",
    "OUTLINE_SIDES",
    "Cluster",
    "ClusterException",
    "ClusterFinding",
    "ClusterReport",
    "ClusterRule",
    "Connectivity",
    "DitherPart",
    "OrderedDither",
    "OutlineSide",
    "Severity",
    "analyze_clusters",
    "bayer_matrix",
    "check_cluster_settings",
    "cluster_bytes",
    "dither_cells",
    "dither_mask",
    "outline_mask",
    "split_dither",
]
