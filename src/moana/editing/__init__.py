"""Atomic, ID-targeted edit batches of Moana documents (MOANA.md section 15, ADR-024).

:func:`apply_batch` turns a validated :class:`~moana.schema.Document` and a typed
:class:`EditBatch` (see :func:`parse_edit_batch`) into an :class:`EditResult` whose
document has ``revision + 1``, or raises without producing anything:
``EditConflict`` when the batch's ``base_revision`` or ``base_snapshot`` is not the
document's, and the ``moana.core`` validation and reference errors otherwise. The
source document is never modified. ``editing`` depends only on ``core`` and
``schema`` (MOANA.md section 3): it neither renders nor touches the disk. The
``apply_edit`` signature of MOANA.md section 13 belongs to the facade, ``moana.api``.

:class:`History` (ADR-026) keeps those revisions in memory: immutable snapshots
indexed by ``snapshot_digest``, a separate cursor for undo, redo and checkout, and
branches after an undo, bounded by :class:`HistoryLimits` without silent eviction.
Persisting it belongs to ``project`` (MOANA-020).
"""

from moana.editing.apply import EditResult, apply_batch
from moana.editing.batch import (
    COMMAND_TYPES,
    MAX_TRANSLATION,
    BatchInput,
    EditBatch,
    EditCommand,
    InsertOperation,
    Remove,
    Reorder,
    ReplacePaletteColor,
    SetColor,
    SetGeometry,
    SetVisibility,
    Translate,
    parse_edit_batch,
)
from moana.editing.history import (
    DEFAULT_HISTORY_LIMITS,
    History,
    HistoryLimits,
    Snapshot,
    canonical_batch,
)

__all__ = [
    "COMMAND_TYPES",
    "DEFAULT_HISTORY_LIMITS",
    "MAX_TRANSLATION",
    "BatchInput",
    "EditBatch",
    "EditCommand",
    "EditResult",
    "History",
    "HistoryLimits",
    "InsertOperation",
    "Remove",
    "Reorder",
    "ReplacePaletteColor",
    "SetColor",
    "SetGeometry",
    "SetVisibility",
    "Snapshot",
    "Translate",
    "apply_batch",
    "canonical_batch",
    "parse_edit_batch",
]
