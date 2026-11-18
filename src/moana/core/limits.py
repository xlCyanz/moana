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
    "MAX_ARCHIVE_BYTES",
    "MAX_ARCHIVE_ENTRIES",
    "MAX_ARCHIVE_EXPANDED_BYTES",
    "MAX_ARCHIVE_RATIO",
    "MAX_ASSET_BYTES",
    "MAX_ASSET_PIXELS",
    "MAX_CLUSTER_EXCEPTIONS",
    "MAX_CLUSTER_RUNS",
    "MAX_COLORS_RGBA",
    "MAX_COLORS_STRICT",
    "MAX_EDIT_COMMANDS",
    "MAX_GROUP_DEPTH",
    "MAX_HISTORY_BYTES",
    "MAX_HISTORY_SNAPSHOTS",
    "MAX_LAYERS",
    "MAX_MASKS",
    "MAX_MASK_DEPTH",
    "MAX_MASK_OPERANDS",
    "MAX_MIGRATION_STEPS",
    "MAX_MORPHOLOGY_RADIUS",
    "MAX_OPERATIONS",
    "MAX_PATH_CELLS",
    "MAX_PATH_COMMANDS",
    "MAX_PATH_CURVE_SEGMENTS",
    "MAX_PATH_SEGMENTS",
    "MAX_PROJECT_ASSETS",
    "MAX_PROJECT_MANIFEST_BYTES",
    "MAX_PROJECT_MANIFEST_DEPTH",
    "MAX_PROJECT_MANIFEST_NODES",
    "MAX_PROJECT_MIGRATIONS",
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
# Commands of one edit batch (MOANA.md section 15, ADR-024). Each command is applied
# to a working copy in time linear in the document and only the final result is fully
# revalidated, so this bounds the whole batch (worst case measured: about 2 s for 1024
# translates of a 3001-command path).
MAX_EDIT_COMMANDS: Final = 1024
# In-memory edit history (MOANA.md section 15, ADR-026): stored snapshots, root
# included, and the bytes they account for (canonical JSON of each document plus the
# canonical batch that produced it). A history that would exceed either bound rejects
# the edit with ``BudgetExceeded`` before adding anything; nothing is evicted. A host
# may lower both through ``moana.editing.HistoryLimits``, never raise them. The byte
# measure is deterministic and proportional to what is stored, but it is not a bound
# on RAM: each snapshot holds a separate validated ``Document``, and the memory traced
# for it was about 10-17x its canonical JSON (about 0.3-0.5 GiB at this maximum). With
# 8 MiB documents only 4 versions fit.
MAX_HISTORY_SNAPSHOTS: Final = 1024
MAX_HISTORY_BYTES: Final = 32 * 1024 * 1024
# Binary morphology and outlines (MOANA.md section 8, ADR-027): the largest Chebyshev
# radius of a dilation or erosion, which is also the largest ``width`` of an
# ``outline`` operation. Pixel-art outlines are one or two pixels wide; 16 keeps the
# padded work box of one pass within ``(w + 33) x (h + 33)`` pixels.
MAX_MORPHOLOGY_RADIUS: Final = 16
# Cluster analysis (MOANA.md section 8, ADR-027): horizontal runs of equal opaque
# colour an analysis may label. Runs are counted row by row (pure Python, grouped in
# C) before the union-find starts, so a noisy image is rejected (``BudgetExceeded``,
# ``cluster_runs``) before its time and memory grow; a 512 x 512 checkerboard is
# exactly at the limit, a 128 x 128 sprite has at most 16 384 runs. The memory of an
# analysis is bounded per run (``moana.techniques.cluster_bytes``).
MAX_CLUSTER_RUNS: Final = 262_144
# Region exceptions of one cluster analysis (MOANA.md section 19, ADR-027): each is
# one bit of the per-pixel ``uint64`` cover of the region masks, so suppression costs
# the pixels of the findings whatever the number of exceptions.
MAX_CLUSTER_EXCEPTIONS: Final = 64


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


# Projects and assets (MOANA.md section 16, ADR-029). The manifest
# ``project.moana.json`` embeds one document (at most 8 MiB, 32 levels, 20 000 nodes)
# plus its asset references and history entries, so its bounds are the document's
# plus room for 128 assets and 1024 entries; the envelope adds two levels of nesting.
MAX_PROJECT_MANIFEST_BYTES: Final = 9 * 1024 * 1024
MAX_PROJECT_MANIFEST_DEPTH: Final = 34
MAX_PROJECT_MANIFEST_NODES: Final = 32_768
# Declared assets of one project, encoded bytes of one PNG asset and decoded pixels of
# all assets together (16 777 216 = 64 MiB of RGBA, the frame budget of section 20).
# Each asset is also bounded by the canvas contract (2048 per axis, 4 194 304 pixels).
MAX_PROJECT_ASSETS: Final = 128
MAX_ASSET_BYTES: Final = 32 * 1024 * 1024
MAX_ASSET_PIXELS: Final = 16_777_216
# Optional ``.moana`` ZIP container (MOANA.md section 16): entries, compressed bytes
# of the archive, declared expanded bytes of all entries and the expansion ratio,
# enforced per entry and in total, all from the central directory before extraction.
MAX_ARCHIVE_ENTRIES: Final = 256
MAX_ARCHIVE_BYTES: Final = 64 * 1024 * 1024
MAX_ARCHIVE_EXPANDED_BYTES: Final = 256 * 1024 * 1024
MAX_ARCHIVE_RATIO: Final = 100


# Format versions and migrations (MOANA.md section 16, ADR-031). A registered chain of
# pure migration steps from any known version to the current one has at most
# ``MAX_MIGRATION_STEPS`` steps; a project keeps at most ``MAX_PROJECT_MIGRATIONS``
# migration records, each with the preserved copy of its original JSON (bounded by
# ``MAX_PROJECT_MANIFEST_BYTES``).
MAX_MIGRATION_STEPS: Final = 16
MAX_PROJECT_MIGRATIONS: Final = 8
