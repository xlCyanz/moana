"""Atomic file commit without accidental overwrite (MOANA.md section 18, ADR-019).

Bytes are written to a fresh sibling temporary file in the destination directory,
flushed and ``fsync``-ed, then committed:

* ``overwrite=False``: ``os.link(temporary, destination)``, which the operating
  system performs atomically and which fails if the destination exists. Two writers
  racing for the same name cannot both win, and an existing file is never replaced.
  A filesystem without hard links cannot give that guarantee, so the export fails
  explicitly instead of falling back to check-then-replace.
* ``overwrite=True``: ``os.replace(temporary, destination)``, atomic on the same
  filesystem.

The temporary file is always removed; ``overwrite=True`` on a symbolic link replaces
the link itself, not its target, and the new file takes default permissions. On any
failure the destination keeps its previous content and no partial success is reported.
Errors carry the file name and a reason, never the full path.
"""

from __future__ import annotations

import errno
import os
import secrets
import stat
from pathlib import Path
from typing import Final

from moana.core.errors import ExportError

__all__ = ["commit_bytes", "stat_is_directory"]

_TEMP_ATTEMPTS: Final = 8
_TEMP_NAME_CHARS: Final = 32  # keeps the temporary name within NAME_MAX for any valid name
_NO_LINK_ERRNOS: Final = frozenset(
    code
    for code in (
        getattr(errno, "EPERM", None),
        getattr(errno, "ENOTSUP", None),
        getattr(errno, "EOPNOTSUPP", None),
        getattr(errno, "EXDEV", None),
        getattr(errno, "EMLINK", None),
        getattr(errno, "ENOSYS", None),
    )
    if code is not None
)
# Windows: ERROR_INVALID_FUNCTION, ERROR_NOT_SUPPORTED, ERROR_NOT_SAME_DEVICE,
# ERROR_TOO_MANY_LINKS (FAT/exFAT and some network shares have no hard links).
_NO_LINK_WINERRORS: Final = frozenset({1, 50, 17, 1142})


def _failure(message: str, reason: str, name: str, cause: OSError | None = None) -> ExportError:
    context: dict[str, object] = {"reason": reason, "file_name": name}
    if cause is not None and cause.errno is not None:
        context["errno"] = errno.errorcode.get(cause.errno, str(cause.errno))
    return ExportError(message, context=context)


def _create_temporary(directory: Path, name: str) -> tuple[Path, int]:
    """A new sibling file opened exclusively, with umask-respecting permissions."""
    for _ in range(_TEMP_ATTEMPTS):
        candidate = directory / f".{name[:_TEMP_NAME_CHARS]}.{secrets.token_hex(8)}.tmp"
        try:
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
            return candidate, os.open(candidate, flags, 0o666)
        except FileExistsError:
            continue
        except PermissionError as exc:
            raise _failure(
                "destination directory is not writable", "permission_denied", name, exc
            ) from None
        except OSError as exc:
            raise _failure("cannot create a temporary file", "io_error", name, exc) from None
        except ValueError:  # unencodable or NUL-containing name
            raise _failure("the file name is not representable", "invalid_name", name) from None
    raise _failure("cannot create a unique temporary file", "io_error", name)


def _write_all(descriptor: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(descriptor, view)
        view = view[written:]
    os.fsync(descriptor)


def _sync_directory(directory: Path) -> None:
    """Persist the directory entry (POSIX); best effort where directories can't be opened."""
    if os.name == "nt":  # pragma: no cover - Windows has no directory fsync
        return
    try:
        descriptor = os.open(directory, os.O_RDONLY)
    except OSError:  # pragma: no cover - the commit already happened
        return
    try:
        os.fsync(descriptor)
    except OSError:  # pragma: no cover - some filesystems reject directory fsync
        pass
    finally:
        os.close(descriptor)


def _commit(temporary: Path, destination: Path, name: str, *, overwrite: bool) -> None:
    if overwrite:
        try:
            os.replace(temporary, destination)
        except PermissionError as exc:
            raise _failure(
                "destination cannot be replaced", "permission_denied", name, exc
            ) from None
        except OSError as exc:
            raise _failure("destination cannot be replaced", "io_error", name, exc) from None
        return
    try:
        os.link(temporary, destination)
    except FileExistsError:
        if _same_file(temporary, destination):  # e.g. NFS retry of a link that succeeded
            return
        raise _failure("destination already exists", "exists", name) from None
    except OSError as exc:
        if exc.errno in _NO_LINK_ERRNOS or getattr(exc, "winerror", None) in _NO_LINK_WINERRORS:
            raise _failure(
                "the destination filesystem cannot commit without replacing",
                "no_replace_unavailable",
                name,
                exc,
            ) from None
        raise _failure("destination cannot be created", "io_error", name, exc) from None


def _same_file(first: Path, second: Path) -> bool:
    try:
        return os.path.samefile(first, second)
    except OSError:
        return False


def stat_is_directory(path: str | Path) -> bool:
    """Whether ``os.stat`` reports a directory; any failure counts as not one (ADR-039).

    Only for naming the reason of a failure that already happened (``is_directory``
    or another one). ``os.path.isdir`` is not used: on Windows it bypasses ``os.stat``,
    so the reason would depend on the platform.
    """
    try:
        return stat.S_ISDIR(os.stat(path).st_mode)
    except (OSError, ValueError):
        return False


def _is_dir(path: Path) -> bool:
    """``True`` for a directory, ``False`` if absent; any other ``OSError`` propagates.

    ``Path.is_dir`` cannot be used: since Python 3.14 it returns ``False`` for every
    ``OSError``, so an unsearchable parent looked like a missing directory. Failing
    closed (ADR-039), a link loop (``ELOOP``) or an invalid Windows name is
    ``io_error`` with its ``errno``. A NUL in the name (``ValueError``) only reaches
    here when :func:`commit_bytes` is called directly (the export entry points
    reject it first); it counts as no directory and the temporary file creation
    reports ``invalid_name``.
    """
    try:
        return stat.S_ISDIR(os.stat(path).st_mode)
    except (FileNotFoundError, NotADirectoryError, ValueError):
        return False


def _check_destination(directory: Path, destination: Path, name: str) -> None:
    """Diagnose the destination before writing; never lets an ``OSError`` with a path escape."""
    try:
        if not _is_dir(directory):
            raise _failure("destination directory does not exist", "missing_directory", name)
        if _is_dir(destination):
            raise _failure("destination is a directory", "is_directory", name)
    except PermissionError as exc:
        raise _failure(
            "destination directory is not accessible", "permission_denied", name, exc
        ) from None
    except OSError as exc:
        raise _failure("destination cannot be inspected", "io_error", name, exc) from None


def commit_bytes(data: bytes, destination: Path, *, overwrite: bool) -> None:
    """Write ``data`` to ``destination`` atomically; see the module docstring."""
    name = destination.name
    directory = destination.parent
    _check_destination(directory, destination, name)
    temporary, descriptor = _create_temporary(directory, name)
    try:
        try:
            _write_all(descriptor, data)
        finally:
            os.close(descriptor)
        _commit(temporary, destination, name, overwrite=overwrite)
    except OSError as exc:
        raise _failure("writing the export failed", "io_error", name, exc) from None
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:  # moved by os.replace
            pass
        except OSError:  # pragma: no cover - leftover temporary is harmless
            pass
    _sync_directory(directory)
