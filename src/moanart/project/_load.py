"""Shared, read-only loading of project sources (ADR-029, ADR-031).

Internal to :mod:`moanart.project`: :mod:`moanart.project.store` (``load_project``) and
:mod:`moanart.project.migrate` (``migrate_project``) open a source with
:func:`consume_source` and verify it with :func:`load_json`, :func:`load_assets` and
:func:`load_migrations`. Nothing here writes. The public API is re-exported by the
package; these names carry no underscore only because two sibling modules use them.
"""

from __future__ import annotations

import hashlib
import os
import stat
from collections.abc import Callable
from contextlib import ExitStack
from pathlib import Path

from moanart.core.errors import BudgetExceeded, MoanArtError, ValidationError
from moanart.editing import History, Snapshot, apply_batch, canonical_batch, parse_edit_batch
from moanart.project._fs import Folder, caller_path, read_caller_file
from moanart.project._json import read_json_object
from moanart.project.archive import inspect_archive
from moanart.project.assets import Asset
from moanart.project.limits import ProjectLimits
from moanart.project.manifest import (
    LEGACY_MANIFEST_NAME,
    MANIFEST_NAME,
    HistoryEntry,
    ProjectManifest,
    legacy_name_error,
    parse_manifest,
)
from moanart.project.model import MigrationBackup, Project, check_asset_ids
from moanart.schema import canonical_json, snapshot_digest, validate_document

__all__ = [
    "DIGEST_PREFIX",
    "Consumer",
    "Reader",
    "batch_path",
    "budget_error",
    "consume_legacy_source",
    "consume_source",
    "load_assets",
    "load_envelope",
    "load_json",
    "load_migrations",
    "sha256_hex",
    "snapshot_path",
]


type Reader = Callable[[str, int], bytes]
"""Reads at most ``limit + 1`` bytes of a relative project path."""

DIGEST_PREFIX = "sha256:"


def snapshot_path(digest: str) -> str:
    """Immutable path of a snapshot document: ``history/snapshots/<hex>.json``."""
    return f"history/snapshots/{digest.removeprefix(DIGEST_PREFIX)}.json"


def batch_path(digest: str) -> str:
    """Immutable path of a canonical batch: ``history/batches/<hex>.json``."""
    return f"history/batches/{digest.removeprefix(DIGEST_PREFIX)}.json"


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def budget_error(resource: str, limit: int, estimated: int) -> BudgetExceeded:
    return BudgetExceeded(
        "the project exceeds its budget",
        context={"resource": resource, "limit": limit, "estimated": estimated},
    )


def _mismatch(message: str, reason: str, **extra: int) -> ValidationError:
    return ValidationError(message, context={"reason": reason, **extra})


def load_assets(
    manifest: ProjectManifest, read: Reader, limits: ProjectLimits
) -> tuple[Asset, ...]:
    refs = manifest.assets
    if len(refs) > limits.max_assets:
        raise budget_error("project_assets", limits.max_assets, len(refs))
    check_asset_ids(manifest.document, tuple(ref.id for ref in refs))
    for ref in refs:
        if ref.byte_length > limits.max_asset_bytes:
            raise budget_error("asset_bytes", limits.max_asset_bytes, ref.byte_length)
    assets: list[Asset] = []
    pixels = 0
    for index, ref in enumerate(refs):
        data = read(ref.path, ref.byte_length)
        if len(data) != ref.byte_length or sha256_hex(data) != ref.sha256:
            raise _mismatch(
                "an asset does not match its checksum", "checksum_mismatch", index=index
            )
        asset = Asset.from_png(
            ref.id,
            data,
            max_bytes=limits.max_asset_bytes,
            max_pixels=limits.max_asset_pixels - pixels,
        )
        pixels += asset.pixels
        assets.append(asset)
    return tuple(assets)


def load_migrations(
    manifest: ProjectManifest, read: Reader, limits: ProjectLimits
) -> tuple[MigrationBackup, ...]:
    """Read and verify the preserved original of each migration record (ADR-031)."""
    records = manifest.migrations
    if len(records) > limits.max_migrations:
        raise budget_error("project_migrations", limits.max_migrations, len(records))
    for record in records:
        if record.byte_length > limits.max_manifest_bytes:
            raise budget_error("migration_bytes", limits.max_manifest_bytes, record.byte_length)
    backups: list[MigrationBackup] = []
    for index, record in enumerate(records):
        data = read(record.path, record.byte_length)
        if len(data) != record.byte_length or sha256_hex(data) != record.sha256:
            raise _mismatch(
                "a migration original does not match its checksum",
                "checksum_mismatch",
                migration=index,
            )
        backups.append(MigrationBackup(record, data))
    return tuple(backups)


def _invalid_history(message: str, index: int) -> ValidationError:
    return ValidationError(message, context={"reason": "invalid_history", "entry": index})


def _read_hashed(read: Reader, name: str, digest: str, limit: int, index: int) -> bytes:
    data = read(name, limit)
    if len(data) > limit:
        raise budget_error("history_file_bytes", limit, len(data))
    if DIGEST_PREFIX + sha256_hex(data) != digest:
        raise _mismatch("a history file does not match its hash", "checksum_mismatch", entry=index)
    return data


def _load_snapshot(
    entry: HistoryEntry,
    index: int,
    stored: dict[str, Snapshot],
    read: Reader,
    limits: ProjectLimits,
) -> Snapshot:
    parse = limits.parse
    raw = _read_hashed(read, snapshot_path(entry.snapshot), entry.snapshot, parse.max_bytes, index)
    try:
        document = validate_document(raw, limits=parse)
    except MoanArtError as exc:
        raise _invalid_history("a stored snapshot is not a valid document", index) from exc
    if canonical_json(document) != raw:
        raise _invalid_history("a stored snapshot is not canonical", index)
    if entry.parent is None or entry.batch is None:
        return Snapshot(entry.snapshot, document, None, None, (), len(raw))
    parent = stored.get(entry.parent)
    if parent is None:
        raise _invalid_history("a parent is not stored before its child", index)
    batch = _read_hashed(read, batch_path(entry.batch), entry.batch, parse.max_bytes, index)
    try:
        parsed = parse_edit_batch(batch, limits=parse)
        result = apply_batch(parent.document, parsed, limits=parse)
    except MoanArtError as exc:
        raise _invalid_history("a stored batch does not apply to its parent", index) from exc
    if canonical_batch(parsed) != batch or result.snapshot != entry.snapshot:
        raise _invalid_history("a stored batch does not reproduce its snapshot", index)
    return Snapshot(
        entry.snapshot, document, entry.parent, batch, result.affected_ids, len(raw) + len(batch)
    )


def _load_history(manifest: ProjectManifest, read: Reader, limits: ProjectLimits) -> History | None:
    """Rebuild the history; its ``limits`` are the loader's ``limits.history``.

    ``HistoryLimits`` is configuration of the host that loads, not project data, so
    it is not persisted (ADR-029 section 7).
    """
    entries = manifest.history
    if not entries:
        return None
    budget = limits.history
    if len(entries) > budget.max_snapshots:
        raise budget_error("history_snapshots", budget.max_snapshots, len(entries))
    stored: dict[str, Snapshot] = {}
    redo: dict[str, str] = {}
    children: dict[str, tuple[str, ...]] = {}
    total = 0
    for index, entry in enumerate(entries):
        if entry.snapshot in stored or (index == 0) != (entry.parent is None):
            raise _invalid_history("history entries are duplicated or have several roots", index)
        snapshot = _load_snapshot(entry, index, stored, read, limits)
        total += snapshot.size
        if total > budget.max_bytes:
            raise budget_error("history_bytes", budget.max_bytes, total)
        stored[entry.snapshot] = snapshot
        if entry.parent is not None:
            children[entry.parent] = (*children.get(entry.parent, ()), entry.snapshot)
            if entry.redo:
                if entry.parent in redo:
                    raise _invalid_history("a snapshot has two active redo children", index)
                redo[entry.parent] = entry.snapshot
    cursor = snapshot_digest(manifest.document)
    if cursor not in stored:
        raise _invalid_history("the project document is not in its history", len(entries))
    return History(
        root=entries[0].snapshot,
        cursor=cursor,
        limits=budget,
        snapshots=stored,
        children=children,
        redo_children=redo,
        total_bytes=total,
    )


def load_json(data: bytes, read: Reader, limits: ProjectLimits) -> Project:
    """A JSON file: an envelope when its root object has a ``kind`` member, else a document.

    The JSON is first read with the manifest bounds (it may be an envelope); a plain
    document is then validated by ``moanart.schema`` with ``limits.parse``, which gives
    its own limits and detailed pointers.
    """
    tree = read_json_object(
        data,
        max_bytes=limits.max_manifest_bytes,
        max_depth=limits.max_manifest_depth,
        max_nodes=limits.max_manifest_nodes,
    )
    if not (isinstance(tree, dict) and "kind" in tree):
        return Project(validate_document(data, limits=limits.parse))
    return load_envelope(parse_manifest(tree, limits=limits.parse), read, limits)


def load_envelope(manifest: ProjectManifest, read: Reader, limits: ProjectLimits) -> Project:
    """The project of a validated envelope: assets, history and migration originals."""
    assets = load_assets(manifest, read, limits)
    history = _load_history(manifest, read, limits)
    migrations = load_migrations(manifest, read, limits)
    return Project(manifest.document, assets, history, migrations)


def _folder_reader(root: Folder) -> Reader:
    def read(name: str, limit: int) -> bytes:
        *directories, part = name.split("/")
        if not directories:
            return root.read(part, limit)
        opened: list[Folder] = []
        try:
            current = root
            for directory in directories:
                current = current.child(directory, create=False)
                opened.append(current)
            return current.read(part, limit)
        finally:
            for folder in reversed(opened):
                folder.close()

    return read


type Consumer[T] = Callable[[bytes, Reader], T]
type LegacyConsumer[T] = Callable[[bytes, Reader, bool], T]
"""Like :data:`Consumer`, plus whether the manifest read was the legacy one (ADR-041)."""
"""Receives the JSON bytes of a source and a reader of the files beside it."""


def _manifest_name(exists: Callable[[str], bool], *, legacy: bool) -> str:
    """The manifest to read: the current one, or the legacy one of ADR-041.

    A legacy manifest without a current one is ``legacy_name`` unless ``legacy``
    (only :func:`~moanart.project.migrate_project` passes it).
    """
    if exists(MANIFEST_NAME) or not exists(LEGACY_MANIFEST_NAME):
        return MANIFEST_NAME
    if legacy:
        return LEGACY_MANIFEST_NAME
    raise legacy_name_error("manifest", MANIFEST_NAME, None)


def _consume_directory[T](
    root_path: Path, limits: ProjectLimits, consume: LegacyConsumer[T], *, legacy: bool
) -> T:
    with Folder.open_root(root_path, create=False, writing=False) as root:
        reader = _folder_reader(root)
        name = _manifest_name(root.exists, legacy=legacy)
        data = reader(name, limits.max_manifest_bytes)
        return consume(data, reader, name == LEGACY_MANIFEST_NAME)


def _consume_beside[T](data: bytes, parent: Path, consume: LegacyConsumer[T]) -> T:
    """Consume JSON read by path; an envelope reads its files from ``parent``.

    The parent is opened on the first read only, so a plain document never touches
    it, and an envelope loads exactly as ``project.moanart.json`` in that directory.
    """
    with ExitStack() as stack:
        opened: list[Reader] = []

        def read(name: str, limit: int) -> bytes:
            if not opened:
                root = Folder.open_root(parent, create=False, writing=False)
                opened.append(_folder_reader(stack.enter_context(root)))
            return opened[0](name, limit)

        return consume(data, read, False)


def consume_source[T](
    path: str | os.PathLike[str], limits: ProjectLimits, consume: Consumer[T]
) -> T:
    """Open a project source read-only and pass its JSON and a reader to ``consume``.

    The dispatch of :func:`load_project`: a directory (its manifest), a ``.moanart`` ZIP
    (inspected first) or a JSON file (files read beside it). Nothing is ever written.
    A directory or ZIP holding only the manifest of 0.1.0rc1 is ``UnsupportedVersion``
    ``legacy_name`` (ADR-041).
    """
    return _open_source(path, limits, lambda data, read, _legacy: consume(data, read), False)


def consume_legacy_source[T](
    path: str | os.PathLike[str], limits: ProjectLimits, consume: LegacyConsumer[T]
) -> T:
    """:func:`consume_source` that also reads the manifest of 0.1.0rc1 (ADR-041).

    Only :func:`~moanart.project.migrate_project` uses it; ``consume`` learns whether
    the manifest it receives was the legacy one.
    """
    return _open_source(path, limits, consume, True)


def _open_source[T](
    path: str | os.PathLike[str], limits: ProjectLimits, consume: LegacyConsumer[T], legacy: bool
) -> T:
    if not isinstance(limits, ProjectLimits):
        raise TypeError("limits must be a ProjectLimits value")
    target = caller_path(path)
    try:
        is_directory = stat.S_ISDIR(os.stat(target).st_mode)
    except OSError:
        is_directory = False
    if is_directory:
        return _consume_directory(target, limits, consume, legacy=legacy)
    data = read_caller_file(target, limits.max_manifest_bytes, zip_limit=limits.max_archive_bytes)
    if data.startswith(b"PK"):
        archive = inspect_archive(data, limits)
        name = _manifest_name(archive.has, legacy=legacy)
        data = archive.read(name, limits.max_manifest_bytes)
        return consume(data, archive.read, name == LEGACY_MANIFEST_NAME)
    return _consume_beside(data, target.parent, consume)
