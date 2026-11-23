"""export/project → disco: injected IO failures never leave partial output (T2, AC2).

The oracle is the destination itself: its bytes before the call. A failure injected at
*any* ``os.write`` or ``os.fsync`` of a save (the step is drawn by Hypothesis among
the steps a successful save performs) must raise ``ExportError`` with the previous
content intact and no temporary file left behind. Budgets of a save are checked
before the first write.
"""

from __future__ import annotations

import errno
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from moanart.api import export_png, load_document, render
from moanart.core.errors import BudgetExceeded, ExportError
from moanart.project import (
    Asset,
    Project,
    ProjectLimits,
    load_project,
    migrate_project,
    save_document,
    save_project,
    save_project_archive,
)
from moanart.schema import Document
from tests.fixtures.migration.formats import OLDEST, TEST_ONLY_MIGRATIONS

from .corpus import MINIMAL, SECRET, tiny_png
from .guards import (
    assert_bounded,
    assert_clean_error,
    bounded_settings,
    forbid_writes,
    measure,
    tree_state,
)

pytestmark = pytest.mark.security

BOUNDED = bounded_settings(25, 10)  # tmp_path_factory is session-scoped

type Save = Callable[[Path, bool], object]


def _png(shade: int) -> bytes:
    return tiny_png(color=(shade, 0, 0, 255))


def _document(seed: int) -> Document:
    tree = load_document(MINIMAL).model_dump(mode="json", exclude_none=True)
    tree["seed"] = seed
    return load_document(tree)


def _project(seed: int) -> Project:
    return Project(_document(seed), (Asset.from_png("texture", _png(seed % 256)),))


def _savers() -> dict[str, tuple[str, Save]]:
    def directory(path: Path, second: bool) -> object:
        return save_project(_project(2 if second else 1), path, overwrite=second)

    def archive(path: Path, second: bool) -> object:
        return save_project_archive(_project(2 if second else 1), path, overwrite=second)

    def document(path: Path, second: bool) -> object:
        return save_document(_document(2 if second else 1), path, overwrite=second)

    def png(path: Path, second: bool) -> object:
        tree = load_document(MINIMAL).model_dump(mode="json", exclude_none=True)
        tree["layers"][0]["operations"][0]["color"] = "ink" if second else "cloth"
        return export_png(render(load_document(tree)), path, overwrite=second)

    return {
        "directory": ("project", directory),
        "archive": ("project.moanart", archive),
        "document": ("doc.moanart.json", document),
        "png": ("sprite.png", png),
    }


SAVERS = _savers()


@contextmanager
def _failing(name: str, at: int, counter: list[int]) -> Iterator[None]:
    """``os.<name>`` raises ``EIO`` on its ``at``-th call (1-based); counts every call."""
    real = getattr(os, name)

    def wrapped(*args: object, **kwargs: object) -> object:
        counter[0] += 1
        if counter[0] == at:
            raise OSError(errno.EIO, "injected failure")
        return real(*args, **kwargs)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(os, name, wrapped)
        yield


def _calls(kind: str, primitive: str, root: Path) -> int:
    """How many ``os.<primitive>`` calls a successful overwrite performs (no failure)."""
    target, save = SAVERS[kind]
    save(root / target, False)
    counter = [0]
    with _failing(primitive, 0, counter):
        save(root / target, True)
    return counter[0]


@BOUNDED
@given(
    kind=st.sampled_from(sorted(SAVERS)),
    primitive=st.sampled_from(["write", "fsync"]),
    data=st.data(),
)
def test_t2_property_injected_io_failure_keeps_the_previous_output(
    tmp_path_factory: pytest.TempPathFactory, kind: str, primitive: str, data: st.DataObject
) -> None:
    calls = _calls(kind, primitive, tmp_path_factory.mktemp("count"))
    assert calls >= 1
    at = data.draw(st.integers(1, calls), label="failing call")
    root = tmp_path_factory.mktemp("save")
    target, save = SAVERS[kind]
    save(root / target, False)
    before = tree_state(root)
    try:
        with _failing(primitive, at, [0]):
            save(root / target, True)
    except ExportError as error:
        assert_clean_error(error, root)
        _assert_previous(kind, root, target, before)
    else:
        # Only the best-effort directory sync after the commit may fail silently
        # (ADR-029): a failed write always raises. The new output is then complete.
        assert primitive == "fsync"
        _assert_complete_new(kind, root, target)


def _assert_previous(kind: str, root: Path, target: str, before: dict[str, bytes]) -> None:
    after = tree_state(root)
    assert not [name for name in after if name.endswith(".tmp")]  # temporaries removed
    if kind != "directory":
        assert after == before
        return
    # Content-addressed files of the new save may remain unreferenced (ADR-029); the
    # committed manifest and every file it references are untouched.
    assert {name: after[name] for name in before} == before
    assert load_project(root / target) == _project(1)


def _assert_complete_new(kind: str, root: Path, target: str) -> None:
    assert not [name for name in tree_state(root) if name.endswith(".tmp")]
    reference = root.parent / f"{root.name}-reference"
    reference.mkdir()
    save = SAVERS[kind][1]
    save(reference / target, False)
    save(reference / target, True)
    assert tree_state(root) == tree_state(reference)


@pytest.mark.parametrize("kind", sorted(SAVERS))
def test_t2_existing_destination_is_never_replaced_implicitly(tmp_path: Path, kind: str) -> None:
    target, save = SAVERS[kind]
    save(tmp_path / target, False)
    before = tree_state(tmp_path)
    # No write tripwire here: "exists" is decided at commit time (no-clobber link,
    # mkdir tolerating EEXIST) to avoid a check-then-write race, so a temporary may be
    # created and removed. The oracle is the byte-identical tree, temporaries included.
    rejection = measure(lambda: save(tmp_path / target, False))
    error = assert_clean_error(assert_bounded(rejection), tmp_path)
    assert isinstance(error, ExportError)
    assert error.context["reason"] == "exists"
    assert tree_state(tmp_path) == before


def test_t2_save_budget_is_checked_before_any_write(tmp_path: Path) -> None:
    project = Project(
        _document(1),
        (Asset.from_png("one", _png(1)), Asset.from_png("two", _png(2))),
    )
    destination = tmp_path / "never"
    with forbid_writes(), pytest.raises(BudgetExceeded) as caught:
        save_project(project, destination, limits=ProjectLimits(max_assets=1))
    assert caught.value.context["resource"] == "project_assets"
    assert not destination.exists()


def test_t2_migration_into_an_existing_project_keeps_both_sides(tmp_path: Path) -> None:
    source = tmp_path / OLDEST.name
    source.write_bytes(OLDEST.read_bytes())
    destination = tmp_path / "existing"
    save_project(_project(1), destination)
    before = tree_state(tmp_path)
    with pytest.raises(ExportError) as caught:
        migrate_project(source, destination, registry=TEST_ONLY_MIGRATIONS)
    assert caught.value.context["reason"] == "exists"
    assert_clean_error(caught.value, tmp_path)
    assert tree_state(tmp_path) == before


def test_t2_linked_project_directory_never_redirects_writes(tmp_path: Path) -> None:
    outside = tmp_path / f"outside-{SECRET}"
    outside.mkdir()
    root = tmp_path / "project"
    save_project(_project(1), root)
    for path in (root / "assets").iterdir():
        path.unlink()
    (root / "assets").rmdir()
    try:
        (root / "assets").symlink_to(outside, target_is_directory=True)
    except OSError:  # pragma: no cover - Windows without symlink privilege
        pytest.skip("symbolic links are not available")
    with pytest.raises(ExportError) as caught:
        save_project(_project(2), root, overwrite=True)
    assert caught.value.context["reason"] == "unsafe_path"
    assert_clean_error(caught.value, tmp_path, SECRET)
    assert list(outside.iterdir()) == []
