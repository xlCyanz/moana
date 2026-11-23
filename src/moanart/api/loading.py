"""Loading documents from a caller-authorised path, bytes or mapping (MOANART.md section 13).

Only the application layer opens files: a path given to :func:`load_document` is
trusted because the caller chose it, never because a document named it. The file is
opened without blocking (``O_NONBLOCK`` where it exists), must be a regular file, and
is read with a bound of one byte over the parse limit, so an oversized file is rejected
by ``moanart.schema`` without reading it whole; then it is validated exactly like bytes.

Failures to read are :class:`~moanart.core.errors.ReadError` (exit code 5, ADR-020). Its
context carries a ``reason`` (``not_found``, ``is_directory``, ``not_a_file``,
``permission_denied``, ``io_error``), the file name (at most 255 characters) and the
``errno`` name, never the full path, mirroring ``moanart.export``.
"""

from __future__ import annotations

import errno
import os
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Final

from moanart.core.errors import ReadError, ValidationError
from moanart.schema import DEFAULT_PARSE_LIMITS, Document, ParseLimits, validate_document

__all__ = ["MAX_REPORTED_NAME", "DocumentSource", "load_document", "read_bounded", "source_path"]

type DocumentSource = str | os.PathLike[str] | bytes | Mapping[str, object]
"""A path chosen by the caller, UTF-8 JSON bytes or an already parsed mapping."""

MAX_REPORTED_NAME: Final = 255
"""Longest file name echoed in an error context."""

# Opening a FIFO or a device must not block; O_BINARY only exists on Windows.
_OPEN_FLAGS: Final = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)


def _read_failure(reason: str, name: str, cause: OSError | None = None) -> ReadError:
    context: dict[str, object] = {"reason": reason, "file_name": name}
    if cause is not None and cause.errno is not None:
        context["errno"] = errno.errorcode.get(cause.errno, str(cause.errno))
    return ReadError("the document file could not be read", context=context)


def _invalid_name() -> ValidationError:
    return ValidationError(
        "the document path is not representable on this system",
        context={"field": "path", "reason": "invalid_name"},
    )


def source_path(path: str | os.PathLike[str]) -> Path:
    """A caller-authorised path; JSON-looking, empty, NUL or unencodable text is rejected.

    Internal to ``moanart.api`` (shared with :mod:`moanart.api.editing`), not re-exported.
    """
    if isinstance(path, str) and path.lstrip().startswith(("{", "[")):
        raise ValidationError(
            "a str source is a path; pass bytes or a mapping for JSON content",
            context={"field": "source", "reason": "json_text"},
        )
    raw = os.fspath(path)
    if not isinstance(raw, str):
        raise TypeError("path must be text, not bytes")
    if not raw or "\x00" in raw:
        raise _invalid_name()
    try:
        raw.encode("utf-8")  # strict: lone surrogates are rejected on every platform
        os.fsencode(raw)
    except UnicodeEncodeError:
        raise _invalid_name() from None
    return Path(raw)


def _stat_is_directory(path: Path) -> bool:
    """Whether ``os.stat`` reports a directory; any failure counts as not one (ADR-039).

    Not ``os.path.isdir``, which bypasses ``os.stat`` on Windows. Private copy of the
    ``export``/``project`` helpers: ``api.loading`` imports neither (it loads no Pillow).
    """
    try:
        return stat.S_ISDIR(os.stat(path).st_mode)
    except (OSError, ValueError):
        return False


def _open(path: Path, name: str) -> int:
    try:
        return os.open(path, _OPEN_FLAGS)
    except FileNotFoundError as exc:
        raise _read_failure("not_found", name, exc) from None
    except IsADirectoryError as exc:
        raise _read_failure("is_directory", name, exc) from None
    except PermissionError as exc:
        # Windows reports opening a directory as a permission error.
        reason = "is_directory" if _stat_is_directory(path) else "permission_denied"
        raise _read_failure(reason, name, exc) from None
    except OSError as exc:
        raise _read_failure("io_error", name, exc) from None


def read_bounded(path: Path, limit: int) -> bytes:
    """At most ``limit + 1`` bytes of a regular file, enough to detect an oversized one.

    Internal to ``moanart.api`` (shared with :mod:`moanart.api.editing`), not re-exported.
    """
    name = path.name[:MAX_REPORTED_NAME]
    descriptor = _open(path, name)
    try:
        mode = os.fstat(descriptor).st_mode
    except OSError as exc:
        os.close(descriptor)
        raise _read_failure("io_error", name, exc) from None
    if not stat.S_ISREG(mode):
        os.close(descriptor)
        raise _read_failure("is_directory" if stat.S_ISDIR(mode) else "not_a_file", name)
    with os.fdopen(descriptor, "rb") as handle:
        try:
            return handle.read(limit + 1)
        except OSError as exc:
            raise _read_failure("io_error", name, exc) from None


def load_document(
    source: DocumentSource, *, limits: ParseLimits = DEFAULT_PARSE_LIMITS
) -> Document:
    """Read, validate and normalise a document into a frozen :class:`Document`.

    A ``str`` or ``os.PathLike`` is a path authorised by the caller (a ``str`` that
    starts with ``{`` or ``[`` is rejected: JSON goes in as bytes or a mapping);
    ``bytes`` are UTF-8 JSON; a ``Mapping`` is an already parsed tree. Raises
    ``ReadError`` when the file cannot be read and the ``moanart.schema`` errors
    otherwise (``ValidationError``, ``UnsupportedVersion``, ``UnsupportedOperation``,
    ``ReferenceError``).
    """
    if not isinstance(limits, ParseLimits):
        raise TypeError("limits must be a ParseLimits value")
    if isinstance(source, bytes | Mapping):
        return validate_document(source, limits=limits)
    if isinstance(source, str | os.PathLike):
        data = read_bounded(source_path(source), limits.max_bytes)
        return validate_document(data, limits=limits)
    raise TypeError("source must be a path, bytes or a mapping")
