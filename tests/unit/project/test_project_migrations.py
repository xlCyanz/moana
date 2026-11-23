"""MOANA-021: explicit, preserving migration of projects (ADR-031).

The 0.8 and 0.9 document formats are test-only (``tests/fixtures/migration``); the
production registry knows schema 1.0 only. Every migration here passes the test-only
registry explicitly.
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from moanart.core.errors import (
    BudgetExceeded,
    ExportError,
    MoanArtError,
    UnsupportedVersion,
    ValidationError,
)
from moanart.core.limits import MAX_PROJECT_MIGRATIONS
from moanart.project import (
    MANIFEST_NAME,
    PROJECT_MIGRATIONS,
    Asset,
    MigrationBackup,
    MigrationRecord,
    Project,
    ProjectLimits,
    encode_project,
    load_project,
    migrate_project,
    migration_path,
    save_project,
    save_project_archive,
)
from moanart.project.archive import build_archive
from moanart.render import render
from moanart.schema import MigrationRegistry, canonical_json, validate_document
from tests.fixtures.migration.formats import EXPECTED, OLDEST, PREVIOUS, TEST_ONLY_MIGRATIONS

from .conftest import PngFactory

_COUNTED = ("mkdir", "open", "read", "write", "fsync", "link", "replace")
_NOT_A_REGISTRY: Any = "1.0"


def _expected() -> Any:
    return validate_document(EXPECTED.read_bytes())


def _state(root: Path) -> dict[str, tuple[bytes | None, int, int]]:
    """Bytes (``None`` for a directory), inode and modification time of ``root`` and
    of every file and directory under it."""
    return {
        path.relative_to(root).as_posix(): (
            path.read_bytes() if path.is_file() else None,
            path.stat().st_ino,
            path.stat().st_mtime_ns,
        )
        for path in [root, *sorted(root.rglob("*"))]
    }


def _legacy_file(tmp_path: Path, fixture: Path = OLDEST) -> Path:
    source = tmp_path / "legacy" / fixture.name
    source.parent.mkdir()
    source.write_bytes(fixture.read_bytes())
    return source


def _legacy_project(tmp_path: Path, png: PngFactory) -> tuple[Path, Asset]:
    """A directory project whose envelope embeds the test-only 0.9 document."""
    asset = Asset.from_png("sheet", png(3, 2, (1, 2, 3, 255)))
    root = tmp_path / "legacy_project"
    save_project(Project(_expected(), (asset,)), root)
    manifest = json.loads((root / MANIFEST_NAME).read_text(encoding="utf-8"))
    manifest["document"] = json.loads(PREVIOUS.read_text(encoding="utf-8"))
    (root / MANIFEST_NAME).write_text(json.dumps(manifest), encoding="utf-8")
    return root, asset


def _legacy_archive(tmp_path: Path, png: PngFactory) -> tuple[Path, Asset, bytes]:
    """A ``.moanart`` ZIP whose manifest embeds the test-only 0.9 document."""
    asset = Asset.from_png("sheet", png(3, 2, (1, 2, 3, 255)))
    current = tmp_path / "current.moanart"
    save_project_archive(Project(_expected(), (asset,)), current)
    with zipfile.ZipFile(current) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    manifest = json.loads(files[MANIFEST_NAME])
    manifest["document"] = json.loads(PREVIOUS.read_text(encoding="utf-8"))
    files[MANIFEST_NAME] = json.dumps(manifest).encode("utf-8")
    source = tmp_path / "legacy.moanart"
    source.write_bytes(build_archive(files, ProjectLimits()))
    current.unlink()
    return source, asset, files[MANIFEST_NAME]


def _fake_backup(index: int) -> MigrationBackup:
    data = json.dumps({"fake_original": index}).encode("utf-8")
    sha256 = hashlib.sha256(data).hexdigest()
    record = MigrationRecord(
        source_kind="document",
        member="schema_version",
        source_version="0.9",
        target_version="1.0",
        steps=("test-only-0-9-to-1-0",),
        path=migration_path(sha256),
        byte_length=len(data),
        sha256=sha256,
    )
    return MigrationBackup(record, data)


def _record(**change: object) -> dict[str, object]:
    record = _fake_backup(0).record.model_dump(mode="json")
    record.update(change)
    return record


def _rewrite(root: Path, change: Callable[[dict[str, Any]], None]) -> None:
    manifest = json.loads((root / MANIFEST_NAME).read_text(encoding="utf-8"))
    change(manifest)
    (root / MANIFEST_NAME).write_text(json.dumps(manifest), encoding="utf-8")


# --- AC1 -------------------------------------------------------------------------------


def test_ac1_document_fixture_migrates_into_a_new_project(tmp_path: Path) -> None:
    source = _legacy_file(tmp_path)
    original = source.read_bytes()
    destination = tmp_path / "migrated"
    report = migrate_project(source, destination, registry=TEST_ONLY_MIGRATIONS)
    assert (report.source_version, report.target_version) == ("0.8", "1.0")
    assert report.steps == ("test-only-0-8-to-0-9", "test-only-0-9-to-1-0")
    assert report.save is not None
    sha256 = hashlib.sha256(original).hexdigest()
    assert report.save.written == (migration_path(sha256), MANIFEST_NAME)
    assert source.read_bytes() == original

    project = load_project(destination)
    expected = _expected()
    assert canonical_json(project.document) == canonical_json(expected)
    assert render(project.document).digest == render(expected).digest
    assert project.assets == () and project.history is None
    (backup,) = project.migrations
    assert backup.data == original
    assert backup.record == MigrationRecord(
        source_kind="document",
        member="schema_version",
        source_version="0.8",
        target_version="1.0",
        steps=report.steps,
        path=f"migrations/{sha256}.json",
        byte_length=len(original),
        sha256=sha256,
    )
    assert (destination / backup.path).read_bytes() == original
    manifest = json.loads((destination / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest["migrations"][0]["source_version"] == "0.8"


def test_ac1_project_fixture_keeps_assets_and_render(tmp_path: Path, png: PngFactory) -> None:
    source, asset = _legacy_project(tmp_path, png)
    original = (source / MANIFEST_NAME).read_bytes()
    destination = tmp_path / "migrated"
    report = migrate_project(source, destination, registry=TEST_ONLY_MIGRATIONS)
    assert report.steps == ("test-only-0-9-to-1-0",)
    project = load_project(destination)
    assert project.assets == (asset,)
    assert render(project.document).digest == render(_expected()).digest
    (backup,) = project.migrations
    assert backup.record.source_kind == "project"
    assert backup.data == original


def test_ac1_migration_records_survive_saving_again(tmp_path: Path) -> None:
    destination = tmp_path / "migrated"
    migrate_project(_legacy_file(tmp_path), destination, registry=TEST_ONLY_MIGRATIONS)
    project = load_project(destination)
    save_project(project, tmp_path / "copy")
    assert load_project(tmp_path / "copy") == project
    save_project_archive(project, tmp_path / "copy.moanart")
    assert load_project(tmp_path / "copy.moanart") == project
    # Explicit empty migrations load like an omitted member; saving omits it again.
    plain = tmp_path / "plain"
    save_project(Project(project.document), plain)
    assert "migrations" not in (plain / MANIFEST_NAME).read_text(encoding="utf-8")
    _rewrite(plain, lambda manifest: manifest.update(migrations=[]))
    assert load_project(plain) == Project(project.document)


def test_ac1_a_migrated_project_can_be_migrated_again(tmp_path: Path) -> None:
    first = tmp_path / "first"
    migrate_project(_legacy_file(tmp_path), first, registry=TEST_ONLY_MIGRATIONS)
    _rewrite(
        first,
        lambda manifest: manifest.update(document=json.loads(PREVIOUS.read_text(encoding="utf-8"))),
    )
    second = tmp_path / "second"
    migrate_project(first, second, registry=TEST_ONLY_MIGRATIONS)
    records = [backup.record for backup in load_project(second).migrations]
    assert [(r.source_kind, r.source_version) for r in records] == [
        ("document", "0.8"),
        ("project", "0.9"),
    ]


# --- AC2 -------------------------------------------------------------------------------


def test_ac2_opening_an_old_file_neither_writes_nor_migrates(
    tmp_path: Path, png: PngFactory
) -> None:
    source = _legacy_file(tmp_path)
    project_root, _ = _legacy_project(tmp_path, png)
    archive, _, _ = _legacy_archive(tmp_path, png)
    before = _state(tmp_path)
    with pytest.raises(UnsupportedVersion) as caught:
        load_project(source)
    assert caught.value.json_pointer == "/schema_version"
    for old in (project_root, archive):
        with pytest.raises(UnsupportedVersion) as caught:
            load_project(old)
        assert caught.value.json_pointer == "/document/schema_version"
    assert _state(tmp_path) == before


def test_ac1_archive_fixture_migrates_and_stays_intact(tmp_path: Path, png: PngFactory) -> None:
    source, asset, inner_manifest = _legacy_archive(tmp_path, png)
    original = source.read_bytes()
    destination = tmp_path / "migrated"
    report = migrate_project(source, destination, registry=TEST_ONLY_MIGRATIONS)
    assert report.steps == ("test-only-0-9-to-1-0",)
    assert source.read_bytes() == original
    project = load_project(destination)
    assert project.assets == (asset,)
    assert render(project.document).digest == render(_expected()).digest
    (backup,) = project.migrations
    assert backup.record.source_kind == "project"
    assert backup.data == inner_manifest  # the manifest inside the ZIP, byte for byte


def test_ac2_migration_never_replaces_an_existing_project(tmp_path: Path, png: PngFactory) -> None:
    source, _ = _legacy_project(tmp_path, png)
    other = tmp_path / "other"
    save_project(Project(_expected()), other)
    before = _state(tmp_path)
    with pytest.raises(ExportError) as caught:
        migrate_project(source, other, registry=TEST_ONLY_MIGRATIONS)
    assert caught.value.context["reason"] == "exists"
    assert _state(tmp_path) == before


@pytest.mark.parametrize("inside", [".", "sub", "sub/deeper", "assets"])
def test_ac2_destination_inside_the_source_is_refused(
    tmp_path: Path, png: PngFactory, inside: str
) -> None:
    source, _ = _legacy_project(tmp_path, png)
    before = _state(source)  # the source tree, its root and directories included
    for destination in (source / inside, tmp_path / "." / source.name / inside):
        with pytest.raises(ExportError) as caught:
            migrate_project(source, destination, registry=TEST_ONLY_MIGRATIONS)
        assert caught.value.context == {"reason": "destination_inside_source"}
        assert str(tmp_path) not in str(caught.value)
    if os.name != "nt":
        link = tmp_path / "link"
        link.symlink_to(source, target_is_directory=True)
        with pytest.raises(ExportError):
            migrate_project(source, link / "sub", registry=TEST_ONLY_MIGRATIONS)
        link.unlink()
    assert _state(source) == before


def test_ac2_a_document_migrated_beside_itself_stays_intact(tmp_path: Path) -> None:
    source = _legacy_file(tmp_path)
    original = source.read_bytes()
    migrate_project(source, source.parent, registry=TEST_ONLY_MIGRATIONS)
    assert source.read_bytes() == original
    assert load_project(source.parent).migrations[0].data == original


# --- T1 --------------------------------------------------------------------------------


def test_t1_migrating_the_destination_again_writes_nothing(tmp_path: Path) -> None:
    destination = tmp_path / "migrated"
    migrate_project(_legacy_file(tmp_path), destination, registry=TEST_ONLY_MIGRATIONS)
    before = _state(tmp_path)
    again = migrate_project(destination, tmp_path / "again", registry=TEST_ONLY_MIGRATIONS)
    assert again.steps == () and again.save is None
    assert again.source_version == again.target_version == "1.0"
    assert _state(tmp_path) == before
    assert not (tmp_path / "again").exists()
    # A current plain document is verified and left alone too.
    current = tmp_path / "current.moanart.json"
    current.write_bytes(EXPECTED.read_bytes())
    assert migrate_project(current, tmp_path / "unused").save is None


@pytest.mark.parametrize(("version", "relation"), [("1.1", "future"), ("0.7", "past")])
def test_t1_unknown_document_versions_are_rejected_before_writing(
    tmp_path: Path, png: PngFactory, version: str, relation: str
) -> None:
    source = tmp_path / "doc.moanart.json"
    tree = json.loads(PREVIOUS.read_text(encoding="utf-8"))
    tree["schema_version"] = version
    source.write_text(json.dumps(tree), encoding="utf-8")
    with pytest.raises(UnsupportedVersion) as caught:
        migrate_project(source, tmp_path / "out", registry=TEST_ONLY_MIGRATIONS)
    assert caught.value.context["relation"] == relation
    project_root, _ = _legacy_project(tmp_path, png)
    _rewrite(project_root, lambda manifest: manifest["document"].update(schema_version=version))
    with pytest.raises(UnsupportedVersion) as caught:
        migrate_project(project_root, tmp_path / "out", registry=TEST_ONLY_MIGRATIONS)
    assert caught.value.json_pointer == "/document/schema_version"
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize(
    ("version", "relation"), [("2.0", "future"), ("0.1", "past"), ("next", "unknown")]
)
def test_t1_unknown_project_versions_are_rejected(
    tmp_path: Path, version: str, relation: str
) -> None:
    root = tmp_path / "p"
    save_project(Project(_expected()), root)
    _rewrite(root, lambda manifest: manifest.update(project_version=version, extra=1))
    for call in (
        lambda: load_project(root),
        lambda: migrate_project(root, tmp_path / "out", registry=TEST_ONLY_MIGRATIONS),
    ):
        with pytest.raises(UnsupportedVersion) as caught:
            call()
        assert caught.value.json_pointer == "/project_version"
        assert caught.value.context["relation"] == relation
    assert PROJECT_MIGRATIONS.versions == frozenset({"1.0"})


def test_t1_envelope_errors_keep_their_pointers(tmp_path: Path, png: PngFactory) -> None:
    root, _ = _legacy_project(tmp_path, png)
    _rewrite(root, lambda manifest: manifest["document"].pop("test_only_format"))
    with pytest.raises(ValidationError) as caught:
        migrate_project(root, tmp_path / "out", registry=TEST_ONLY_MIGRATIONS)
    assert caught.value.json_pointer == "/document/schema_version"
    assert caught.value.context["reason"] == "migration_failed"
    _rewrite(root, lambda manifest: manifest.update(kind="other"))
    with pytest.raises(ValidationError) as caught:
        migrate_project(root, tmp_path / "out", registry=TEST_ONLY_MIGRATIONS)
    assert caught.value.context["reason"] == "invalid_manifest"
    _rewrite(root, lambda manifest: manifest.update(kind="moanart-project", document=[]))
    with pytest.raises(ValidationError) as caught:
        migrate_project(root, tmp_path / "out", registry=TEST_ONLY_MIGRATIONS)
    assert caught.value.json_pointer == "/document"
    _rewrite(
        root,
        lambda manifest: manifest.update(
            document=json.loads(PREVIOUS.read_text(encoding="utf-8")), history="x"
        ),
    )
    with pytest.raises(ValidationError) as caught:
        migrate_project(root, tmp_path / "out", registry=TEST_ONLY_MIGRATIONS)
    assert caught.value.context["reason"] == "invalid_manifest"
    assert caught.value.details[0].json_pointer == "/history"
    not_object = tmp_path / "list.moanart.json"
    not_object.write_text("[]", encoding="utf-8")
    with pytest.raises(ValidationError):
        migrate_project(not_object, tmp_path / "out", registry=TEST_ONLY_MIGRATIONS)
    assert not (tmp_path / "out").exists()


def test_t1_history_has_no_migration_contract(
    tmp_path: Path, project: Project, png: PngFactory
) -> None:
    root = tmp_path / "with_history"
    save_project(project, root)
    _rewrite(
        root,
        lambda manifest: manifest.update(document=json.loads(PREVIOUS.read_text(encoding="utf-8"))),
    )
    before = _state(tmp_path)
    with pytest.raises(UnsupportedVersion) as caught:
        migrate_project(root, tmp_path / "out", registry=TEST_ONLY_MIGRATIONS)
    assert caught.value.json_pointer == "/history"
    assert caught.value.context["reason"] == "history_not_migratable"
    assert _state(tmp_path) == before


def test_t1_registry_must_migrate_documents_to_the_current_schema(tmp_path: Path) -> None:
    source = _legacy_file(tmp_path)
    with pytest.raises(TypeError):
        migrate_project(source, tmp_path / "out", registry=_NOT_A_REGISTRY)
    with pytest.raises(TypeError):
        migrate_project(source, tmp_path / "out", registry=PROJECT_MIGRATIONS)
    with pytest.raises(ValueError, match="current schema"):
        migrate_project(
            source,
            tmp_path / "out",
            registry=MigrationRegistry(member="schema_version", current="2.0"),
        )
    # The production registry does not know the test-only format.
    with pytest.raises(UnsupportedVersion):
        migrate_project(source, tmp_path / "out")


def test_t1_preserved_originals_are_verified_and_bounded(tmp_path: Path) -> None:
    destination = tmp_path / "migrated"
    migrate_project(_legacy_file(tmp_path), destination, registry=TEST_ONLY_MIGRATIONS)
    project = load_project(destination)
    (backup,) = project.migrations
    with pytest.raises(BudgetExceeded) as caught:
        load_project(destination, limits=ProjectLimits(max_migrations=0))
    assert caught.value.context["resource"] == "project_migrations"
    with pytest.raises(BudgetExceeded) as caught:
        encode_project(project, limits=ProjectLimits(max_migrations=0))
    assert caught.value.context["resource"] == "project_migrations"
    small = ProjectLimits(max_manifest_bytes=backup.record.byte_length - 1)
    with pytest.raises(BudgetExceeded) as caught:
        encode_project(Project(project.document, migrations=project.migrations), limits=small)
    assert caught.value.context["resource"] == "migration_bytes"
    _rewrite(destination, lambda manifest: manifest["migrations"][0].update(byte_length=10**8))
    with pytest.raises(BudgetExceeded) as caught:
        load_project(destination)
    assert caught.value.context["resource"] == "migration_bytes"
    _rewrite(
        destination,
        lambda manifest: manifest["migrations"][0].update(byte_length=backup.record.byte_length),
    )
    (destination / backup.path).write_bytes(backup.data.replace(b"0.8", b"0.9"))
    with pytest.raises(ValidationError) as invalid:
        load_project(destination)
    assert invalid.value.context == {"reason": "checksum_mismatch", "migration": 0}
    _rewrite(destination, lambda manifest: manifest["migrations"][0].update(path="../x.json"))
    with pytest.raises(ValidationError) as invalid:
        load_project(destination)
    assert invalid.value.context["reason"] == "invalid_manifest"
    assert invalid.value.details[0].json_pointer == "/migrations/0"


@pytest.mark.parametrize(
    ("change", "pointer"),
    [
        ({"source_version": "1.0"}, "/migrations/0"),
        ({"source_version": "1.1"}, "/migrations/0"),
        ({"member": "revision"}, "/migrations/0/member"),
        ({"steps": []}, "/migrations/0/steps"),
        ({"steps": [f"s{index}" for index in range(17)]}, "/migrations/0/steps"),
        ({"steps": ["Bad"]}, "/migrations/0/steps/0"),
        ({"source_version": "0.09"}, "/migrations/0/source_version"),
    ],
)
def test_t1_migration_records_are_strict(
    tmp_path: Path, change: dict[str, object], pointer: str
) -> None:
    root = tmp_path / "p"
    save_project(Project(_expected(), migrations=(_fake_backup(0),)), root)
    assert load_project(root).migrations == (_fake_backup(0),)
    _rewrite(root, lambda manifest: manifest.update(migrations=[_record(**change)]))
    with pytest.raises(ValidationError) as caught:
        load_project(root)
    assert caught.value.context["reason"] == "invalid_manifest"
    assert caught.value.details[0].json_pointer == pointer


def test_t1_each_original_is_preserved_once(tmp_path: Path) -> None:
    root = tmp_path / "p"
    save_project(Project(_expected(), migrations=(_fake_backup(0),)), root)
    _rewrite(root, lambda manifest: manifest.update(migrations=[_record(), _record()]))
    with pytest.raises(ValidationError) as caught:
        load_project(root)
    assert caught.value.context["reason"] == "invalid_manifest"
    with pytest.raises(ValidationError) as invalid:
        Project(_expected(), migrations=(_fake_backup(0), _fake_backup(0)))
    assert invalid.value.context == {"field": "migrations", "reason": "duplicate_migration"}


def test_t1_migration_budget_is_checked_before_writing(tmp_path: Path) -> None:
    full = tuple(_fake_backup(index) for index in range(MAX_PROJECT_MIGRATIONS))
    root = tmp_path / "full"
    save_project(Project(_expected(), migrations=full), root)
    assert len(load_project(root).migrations) == MAX_PROJECT_MIGRATIONS
    _rewrite(
        root,
        lambda manifest: manifest.update(document=json.loads(PREVIOUS.read_text(encoding="utf-8"))),
    )
    with pytest.raises(BudgetExceeded) as caught:
        migrate_project(root, tmp_path / "out", registry=TEST_ONLY_MIGRATIONS)
    assert caught.value.context["resource"] == "project_migrations"
    assert not (tmp_path / "out").exists()
    # A ninth record on disk is refused with the default limits, before reading it.
    ninth = _fake_backup(MAX_PROJECT_MIGRATIONS)
    _rewrite(
        root,
        lambda manifest: manifest.update(
            document=json.loads(EXPECTED.read_text(encoding="utf-8")),
            migrations=[*manifest["migrations"], ninth.record.model_dump(mode="json")],
        ),
    )
    with pytest.raises(BudgetExceeded) as caught:
        load_project(root)
    assert caught.value.context["resource"] == "project_migrations"
    for value in (MAX_PROJECT_MIGRATIONS + 1, -1, True):
        with pytest.raises(ValidationError):
            ProjectLimits(max_migrations=value)


def test_t1_future_envelope_wins_over_an_old_document(tmp_path: Path, png: PngFactory) -> None:
    root, _ = _legacy_project(tmp_path, png)
    _rewrite(root, lambda manifest: manifest.update(project_version="2.0"))
    for call in (
        lambda: load_project(root),
        lambda: migrate_project(root, tmp_path / "out", registry=TEST_ONLY_MIGRATIONS),
    ):
        with pytest.raises(UnsupportedVersion) as caught:
            call()
        assert caught.value.json_pointer == "/project_version"
        assert caught.value.context["relation"] == "future"


def test_t1_backups_are_checked_in_memory(tmp_path: Path) -> None:
    destination = tmp_path / "migrated"
    migrate_project(_legacy_file(tmp_path), destination, registry=TEST_ONLY_MIGRATIONS)
    (backup,) = load_project(destination).migrations
    with pytest.raises(ValidationError) as caught:
        MigrationBackup(backup.record, backup.data + b" ")
    assert caught.value.context["reason"] == "checksum_mismatch"
    with pytest.raises(TypeError):
        MigrationBackup(backup.record.model_dump(), backup.data)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        MigrationBackup(backup.record, bytearray(backup.data))  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        Project(_expected(), migrations=[backup])  # type: ignore[arg-type]
    with pytest.raises(BudgetExceeded) as budget:
        Project(_expected(), migrations=(backup,) * (MAX_PROJECT_MIGRATIONS + 1))
    assert budget.value.context["resource"] == "project_migrations"


# --- T2 --------------------------------------------------------------------------------


class _Counter:
    """Wraps the ``os`` calls of a migration; the call number ``fail_at`` raises EIO."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, fail_at: int) -> None:
        self.calls: list[str] = []
        self.fail_at = fail_at
        for name in _COUNTED:
            monkeypatch.setattr(os, name, self._wrap(getattr(os, name)))

    def _wrap(self, original: Callable[..., Any]) -> Callable[..., Any]:
        def call(*args: Any, **kwargs: Any) -> Any:
            self.calls.append(original.__name__)
            if len(self.calls) - 1 == self.fail_at:
                raise OSError(errno.EIO, "simulated failure")
            return original(*args, **kwargs)

        return call


@pytest.mark.parametrize("kind", ["document", "project"])
def test_t2_failure_at_every_step_keeps_the_original_intact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    png: PngFactory,
    confinement: bool,
    kind: str,
) -> None:
    if kind == "document":
        source = _legacy_file(tmp_path)
        tree = source.parent
    else:
        source, _ = _legacy_project(tmp_path, png)
        tree = source
    original = _state(tree)
    step = 0
    while True:
        destination = tmp_path / f"run{step}"
        with monkeypatch.context() as patch:
            counter = _Counter(patch, step)
            try:
                migrate_project(source, destination, registry=TEST_ONLY_MIGRATIONS)
            except MoanArtError as exc:
                failed: MoanArtError | None = exc
            else:
                failed = None
        step += 1
        assert _state(tree) == original, (step, counter.calls)
        if step > len(counter.calls):  # every call has failed once
            assert failed is None and step > 10
            break
        if failed is None:
            # Only the best-effort sync after the commit may fail without an error.
            assert counter.calls[step - 1] in ("open", "fsync")
            (backup,) = load_project(destination).migrations
            assert backup.record.source_kind == kind
            continue
        assert failed.context.get("errno") == "EIO"
        assert str(tmp_path) not in str(failed)
        assert not (destination / MANIFEST_NAME).exists()
        with pytest.raises(UnsupportedVersion):
            load_project(source)  # still the untouched test-only original


def test_t2_a_failing_second_step_writes_nothing(tmp_path: Path) -> None:
    tree = json.loads(OLDEST.read_text(encoding="utf-8"))
    del tree["test_only_format"]  # the 0.8 -> 0.9 step succeeds, 0.9 -> 1.0 fails
    source = tmp_path / "legacy" / "doc.moanart.json"
    source.parent.mkdir()
    source.write_text(json.dumps(tree), encoding="utf-8")
    before = _state(tmp_path)
    with pytest.raises(ValidationError) as caught:
        migrate_project(source, tmp_path / "out", registry=TEST_ONLY_MIGRATIONS)
    assert caught.value.context["migration"] == "test-only-0-9-to-1-0"
    assert _state(tmp_path) == before


def test_ac2_unresolvable_paths_are_compared_as_absolute(
    tmp_path: Path, png: PngFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, _ = _legacy_project(tmp_path, png)

    def loop(self: Path, strict: bool = False) -> Path:
        raise RuntimeError("symlink loop")

    monkeypatch.setattr(Path, "resolve", loop)
    with pytest.raises(ExportError) as caught:
        migrate_project(source, source / "sub", registry=TEST_ONLY_MIGRATIONS)
    assert caught.value.context == {"reason": "destination_inside_source"}
