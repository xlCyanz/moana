"""Immutable in-memory edit history with undo, redo and branches (MOANA.md §15, ADR-026).

A :class:`History` is a frozen value. Every method that changes it returns a new
``History`` and leaves the receiver untouched, so a caller can keep any earlier value.

* Snapshots are indexed by their identity, :func:`moana.schema.snapshot_digest`. Each
  :class:`Snapshot` stores the exact frozen ``Document``, the digest of its parent, the
  canonical JSON of the batch that produced it, the IDs that batch touched and its
  revision, which is local to the branch and never a key.
* A cursor selects the current snapshot. :meth:`History.undo`, :meth:`History.redo`
  and :meth:`History.checkout` only move it; :meth:`History.edit` is the only way to
  add a snapshot, through :func:`~moana.editing.apply_batch` on the cursor's document.
* States are never rebuilt with inverse operations: navigation returns the stored
  ``Document`` object itself.
* Editing after an undo starts a branch at the cursor. It replaces only the cursor's
  active redo child; the previous child and its descendants stay reachable by digest.
* :class:`HistoryLimits` bounds the snapshots and their canonical JSON bytes. A
  history that would exceed either raises ``BudgetExceeded`` before anything is
  added; nothing is evicted. The byte measure is deterministic and proportional to
  the stored documents, but it is not a bound on RAM (ADR-026 §5).

:meth:`History.start` is the normal entry point. The public constructor validates a
hand-built history in full (``ValidationError``, ``reason: invalid_history``), so
``project`` can rebuild one from persisted snapshots (MOANA-020).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from moana.core.coordinates import require_int
from moana.core.errors import BudgetExceeded, EditConflict, ReferenceError, ValidationError
from moana.core.limits import MAX_HISTORY_BYTES, MAX_HISTORY_SNAPSHOTS
from moana.editing.apply import apply_batch
from moana.editing.batch import BatchInput, EditBatch, parse_edit_batch
from moana.schema import (
    DEFAULT_PARSE_LIMITS,
    Document,
    ParseLimits,
    canonical_json,
    snapshot_digest,
)

__all__ = [
    "DEFAULT_HISTORY_LIMITS",
    "History",
    "HistoryLimits",
    "Snapshot",
    "canonical_batch",
]


@dataclass(frozen=True, slots=True)
class HistoryLimits:
    """Bounds of one history; a host may lower them, never raise them.

    ``max_snapshots`` counts stored snapshots, the root included. ``max_bytes`` bounds
    the sum of :attr:`Snapshot.size` (canonical document plus canonical batch), a
    deterministic measure that is not a bound on the memory Python uses.
    """

    max_snapshots: int = MAX_HISTORY_SNAPSHOTS
    max_bytes: int = MAX_HISTORY_BYTES

    def __post_init__(self) -> None:
        require_int(self.max_snapshots, "max_snapshots", minimum=1, maximum=MAX_HISTORY_SNAPSHOTS)
        require_int(self.max_bytes, "max_bytes", minimum=1, maximum=MAX_HISTORY_BYTES)


DEFAULT_HISTORY_LIMITS: Final = HistoryLimits()


def _canonical_json(tree: object) -> bytes:
    """The encoding of :func:`moana.schema.canonical_json` for any JSON tree.

    A test fixes that both agree on normalised documents.
    """
    return json.dumps(
        tree, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def canonical_batch(batch: EditBatch) -> bytes:
    """Canonical JSON of a batch: sorted keys, no spaces, UTF-8, explicit ``null``."""
    return _canonical_json(batch.model_dump(mode="json"))


@dataclass(frozen=True, slots=True)
class Snapshot:
    """One stored state; ``parent`` and ``batch`` are ``None`` only for the root.

    ``batch`` is the canonical JSON of the batch that first produced ``document`` from
    ``parent`` (bytes, so it cannot be mutated; :func:`parse_edit_batch` reads it
    back). Another batch reaching the same digest from the same parent reuses this
    snapshot and replaces neither ``batch`` nor ``affected_ids``. ``size`` is what the
    snapshot counts against ``HistoryLimits.max_bytes``.
    """

    digest: str
    document: Document
    parent: str | None
    batch: bytes | None
    affected_ids: tuple[str, ...]
    size: int

    @property
    def revision(self) -> int:
        """Revision of the document, local to its branch; never an identity."""
        return self.document.revision


def _frozen[K, V](mapping: Mapping[K, V]) -> Mapping[K, V]:
    return MappingProxyType(dict(mapping))


# --- validation of a hand-built history ---------------------------------------------


def _invalid(message: str) -> ValidationError:
    return ValidationError(message, context={"reason": "invalid_history"})


def _check_snapshot(
    digest: object, snapshot: object, root: str, seen: Mapping[str, Snapshot]
) -> None:
    """One stored node: its key, digest, size, parent (stored earlier) and revision."""
    if not isinstance(snapshot, Snapshot) or snapshot.digest != digest:
        raise _invalid("a snapshot is not stored under its digest")
    if not isinstance(snapshot.document, Document) or type(snapshot.size) is not int:
        raise _invalid("a snapshot has a wrong document or size type")
    if snapshot.size < 0 or snapshot_digest(snapshot.document) != digest:
        raise _invalid("a snapshot digest or size does not match its document")
    is_root = snapshot.parent is None
    if is_root != (digest == root) or is_root != (snapshot.batch is None):
        raise _invalid("only the root has no parent and no batch")
    if snapshot.parent is not None:
        parent = seen.get(snapshot.parent)
        if parent is None or snapshot.revision != parent.revision + 1:
            raise _invalid("a parent is not stored before its child at the previous revision")


def _derived_children(snapshots: Mapping[str, Snapshot]) -> dict[str, tuple[str, ...]]:
    children: dict[str, tuple[str, ...]] = {}
    for digest, snapshot in snapshots.items():
        if snapshot.parent is not None:
            children[snapshot.parent] = (*children.get(snapshot.parent, ()), digest)
    return children


def _check_history(history: History) -> None:
    """Every invariant that :meth:`History.start` and the methods keep, in full."""
    seen: dict[str, Snapshot] = {}
    for digest, snapshot in history.snapshots.items():
        _check_snapshot(digest, snapshot, history.root, seen)
        seen[digest] = snapshot
    if history.root not in seen or history.cursor not in seen:
        raise _invalid("the root or the cursor is not a stored snapshot")
    children = _derived_children(seen)
    if dict(history.children) != children:
        raise _invalid("children do not match the parents of the snapshots")
    for parent, child in history.redo_children.items():
        if child not in children.get(parent, ()):
            raise _invalid("an active redo is not a child of its snapshot")
    if history.total_bytes != sum(snapshot.size for snapshot in seen.values()):
        raise _invalid("total_bytes is not the sum of the snapshot sizes")
    _check_count(history.limits, len(seen) - 1)
    _check_bytes(history.limits, 0, history.total_bytes)


_FIELDS: Final = (
    "root",
    "cursor",
    "limits",
    "snapshots",
    "children",
    "redo_children",
    "total_bytes",
)


@dataclass(frozen=True, slots=True)
class History:
    """Frozen tree of snapshots plus a cursor; build one with :meth:`start`.

    ``snapshots`` keeps insertion order (a parent before its children), ``children``
    lists each node's children in creation order and ``redo_children`` the active
    redo child of each node. The constructor copies every mapping into a read-only
    one and validates the whole tree (``invalid_history``; ``BudgetExceeded`` over
    ``limits``), which costs one digest per snapshot; the methods build their
    results from values they keep valid, without revalidating.
    """

    root: str
    cursor: str
    limits: HistoryLimits
    snapshots: Mapping[str, Snapshot]
    children: Mapping[str, tuple[str, ...]]
    redo_children: Mapping[str, str]
    total_bytes: int

    def __post_init__(self) -> None:
        if not isinstance(self.limits, HistoryLimits):
            raise TypeError("limits must be a HistoryLimits value")
        for name in ("snapshots", "children", "redo_children"):
            value = getattr(self, name)
            if not isinstance(value, Mapping):
                raise TypeError(f"{name} must be a mapping")
            object.__setattr__(self, name, _frozen(value))
        _check_history(self)

    def __hash__(self) -> int:
        """Consistent with ``==``: equal histories share these four values."""
        return hash((self.root, self.cursor, self.total_bytes, len(self.snapshots)))

    @classmethod
    def _trusted(cls, *values: object) -> History:
        """Build from values the methods already keep valid, without revalidating."""
        history = object.__new__(cls)
        for name, value in zip(_FIELDS, values, strict=True):
            object.__setattr__(history, name, value)
        return history

    @classmethod
    def start(
        cls, document: Document, *, limits: HistoryLimits = DEFAULT_HISTORY_LIMITS
    ) -> History:
        """A history whose root and cursor are ``document``.

        Raises ``BudgetExceeded`` when the document alone exceeds ``limits.max_bytes``.
        """
        if not isinstance(document, Document):
            raise TypeError("document must be a moana.schema.Document")
        if not isinstance(limits, HistoryLimits):
            raise TypeError("limits must be a HistoryLimits value")
        size = len(canonical_json(document))
        _check_bytes(limits, 0, size)
        digest = snapshot_digest(document)
        root = Snapshot(digest, document, None, None, (), size)
        empty: Mapping[str, str] = _frozen({})
        return cls._trusted(digest, digest, limits, _frozen({digest: root}), empty, empty, size)

    # --- reading ----------------------------------------------------------------------

    @property
    def current(self) -> Snapshot:
        """The snapshot under the cursor."""
        return self.snapshots[self.cursor]

    @property
    def document(self) -> Document:
        """The stored document under the cursor (the same object, not a copy)."""
        return self.current.document

    def __len__(self) -> int:
        """Number of stored snapshots, the root included."""
        return len(self.snapshots)

    def __contains__(self, digest: object) -> bool:
        """Whether ``digest`` names a stored snapshot."""
        return digest in self.snapshots

    def snapshot(self, digest: str) -> Snapshot:
        """The stored snapshot ``digest``; ``ReferenceError`` if there is none."""
        if not isinstance(digest, str):
            raise TypeError("digest must be a string")
        found = self.snapshots.get(digest)
        if found is None:
            raise ReferenceError(
                "the snapshot is not in this history", context={"reason": "unknown_snapshot"}
            )
        return found

    def children_of(self, digest: str) -> tuple[str, ...]:
        """Digests created from ``digest``, in creation order (one per branch)."""
        self.snapshot(digest)
        return self.children.get(digest, ())

    def leaves(self) -> tuple[str, ...]:
        """Tip of every branch: snapshots without children, in insertion order."""
        return tuple(digest for digest in self.snapshots if digest not in self.children)

    @property
    def can_undo(self) -> bool:
        """Whether the cursor has a parent."""
        return self.current.parent is not None

    @property
    def can_redo(self) -> bool:
        """Whether the cursor has an active redo child."""
        return self.cursor in self.redo_children

    # --- navigation (never creates a snapshot) ----------------------------------------

    def _moved(self, cursor: str, redo_children: Mapping[str, str]) -> History:
        return History._trusted(
            self.root,
            cursor,
            self.limits,
            self.snapshots,
            self.children,
            redo_children,
            self.total_bytes,
        )

    def undo(self) -> History:
        """Move the cursor to its parent; the left snapshot becomes the active redo.

        Raises ``ValidationError`` (``reason: no_parent``) at the root.
        """
        parent = self.current.parent
        if parent is None:
            raise ValidationError(
                "the cursor is at the root of the history", context={"reason": "no_parent"}
            )
        return self._moved(parent, _frozen({**self.redo_children, parent: self.cursor}))

    def redo(self) -> History:
        """Move the cursor to its active redo child.

        Raises ``ValidationError`` (``reason: no_redo``) when there is none: at the tip
        of a branch, or after an edit replaced it.
        """
        child = self.redo_children.get(self.cursor)
        if child is None:
            raise ValidationError(
                "the cursor has no active redo snapshot", context={"reason": "no_redo"}
            )
        return self._moved(child, self.redo_children)

    def checkout(self, digest: str) -> History:
        """Select any stored snapshot by digest; ``ReferenceError`` if unknown.

        It only moves the cursor: no snapshot, revision or redo change.
        """
        return self._moved(self.snapshot(digest).digest, self.redo_children)

    # --- editing (the only way to add a snapshot) -------------------------------------

    def edit(
        self, batch: BatchInput, *, parse_limits: ParseLimits = DEFAULT_PARSE_LIMITS
    ) -> History:
        """Apply ``batch`` to the cursor's document and move the cursor to the result.

        The batch's ``base_revision`` and ``base_snapshot`` must be the cursor's
        (``EditConflict`` otherwise); every error of :func:`apply_batch` propagates and
        leaves no trace. The new snapshot becomes the cursor's active redo child,
        which is all an edit after an undo invalidates. ``BudgetExceeded`` is raised
        before adding when ``HistoryLimits`` would be exceeded. A result whose digest
        is already stored is reused when its parent is the cursor (its batch and
        ``affected_ids`` stay those of the first edit, and its active redo is cleared,
        as after any edit); under another parent it is ``EditConflict``
        (``existing_snapshot``), retryable with :meth:`checkout`. After an edit
        ``can_redo`` is always false. ``parse_limits`` bound reading the batch and
        validating the result, as in :func:`apply_batch`; the batch is parsed once.
        """
        parsed = parse_edit_batch(batch, limits=parse_limits)
        result = apply_batch(self.document, parsed, limits=parse_limits)
        known = self.snapshots.get(result.snapshot)
        if known is not None:
            return self._reused(known)
        _check_count(self.limits, len(self.snapshots))
        encoded = canonical_batch(parsed)
        size = len(canonical_json(result.document)) + len(encoded)
        _check_bytes(self.limits, self.total_bytes, size)
        added = Snapshot(
            result.snapshot, result.document, self.cursor, encoded, result.affected_ids, size
        )
        return self._added(added)

    def _reused(self, known: Snapshot) -> History:
        if known.parent != self.cursor:
            raise EditConflict(
                "the edited document is already stored under another parent",
                context={"reason": "existing_snapshot", "snapshot": known.digest},
            )
        # Like a new snapshot, the result of an edit has no active redo: its children
        # stay stored and reachable by digest, but redo no longer leads to them.
        redo = {**self.redo_children, self.cursor: known.digest}
        redo.pop(known.digest, None)
        return self._moved(known.digest, _frozen(redo))

    def _added(self, added: Snapshot) -> History:
        parent = self.cursor
        siblings = self.children.get(parent, ())
        return History._trusted(
            self.root,
            added.digest,
            self.limits,
            _frozen({**self.snapshots, added.digest: added}),
            _frozen({**self.children, parent: (*siblings, added.digest)}),
            _frozen({**self.redo_children, parent: added.digest}),
            self.total_bytes + added.size,
        )


def _check_count(limits: HistoryLimits, stored: int) -> None:
    if stored + 1 > limits.max_snapshots:
        raise BudgetExceeded(
            "the history is at its snapshot budget",
            context={
                "resource": "history_snapshots",
                "limit": limits.max_snapshots,
                "estimated": stored + 1,
            },
        )


def _check_bytes(limits: HistoryLimits, stored: int, size: int) -> None:
    if stored + size > limits.max_bytes:
        raise BudgetExceeded(
            "the history would exceed its byte budget",
            context={
                "resource": "history_bytes",
                "limit": limits.max_bytes,
                "estimated": stored + size,
            },
        )
