"""Atomic, ID-targeted edit batches of MoanArt documents (MOANART.md section 15, ADR-024).

:func:`apply_batch` turns a validated :class:`~moanart.schema.Document` and a typed
:class:`EditBatch` (see :func:`parse_edit_batch`) into an :class:`EditResult` whose
document has ``revision + 1``, or raises without producing anything:
``EditConflict`` when the batch's ``base_revision`` or ``base_snapshot`` is not the
document's, and the ``moanart.core`` validation and reference errors otherwise. The
source document is never modified. ``editing`` depends only on ``core`` and
``schema`` (MOANART.md section 3): it neither renders nor touches the disk. The
``apply_edit`` signature of MOANART.md section 13 belongs to the facade, ``moanart.api``.

:class:`History` (ADR-026) keeps those revisions in memory: immutable snapshots
indexed by ``snapshot_digest``, a separate cursor for undo, redo and checkout, and
branches after an undo, bounded by :class:`HistoryLimits` without silent eviction.
Persisting it belongs to ``project`` (MOANA-020).

:func:`apply_commands` runs typed commands with the same rules but no precondition
and no new revision: the transient evaluation of an animation frame (ADR-032).
"""

from moanart.editing.apply import EditResult, apply_batch, apply_commands
from moanart.editing.batch import (
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
    SetParameters,
    SetVisibility,
    Translate,
    parse_edit_batch,
)
from moanart.editing.history import (
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
    "SetParameters",
    "SetVisibility",
    "Snapshot",
    "Translate",
    "apply_batch",
    "apply_commands",
    "canonical_batch",
    "parse_edit_batch",
]
