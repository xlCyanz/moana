"""The optional ``.moana`` ZIP container, inspected before extraction (MOANA.md section 16).

Reading never extracts to disk. :func:`inspect_archive` checks, from the end of
central directory record and then from the central directory, before any entry is
decompressed:

* the archive size; an end record in the last 22 bytes with no comment, one disk and
  no ZIP64 locator; a central directory that ends exactly at that record and is no
  larger than its declared entries can be; the declared entry count;
* for each entry: no encryption, only *stored* or *deflate*; no symbolic link (Unix
  mode ``S_IFLNK``); a name that is a relative POSIX path with no ``..``, ``.`` or
  empty segment, no backslash, NUL or drive letter; not a duplicate and not equal to
  another name after Unicode NFC normalisation and case folding;
* the expansion ratio of each entry (which bounds the whole archive too) and the
  total declared expanded bytes;
* that every file entry is a name of the project layout (manifest, content-addressed
  assets, snapshots, batches and preserved migration originals, ADR-031); directory
  entries of that layout are ignored.

:class:`ArchiveReader` then decompresses only the entries ``project`` asks for, at
most their declared size (``zipfile`` verifies each CRC). Problems are
``ValidationError`` (``unsafe_archive`` with ``entry_reason`` and the entry index; the
untrusted name is never echoed) or ``BudgetExceeded`` (``archive_*`` resources).

:func:`build_archive` writes a deterministic archive: sorted names, fixed timestamps
and permissions, deflate level 9, and *stored* for any entry whose deflate ratio would
exceed the ratio limit, so a saved archive always passes its own inspection.
"""

from __future__ import annotations

import io
import re
import stat
import struct
import unicodedata
import zipfile
import zlib
from collections.abc import Mapping
from typing import Final

from moana.core.errors import BudgetExceeded, ValidationError
from moana.project.limits import ProjectLimits
from moana.project.manifest import MANIFEST_NAME

__all__ = ["ZIP_MAGIC", "ArchiveReader", "build_archive", "inspect_archive"]

ZIP_MAGIC: Final = b"PK\x03\x04"
_EMPTY_MAGIC: Final = b"PK\x05\x06"
_EOCD: Final = struct.Struct("<4sHHHHIIH")
_ZIP64_LOCATOR: Final = b"PK\x06\x07"
_ZIP64_LOCATOR_SIZE: Final = 20
# A central directory record is 46 bytes plus its name; Moana writes no extra field
# or comment, and the longest name of the layout is a snapshot path (87 bytes).
_CENTRAL_RECORD_MAX: Final = 46 + len("history/snapshots/") + 64 + len(".json")
_LAYOUT: Final = re.compile(
    r"(?:assets/[0-9a-f]{64}\.png|history/(?:snapshots|batches)/[0-9a-f]{64}\.json"
    r"|migrations/[0-9a-f]{64}\.json)"
)
_LAYOUT_DIRECTORIES: Final = frozenset(
    {"assets/", "history/", "history/snapshots/", "history/batches/", "migrations/"}
)
_DRIVE: Final = re.compile(r"^[A-Za-z]:")
_FIXED_TIME: Final = (1980, 1, 1, 0, 0, 0)
_FILE_MODE: Final = (stat.S_IFREG | 0o644) << 16


def _unsafe(reason: str, index: int) -> ValidationError:
    return ValidationError(
        "the project archive contains an unsafe entry",
        context={"reason": "unsafe_archive", "entry_reason": reason, "entry": index},
    )


def _corrupt() -> ValidationError:
    return ValidationError("the project archive is corrupt", context={"reason": "corrupt_archive"})


def _budget(message: str, resource: str, limit: int, estimated: int) -> BudgetExceeded:
    return BudgetExceeded(
        message, context={"resource": resource, "limit": limit, "estimated": estimated}
    )


def _central_directory(data: bytes) -> tuple[int, int]:
    """Entry count and central directory size from a strict end record, before ``zipfile``.

    Moana writes the end of central directory record as the last 22 bytes, with no
    comment, one disk and no ZIP64 records, and the central directory right before
    it. Anything else (a comment that could hide a second record, ZIP64, several
    disks, a gap or overlap) is ``corrupt_archive``.
    """
    position = len(data) - _EOCD.size
    if position < 0:
        raise _corrupt()
    magic, disk, start_disk, on_disk, total, size, offset, comment = _EOCD.unpack_from(
        data, position
    )
    if magic != _EMPTY_MAGIC or comment or disk or start_disk or on_disk != total:
        raise _corrupt()
    if total == 0xFFFF or 0xFFFFFFFF in (size, offset):  # ZIP64 sentinels
        raise _corrupt()
    if _ZIP64_LOCATOR in data[max(0, position - _ZIP64_LOCATOR_SIZE) : position]:
        raise _corrupt()
    if offset + size != position:
        raise _corrupt()
    return int(total), int(size)


def _name_reason(name: str) -> str | None:
    if "\\" in name or "\x00" in name:
        return "invalid_name"
    if name.startswith("/") or _DRIVE.match(name):
        return "absolute_path"
    segments = name.rstrip("/").split("/")
    if ".." in segments:
        return "parent_reference"
    if any(segment in ("", ".") for segment in segments):
        return "invalid_name"
    return None


def _entry_reason(info: zipfile.ZipInfo) -> str | None:
    if info.flag_bits & 0x1:
        return "encrypted"
    if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
        return "compression"
    if stat.S_ISLNK(info.external_attr >> 16):
        return "symlink"
    return _name_reason(info.filename)


def _check_ratio(info: zipfile.ZipInfo, index: int, ratio: int) -> None:
    if info.file_size > ratio * max(info.compress_size, 1):
        raise _unsafe("expansion_ratio", index)


def _check_names(infos: list[zipfile.ZipInfo]) -> None:
    """Entry kinds and names, duplicates and normalised collisions, over every entry."""
    exact: set[str] = set()
    folded: set[str] = set()
    for index, info in enumerate(infos):
        reason = _entry_reason(info)
        if reason is not None:
            raise _unsafe(reason, index)
        name = info.filename
        key = unicodedata.normalize("NFC", name).casefold()
        if name in exact:
            raise _unsafe("duplicate_name", index)
        if key in folded:
            raise _unsafe("name_collision", index)
        exact.add(name)
        folded.add(key)


def _check_entries(
    infos: list[zipfile.ZipInfo], limits: ProjectLimits
) -> dict[str, zipfile.ZipInfo]:
    """Names, then ratio and expanded size, then the layout; returns the file entries.

    The ratio is bounded per entry with a compressed size of at least one byte, which
    also bounds the whole archive: its expanded total is at most the limit times the
    sum of those compressed sizes.
    """
    _check_names(infos)
    files: dict[str, zipfile.ZipInfo] = {}
    expanded = 0
    for index, info in enumerate(infos):
        _check_ratio(info, index, limits.max_archive_ratio)
        expanded += info.file_size
        if expanded > limits.max_archive_expanded_bytes:
            raise _budget(
                "the archive expands beyond its budget",
                "archive_expanded_bytes",
                limits.max_archive_expanded_bytes,
                expanded,
            )
        name = info.filename
        if name.endswith("/"):
            if name not in _LAYOUT_DIRECTORIES or info.file_size:
                raise _unsafe("unexpected_entry", index)
            continue
        if name != MANIFEST_NAME and not _LAYOUT.fullmatch(name):
            raise _unsafe("unexpected_entry", index)
        files[name] = info
    return files


class ArchiveReader:
    """Decompresses only inspected entries, each at most its declared size."""

    def __init__(self, archive: zipfile.ZipFile, files: Mapping[str, zipfile.ZipInfo]) -> None:
        """Wrap an archive whose central directory :func:`inspect_archive` accepted."""
        self._archive = archive
        self._files = dict(files)

    def read(self, name: str, limit: int) -> bytes:
        """At most ``limit + 1`` bytes of ``name``, like a bounded file read.

        A missing entry is ``ValidationError`` (``missing_entry``); the caller checks
        the length, as for a directory project.
        """
        info = self._files.get(name)
        if info is None:
            raise ValidationError(
                "the project archive lacks a declared file",
                context={"reason": "missing_entry", "file_name": name},
            )
        try:
            with self._archive.open(info) as handle:
                return handle.read(min(info.file_size, limit) + 1)
        except (zipfile.BadZipFile, zlib.error, EOFError, OSError, ValueError):
            raise _corrupt() from None


def inspect_archive(data: bytes, limits: ProjectLimits) -> ArchiveReader:
    """Inspect the archive ``data`` (already bounded by ``max_archive_bytes``)."""
    if len(data) > limits.max_archive_bytes:
        raise _budget(
            "the archive exceeds its byte budget",
            "archive_bytes",
            limits.max_archive_bytes,
            len(data),
        )
    declared, size = _central_directory(data)
    if declared > limits.max_archive_entries:
        raise _budget(
            "the archive has too many entries",
            "archive_entries",
            limits.max_archive_entries,
            declared,
        )
    if size > declared * _CENTRAL_RECORD_MAX:
        raise _corrupt()  # more directory than the declared entries can occupy
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
        infos = archive.infolist()
    except (zipfile.BadZipFile, zlib.error, EOFError, OSError, ValueError):
        raise _corrupt() from None
    if len(infos) != declared:
        raise _corrupt()
    return ArchiveReader(archive, _check_entries(infos, limits))


def _write(files: Mapping[str, bytes], stored: frozenset[str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name in sorted(files, key=lambda item: (item != MANIFEST_NAME, item)):
            info = zipfile.ZipInfo(name, date_time=_FIXED_TIME)
            info.create_system = 3
            info.external_attr = _FILE_MODE
            info.compress_type = zipfile.ZIP_STORED if name in stored else zipfile.ZIP_DEFLATED
            archive.writestr(info, files[name], compresslevel=9)
    return buffer.getvalue()


def build_archive(files: Mapping[str, bytes], limits: ProjectLimits) -> bytes:
    """A deterministic archive of ``files`` that passes :func:`inspect_archive`."""
    if len(files) > limits.max_archive_entries:
        raise _budget(
            "the project needs more archive entries than allowed",
            "archive_entries",
            limits.max_archive_entries,
            len(files),
        )
    data = _write(files, frozenset())
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        dense = frozenset(
            info.filename
            for info in archive.infolist()
            if info.file_size > limits.max_archive_ratio * max(info.compress_size, 1)
        )
    if dense:
        data = _write(files, dense)
    inspect_archive(data, limits)  # budgets of the reader apply to what is written
    return data
