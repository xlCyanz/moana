"""T1/T3 of MOANA-020: simulated disk failures keep the previous project intact."""

from __future__ import annotations

import errno
import os
import stat
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from moana.core.errors import ExportError, ReadError, ValidationError
from moana.export.atomic import commit_bytes
from moana.project import (
    MANIFEST_NAME,
    Asset,
    Project,
    _fs,
    load_project,
    save_document,
    save_project,
    save_project_archive,
)
from moana.schema import Document, canonical_json

from .conftest import PngFactory, make_batch

_COUNTED = ("mkdir", "open", "write", "fsync", "link", "replace")
_POSIX_ONLY = pytest.mark.skipif(os.name == "nt", reason="POSIX permissions and links")


def _fail(*_args: Any, **_kwargs: Any) -> Any:
    raise OSError(errno.EIO, "simulated disk failure")


def _leftovers(root: Path) -> list[Path]:
    return [path for path in root.rglob("*") if path.name.endswith(".tmp")]


def _state(root: Path) -> dict[str, tuple[bytes, int]]:
    """Bytes and inode of every file under ``root``, by relative path."""
    return {
        path.relative_to(root).as_posix(): (path.read_bytes(), path.stat().st_ino)
        for path in root.rglob("*")
        if path.is_file()
    }


def _newer(project: Project, png: PngFactory) -> Project:
    """``project`` plus one edit (new snapshot and batch) and one new asset."""
    assert project.history is not None
    recolor = {"type": "set_color", "target_id": "body_fill", "color": "ink"}
    history = project.history.edit(make_batch(project.document, recolor))
    extra = Asset.from_png("extra", png(5, 5, (90, 80, 70, 60)))
    return Project(history.document, (*project.assets, extra), history)


class _Counter:
    """Wraps the ``os`` calls of a save; the call number ``fail_at`` raises EIO."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, fail_at: int | None) -> None:
        self.calls: list[str] = []
        self.fail_at = fail_at
        for name in _COUNTED:
            monkeypatch.setattr(os, name, self._wrap(name, getattr(os, name)))

    def _wrap(self, name: str, original: Callable[..., Any]) -> Callable[..., Any]:
        def call(*args: Any, **kwargs: Any) -> Any:
            self.calls.append(name)
            if len(self.calls) - 1 == self.fail_at:
                raise OSError(errno.EIO, "simulated failure")
            return original(*args, **kwargs)

        return call


@pytest.mark.parametrize("first_save", [True, False], ids=["first", "resave"])
def test_t1_failure_at_every_step_keeps_the_previous_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    project: Project,
    png: PngFactory,
    confinement: bool,
    first_save: bool,
) -> None:
    new = _newer(project, png)
    step = 0
    while True:
        root = tmp_path / f"run{step}"
        if not first_save:
            save_project(project, root)
        before = _state(root) if root.exists() else {}
        with monkeypatch.context() as patch:
            counter = _Counter(patch, step)
            try:
                save_project(new, root, overwrite=not first_save)
            except ExportError as exc:
                failed: ExportError | None = exc
            else:
                failed = None
        step += 1
        if step > len(counter.calls):  # every call has failed once
            assert failed is None
            assert step > 20
            break
        if failed is None:
            # Only the best-effort sync after the commit may fail without an error.
            commit = max(i for i, name in enumerate(counter.calls) if name in ("link", "replace"))
            assert step - 1 > commit
            assert counter.calls[step - 1] in ("open", "fsync")
            assert load_project(root) == new
            continue
        assert failed.context["reason"] == "io_error", (step, counter.calls[step - 1])
        assert failed.context.get("errno") == "EIO"
        assert str(tmp_path) not in str(failed)
        after = _state(root) if root.exists() else {}
        for name, (data, inode) in before.items():
            assert after[name] == (data, inode), (step, name)
        assert _leftovers(tmp_path) == []
        if first_save:
            assert MANIFEST_NAME not in after
        else:
            assert load_project(root) == project


def test_t1_commit_order_content_then_directories_then_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, project: Project, png: PngFactory
) -> None:
    root = tmp_path / "p"
    save_project(project, root)
    new = _newer(project, png)
    folders = {".", "assets", "history", "history/snapshots", "history/batches"}
    inodes = {(root / name).stat().st_ino: name for name in folders}
    events: list[tuple[str, str]] = []
    real_fsync, real_replace, real_link = os.fsync, os.replace, os.link

    def fsync(descriptor: int) -> None:
        info = os.fstat(descriptor)
        kind = inodes[info.st_ino] if stat.S_ISDIR(info.st_mode) else "file"
        events.append(("fsync", kind))
        real_fsync(descriptor)

    def committing(original: Callable[..., Any]) -> Callable[..., Any]:
        def commit(source: Any, destination: Any, **kwargs: Any) -> Any:
            events.append(("commit", Path(destination).name))
            return original(source, destination, **kwargs)

        return commit

    monkeypatch.setattr(os, "fsync", fsync)
    monkeypatch.setattr(os, "replace", committing(real_replace))
    monkeypatch.setattr(os, "link", committing(real_link))
    save_project(new, root, overwrite=True)
    monkeypatch.undo()
    manifest = events.index(("commit", MANIFEST_NAME))
    for index, event in enumerate(events):
        if event[0] == "commit":
            assert events[index - 1] == ("fsync", "file")
    synced = {kind for action, kind in events[:manifest] if action == "fsync"}
    assert folders <= synced
    assert events[manifest + 1 :] == [("fsync", ".")]
    written = [kind for action, kind in events[:manifest] if action == "commit"]
    assert len(written) == 3  # new snapshot, new batch and new asset


@pytest.mark.parametrize(("code", "fails"), [(errno.EIO, True), (errno.EINVAL, False)])
def test_t1_directory_sync_failure_aborts_before_the_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    project: Project,
    png: PngFactory,
    code: int,
    fails: bool,
) -> None:
    root = tmp_path / "p"
    save_project(project, root)
    before = (root / MANIFEST_NAME).read_bytes()
    real_fsync = os.fsync

    def fsync(descriptor: int) -> None:
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise OSError(code, "directory fsync")
        real_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", fsync)
    new = _newer(project, png)
    if not fails:  # a filesystem without directory fsync is accepted
        save_project(new, root, overwrite=True)
        monkeypatch.undo()
        assert load_project(root) == new
        return
    with pytest.raises(ExportError) as caught:
        save_project(new, root, overwrite=True)
    monkeypatch.undo()
    assert caught.value.context["reason"] == "io_error"
    assert (root / MANIFEST_NAME).read_bytes() == before


def test_t3_failure_after_new_assets_keeps_previous_manifest_and_assets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    document: Document,
    png: PngFactory,
) -> None:
    root = tmp_path / "p"
    old_asset = Asset.from_png("old_tex", png(2, 2, (1, 2, 3, 4)))
    old = Project(document, (old_asset,))
    save_project(old, root)
    new_asset = Asset.from_png("new_tex", png(3, 3, (9, 8, 7, 6)))
    new = Project(document, (old_asset, new_asset))
    real_replace = os.replace

    def replace(source: Any, destination: Any, **kwargs: Any) -> None:
        if Path(destination).name == MANIFEST_NAME:
            raise OSError(errno.ENOSPC, "simulated full disk")
        real_replace(source, destination, **kwargs)

    monkeypatch.setattr(os, "replace", replace)
    with pytest.raises(ExportError) as caught:
        save_project(new, root, overwrite=True)
    monkeypatch.undo()
    assert caught.value.context["file_name"] == MANIFEST_NAME
    # The new asset was written and synced before the commit that failed: an orphan.
    assert (root / new_asset.path).read_bytes() == new_asset.data
    assert (root / old_asset.path).read_bytes() == old_asset.data
    assert load_project(root) == old
    retry = save_project(new, root, overwrite=True)
    assert retry.reused == tuple(sorted((old_asset.path, new_asset.path)))
    assert load_project(root) == new


def test_t3_new_save_never_rewrites_referenced_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, project: Project
) -> None:
    root = tmp_path / "p"
    save_project(project, root)
    before = _state(root)
    replaced: list[str] = []
    original = os.replace

    def spy(source: Any, destination: Any, **kwargs: Any) -> None:
        replaced.append(Path(destination).name)
        original(source, destination, **kwargs)

    monkeypatch.setattr(os, "replace", spy)
    save_project(project, root, overwrite=True)
    assert replaced == [MANIFEST_NAME]
    after = _state(root)
    for name, value in before.items():
        if name != MANIFEST_NAME:
            assert after[name] == value


@pytest.mark.parametrize("stage", ["write", "fsync", "replace", "link"])
def test_t1_archive_failure_keeps_the_previous_archive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    document: Document,
    project: Project,
    stage: str,
) -> None:
    target = tmp_path / "p.moana"
    if stage != "link":
        save_project_archive(Project(document), target)
    before = target.read_bytes() if target.exists() else None
    monkeypatch.setattr(os, stage, _fail)
    with pytest.raises(ExportError):
        save_project_archive(project, target, overwrite=stage != "link")
    monkeypatch.undo()
    assert (target.read_bytes() if target.exists() else None) == before
    assert _leftovers(tmp_path) == []


def test_t1_single_file_saves_never_overwrite_implicitly(
    tmp_path: Path, document: Document, project: Project
) -> None:
    target = tmp_path / "doc.moana.json"
    save_document(document, target)
    with pytest.raises(ExportError) as caught:
        save_document(document, target)
    assert caught.value.context["reason"] == "exists"
    save_document(document, target, overwrite=True)
    with pytest.raises(ExportError) as missing:
        save_project_archive(project, tmp_path / "absent" / "p.moana")
    assert missing.value.context["reason"] == "missing_directory"
    (tmp_path / "folder").mkdir()
    for overwrite in (False, True):
        with pytest.raises(ExportError) as folder:
            save_document(document, tmp_path / "folder", overwrite=overwrite)
        assert folder.value.context["reason"] == "is_directory"
    with pytest.raises(TypeError):
        save_document({}, target)  # type: ignore[arg-type]


# --- parity with moana.export.atomic (ADR-019) ---------------------------------------


class _WindowsNoLinks(OSError):
    winerror = 1  # ERROR_INVALID_FUNCTION, as FAT/exFAT report it


class _WindowsNotSameDevice(OSError):
    winerror = 17  # ERROR_NOT_SAME_DEVICE


def _raising(error: BaseException, only_temporary: bool = False) -> Callable[..., Any]:
    real_open = os.open

    def call(*args: Any, **kwargs: Any) -> Any:
        if only_temporary and not str(args[0]).endswith(".tmp"):
            return real_open(*args, **kwargs)
        raise error

    return call


@pytest.mark.parametrize(
    ("function", "error", "overwrite", "reason"),
    [
        ("link", OSError(errno.EPERM, "x"), False, "no_replace_unavailable"),
        ("link", OSError(errno.EXDEV, "x"), False, "no_replace_unavailable"),
        ("link", OSError(errno.ENOTSUP, "x"), False, "no_replace_unavailable"),
        ("link", _WindowsNoLinks(errno.EINVAL, "x"), False, "no_replace_unavailable"),
        ("link", _WindowsNotSameDevice(errno.EINVAL, "x"), False, "no_replace_unavailable"),
        ("link", OSError(errno.EIO, "x"), False, "io_error"),
        ("link", FileExistsError(errno.EEXIST, "x"), False, "exists"),
        ("replace", PermissionError(errno.EACCES, "x"), True, "permission_denied"),
        ("replace", OSError(errno.EIO, "x"), True, "io_error"),
        ("open", PermissionError(errno.EACCES, "x"), True, "permission_denied"),
        ("open", OSError(errno.EIO, "x"), True, "io_error"),
        ("open", ValueError("embedded null byte"), True, "invalid_name"),
    ],
)
def test_t1_atomic_write_errors_match_export_atomic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    document: Document,
    function: str,
    error: BaseException,
    overwrite: bool,
    reason: str,
) -> None:
    data = canonical_json(document)
    contexts: list[dict[str, object]] = []
    for writer in ("export", "project"):
        target = tmp_path / writer / "doc.moana.json"
        target.parent.mkdir()
        replacement = _raising(error, only_temporary=function == "open")
        with monkeypatch.context() as patch:
            patch.setattr(os, function, replacement)
            with pytest.raises(ExportError) as caught:
                if writer == "export":
                    commit_bytes(data, target, overwrite=overwrite)
                else:
                    save_document(document, target, overwrite=overwrite)
        contexts.append(dict(caught.value.context))
        assert list(target.parent.iterdir()) == []
    assert contexts[0] == contexts[1]
    assert contexts[0]["reason"] == reason


@pytest.mark.parametrize("save", ["document", "project"])
def test_t1_eexist_for_the_same_file_is_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, project: Project, save: str
) -> None:
    real_link = os.link

    def link_then_lost_reply(source: Any, destination: Any, **kwargs: Any) -> None:
        real_link(source, destination, **kwargs)
        raise FileExistsError(errno.EEXIST, "retried")

    monkeypatch.setattr(os, "link", link_then_lost_reply)
    if save == "document":
        save_document(project.document, tmp_path / "d.moana.json")
    else:
        save_project(project, tmp_path / "p")
    monkeypatch.undo()
    loaded = load_project(tmp_path / ("d.moana.json" if save == "document" else "p"))
    assert loaded.document == project.document
    assert _leftovers(tmp_path) == []


def test_t1_missing_hard_links_fail_before_writing_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, project: Project
) -> None:
    monkeypatch.setattr(os, "link", _raising(OSError(errno.EPERM, "no links")))
    with pytest.raises(ExportError) as caught:
        save_project(project, tmp_path / "p")
    monkeypatch.undo()
    assert caught.value.context["reason"] == "no_replace_unavailable"
    assert caught.value.context["file_name"] == MANIFEST_NAME
    assert list((tmp_path / "p").iterdir()) == []


# --- directories and confinement -----------------------------------------------------


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (FileNotFoundError(2, "x"), "missing_directory"),
        (PermissionError(13, "x"), "permission_denied"),
        (OSError(5, "x"), "io_error"),
    ],
)
def test_t1_directory_creation_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    project: Project,
    error: OSError,
    reason: str,
) -> None:
    def mkdir(*_args: Any, **_kwargs: Any) -> None:
        raise error

    monkeypatch.setattr(os, "mkdir", mkdir)
    with pytest.raises(ExportError) as caught:
        save_project(project, tmp_path / "p")
    assert caught.value.context["reason"] == reason


@pytest.mark.parametrize(
    ("error", "reason"),
    [(PermissionError(13, "x"), "permission_denied"), (OSError(5, "x"), "io_error")],
)
def test_t1_subdirectory_creation_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    project: Project,
    confinement: bool,
    error: OSError,
    reason: str,
) -> None:
    real_mkdir = os.mkdir
    root = tmp_path / "p"

    def mkdir(path: Any, *args: Any, **kwargs: Any) -> None:
        if Path(path).name == "assets":
            raise error
        real_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(os, "mkdir", mkdir)
    with pytest.raises(ExportError) as caught:
        save_project(project, root)
    assert caught.value.context == {
        "reason": reason,
        "file_name": "assets",
        "errno": errno.errorcode[error.errno or 0],
    }


def test_t1_temporary_file_creation_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, document: Document
) -> None:
    monkeypatch.setattr(os, "open", _raising(FileExistsError(17, "x"), only_temporary=True))
    with pytest.raises(ExportError) as caught:
        save_document(document, tmp_path / "d.moana.json")
    assert caught.value.context["reason"] == "io_error"
    assert "errno" not in caught.value.context


def test_t1_unsafe_project_directories_are_refused(
    tmp_path: Path, project: Project, confinement: bool
) -> None:
    (tmp_path / "file").write_bytes(b"x")
    with pytest.raises(ExportError) as caught:
        save_project(project, tmp_path / "file")
    assert caught.value.context["reason"] == "not_a_directory"
    root = tmp_path / "p"
    root.mkdir()
    (root / "assets").write_bytes(b"x")
    with pytest.raises(ExportError) as caught:
        save_project(project, root)
    assert caught.value.context["reason"] == "not_a_directory"
    (root / "assets").unlink()
    (root / "assets").mkdir()
    (root / project.assets[0].path).mkdir()
    with pytest.raises(ExportError) as caught:
        save_project(project, root)
    # _intact keeps the reason of the read that failed.
    assert caught.value.context["reason"] == "is_directory"
    assert caught.value.context["file_name"] == project.assets[0].path
    assert not (root / MANIFEST_NAME).exists()


def _symlink(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=target.is_dir())
    except OSError:  # pragma: no cover - Windows without symlink privilege
        pytest.skip("symbolic links are not available")


def test_t1_linked_directories_are_refused(
    tmp_path: Path, project: Project, confinement: bool
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "p"
    root.mkdir()
    _symlink(root / "assets", outside)
    with pytest.raises(ExportError) as caught:
        save_project(project, root)
    assert caught.value.context["reason"] == "unsafe_path"
    assert caught.value.context["file_name"] == "assets"
    assert list(outside.iterdir()) == []


def test_t1_caller_path_links_are_followed(
    tmp_path: Path, project: Project, confinement: bool
) -> None:
    real = tmp_path / "real"
    real.mkdir()
    _symlink(tmp_path / "alias", real)
    save_project(project, tmp_path / "alias" / "p")
    save_project_archive(project, tmp_path / "alias" / "p.moana")
    assert load_project(tmp_path / "alias" / "p") == project
    assert load_project(real / "p.moana") == project
    _symlink(tmp_path / "linked-project", real / "p")
    assert load_project(tmp_path / "linked-project") == project


@_POSIX_ONLY
def test_t1_link_swapped_in_after_mkdir_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, project: Project
) -> None:
    """Race: ``assets`` becomes a link between its creation and its opening."""
    if not _fs.DIR_FD:  # pragma: no cover - POSIX without dir_fd
        pytest.skip("dir_fd is not available")
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "p"
    real_mkdir = os.mkdir

    def mkdir(path: Any, *args: Any, **kwargs: Any) -> None:
        real_mkdir(path, *args, **kwargs)
        if path == "assets":
            os.rmdir(root / "assets")
            os.symlink(outside, root / "assets")

    monkeypatch.setattr(os, "mkdir", mkdir)
    with pytest.raises(ExportError) as caught:
        save_project(project, root)
    monkeypatch.undo()
    assert caught.value.context["reason"] == "unsafe_path"
    assert list(outside.iterdir()) == []
    assert not (root / MANIFEST_NAME).exists()


@_POSIX_ONLY
def test_t1_link_swapped_in_after_opening_never_redirects_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, project: Project
) -> None:
    """Race: ``assets`` is moved and replaced by a link once opened; writes stay inside."""
    if not _fs.DIR_FD:  # pragma: no cover - POSIX without dir_fd
        pytest.skip("dir_fd is not available")
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "p"
    real_child = _fs.Folder.child

    def child(self: _fs.Folder, part: str, *, create: bool) -> _fs.Folder:
        opened = real_child(self, part, create=create)
        if opened.name == "assets":
            os.rename(root / "assets", root / "moved")
            os.symlink(outside, root / "assets")
        return opened

    monkeypatch.setattr(_fs.Folder, "child", child)
    save_project(project, root)
    monkeypatch.undo()
    assert list(outside.iterdir()) == []
    assert sorted(path.name for path in (root / "moved").iterdir()) == sorted(
        Path(asset.path).name for asset in project.assets
    )
    with pytest.raises(ReadError) as caught:
        load_project(root)
    assert caught.value.context["reason"] == "not_a_file"


@_POSIX_ONLY
def test_t1_unreadable_ancestor_is_permission_denied_without_the_path(
    tmp_path: Path, document: Document
) -> None:
    # Checked through sys.platform so mypy also accepts it when targeting win32.
    if sys.platform != "win32" and os.geteuid() == 0:  # pragma: no cover - root ignores permissions
        pytest.skip("permissions are not enforced for root")
    locked = tmp_path / "locked"
    (locked / "sub").mkdir(parents=True)
    locked.chmod(0)
    try:
        calls: tuple[Callable[[], object], ...] = (
            lambda: save_document(document, locked / "sub" / "d.moana.json"),
            lambda: save_project(Project(document), locked / "sub" / "p"),
        )
        for call in calls:
            with pytest.raises(ExportError) as caught:
                call()
            assert caught.value.context["reason"] == "permission_denied"
            assert caught.value.context["errno"] == "EACCES"
            assert str(tmp_path) not in str(caught.value)
            assert str(tmp_path) not in repr(caught.value.context)
    finally:
        locked.chmod(0o700)


def test_t1_inspection_failures_of_the_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, document: Document, confinement: bool
) -> None:
    real_stat, real_lstat = os.stat, os.lstat

    def failing(error: OSError, original: Callable[..., Any]) -> Callable[..., Any]:
        def call(path: Any, *args: Any, **kwargs: Any) -> Any:
            if Path(path).name == "d.moana.json":
                raise error
            return original(path, *args, **kwargs)

        return call

    for error, reason in (
        (PermissionError(errno.EACCES, "x"), "permission_denied"),
        (OSError(errno.EIO, "x"), "io_error"),
    ):
        with monkeypatch.context() as patch:
            patch.setattr(os, "stat", failing(error, real_stat))
            patch.setattr(os, "lstat", failing(error, real_lstat))
            with pytest.raises(ExportError) as caught:
                save_document(document, tmp_path / "d.moana.json")
        assert caught.value.context["reason"] == reason
        assert caught.value.context["file_name"] == "d.moana.json"


# --- caller paths and reads ----------------------------------------------------------


def test_caller_paths_are_checked(tmp_path: Path, document: Document) -> None:
    for bad in ("", "a\x00b", "\ud800"):
        with pytest.raises(ValidationError) as caught:
            save_document(document, bad)
        assert caught.value.context["reason"] == "invalid_name"
    for wrong in (b"bytes", 3):
        with pytest.raises(TypeError):
            load_project(wrong)  # type: ignore[arg-type]


class _BytesPath:
    def __fspath__(self) -> bytes:
        return b"project"


def test_bytes_path_like_is_rejected(document: Document) -> None:
    with pytest.raises(TypeError):
        save_document(document, _BytesPath())  # type: ignore[arg-type]


def test_temporary_file_errors_carry_errno(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, document: Document
) -> None:
    monkeypatch.setattr(os, "open", _raising(PermissionError(13, "x"), only_temporary=True))
    with pytest.raises(ExportError) as caught:
        save_document(document, tmp_path / "d.moana.json")
    assert caught.value.context["errno"] == "EACCES"


@pytest.mark.parametrize(
    ("error", "directory", "reason"),
    [
        (FileNotFoundError(2, "x"), False, "not_found"),
        (PermissionError(13, "x"), False, "permission_denied"),
        (PermissionError(13, "x"), True, "is_directory"),
        (IsADirectoryError(21, "x"), True, "is_directory"),
        (OSError(5, "x"), False, "io_error"),
    ],
)
def test_read_open_failures_are_read_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error: OSError,
    directory: bool,
    reason: str,
) -> None:
    target = tmp_path / "target"
    if directory:
        target.mkdir()
    else:
        target.write_bytes(b"{}")
    monkeypatch.setattr(os, "open", _raising(error))
    with pytest.raises(ReadError) as caught:
        _fs.read_caller_file(target, 10)
    assert caught.value.context["reason"] == reason
    assert caught.value.context["file_name"] == "target"


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (PermissionError(13, "x"), "permission_denied"),
        (OSError(errno.ELOOP, "x"), "not_a_file"),
        (OSError(5, "x"), "io_error"),
        (PermissionError(13, "directory"), "is_directory"),
    ],
)
def test_project_file_open_failures_are_read_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    project: Project,
    confinement: bool,
    error: OSError,
    reason: str,
) -> None:
    save_project(project, tmp_path / "p")
    if reason == "is_directory":
        (tmp_path / "p" / project.assets[0].path).unlink()
        (tmp_path / "p" / project.assets[0].path).mkdir()
    real_open = os.open

    def open_(path: Any, *args: Any, **kwargs: Any) -> int:
        if str(path).endswith(".png"):
            raise error
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(os, "open", open_)
    with pytest.raises(ReadError) as caught:
        load_project(tmp_path / "p")
    assert caught.value.context["reason"] == reason
    assert str(caught.value.context["file_name"]).startswith("assets/")


def test_open_failure_reason_survives_an_uninspectable_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, project: Project, confinement: bool
) -> None:
    save_project(project, tmp_path / "p")

    def failing(original: Callable[..., Any]) -> Callable[..., Any]:
        def call(path: Any, *args: Any, **kwargs: Any) -> Any:
            if str(path).endswith(".png"):
                raise PermissionError(errno.EACCES, "x")
            return original(path, *args, **kwargs)

        return call

    for name in ("open", "stat", "lstat"):
        monkeypatch.setattr(os, name, failing(getattr(os, name)))
    with pytest.raises(ReadError) as caught:
        load_project(tmp_path / "p")
    assert caught.value.context["reason"] == "permission_denied"


def test_missing_project_directory_is_not_found(
    tmp_path: Path, project: Project, confinement: bool
) -> None:
    root = tmp_path / "p"
    save_project(project, root)
    for item in (root / "assets").iterdir():
        item.unlink()
    (root / "assets").rmdir()
    with pytest.raises(ReadError) as caught:
        load_project(root)
    assert caught.value.context["reason"] == "not_found"
    assert caught.value.context["file_name"] == "assets"


def test_read_failures_after_open_are_io_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, document: Document
) -> None:
    save_document(document, tmp_path / "d.moana.json")
    monkeypatch.setattr(os, "read", _fail)
    with pytest.raises(ReadError) as caught:
        load_project(tmp_path / "d.moana.json")
    assert caught.value.context["reason"] == "io_error"


def test_project_directory_open_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, project: Project, confinement: bool
) -> None:
    root = tmp_path / "p"
    save_project(project, root)
    real_open, real_stat = os.open, os.stat

    def failing(original: Callable[..., Any]) -> Callable[..., Any]:
        def call(path: Any, *args: Any, **kwargs: Any) -> Any:
            if path in ("history", root):
                raise OSError(errno.EIO, "x")
            return original(path, *args, **kwargs)

        return call

    monkeypatch.setattr(os, "open", failing(real_open))
    monkeypatch.setattr(os, "lstat", failing(os.lstat))
    if confinement:
        with pytest.raises(ReadError) as caught:
            _fs.Folder.open_root(root, create=False, writing=False).close()
        assert caught.value.context["reason"] == "io_error"
    monkeypatch.setattr(os, "stat", failing(real_stat))
    with pytest.raises(ReadError) as caught:
        load_project(root)
    assert caught.value.context["reason"] == "io_error"


def test_special_files_are_not_read(tmp_path: Path) -> None:
    if not hasattr(os, "mkfifo"):  # pragma: no cover - Windows has no FIFOs
        pytest.skip("FIFOs are not available")
    os.mkfifo(tmp_path / "fifo")
    with pytest.raises(ReadError) as caught:
        load_project(tmp_path / "fifo")
    assert caught.value.context["reason"] == "not_a_file"
