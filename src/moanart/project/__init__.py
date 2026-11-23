"""Confined, verified and atomic project persistence (MOANART.md section 16, ADR-029).

A :class:`Project` holds a validated :class:`~moanart.schema.Document`, its declared PNG
:class:`Asset` values and an optional :class:`~moanart.editing.History` whose cursor is
the document. :func:`save_project` writes a directory, :func:`save_project_archive`
a deterministic ``.moanart`` ZIP and :func:`save_document` a self-contained
``.moanart.json``; :func:`load_project` reads any of the three and verifies every byte
before returning. The envelope ``project.moanart.json`` is a :class:`ProjectManifest`,
separate from ``Document``; assets and snapshots live under immutable paths derived
from their hashes and the manifest is committed last.

``project`` depends on ``core``, ``schema`` and ``editing`` only (MOANART.md section 3),
plus Pillow behind :mod:`moanart.project.assets`; it renders nothing and never imports
``export`` or ``api``.

Loading never migrates (ADR-031): another ``schema_version`` or ``project_version``
is ``UnsupportedVersion``. :func:`migrate_project` migrates explicitly into a new
destination with the pure steps of a :class:`~moanart.schema.MigrationRegistry`,
keeping the source untouched and recording provenance (:class:`MigrationRecord`)
plus the preserved original (:class:`MigrationBackup`) in the new project.
"""

from moanart.project.archive import ZIP_MAGIC
from moanart.project.assets import PNG_MIME, Asset, asset_path
from moanart.project.limits import DEFAULT_PROJECT_LIMITS, ProjectLimits
from moanart.project.manifest import (
    LEGACY_MANIFEST_NAME,
    LEGACY_PROJECT_KIND,
    MANIFEST_NAME,
    PROJECT_KIND,
    PROJECT_MIGRATIONS,
    PROJECT_VERSION,
    AssetRef,
    HistoryEntry,
    MigrationRecord,
    ProjectManifest,
    migration_path,
)
from moanart.project.migrate import MigrationReport, migrate_project
from moanart.project.model import MigrationBackup, Project
from moanart.project.store import (
    SaveReport,
    batch_path,
    encode_project,
    load_project,
    save_document,
    save_project,
    save_project_archive,
    snapshot_path,
)

__all__ = [
    "DEFAULT_PROJECT_LIMITS",
    "LEGACY_MANIFEST_NAME",
    "LEGACY_PROJECT_KIND",
    "MANIFEST_NAME",
    "PNG_MIME",
    "PROJECT_KIND",
    "PROJECT_MIGRATIONS",
    "PROJECT_VERSION",
    "ZIP_MAGIC",
    "Asset",
    "AssetRef",
    "HistoryEntry",
    "MigrationBackup",
    "MigrationRecord",
    "MigrationReport",
    "Project",
    "ProjectLimits",
    "ProjectManifest",
    "SaveReport",
    "asset_path",
    "batch_path",
    "encode_project",
    "load_project",
    "migrate_project",
    "migration_path",
    "save_document",
    "save_project",
    "save_project_archive",
    "snapshot_path",
]
