"""Edit entry points of the public facade (MOANA.md sections 13 and 15, ADR-024).

They compose :mod:`moana.editing` without reimplementing it. :func:`load_edit_batch`
reads a batch from a caller-authorised path with the same bounded, non-blocking
reading as :func:`~moana.api.load_document` (or from bytes or a mapping);
:func:`apply_edit` returns the new :class:`~moana.schema.Document` and
:func:`edit_document` the full :class:`~moana.editing.EditResult` (new snapshot and
affected IDs). Nothing is written: persisting the new revision belongs to
``project`` (MOANA-020).
"""

from __future__ import annotations

import os
from collections.abc import Mapping

from moana.api.loading import read_bounded, source_path
from moana.core.errors import ReadError
from moana.editing import EditBatch, EditResult, apply_batch, parse_edit_batch
from moana.schema import DEFAULT_PARSE_LIMITS, Document, ParseLimits

__all__ = ["BatchSource", "apply_edit", "edit_document", "load_edit_batch"]

type BatchSource = EditBatch | str | os.PathLike[str] | bytes | Mapping[str, object]
"""A batch value, a path chosen by the caller, UTF-8 JSON bytes or a parsed mapping."""


def _read_batch(path: str | os.PathLike[str], limits: ParseLimits) -> bytes:
    try:
        return read_bounded(source_path(path), limits.max_bytes)
    except ReadError as error:
        raise ReadError("the edit batch file could not be read", context=error.context) from None


def load_edit_batch(
    source: BatchSource, *, limits: ParseLimits = DEFAULT_PARSE_LIMITS
) -> EditBatch:
    """Read and validate an edit batch into a frozen :class:`~moana.editing.EditBatch`.

    Paths follow the rules of ``load_document`` (``ReadError`` without the full
    path; a ``str`` that looks like JSON is rejected). Raises ``ValidationError`` or
    ``UnsupportedVersion`` for an invalid batch.
    """
    if not isinstance(limits, ParseLimits):
        raise TypeError("limits must be a ParseLimits value")
    if isinstance(source, str | os.PathLike):
        return parse_edit_batch(_read_batch(source, limits), limits=limits)
    return parse_edit_batch(source, limits=limits)


def edit_document(
    document: Document, batch: BatchSource, *, limits: ParseLimits = DEFAULT_PARSE_LIMITS
) -> EditResult:
    """Apply ``batch`` atomically; return the new document, snapshot and affected IDs.

    Raises ``EditConflict`` (exit code 4) when the batch's ``base_revision`` or
    ``base_snapshot`` is not the document's, and ``ValidationError``,
    ``ReferenceError``, ``UnsupportedOperation``, ``UnsupportedVersion`` or
    ``ReadError`` otherwise; ``document`` is never modified.
    """
    return apply_batch(document, load_edit_batch(batch, limits=limits), limits=limits)


def apply_edit(
    document: Document, batch: BatchSource, *, limits: ParseLimits = DEFAULT_PARSE_LIMITS
) -> Document:
    """The new document of :func:`edit_document`, with ``revision + 1``."""
    return edit_document(document, batch, limits=limits).document
