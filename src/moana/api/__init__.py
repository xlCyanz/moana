"""Public Python facade of Moana (MOANA.md section 13, ADR-020).

The facade composes the implemented services and adds no algorithm of its own:

* :func:`load_document` reads a caller-authorised path, bytes or a mapping and
  returns a frozen, validated :class:`~moana.schema.Document`;
* :func:`render` returns an immutable :class:`~moana.render.RenderResult` (RGBA
  ``bytes``, digest, warnings, provenance) and writes nothing;
* :func:`export_png` writes the RGBA PNG atomically and returns an
  :class:`~moana.export.ExportManifest`;
* :func:`inspect_document` and :func:`capabilities` are read-only reports;
* :func:`resolve_region` resolves a semantic region by ID to its mask, the masks it
  depends on and its operations (ADR-022), delegating to :mod:`moana.schema`;
* :func:`apply_edit` and :func:`edit_document` apply a typed edit batch atomically
  (section 15, ADR-024) and :func:`load_edit_batch` reads one, delegating to
  :mod:`moana.editing`; a stale ``base_revision``/``base_snapshot`` is
  ``EditConflict``.

Every return value is frozen and holds no NumPy array or Pillow image. Errors are
``moana.core.errors`` classes (``ReadError`` for unreadable input files is
re-exported here), each with a stable ``code`` and CLI ``exit_code``.
:data:`MAX_SCALE` and :func:`~moana.schema.snapshot_digest` are re-exported so callers
such as the CLI need nothing below the facade. :data:`PLANNED_FUNCTIONS` is empty:
every function of section 13 is implemented.
"""

from moana.api.editing import BatchSource, apply_edit, edit_document, load_edit_batch
from moana.api.inspection import (
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
from moana.api.loading import DocumentSource, load_document
from moana.api.services import export_png, render
from moana.core.budget import Deadline, RenderLimits
from moana.core.errors import EditConflict, ReadError
from moana.editing import COMMAND_TYPES, EditBatch, EditResult
from moana.export import MAX_SCALE, ExportManifest
from moana.render import RenderResult, RenderWarning
from moana.schema import (
    Document,
    ParseLimits,
    ResolvedRegion,
    resolve_region,
    snapshot_digest,
)

__all__ = [
    "AVAILABLE_FUNCTIONS",
    "COMMAND_TYPES",
    "MAX_SCALE",
    "PLANNED_FUNCTIONS",
    "BackendSummary",
    "BatchSource",
    "BudgetReport",
    "Capabilities",
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
    "ReadError",
    "RegionSummary",
    "RenderLimits",
    "RenderResult",
    "RenderWarning",
    "ResolvedRegion",
    "apply_edit",
    "capabilities",
    "edit_document",
    "export_png",
    "inspect_document",
    "load_document",
    "load_edit_batch",
    "render",
    "resolve_region",
    "snapshot_digest",
]
