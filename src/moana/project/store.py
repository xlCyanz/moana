"""Saving and loading projects: directory, ``.moana`` ZIP or ``.moana.json`` (ADR-029).

Layout (MOANA.md section 16), identical in a directory and in a ZIP::

    project.moana.json                  envelope (ProjectManifest), committed last
    assets/<sha256>.png                 source bytes of each asset
    history/snapshots/<sha256>.json     canonical JSON of each snapshot document
    history/batches/<sha256>.json       canonical JSON of each batch

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

import hashlib
import os
import stat
from collections.abc import Callable, Mapping
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path

from moana.core.errors import BudgetExceeded, ExportError, MoanaError, ReadError, ValidationError
from moana.editing import History, Snapshot, apply_batch, canonical_batch, parse_edit_batch
from moana.project._fs import Folder, caller_path, read_caller_file, write_failure
from moana.project._json import canonical_bytes, measure_shape, read_json_object
from moana.project.archive import build_archive as _build_archive
from moana.project.archive import inspect_archive
from moana.project.assets import PNG_MIME, Asset
from moana.project.limits import DEFAULT_PROJECT_LIMITS, ProjectLimits
from moana.project.manifest import (
    MANIFEST_NAME,
    PROJECT_KIND,
    PROJECT_VERSION,
    AssetRef,
    HistoryEntry,
    ProjectManifest,
    parse_manifest,
)
from moana.project.model import Project, check_asset_ids
from moana.schema import (
    DEFAULT_PARSE_LIMITS,
    Document,
    ParseLimits,
    canonical_json,
    snapshot_digest,
    validate_document,
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

type _Reader = Callable[[str, int], bytes]
"""Reads at most ``limit + 1`` bytes of a relative project path."""

_DIGEST_PREFIX = "sha256:"


def snapshot_path(digest: str) -> str:
    """Immutable path of a snapshot document: ``history/snapshots/<hex>.json``."""
    return f"history/snapshots/{digest.removeprefix(_DIGEST_PREFIX)}.json"


def batch_path(digest: str) -> str:
    """Immutable path of a canonical batch: ``history/batches/<hex>.json``."""
    return f"history/batches/{digest.removeprefix(_DIGEST_PREFIX)}.json"


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


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _budget(resource: str, limit: int, estimated: int) -> BudgetExceeded:
    return BudgetExceeded(
        "the project exceeds its budget",
        context={"resource": resource, "limit": limit, "estimated": estimated},
    )


def _check_loadable(data: bytes, what: str, max_bytes: int, max_depth: int, max_nodes: int) -> None:
    """Fail now if a reader with these bounds would reject ``data`` when loading."""
    if len(data) > max_bytes:
        raise _budget(f"{what}_bytes", max_bytes, len(data))
    depth, nodes = measure_shape(data.decode("utf-8"))
    if depth > max_depth:
        raise _budget(f"{what}_depth", max_depth, depth)
    if nodes > max_nodes:
        raise _budget(f"{what}_nodes", max_nodes, nodes)


def _check_parse(data: bytes, what: str, limits: ParseLimits) -> None:
    _check_loadable(data, what, limits.max_bytes, limits.max_depth, limits.max_nodes)


def _history_files(
    history: History, files: dict[str, bytes], limits: ProjectLimits
) -> tuple[HistoryEntry, ...]:
    budget = limits.history
    if len(history.snapshots) > budget.max_snapshots:
        raise _budget("history_snapshots", budget.max_snapshots, len(history.snapshots))
    if history.total_bytes > budget.max_bytes:
        raise _budget("history_bytes", budget.max_bytes, history.total_bytes)
    entries: list[HistoryEntry] = []
    for digest, snapshot in history.snapshots.items():
        document = canonical_json(snapshot.document)
        _check_parse(document, "document", limits.parse)
        files[snapshot_path(digest)] = document
        batch = None
        if snapshot.batch is not None:
            _check_parse(snapshot.batch, "batch", limits.parse)
            batch = _DIGEST_PREFIX + _sha(snapshot.batch)
            files[batch_path(batch)] = snapshot.batch
        redo = snapshot.parent is not None and history.redo_children.get(snapshot.parent) == digest
        entries.append(
            HistoryEntry(snapshot=digest, parent=snapshot.parent, batch=batch, redo=redo)
        )
    return tuple(entries)


def _check_assets(project: Project, limits: ProjectLimits) -> None:
    if len(project.assets) > limits.max_assets:
        raise _budget("project_assets", limits.max_assets, len(project.assets))
    for asset in project.assets:
        if len(asset.data) > limits.max_asset_bytes:
            raise _budget("asset_bytes", limits.max_asset_bytes, len(asset.data))
    pixels = sum(asset.pixels for asset in project.assets)
    if pixels > limits.max_asset_pixels:
        raise _budget("asset_pixels", limits.max_asset_pixels, pixels)


def encode_project(
    project: Project, *, limits: ProjectLimits = DEFAULT_PROJECT_LIMITS
) -> tuple[bytes, dict[str, bytes]]:
    """Canonical manifest bytes and the content-addressed files of ``project``.

    Deterministic: the same project always encodes to the same bytes. Every part is
    checked against the bounds :func:`load_project` applies with the same ``limits``
    (bytes, depth and nodes of the manifest, of the document and of each snapshot
    and batch; asset and history budgets), so ``BudgetExceeded`` is raised here,
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
    manifest = ProjectManifest(
        kind=PROJECT_KIND,
        project_version=PROJECT_VERSION,
        document=project.document,
        assets=tuple(refs),
        history=entries,
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
    return SaveReport(_sha(manifest), (*written, MANIFEST_NAME), tuple(reused))


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
    return SaveReport(_sha(data), (name,), ())


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


def _mismatch(message: str, reason: str, **extra: int) -> ValidationError:
    return ValidationError(message, context={"reason": reason, **extra})


def _load_assets(
    manifest: ProjectManifest, read: _Reader, limits: ProjectLimits
) -> tuple[Asset, ...]:
    refs = manifest.assets
    if len(refs) > limits.max_assets:
        raise _budget("project_assets", limits.max_assets, len(refs))
    check_asset_ids(manifest.document, tuple(ref.id for ref in refs))
    for ref in refs:
        if ref.byte_length > limits.max_asset_bytes:
            raise _budget("asset_bytes", limits.max_asset_bytes, ref.byte_length)
    assets: list[Asset] = []
    pixels = 0
    for index, ref in enumerate(refs):
        data = read(ref.path, ref.byte_length)
        if len(data) != ref.byte_length or _sha(data) != ref.sha256:
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


def _invalid_history(message: str, index: int) -> ValidationError:
    return ValidationError(message, context={"reason": "invalid_history", "entry": index})


def _read_hashed(read: _Reader, name: str, digest: str, limit: int, index: int) -> bytes:
    data = read(name, limit)
    if len(data) > limit:
        raise _budget("history_file_bytes", limit, len(data))
    if _DIGEST_PREFIX + _sha(data) != digest:
        raise _mismatch("a history file does not match its hash", "checksum_mismatch", entry=index)
    return data


def _load_snapshot(
    entry: HistoryEntry,
    index: int,
    stored: dict[str, Snapshot],
    read: _Reader,
    limits: ProjectLimits,
) -> Snapshot:
    parse = limits.parse
    raw = _read_hashed(read, snapshot_path(entry.snapshot), entry.snapshot, parse.max_bytes, index)
    try:
        document = validate_document(raw, limits=parse)
    except MoanaError as exc:
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
    except MoanaError as exc:
        raise _invalid_history("a stored batch does not apply to its parent", index) from exc
    if canonical_batch(parsed) != batch or result.snapshot != entry.snapshot:
        raise _invalid_history("a stored batch does not reproduce its snapshot", index)
    return Snapshot(
        entry.snapshot, document, entry.parent, batch, result.affected_ids, len(raw) + len(batch)
    )


def _load_history(
    manifest: ProjectManifest, read: _Reader, limits: ProjectLimits
) -> History | None:
    """Rebuild the history; its ``limits`` are the loader's ``limits.history``.

    ``HistoryLimits`` is configuration of the host that loads, not project data, so
    it is not persisted (ADR-029 section 7).
    """
    entries = manifest.history
    if not entries:
        return None
    budget = limits.history
    if len(entries) > budget.max_snapshots:
        raise _budget("history_snapshots", budget.max_snapshots, len(entries))
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
            raise _budget("history_bytes", budget.max_bytes, total)
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


def _load_json(data: bytes, read: _Reader, limits: ProjectLimits) -> Project:
    """A JSON file: an envelope when its root object has a ``kind`` member, else a document.

    The JSON is first read with the manifest bounds (it may be an envelope); a plain
    document is then validated by ``moana.schema`` with ``limits.parse``, which gives
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
    manifest = parse_manifest(tree, limits=limits.parse)
    assets = _load_assets(manifest, read, limits)
    history = _load_history(manifest, read, limits)
    return Project(manifest.document, assets, history)


def _folder_reader(root: Folder) -> _Reader:
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


def _load_directory(root_path: Path, limits: ProjectLimits) -> Project:
    with Folder.open_root(root_path, create=False, writing=False) as root:
        reader = _folder_reader(root)
        return _load_json(reader(MANIFEST_NAME, limits.max_manifest_bytes), reader, limits)


def _load_beside(data: bytes, parent: Path, limits: ProjectLimits) -> Project:
    """Load JSON read by path; an envelope reads its files from ``parent``.

    The parent is opened on the first read only, so a plain document never touches
    it, and an envelope loads exactly as ``project.moana.json`` in that directory.
    """
    with ExitStack() as stack:
        opened: list[_Reader] = []

        def read(name: str, limit: int) -> bytes:
            if not opened:
                root = Folder.open_root(parent, create=False, writing=False)
                opened.append(_folder_reader(stack.enter_context(root)))
            return opened[0](name, limit)

        return _load_json(data, read, limits)


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
    """
    if not isinstance(limits, ProjectLimits):
        raise TypeError("limits must be a ProjectLimits value")
    target = caller_path(path)
    try:
        is_directory = stat.S_ISDIR(os.stat(target).st_mode)
    except OSError:
        is_directory = False
    if is_directory:
        return _load_directory(target, limits)
    data = read_caller_file(target, limits.max_manifest_bytes, zip_limit=limits.max_archive_bytes)
    if data.startswith(b"PK"):
        archive = inspect_archive(data, limits)
        return _load_json(
            archive.read(MANIFEST_NAME, limits.max_manifest_bytes), archive.read, limits
        )
    return _load_beside(data, target.parent, limits)
