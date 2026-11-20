"""Confined reads and atomic writes of project files (MOANA.md sections 16 and 20, ADR-029).

**Paths.** A path passed to the API is chosen by the caller and resolved by the
operating system, symbolic links included, like any file API (ADR-020). Every path
*inside* a project is relative, derived from a hash, and never follows a link: a
link or junction there is refused.

**Confinement.** :class:`Folder` is an opened directory. Where the platform supports
``dir_fd`` (POSIX: :data:`DIR_FD`), each level is created and opened relative to its
parent's descriptor with ``O_DIRECTORY | O_NOFOLLOW``, and files are opened, linked,
renamed and synced through those descriptors. Replacing a checked directory by a
link after the check therefore cannot redirect a read or a write outside the root.
Without ``dir_fd`` (Windows), :class:`Folder` falls back to paths with an ``lstat``
and junction check before each use; the remaining race window is documented in
ADR-029 section 8.

**Writes** follow ADR-019 without importing ``export`` (MOANA.md section 3), with the
same reasons: bytes go to a fresh sibling temporary file (``O_EXCL``), are written and
``fsync``-ed, then committed with ``os.link`` (never replaces; ``exists``, or
``no_replace_unavailable`` on a filesystem without hard links; an ``EEXIST`` for the
same file, as after an NFS retry, is success) or ``os.replace``. The temporary file is
always removed and the destination keeps its previous content on any failure.
Errors carry a ``reason``, a relative or bare file name (never the full path) and the
``errno`` name.
"""

from __future__ import annotations

import contextlib
import errno
import os
import secrets
import stat
from pathlib import Path
from typing import Final, Self

from moana.core.errors import ExportError, MoanaError, ReadError, ValidationError

__all__ = [
    "DIR_FD",
    "Folder",
    "caller_path",
    "read_caller_file",
    "read_failure",
    "stat_is_directory",
    "write_failure",
]

MAX_REPORTED_NAME: Final = 255
_TEMP_ATTEMPTS: Final = 8
_TEMP_NAME_CHARS: Final = 32
_READ_CHUNK: Final = 1 << 20
_NOFOLLOW: Final = getattr(os, "O_NOFOLLOW", 0)
_DIRECTORY: Final = getattr(os, "O_DIRECTORY", 0)
_BASE_READ: Final = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
_WRITE_FLAGS: Final = os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW | getattr(os, "O_BINARY", 0)
_DIR_FLAGS: Final = os.O_RDONLY | _DIRECTORY | _NOFOLLOW
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
# Directory fsync is unsupported on some filesystems; that is not a failure.
_NO_SYNC_ERRNOS: Final = frozenset(
    code
    for code in (errno.EINVAL, getattr(errno, "ENOTSUP", None), getattr(errno, "EOPNOTSUPP", None))
    if code is not None
)

DIR_FD: Final[bool] = (
    os.name != "nt"
    and bool(_DIRECTORY and _NOFOLLOW)
    and {os.open, os.mkdir, os.stat, os.unlink, os.link, os.rename} <= os.supports_dir_fd
)
"""Whether :class:`Folder` confines through directory descriptors (POSIX)."""


def _errno_context(reason: str, name: str, cause: OSError | None) -> dict[str, object]:
    context: dict[str, object] = {"reason": reason, "file_name": name[:MAX_REPORTED_NAME]}
    if cause is not None and cause.errno is not None:
        context["errno"] = errno.errorcode.get(cause.errno, str(cause.errno))
    return context


def write_failure(
    message: str, reason: str, name: str, cause: OSError | None = None
) -> ExportError:
    """``ExportError`` of a project write; ``name`` is relative to the project root."""
    return ExportError(message, context=_errno_context(reason, name, cause))


def read_failure(message: str, reason: str, name: str, cause: OSError | None = None) -> ReadError:
    """``ReadError`` of a project read; ``name`` is relative to the project root."""
    return ReadError(message, context=_errno_context(reason, name, cause))


def caller_path(path: object) -> Path:
    """A path chosen by the caller; empty, NUL-containing or unencodable text is rejected."""
    if not isinstance(path, str | os.PathLike):
        raise TypeError("path must be a str or os.PathLike")
    raw = os.fspath(path)
    if not isinstance(raw, str):
        raise TypeError("path must be text, not bytes")
    try:
        if not raw or "\x00" in raw:
            raise UnicodeEncodeError("utf-8", raw, 0, 1, "empty or NUL")
        raw.encode("utf-8")  # strict: lone surrogates are rejected on every platform
        os.fsencode(raw)
    except UnicodeEncodeError:
        raise ValidationError(
            "the path is not representable on this system",
            context={"field": "path", "reason": "invalid_name"},
        ) from None
    return Path(raw)


def _is_link(path: Path) -> bool:
    return os.path.islink(path) or os.path.isjunction(path)


def _read_descriptor(descriptor: int, limit: int, name: str, *, zip_limit: int | None) -> bytes:
    """At most ``limit + 1`` bytes of a regular file (``zip_limit`` after a ZIP signature)."""
    try:
        mode = os.fstat(descriptor).st_mode
        if not stat.S_ISREG(mode):
            reason = "is_directory" if stat.S_ISDIR(mode) else "not_a_file"
            raise read_failure("a project path is not a regular file", reason, name)
        chunks: list[bytes] = []
        remaining = limit + 1
        first = True
        while remaining > 0:
            chunk = os.read(descriptor, min(remaining, 4 if first else _READ_CHUNK))
            if not chunk:
                break
            if first and zip_limit is not None and chunk.startswith(b"PK"):
                remaining = zip_limit + 1
            first = False
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)
    except OSError as exc:
        raise read_failure("a project file cannot be read", "io_error", name, exc) from None
    finally:
        os.close(descriptor)


def stat_is_directory(path: Path) -> bool:
    """Whether ``os.stat`` reports a directory; any failure counts as not one (ADR-039).

    Used instead of ``os.path.isdir`` (which on Windows bypasses ``os.stat``) and
    ``Path.is_dir`` (whose error handling changed in Python 3.14): one primitive
    classifies the same way on every platform and version. ``project`` does not import
    ``export``, hence its own copy of ``moana.export.atomic.stat_is_directory``.
    """
    try:
        return stat.S_ISDIR(os.stat(path).st_mode)
    except (OSError, ValueError):
        return False


def read_caller_file(path: Path, limit: int, *, zip_limit: int | None = None) -> bytes:
    """Bounded read of a file the caller named (links followed, opened without blocking).

    Reads at most ``limit + 1`` bytes, or ``zip_limit + 1`` when the file starts with
    ``PK`` and ``zip_limit`` is given, so a JSON file is never read beyond its bound.
    """
    name = path.name
    try:
        descriptor = os.open(path, _BASE_READ)
    except FileNotFoundError as exc:
        raise read_failure("the project file is missing", "not_found", name, exc) from None
    except PermissionError as exc:
        reason = "is_directory" if stat_is_directory(path) else "permission_denied"
        raise read_failure("the project file cannot be opened", reason, name, exc) from None
    except OSError as exc:
        reason = "is_directory" if stat_is_directory(path) else "io_error"
        raise read_failure("the project file cannot be opened", reason, name, exc) from None
    return _read_descriptor(descriptor, limit, name, zip_limit=zip_limit)


class Folder:
    """An opened project directory: confined creation, reads, writes and syncs.

    ``name`` is the directory relative to the project root (``.`` for the root).
    ``writing`` selects ``ExportError`` or ``ReadError`` for failures. Use it as a
    context manager; children must be closed before their parent.
    """

    __slots__ = ("_fd", "_path", "name", "writing")

    def __init__(self, path: Path, fd: int | None, name: str, *, writing: bool) -> None:
        """Wrap an already opened directory; use :meth:`open_root` or :meth:`child`."""
        self._path = path
        self._fd = fd
        self.name = name
        self.writing = writing

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        """Release the directory descriptor, if any."""
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    def _fail(
        self, message: str, reason: str, name: str, cause: OSError | None = None
    ) -> MoanaError:
        if self.writing:
            return write_failure(message, reason, name, cause)
        return read_failure(message, reason, name, cause)

    def _relative(self, part: str) -> str:
        return part if self.name == "." else f"{self.name}/{part}"

    # --- opening ---------------------------------------------------------------------

    @classmethod
    def open_root(cls, path: Path, *, create: bool, writing: bool) -> Folder:
        """Open the caller's root directory (links in the caller's path are followed).

        With ``create``, a missing root is created (one level; its parent must exist).
        """
        probe = cls(path, None, ".", writing=writing)
        try:
            if create:
                with contextlib.suppress(FileExistsError):
                    os.mkdir(path)
            if DIR_FD:
                return cls(path, os.open(path, os.O_RDONLY | _DIRECTORY), ".", writing=writing)
            if not stat.S_ISDIR(os.stat(path).st_mode):
                raise NotADirectoryError(errno.ENOTDIR, "not a directory")
            return probe
        except FileNotFoundError as exc:
            reason = "missing_directory" if writing else "not_found"
            raise probe._fail("the project directory does not exist", reason, ".", exc) from None
        except NotADirectoryError as exc:
            raise probe._fail(
                "the project path is not a directory", "not_a_directory", ".", exc
            ) from None
        except PermissionError as exc:
            raise probe._fail(
                "the project directory is not accessible", "permission_denied", ".", exc
            ) from None
        except OSError as exc:
            raise probe._fail(
                "the project directory cannot be opened", "io_error", ".", exc
            ) from None

    def lstat_mode(self, part: str) -> int | None:
        """``lstat`` mode of ``part`` (never follows it), ``None`` when absent."""
        try:
            if self._fd is not None:
                return os.stat(part, dir_fd=self._fd, follow_symlinks=False).st_mode
            return os.lstat(self._path / part).st_mode
        except FileNotFoundError:
            return None
        except PermissionError as exc:
            raise self._fail(
                "a project path is not accessible", "permission_denied", self._relative(part), exc
            ) from None
        except OSError as exc:
            raise self._fail(
                "a project path cannot be inspected", "io_error", self._relative(part), exc
            ) from None

    def exists(self, part: str) -> bool:
        """Whether ``part`` exists in this directory, links included."""
        return self.lstat_mode(part) is not None

    def child(self, part: str, *, create: bool) -> Folder:
        """Open (and with ``create``, make) the subdirectory ``part``; never a link."""
        name = self._relative(part)
        unsafe = "unsafe_path" if self.writing else "not_a_file"
        if create:
            try:
                if self._fd is not None:
                    os.mkdir(part, dir_fd=self._fd)
                else:
                    os.mkdir(self._path / part)
            except FileExistsError:
                pass
            except PermissionError as exc:
                raise self._fail(
                    "a directory is not writable", "permission_denied", name, exc
                ) from None
            except OSError as exc:
                raise self._fail("a directory cannot be created", "io_error", name, exc) from None
        if self._fd is None:
            return self._child_by_path(part, name, unsafe)
        try:
            descriptor = os.open(part, _DIR_FLAGS, dir_fd=self._fd)
        except FileNotFoundError as exc:
            raise self._fail("a project directory is missing", "not_found", name, exc) from None
        except OSError as exc:
            mode = self.lstat_mode(part)
            if mode is not None and stat.S_ISLNK(mode):
                raise self._fail("a project directory is a link", unsafe, name, exc) from None
            if mode is not None and not stat.S_ISDIR(mode):
                raise self._fail(
                    "a project path is not a directory", "not_a_directory", name, exc
                ) from None
            raise self._fail(
                "a project directory cannot be opened", "io_error", name, exc
            ) from None
        return Folder(self._path / part, descriptor, name, writing=self.writing)

    def _child_by_path(self, part: str, name: str, unsafe: str) -> Folder:
        path = self._path / part
        mode = self.lstat_mode(part)
        if mode is None:
            raise self._fail("a project directory is missing", "not_found", name)
        if _is_link(path):
            raise self._fail("a project directory is a link", unsafe, name)
        if not stat.S_ISDIR(mode):
            raise self._fail("a project path is not a directory", "not_a_directory", name)
        return Folder(path, None, name, writing=self.writing)

    # --- reading ---------------------------------------------------------------------

    def read(self, part: str, limit: int) -> bytes:
        """At most ``limit + 1`` bytes of the regular file ``part`` (never a link).

        ``ReadError`` reasons: ``not_found``, ``is_directory``, ``not_a_file`` (a link,
        a FIFO or a device), ``permission_denied`` and ``io_error``.
        """
        name = self._relative(part)
        try:
            if self._fd is not None:
                descriptor = os.open(part, _BASE_READ | _NOFOLLOW, dir_fd=self._fd)
            else:
                if _is_link(self._path / part):
                    raise read_failure("a project file is a link", "not_a_file", name)
                descriptor = os.open(self._path / part, _BASE_READ | _NOFOLLOW)
        except FileNotFoundError as exc:
            raise read_failure("a project file is missing", "not_found", name, exc) from None
        except OSError as exc:
            raise read_failure(
                "a project file cannot be opened", self._open_reason(part, exc), name, exc
            ) from None
        return _read_descriptor(descriptor, limit, name, zip_limit=None)

    def _open_reason(self, part: str, exc: OSError) -> str:
        try:
            mode = self.lstat_mode(part)
        except MoanaError:
            mode = None
        if mode is not None and stat.S_ISDIR(mode):
            return "is_directory"
        if exc.errno == errno.ELOOP or (mode is not None and stat.S_ISLNK(mode)):
            return "not_a_file"
        return "permission_denied" if isinstance(exc, PermissionError) else "io_error"

    # --- writing ---------------------------------------------------------------------

    def _target(self, part: str) -> str | Path:
        return part if self._fd is not None else self._path / part

    def _create_temporary(self, part: str, name: str) -> tuple[str, int]:
        stem = part[:_TEMP_NAME_CHARS]
        for _ in range(_TEMP_ATTEMPTS):
            candidate = f".{stem}.{secrets.token_hex(8)}.tmp"
            try:
                return candidate, os.open(
                    self._target(candidate), _WRITE_FLAGS, 0o666, dir_fd=self._fd
                )
            except FileExistsError:
                continue
            except PermissionError as exc:
                raise write_failure(
                    "destination directory is not writable", "permission_denied", name, exc
                ) from None
            except OSError as exc:
                raise write_failure(
                    "cannot create a temporary file", "io_error", name, exc
                ) from None
            except ValueError:  # unencodable or NUL-containing name
                raise write_failure(
                    "the file name is not representable", "invalid_name", name
                ) from None
        raise write_failure("cannot create a unique temporary file", "io_error", name)

    def _unlink(self, part: str) -> None:
        try:
            os.unlink(self._target(part), dir_fd=self._fd)
        except FileNotFoundError:  # moved by os.replace
            pass
        except OSError:  # pragma: no cover - a leftover temporary is harmless
            pass

    def _same_file(self, first: str, second: str) -> bool:
        try:
            a = os.stat(self._target(first), dir_fd=self._fd, follow_symlinks=False)
            b = os.stat(self._target(second), dir_fd=self._fd, follow_symlinks=False)
        except OSError:
            return False
        return (a.st_dev, a.st_ino) == (b.st_dev, b.st_ino)

    def _commit(self, temporary: str, part: str, name: str, *, overwrite: bool) -> None:
        source, destination = self._target(temporary), self._target(part)
        if overwrite:
            try:
                os.replace(source, destination, src_dir_fd=self._fd, dst_dir_fd=self._fd)
            except PermissionError as exc:
                raise write_failure(
                    "destination cannot be replaced", "permission_denied", name, exc
                ) from None
            except OSError as exc:
                raise write_failure(
                    "destination cannot be replaced", "io_error", name, exc
                ) from None
            return
        try:
            os.link(
                source,
                destination,
                src_dir_fd=self._fd,
                dst_dir_fd=self._fd,
                follow_symlinks=False,
            )
        except FileExistsError:
            if self._same_file(temporary, part):  # e.g. NFS retry of a link that succeeded
                return
            raise write_failure("destination already exists", "exists", name) from None
        except OSError as exc:
            if exc.errno in _NO_LINK_ERRNOS or getattr(exc, "winerror", None) in _NO_LINK_WINERRORS:
                raise write_failure(
                    "the destination filesystem cannot commit without replacing",
                    "no_replace_unavailable",
                    name,
                    exc,
                ) from None
            raise write_failure("destination cannot be created", "io_error", name, exc) from None

    def write(self, part: str, data: bytes, *, overwrite: bool) -> None:
        """Write ``data`` to ``part`` atomically through a sibling temporary file.

        ``overwrite=False`` never replaces an existing file (``exists``); ``True``
        replaces it atomically (a link at ``part`` is replaced, its target untouched).
        """
        name = self._relative(part)
        temporary, descriptor = self._create_temporary(part, name)
        try:
            try:
                view = memoryview(data)
                while view:
                    view = view[os.write(descriptor, view) :]
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            self._commit(temporary, part, name, overwrite=overwrite)
        except OSError as exc:
            raise write_failure("writing a project file failed", "io_error", name, exc) from None
        finally:
            self._unlink(temporary)

    def check_links(self, part: str) -> None:
        """Fail before writing anything if a no-replace commit is impossible here.

        Creates and hard-links two empty temporary files, then removes both.
        """
        name = self._relative(part)
        temporary, descriptor = self._create_temporary(part, name)
        os.close(descriptor)
        probe = f"{temporary}.link"
        try:
            self._commit(temporary, probe, name, overwrite=False)
        finally:
            self._unlink(temporary)
            self._unlink(probe)

    def sync(self, *, strict: bool = True) -> None:
        """``fsync`` the directory entries.

        A failure is ``ExportError`` ``io_error`` when ``strict`` (before a commit);
        filesystems that do not support directory fsync are accepted. Windows has no
        directory fsync. With ``strict=False`` (after the commit) failures are ignored.
        """
        if os.name == "nt":  # pragma: no cover - Windows has no directory fsync
            return
        descriptor = self._fd
        try:
            if descriptor is None:
                descriptor = os.open(self._path, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                if descriptor != self._fd:
                    os.close(descriptor)
        except OSError as exc:
            if strict and exc.errno not in _NO_SYNC_ERRNOS:
                raise write_failure(
                    "a project directory cannot be synced", "io_error", self.name, exc
                ) from None
