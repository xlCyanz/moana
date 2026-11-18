"""Public Python facade of Moana (MOANA.md section 13, ADR-020).

The facade composes the implemented services and adds no algorithm of its own:

* :func:`load_document` reads a caller-authorised path, bytes or a mapping and
  returns a frozen, validated :class:`~moana.schema.Document`;
* :func:`render` returns an immutable :class:`~moana.render.RenderResult` (RGBA
  ``bytes``, digest, warnings, provenance) and writes nothing;
* :func:`export_png` writes the RGBA PNG atomically and returns an
  :class:`~moana.export.ExportManifest`;
* :func:`inspect_document` and :func:`capabilities` are read-only reports.

Every return value is frozen and holds no NumPy array or Pillow image. Errors are
``moana.core.errors`` classes (``ReadError`` for unreadable input files is
re-exported here), each with a stable ``code`` and CLI ``exit_code``.
:data:`MAX_SCALE` and :func:`~moana.schema.snapshot_digest` are re-exported so callers
such as the CLI need nothing below the facade. ``apply_edit`` (section 15) is not
implemented yet; it is listed in :data:`PLANNED_FUNCTIONS`, not exported.
"""

from moana.api.inspection import (
    AVAILABLE_FUNCTIONS,
    PLANNED_FUNCTIONS,
    BudgetReport,
    Capabilities,
    DocumentReport,
    ExceededResource,
    LayerSummary,
    OperationSummary,
    capabilities,
    inspect_document,
)
from moana.api.loading import DocumentSource, load_document
from moana.api.services import export_png, render
from moana.core.budget import Deadline, RenderLimits
from moana.core.errors import ReadError
from moana.export import MAX_SCALE, ExportManifest
from moana.render import RenderResult, RenderWarning
from moana.schema import Document, ParseLimits, snapshot_digest

__all__ = [
    "AVAILABLE_FUNCTIONS",
    "MAX_SCALE",
    "PLANNED_FUNCTIONS",
    "BudgetReport",
    "Capabilities",
    "Deadline",
    "Document",
    "DocumentReport",
    "DocumentSource",
    "ExceededResource",
    "ExportManifest",
    "LayerSummary",
    "OperationSummary",
    "ParseLimits",
    "ReadError",
    "RenderLimits",
    "RenderResult",
    "RenderWarning",
    "capabilities",
    "export_png",
    "inspect_document",
    "load_document",
    "render",
    "snapshot_digest",
]
