"""Explicit migration of a project into a new destination (MOANART.md section 16, ADR-031).

:func:`migrate_project` is the only way an older format becomes current on disk.
Reading the source never writes: it goes through the read-only dispatch of
:func:`~moanart.project.load_project` (:mod:`moanart.project._load`). The document
migration itself is the pure :func:`moanart.schema.migrate_document` (no I/O); this
module only reads, verifies and saves. The migrated project is written with
:func:`~moanart.project.save_project` without ``overwrite`` into ``destination``, so an
existing project there is never replaced (``exists``); a destination equal to, or
inside, a source directory is refused before anything is read
(``destination_inside_source``). The new manifest carries a
:class:`~moanart.project.MigrationRecord` (source kind, migrated member, source and
target versions, applied step IDs) and the exact bytes of the original JSON under
``migrations/<sha256>.json``; assets are carried over byte for byte after their
usual verification.

A source already in the current version is verified as :func:`load_project` would,
and nothing is written: migrating a migrated project is the identity. A project
history cannot be migrated (its snapshots and batches have no migration contract),
so a source with history in an older version is ``UnsupportedVersion``
(``history_not_migratable``) before anything is written.

A project saved by 0.1.0rc1, before the rename of ADR-041 (manifest
``project.moana.json``, ``kind`` ``moana-project``), is migrated by renaming only its
envelope: ``kind`` becomes ``moanart-project`` and the manifest is written as
``project.moanart.json``. Its document, assets and history are unchanged (the old name
only ever existed with schema and envelope 1.0, and documents carry no product name),
so the history is kept and every ``snapshot_digest`` is the same. The record has
``member`` ``kind`` and the step ``rename-to-moanart``; the legacy manifest is
preserved byte for byte under ``migrations/<sha256>.json``.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from moanart.core.errors import ExportError, MoanArtError, UnsupportedVersion, ValidationError
from moanart.project._fs import caller_path, stat_is_directory
from moanart.project._json import read_json_object
from moanart.project._load import (
    Reader,
    consume_legacy_source,
    load_assets,
    load_envelope,
    load_json,
    load_migrations,
)
from moanart.project.limits import DEFAULT_PROJECT_LIMITS, ProjectLimits
from moanart.project.manifest import (
    LEGACY_PROJECT_KIND,
    PROJECT_KIND,
    PROJECT_MIGRATIONS,
    RENAME_STEP,
    MigrationRecord,
    migration_path,
    parse_manifest,
    relocated,
)
from moanart.project.model import MigrationBackup, Project
from moanart.project.store import SaveReport, save_project
from moanart.schema import (
    DOCUMENT_MIGRATIONS,
    SCHEMA_VERSION,
    DocumentMigration,
    MigrationRegistry,
    migrate_document,
)

__all__ = ["MigrationReport", "migrate_project"]


@dataclass(frozen=True, slots=True)
class MigrationReport:
    """What :func:`migrate_project` did.

    ``steps`` lists the applied migration IDs; when it is empty the source was
    already current, ``source_version == target_version`` and ``save`` is ``None``
    (nothing was written). Otherwise ``save`` is the report of the new project. The
    rename of a 0.1.0rc1 project (ADR-041) migrates no version: its ``steps`` are
    ``("rename-to-moanart",)`` with ``source_version == target_version``, so whether
    anything was migrated is told by ``steps``, never by comparing the versions.
    """

    source_version: str
    target_version: str
    steps: tuple[str, ...]
    save: SaveReport | None


def _history_not_migratable() -> UnsupportedVersion:
    return UnsupportedVersion(
        "a project history cannot be migrated",
        json_pointer="/history",
        context={"field": "history", "reason": "history_not_migratable"},
    )


def _backup(
    kind: Literal["document", "project"], migration: DocumentMigration, data: bytes
) -> MigrationBackup:
    sha256 = hashlib.sha256(data).hexdigest()
    record = MigrationRecord(
        source_kind=kind,
        member="schema_version",
        source_version=migration.source_version,
        target_version=migration.target_version,
        steps=migration.steps,
        path=migration_path(sha256),
        byte_length=len(data),
        sha256=sha256,
    )
    return MigrationBackup(record, data)


def _rename_legacy(
    tree: dict[str, object], data: bytes, read: Reader, limits: ProjectLimits
) -> tuple[Project, MigrationReport]:
    """Rename a 0.1.0rc1 envelope (ADR-041); everything else is verified unchanged."""
    renamed = {**tree, "kind": PROJECT_KIND}
    project = load_envelope(parse_manifest(renamed, limits=limits.parse), read, limits)
    sha256 = hashlib.sha256(data).hexdigest()
    record = MigrationRecord(
        source_kind="project",
        member="kind",
        source_version=LEGACY_PROJECT_KIND,
        target_version=PROJECT_KIND,
        steps=(RENAME_STEP,),
        path=migration_path(sha256),
        byte_length=len(data),
        sha256=sha256,
    )
    migrated = replace(project, migrations=(*project.migrations, MigrationBackup(record, data)))
    version = project.document.schema_version
    return migrated, MigrationReport(version, version, (RENAME_STEP,), None)


def _migrate_envelope(
    tree: dict[str, object],
    data: bytes,
    read: Reader,
    registry: MigrationRegistry,
    limits: ProjectLimits,
) -> tuple[Project, DocumentMigration] | None:
    if tree.get("kind") != PROJECT_KIND:
        parse_manifest(tree, limits=limits.parse)  # raises the envelope error
    PROJECT_MIGRATIONS.check(tree)
    document = tree.get("document")
    if not isinstance(document, Mapping):
        return None  # loading reports the envelope error
    version = document.get("schema_version")
    try:
        if not isinstance(version, str) or not registry.path(version):
            return None
        migration = migrate_document(document, registry=registry, limits=limits.parse)
    except MoanArtError as exc:
        raise relocated(exc) from None
    # The whole envelope (history, assets, migrations) is validated before its use.
    manifest = parse_manifest({**tree, "document": migration.document}, limits=limits.parse)
    if manifest.history:
        raise _history_not_migratable()
    assets = load_assets(manifest, read, limits)
    previous = load_migrations(manifest, read, limits)
    backup = _backup("project", migration, data)
    return Project(migration.document, assets, None, (*previous, backup)), migration


def _plan(
    data: bytes,
    read: Reader,
    registry: MigrationRegistry,
    limits: ProjectLimits,
    legacy_manifest: bool,
) -> tuple[Project | None, MigrationReport]:
    """The migrated project (``None`` when already current) and its report.

    ``legacy_manifest`` says that ``data`` is the manifest of 0.1.0rc1 of a directory
    or ZIP; its ``kind`` must then be the legacy one too (no version wrote anything
    else), otherwise the source is ``ValidationError`` ``inconsistent_legacy_manifest``.
    """
    tree = read_json_object(
        data,
        max_bytes=limits.max_manifest_bytes,
        max_depth=limits.max_manifest_depth,
        max_nodes=limits.max_manifest_nodes,
    )
    planned: tuple[Project, DocumentMigration] | None = None
    if isinstance(tree, dict) and tree.get("kind") == LEGACY_PROJECT_KIND:
        return _rename_legacy(tree, data, read, limits)
    if legacy_manifest:
        raise ValidationError(
            "a legacy project manifest must have the legacy kind",
            json_pointer="/kind",
            context={"field": "kind", "reason": "inconsistent_legacy_manifest"},
        )
    if isinstance(tree, dict) and "kind" in tree:
        planned = _migrate_envelope(tree, data, read, registry, limits)
    elif isinstance(tree, dict):
        version = tree.get("schema_version")
        if isinstance(version, str) and registry.path(version):
            migration = migrate_document(tree, registry=registry, limits=limits.parse)
            backup = _backup("document", migration, data)
            planned = Project(migration.document, migrations=(backup,)), migration
    if planned is None:
        load_json(data, read, limits)  # current: verify it exactly as loading would
        current = registry.current
        return None, MigrationReport(current, current, (), None)
    project, migration = planned
    return project, MigrationReport(
        migration.source_version, migration.target_version, migration.steps, None
    )


def _resolved(path: Path) -> Path:
    try:
        return path.resolve()
    except (OSError, RuntimeError):  # a link loop: compare the absolute paths instead
        return Path(os.path.abspath(path))


def _check_destination(source: Path, destination: Path) -> None:
    """Refuse a destination equal to, or inside, a source directory (no path echoed)."""
    if not stat_is_directory(source):
        return
    root, target = _resolved(source), _resolved(destination)
    if target == root or root in target.parents:
        raise ExportError(
            "the destination is inside the source project",
            context={"reason": "destination_inside_source"},
        )


def migrate_project(
    source: str | os.PathLike[str],
    destination: str | os.PathLike[str],
    *,
    registry: MigrationRegistry = DOCUMENT_MIGRATIONS,
    limits: ProjectLimits = DEFAULT_PROJECT_LIMITS,
) -> MigrationReport:
    """Migrate the document or project at ``source`` into a new project at ``destination``.

    ``source`` is read like :func:`~moanart.project.load_project` (directory, ``.moanart``
    ZIP or JSON file) and never written. Its document is migrated with the pure
    steps of ``registry`` (the production :data:`~moanart.schema.DOCUMENT_MIGRATIONS`
    registers none: schema 1.0 is the only version that ever existed) and validated;
    the result is saved as a directory project without ``overwrite``, with a
    migration record and the preserved original. A destination equal to, or inside,
    a source directory is ``ExportError`` ``destination_inside_source`` (resolved
    paths, links included; a JSON source may be migrated into its own directory or
    any subdirectory). Any failure leaves the source intact and commits no manifest
    at ``destination``. A current source writes nothing (identity). Raises
    ``UnsupportedVersion`` (unknown or future versions, ``history_not_migratable``),
    ``ValidationError`` (``migration_failed`` or an invalid result), ``ReadError``,
    ``BudgetExceeded`` or ``ExportError``.
    """
    if not isinstance(registry, MigrationRegistry) or registry.member != "schema_version":
        raise TypeError("registry must be a schema_version MigrationRegistry")
    if registry.current != SCHEMA_VERSION:
        raise ValueError("registry must migrate to the current schema version")
    _check_destination(caller_path(source), caller_path(destination))
    project, report = consume_legacy_source(
        source,
        limits,
        lambda data, read, legacy: _plan(data, read, registry, limits, legacy),
    )
    if project is None:
        return report
    return replace(report, save=save_project(project, destination, limits=limits))
