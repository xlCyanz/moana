"""MOANA-037 T3: projects saved before the rename to MoanArt (ADR-041).

A 0.1.0rc1 project differs from a current one only in its envelope: the manifest is
``project.moana.json`` and its ``kind`` is ``moana-project``. The legacy layouts below
are built by hand from those two published identifiers (the oracle), never by asking
the implementation to write them. Loading one fails with ``legacy_name`` and names
the replacement; :func:`migrate_project` renames the envelope only, into a new
destination, keeping the history, every snapshot digest and the original bytes.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError as PydanticValidationError

from moanart.core.errors import UnsupportedVersion, ValidationError
from moanart.project import (
    LEGACY_MANIFEST_NAME,
    LEGACY_PROJECT_KIND,
    MANIFEST_NAME,
    PROJECT_KIND,
    MigrationBackup,
    MigrationRecord,
    Project,
    ProjectLimits,
    load_project,
    migrate_project,
    migration_path,
    save_document,
    save_project,
)
from moanart.project.archive import build_archive
from moanart.schema import Document, snapshot_digest
from scripts.legacy_name import LEGACY_NAME

OLD_MANIFEST = "project.moana.json"
OLD_KIND = "moana-project"
NEW_MANIFEST = "project.moanart.json"
NEW_KIND = "moanart-project"


def _tree(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def _legacy_manifest(current: bytes) -> bytes:
    manifest = json.loads(current)
    assert manifest["kind"] == NEW_KIND
    manifest["kind"] = OLD_KIND
    return json.dumps(manifest, indent=2).encode("utf-8")


def _legacy_directory(tmp_path: Path, project: Project) -> Path:
    """A 0.1.0rc1 directory project: same files, legacy manifest name and kind."""
    save_project(project, tmp_path / "current")
    files = _tree(tmp_path / "current")
    root = tmp_path / "legacy"
    for name, data in files.items():
        target = root / (OLD_MANIFEST if name == NEW_MANIFEST else name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(_legacy_manifest(data) if name == NEW_MANIFEST else data)
    return root


def _assert_legacy_error(error: pytest.ExceptionInfo[UnsupportedVersion], field: str) -> None:
    context = error.value.context
    assert context["reason"] == "legacy_name"
    assert context["field"] == field
    assert context["replacement"] == (NEW_MANIFEST if field == "manifest" else NEW_KIND)
    assert "migrate_project" in error.value.message


def _assert_migrated(destination: Path, project: Project, original: bytes) -> None:
    files = _tree(destination)
    assert NEW_MANIFEST in files and OLD_MANIFEST not in files
    manifest = json.loads(files[NEW_MANIFEST])
    assert manifest["kind"] == NEW_KIND
    sha256 = hashlib.sha256(original).hexdigest()
    assert manifest["migrations"] == [
        {
            "source_kind": "project",
            "member": "kind",
            "source_version": OLD_KIND,
            "target_version": NEW_KIND,
            "steps": ["rename-to-moanart"],
            "path": f"migrations/{sha256}.json",
            "byte_length": len(original),
            "sha256": sha256,
        }
    ]
    assert files[f"migrations/{sha256}.json"] == original
    loaded = load_project(destination)
    assert snapshot_digest(loaded.document) == snapshot_digest(project.document)
    assert [asset.data for asset in loaded.assets] == [asset.data for asset in project.assets]
    assert project.history is not None and loaded.history is not None
    assert list(loaded.history.snapshots) == list(project.history.snapshots)
    assert snapshot_digest(loaded.history.document) == snapshot_digest(project.history.document)


def test_legacy_identifiers_are_the_published_ones() -> None:
    assert (LEGACY_MANIFEST_NAME, LEGACY_PROJECT_KIND) == (OLD_MANIFEST, OLD_KIND)
    assert (MANIFEST_NAME, PROJECT_KIND) == (NEW_MANIFEST, NEW_KIND)


def test_t3_legacy_directory_is_rejected_then_migrated(tmp_path: Path, project: Project) -> None:
    source = _legacy_directory(tmp_path, project)
    before = _tree(source)
    with pytest.raises(UnsupportedVersion) as error:
        load_project(source)
    _assert_legacy_error(error, "manifest")
    report = migrate_project(source, tmp_path / "migrated")
    assert report.steps == ("rename-to-moanart",)
    assert report.source_version == report.target_version == "1.0"
    assert report.save is not None
    _assert_migrated(tmp_path / "migrated", project, before[OLD_MANIFEST])
    assert _tree(source) == before  # the original is never written


def test_t3_legacy_archive_is_rejected_then_migrated(tmp_path: Path, project: Project) -> None:
    save_project(project, tmp_path / "current")
    files = _tree(tmp_path / "current")
    legacy = {
        (OLD_MANIFEST if name == NEW_MANIFEST else name): (
            _legacy_manifest(data) if name == NEW_MANIFEST else data
        )
        for name, data in files.items()
    }
    source = tmp_path / "legacy.moana"
    source.write_bytes(build_archive(legacy, ProjectLimits()))
    with zipfile.ZipFile(source) as archive:
        assert OLD_MANIFEST in archive.namelist()
    before = source.read_bytes()
    with pytest.raises(UnsupportedVersion) as error:
        load_project(source)
    _assert_legacy_error(error, "manifest")
    migrate_project(source, tmp_path / "migrated")
    _assert_migrated(tmp_path / "migrated", project, legacy[OLD_MANIFEST])
    assert source.read_bytes() == before


def test_t3_legacy_envelope_file_is_rejected_then_migrated(
    tmp_path: Path, project: Project
) -> None:
    root = _legacy_directory(tmp_path, project)
    source = root / "envelope.moana.json"
    original = (root / OLD_MANIFEST).read_bytes()
    (root / OLD_MANIFEST).rename(source)
    with pytest.raises(UnsupportedVersion) as error:
        load_project(source)
    _assert_legacy_error(error, "kind")
    assert error.value.json_pointer == "/kind"
    migrate_project(source, tmp_path / "migrated")
    _assert_migrated(tmp_path / "migrated", project, original)
    assert source.read_bytes() == original


def test_t3_plain_document_carries_no_name(tmp_path: Path, document: Document) -> None:
    """A ``.moana.json`` document has no product name inside: it loads as it is."""
    source = tmp_path / "sprite.moana.json"
    save_document(document, source)
    before = source.read_bytes()
    assert LEGACY_NAME.search(before.decode("utf-8")) is None
    assert snapshot_digest(load_project(source).document) == snapshot_digest(document)
    report = migrate_project(source, tmp_path / "migrated")
    assert report.steps == () and report.save is None
    assert not (tmp_path / "migrated").exists()
    assert source.read_bytes() == before


def test_t3_migrating_twice_is_the_identity(tmp_path: Path, project: Project) -> None:
    source = _legacy_directory(tmp_path, project)
    migrate_project(source, tmp_path / "once")
    once = _tree(tmp_path / "once")
    report = migrate_project(tmp_path / "once", tmp_path / "twice")
    assert report.steps == () and report.save is None
    assert not (tmp_path / "twice").exists()
    assert _tree(tmp_path / "once") == once


def test_t3_a_current_manifest_wins_over_a_legacy_one(tmp_path: Path, project: Project) -> None:
    save_project(project, tmp_path / "both")
    stray = _legacy_manifest((tmp_path / "both" / NEW_MANIFEST).read_bytes())
    (tmp_path / "both" / OLD_MANIFEST).write_bytes(stray)
    assert snapshot_digest(load_project(tmp_path / "both").document) == snapshot_digest(
        project.document
    )


def _kind_record(**change: Any) -> dict[str, Any]:
    data = b"{}"
    sha256 = hashlib.sha256(data).hexdigest()
    record: dict[str, Any] = {
        "source_kind": "project",
        "member": "kind",
        "source_version": OLD_KIND,
        "target_version": NEW_KIND,
        "steps": ("rename-to-moanart",),
        "path": migration_path(sha256),
        "byte_length": len(data),
        "sha256": sha256,
    }
    return record | change


def test_t3_kind_records_rename_only_the_legacy_kind() -> None:
    assert MigrationRecord.model_validate(_kind_record()).member == "kind"
    for change in (
        {"source_version": NEW_KIND, "target_version": OLD_KIND},
        {"source_version": "1.0", "target_version": "1.0"},
        {"source_kind": "document"},
        {"member": "schema_version"},
        {"source_version": "other-project"},
    ):
        with pytest.raises(PydanticValidationError):
            MigrationRecord.model_validate(_kind_record(**change))


# Real bytes written by the v0.1.0rc1 code (tests/fixtures/rename/README.md).
RC1 = Path(__file__).resolve().parents[2] / "fixtures" / "rename" / "rc1"
RC1_SNAPSHOTS = [
    "sha256:f2faa0b919ff3daa701d8e87962415881fa9085f9e28f15f9388da6ffe4e4059",
    "sha256:32abae8f56bc3839d8b17c24abbbfecc291a2b1ad465da9e45a626124c8dbac7",
    "sha256:054c28d1605d2af19f69ebde0e05c26e3f74ed07551cafae3ff461f96dca9d73",
]


@pytest.mark.parametrize("source", ["project", "project.zip"])
def test_t3_real_rc1_projects_are_rejected_then_migrated(tmp_path: Path, source: str) -> None:
    path = RC1 / source
    before = _tree(path) if path.is_dir() else {"": path.read_bytes()}
    with pytest.raises(UnsupportedVersion) as error:
        load_project(path)
    _assert_legacy_error(error, "manifest")
    report = migrate_project(path, tmp_path / "migrated")
    assert report.steps == ("rename-to-moanart",)
    migrated = load_project(tmp_path / "migrated")
    assert migrated.history is not None
    assert list(migrated.history.snapshots) == RC1_SNAPSHOTS
    assert snapshot_digest(migrated.document) == RC1_SNAPSHOTS[-1]
    assert [asset.id for asset in migrated.assets] == ["texture"]
    original = (RC1 / "project" / OLD_MANIFEST).read_bytes()
    (record,) = migrated.migrations
    assert record.data == original and record.record.member == "kind"
    assert (_tree(path) if path.is_dir() else {"": path.read_bytes()}) == before


def test_t3_legacy_name_with_current_kind_is_refused(tmp_path: Path, project: Project) -> None:
    """No version wrote a legacy manifest with the current kind: it is never accepted."""
    save_project(project, tmp_path / "odd")
    (tmp_path / "odd" / NEW_MANIFEST).rename(tmp_path / "odd" / OLD_MANIFEST)
    with pytest.raises(UnsupportedVersion):
        load_project(tmp_path / "odd")
    with pytest.raises(ValidationError) as error:
        migrate_project(tmp_path / "odd", tmp_path / "migrated")
    assert error.value.context["reason"] == "inconsistent_legacy_manifest"
    assert not (tmp_path / "migrated").exists()


def test_t3_previous_migration_records_are_kept(tmp_path: Path, document: Document) -> None:
    data = b'{"previous": "original"}'
    sha256 = hashlib.sha256(data).hexdigest()
    previous = MigrationRecord(
        source_kind="document",
        member="schema_version",
        source_version="0.9",
        target_version="1.0",
        steps=("test-only-0-9-to-1-0",),
        path=migration_path(sha256),
        byte_length=len(data),
        sha256=sha256,
    )
    project = Project(document, migrations=(MigrationBackup(previous, data),))
    source = _legacy_directory(tmp_path, project)
    migrate_project(source, tmp_path / "migrated")
    migrated = load_project(tmp_path / "migrated")
    assert [backup.record.member for backup in migrated.migrations] == ["schema_version", "kind"]
    assert migrated.migrations[0].data == data


def test_t3_a_project_is_renamed_at_most_once(tmp_path: Path, project: Project) -> None:
    migrate_project(_legacy_directory(tmp_path, project), tmp_path / "migrated")
    manifest_path = tmp_path / "migrated" / NEW_MANIFEST
    manifest = json.loads(manifest_path.read_bytes())
    second = dict(manifest["migrations"][0], sha256="0" * 64, path=f"migrations/{'0' * 64}.json")
    manifest["migrations"].append(second)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValidationError) as error:
        load_project(tmp_path / "migrated")
    assert error.value.context["reason"] == "invalid_manifest"


def test_t3_kind_records_carry_only_the_rename_step() -> None:
    with pytest.raises(PydanticValidationError):
        MigrationRecord.model_validate(_kind_record(steps=("other-step",)))
