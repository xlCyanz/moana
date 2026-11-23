"""Public Python facade of MoanArt (MOANART.md section 13, ADR-020).

The facade composes the implemented services and adds no algorithm of its own:

* :func:`load_document` reads a caller-authorised path, bytes or a mapping and
  returns a frozen, validated :class:`~moanart.schema.Document`;
* :func:`render` returns an immutable :class:`~moanart.render.RenderResult` (RGBA
  ``bytes``, digest, warnings, provenance) and writes nothing; with ``frame_id`` it
  renders that animation frame through :mod:`moanart.animation` (ADR-032);
* :func:`export_png` writes the RGBA PNG atomically and returns an
  :class:`~moanart.export.ExportManifest`;
* :func:`inspect_document` and :func:`capabilities` are read-only reports;
* :func:`resolve_region` resolves a semantic region by ID to its mask, the masks it
  depends on and its operations (ADR-022), delegating to :mod:`moanart.schema`;
* :func:`apply_edit` and :func:`edit_document` apply a typed edit batch atomically
  (section 15, ADR-024) and :func:`load_edit_batch` reads one, delegating to
  :mod:`moanart.editing`; a stale ``base_revision``/``base_snapshot`` is
  ``EditConflict``;
* :func:`analyze_clusters` reports the pixel clusters of the render and their
  artistic warnings, with region exceptions as evaluation configuration (sections 8
  and 19, ADR-027); it never modifies the document;
* :func:`evaluate_quality` reports hard checks, artistic warnings and metrics of the
  render (and of an animation's frames) with a :class:`QualityConfig` that is
  evaluation configuration, never document data (section 19, ADR-036); it has no
  score and never modifies the document.

Every return value is frozen and holds no NumPy array or Pillow image. Errors are
``moanart.core.errors`` classes (``ReadError`` for unreadable input files is
re-exported here), each with a stable ``code`` and CLI ``exit_code``.
:data:`MAX_SCALE` and :func:`~moanart.schema.snapshot_digest` are re-exported so callers
such as the CLI need nothing below the facade. :data:`PLANNED_FUNCTIONS` is empty:
every function of section 13 is implemented.
"""

from moanart.api.analysis import analyze_clusters
from moanart.api.editing import BatchSource, apply_edit, edit_document, load_edit_batch
from moanart.api.inspection import (
    AVAILABLE_FUNCTIONS,
    PLANNED_FUNCTIONS,
    BackendSummary,
    BudgetReport,
    Capabilities,
    DocumentReport,
    ExceededResource,
    LayerSummary,
    MaskSummary,
    OperationSummary,
    RegionSummary,
    capabilities,
    inspect_document,
)
from moanart.api.loading import DocumentSource, load_document
from moanart.api.quality import evaluate_quality
from moanart.api.services import export_png, render
from moanart.core.budget import Deadline, RenderLimits
from moanart.core.errors import EditConflict, ReadError
from moanart.editing import COMMAND_TYPES, EditBatch, EditResult
from moanart.export import MAX_SCALE, ExportManifest
from moanart.quality import (
    QUALITY_RULES,
    QualityConfig,
    QualityFinding,
    QualityReport,
    RegionSettings,
    Suppression,
)
from moanart.render import RenderResult, RenderWarning
from moanart.schema import (
    Document,
    ParseLimits,
    ResolvedRegion,
    resolve_region,
    snapshot_digest,
)
from moanart.techniques import (
    CLUSTER_RULES,
    Cluster,
    ClusterException,
    ClusterFinding,
    ClusterReport,
)

__all__ = [
    "AVAILABLE_FUNCTIONS",
    "CLUSTER_RULES",
    "COMMAND_TYPES",
    "MAX_SCALE",
    "PLANNED_FUNCTIONS",
    "QUALITY_RULES",
    "BackendSummary",
    "BatchSource",
    "BudgetReport",
    "Capabilities",
    "Cluster",
    "ClusterException",
    "ClusterFinding",
    "ClusterReport",
    "Deadline",
    "Document",
    "DocumentReport",
    "DocumentSource",
    "EditBatch",
    "EditConflict",
    "EditResult",
    "ExceededResource",
    "ExportManifest",
    "LayerSummary",
    "MaskSummary",
    "OperationSummary",
    "ParseLimits",
    "QualityConfig",
    "QualityFinding",
    "QualityReport",
    "ReadError",
    "RegionSettings",
    "RegionSummary",
    "RenderLimits",
    "RenderResult",
    "RenderWarning",
    "ResolvedRegion",
    "Suppression",
    "analyze_clusters",
    "apply_edit",
    "capabilities",
    "edit_document",
    "evaluate_quality",
    "export_png",
    "inspect_document",
    "load_document",
    "load_edit_batch",
    "render",
    "resolve_region",
    "snapshot_digest",
]
