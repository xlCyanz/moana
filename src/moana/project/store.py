"""Saving and loading projects: directory, ``.moana`` ZIP or ``.moana.json`` (ADR-029).

Layout (MOANA.md section 16), identical in a directory and in a ZIP::

    project.moana.json                  envelope (ProjectManifest), committed last
    assets/<sha256>.png                 source bytes of each asset
    history/snapshots/<sha256>.json     canonical JSON of each snapshot document
    history/batches/<sha256>.json       canonical JSON of each batch
    migrations/<sha256>.json            preserved original of each migration (ADR-031)

Every file but the manifest is content-addressed: its name is the SHA-256 of its
bytes (for a snapshot, the hex of its ``snapshot_digest``), so it is immutable and a
save never replaces bytes that a previous manifest references.

**Saving** first encodes everything and checks that it would load under the same
:class:`ProjectLimits` (``BudgetExceeded`` before any write). A directory save then
writes and ``fsync``-s each missing content file, ``fsync``-s each directory (a
failure aborts with ``io_error``) and commits the manifest last with an atomic
rename or link; any failure leaves the previous manifest and every file it
references untouched (new files remain as recoverable orphans; collecting them is a
later explicit action). A ZIP save builds the whole archive in memory and commits it
atomically.

**Loading** reads everything into memory and verifies it before returning: the
envelope and its document, every asset (length, SHA-256 and a bounded PNG decode)
and every history entry (snapshot hash, canonical batch, and that the batch applied
to the parent reproduces the snapshot). Nothing is returned on failure, so a project
never loads partially.

Paths inside a project never follow links (``moana.project._fs``); on POSIX this is
enforced through directory descriptors, on Windows by checks before each use, with
the race window described in ADR-029 section 8.
"""

from __future__ import annotations

import os
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from moana.core.errors import ExportError, ReadError
from moana.editing import History
from moana.project._fs import Folder, caller_path, write_failure
from moana.project._json import canonical_bytes, measure_shape
from moana.project._load import (
    DIGEST_PREFIX,
    batch_path,
    budget_error,
    consume_source,
    load_json,
    sha256_hex,
    snapshot_path,
)
from moana.project.archive import build_archive as _build_archive
from moana.project.assets import PNG_MIME
from moana.project.limits import DEFAULT_PROJECT_LIMITS, ProjectLimits
from moana.project.manifest import (
    MANIFEST_NAME,
    PROJECT_KIND,
    PROJECT_VERSION,
    AssetRef,
    HistoryEntry,
    MigrationRecord,
    ProjectManifest,
)
from moana.project.model import Project
from moana.schema import (
    DEFAULT_PARSE_LIMITS,
    Document,
    ParseLimits,
    canonical_json,
)

__all__ = [
    "SaveReport",
    "batch_path",
    "encode_project",
    "load_project",
    "save_document",
    "save_project",
    "save_project_archive",
    "snapshot_path",
]


@dataclass(frozen=True, slots=True)
class SaveReport:
    """What a save committed and where, with relative paths only.

    ``sha256`` is the hex SHA-256 of the file committed last: the manifest of a
    directory project, the whole ZIP of :func:`save_project_archive` (its bytes depend
    on the zlib implementation; the manifest hash is the identity that is stable
    across platforms) or the ``.moana.json`` of :func:`save_document`. ``written``
    lists the files written by this save, ``reused`` the content files that were
    already present with the right bytes (for a single-file save, the file name).
    """

    sha256: str
    written: tuple[str, ...]
    reused: tuple[str, ...]


# --- encoding ------------------------------------------------------------------------


def _check_loadable(data: bytes, what: str, max_bytes: int, max_depth: int, max_nodes: int) -> None:
    """Fail now if a reader with these bounds would reject ``data`` when loading."""
    if len(data) > max_bytes:
        raise budget_error(f"{what}_bytes", max_bytes, len(data))
    depth, nodes = measure_shape(data.decode("utf-8"))
    if depth > max_depth:
        raise budget_error(f"{what}_depth", max_depth, depth)
    if nodes > max_nodes:
        raise budget_error(f"{what}_nodes", max_nodes, nodes)


def _check_parse(data: bytes, what: str, limits: ParseLimits) -> None:
    _check_loadable(data, what, limits.max_bytes, limits.max_depth, limits.max_nodes)


def _history_files(
    history: History, files: dict[str, bytes], limits: ProjectLimits
) -> tuple[HistoryEntry, ...]:
    budget = limits.history
    if len(history.snapshots) > budget.max_snapshots:
        raise budget_error("history_snapshots", budget.max_snapshots, len(history.snapshots))
    if history.total_bytes > budget.max_bytes:
        raise budget_error("history_bytes", budget.max_bytes, history.total_bytes)
    entries: list[HistoryEntry] = []
    for digest, snapshot in history.snapshots.items():
        document = canonical_json(snapshot.document)
        _check_parse(document, "document", limits.parse)
        files[snapshot_path(digest)] = document
        batch = None
        if snapshot.batch is not None:
            _check_parse(snapshot.batch, "batch", limits.parse)
            batch = DIGEST_PREFIX + sha256_hex(snapshot.batch)
            files[batch_path(batch)] = snapshot.batch
        redo = snapshot.parent is not None and history.redo_children.get(snapshot.parent) == digest
        entries.append(
            HistoryEntry(snapshot=digest, parent=snapshot.parent, batch=batch, redo=redo)
        )
    return tuple(entries)


def _check_assets(project: Project, limits: ProjectLimits) -> None:
    if len(project.assets) > limits.max_assets:
        raise budget_error("project_assets", limits.max_assets, len(project.assets))
    for asset in project.assets:
        if len(asset.data) > limits.max_asset_bytes:
            raise budget_error("asset_bytes", limits.max_asset_bytes, len(asset.data))
    pixels = sum(asset.pixels for asset in project.assets)
    if pixels > limits.max_asset_pixels:
        raise budget_error("asset_pixels", limits.max_asset_pixels, pixels)


def _migration_files(
    project: Project, files: dict[str, bytes], limits: ProjectLimits
) -> tuple[MigrationRecord, ...]:
    if len(project.migrations) > limits.max_migrations:
        raise budget_error("project_migrations", limits.max_migrations, len(project.migrations))
    for backup in project.migrations:
        if len(backup.data) > limits.max_manifest_bytes:
            raise budget_error("migration_bytes", limits.max_manifest_bytes, len(backup.data))
        files[backup.path] = backup.data
    return tuple(backup.record for backup in project.migrations)


def encode_project(
    project: Project, *, limits: ProjectLimits = DEFAULT_PROJECT_LIMITS
) -> tuple[bytes, dict[str, bytes]]:
    """Canonical manifest bytes and the content-addressed files of ``project``.

    Deterministic: the same project always encodes to the same bytes. Every part is
    checked against the bounds :func:`load_project` applies with the same ``limits``
    (bytes, depth and nodes of the manifest, of the document and of each snapshot
    and batch; asset, history and migration budgets), so ``BudgetExceeded`` is raised here,
    before anything is written, for a project that would not load.
    """
    if not isinstance(project, Project):
        raise TypeError("project must be a moana.project.Project")
    _check_assets(project, limits)
    _check_parse(canonical_json(project.document), "document", limits.parse)
    files: dict[str, bytes] = {}
    refs: list[AssetRef] = []
    for asset in project.assets:
        files[asset.path] = asset.data
        refs.append(
            AssetRef(
                id=asset.id,
                path=asset.path,
                mime=PNG_MIME,
                byte_length=len(asset.data),
                sha256=asset.sha256,
            )
        )
    history = project.history
    entries = () if history is None else _history_files(history, files, limits)
    migrations = _migration_files(project, files, limits)
    manifest = ProjectManifest(
        kind=PROJECT_KIND,
        project_version=PROJECT_VERSION,
        document=project.document,
        assets=tuple(refs),
        history=entries,
        migrations=migrations,
    )
    data = canonical_bytes(manifest.to_tree())
    _check_loadable(
        data,
        "manifest",
        limits.max_manifest_bytes,
        limits.max_manifest_depth,
        limits.max_manifest_nodes,
    )
    return data, files


# --- saving --------------------------------------------------------------------------


def _intact(folder: Folder, part: str, data: bytes) -> bool:
    """Whether ``part`` already holds exactly ``data`` (a content-addressed file).

    A missing file is ``False``; any other read failure keeps its reason
    (``not_a_file`` for a link, ``is_directory``, ``permission_denied``, ``io_error``)
    as an ``ExportError``.
    """
    try:
        return folder.read(part, len(data)) == data
    except ReadError as exc:
        if exc.context.get("reason") == "not_found":
            return False
        raise ExportError("a project file cannot be checked", context=exc.context) from exc


def _write_tree(
    folder: Folder, files: Mapping[str, bytes], written: list[str], reused: list[str]
) -> None:
    """Write ``files`` (relative to ``folder``) depth first, syncing each directory."""
    children: dict[str, dict[str, bytes]] = {}
    for name in sorted(files):
        head, _, rest = name.partition("/")
        if rest:
            children.setdefault(head, {})[rest] = files[name]
            continue
        relative = f"{folder.name}/{name}" if folder.name != "." else name
        if _intact(folder, name, files[name]):
            reused.append(relative)
        else:
            folder.write(name, files[name], overwrite=True)
            written.append(relative)
    for head, nested in children.items():
        with folder.child(head, create=True) as child:
            _write_tree(child, nested, written, reused)
            child.sync()


def save_project(
    project: Project,
    directory: str | os.PathLike[str],
    *,
    overwrite: bool = False,
    limits: ProjectLimits = DEFAULT_PROJECT_LIMITS,
) -> SaveReport:
    """Save ``project`` into ``directory`` (created if absent, one level).

    Order: budget check (``encode_project``); without ``overwrite``, ``exists`` if a
    manifest is present and ``no_replace_unavailable`` if the filesystem has no hard
    links, before writing anything; content files written and synced; directories
    synced (a failure aborts with ``io_error``); manifest committed last; root synced
    (best effort, the commit already happened). The previous project survives any
    failure. ``directory`` is the caller's path (links in it are followed); nothing
    inside the project follows a link (``unsafe_path``/``not_a_file``). On Windows,
    which has no ``dir_fd``, links are checked before each use (ADR-029 section 8).
    """
    manifest, files = encode_project(project, limits=limits)
    with Folder.open_root(caller_path(directory), create=True, writing=True) as root:
        if not overwrite:
            if root.exists(MANIFEST_NAME):
                raise write_failure("the project manifest already exists", "exists", MANIFEST_NAME)
            root.check_links(MANIFEST_NAME)
        written: list[str] = []
        reused: list[str] = []
        _write_tree(root, files, written, reused)
        root.sync()
        root.write(MANIFEST_NAME, manifest, overwrite=overwrite)
        root.sync(strict=False)
    return SaveReport(sha256_hex(manifest), (*written, MANIFEST_NAME), tuple(reused))


def _save_file(path: Path, data: bytes, *, overwrite: bool) -> SaveReport:
    name = path.name
    with Folder.open_root(path.parent, create=False, writing=True) as parent:
        mode = parent.lstat_mode(name) if name not in ("", ".", "..") else stat.S_IFDIR
        if mode is not None and stat.S_ISDIR(mode):
            raise write_failure("the destination is a directory", "is_directory", name)
        if not overwrite:
            if mode is not None:
                raise write_failure("destination already exists", "exists", name)
            parent.check_links(name)
        parent.write(name, data, overwrite=overwrite)
        parent.sync(strict=False)
    return SaveReport(sha256_hex(data), (name,), ())


def save_project_archive(
    project: Project,
    path: str | os.PathLike[str],
    *,
    overwrite: bool = False,
    limits: ProjectLimits = DEFAULT_PROJECT_LIMITS,
) -> SaveReport:
    """Save ``project`` as one deterministic ``.moana`` ZIP, committed atomically.

    The archive is built in memory and inspected with the reader's own rules before
    the commit; ``BudgetExceeded`` (``archive_*``) when it would not load. Its bytes
    are deterministic for one zlib implementation; across platforms the stable
    identity is the manifest hash.
    """
    manifest, files = encode_project(project, limits=limits)
    data = _build_archive({MANIFEST_NAME: manifest, **files}, limits)
    return _save_file(caller_path(path), data, overwrite=overwrite)


def save_document(
    document: Document,
    path: str | os.PathLike[str],
    *,
    overwrite: bool = False,
    limits: ParseLimits = DEFAULT_PARSE_LIMITS,
) -> SaveReport:
    """Save a self-contained ``.moana.json`` (canonical JSON of section 14) atomically.

    ``BudgetExceeded`` (``document_bytes``/``_depth``/``_nodes``) before writing when
    the canonical form would not load under ``limits``.
    """
    if not isinstance(document, Document):
        raise TypeError("document must be a moana.schema.Document")
    data = canonical_json(document)
    _check_parse(data, "document", limits)
    return _save_file(caller_path(path), data, overwrite=overwrite)


# --- loading -------------------------------------------------------------------------


def load_project(
    path: str | os.PathLike[str], *, limits: ProjectLimits = DEFAULT_PROJECT_LIMITS
) -> Project:
    """Load and verify a project directory, a ``.moana`` ZIP or a ``.moana.json`` file.

    A directory holds ``project.moana.json``. A file starting with ``PK`` is read up
    to ``max_archive_bytes`` and inspected as an archive before any entry is
    decompressed; any other file is read up to ``max_manifest_bytes`` as JSON. JSON
    (also the manifest of a directory) is an envelope when its root object has a
    ``kind`` member, with assets and history beside it, and otherwise a plain
    document, which loads as a project without assets or history. ``path`` is the
    caller's (links in it are followed); every path inside a project is derived from
    a hash, confined to the root and never follows a link (through directory
    descriptors on POSIX; on Windows by checks before each use, ADR-029 section 8).
    Raises ``ReadError``, ``ValidationError``, ``BudgetExceeded`` or the errors of
    ``moana.schema`` and ``moana.editing``; nothing is returned partially.

    Loading never writes and never migrates (ADR-031): a document or envelope in
    another version is ``UnsupportedVersion`` (``migration_required`` when a
    migration is registered); :func:`moana.project.migrate_project` migrates
    explicitly into a new destination. Migration records and their preserved
    originals are verified (length and SHA-256) and kept in ``Project.migrations``.
    """
    return consume_source(path, limits, lambda data, read: load_json(data, read, limits))
