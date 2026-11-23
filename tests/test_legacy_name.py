"""MOANA-037 T1: the old name stays out of the repository, the wheel and the sdist.

``OLD`` is spelled out once here (this file is an audited exception of
``scripts/legacy_name.py``); every other case is built from it.
"""

from __future__ import annotations

import fnmatch
import io
import json
import tarfile
import zipfile
from pathlib import Path

import pytest

from scripts.check_wheel import SDIST_REQUIRED, audit_sdist, audit_wheel
from scripts.legacy_name import EXCEPTIONS, legacy_name_errors, repository_files

OLD = "moana"


def test_t1_the_repository_uses_the_old_name_only_in_audited_exceptions() -> None:
    assert legacy_name_errors(repository_files()) == []


def test_t1_every_exception_names_existing_files_and_a_reason() -> None:
    files = repository_files()
    for exception in EXCEPTIONS:
        assert exception.reason
        for pattern in exception.patterns:
            assert any(fnmatch.fnmatchcase(path, pattern) for path in files), pattern


@pytest.mark.parametrize(
    "files",
    [
        pytest.param({f"src/{OLD}/core.py": b""}, id="path"),
        pytest.param({f"docs/{OLD.upper()}.md": b""}, id="path-upper"),
        pytest.param({"README.md": f"import {OLD}\n".encode()}, id="text"),
        pytest.param({"README.md": b"The " + OLD.title().encode() + b" engine"}, id="title-case"),
        pytest.param({"docs/x.md": f"`{OLD}-spritesheet`".encode()}, id="format-outside-tables"),
        pytest.param(
            {"src/moanart/project/manifest.py": f"import {OLD}.core\n".encode()},
            id="migration-table-allows-only-legacy-identifiers",
        ),
        pytest.param(
            {"examples/a.moanart.json": json.dumps({"id": OLD, "metadata": {}}).encode()},
            id="document-outside-metadata",
        ),
        pytest.param(
            {
                "docs/issues/catalog.json": json.dumps(
                    {"issues": [{"id": "MOANA-001", "title": OLD}]}
                ).encode()
            },
            id="catalog-outside-the-rename-issue",
        ),
    ],
)
def test_t1_stray_occurrences_are_reported(files: dict[str, bytes]) -> None:
    errors = legacy_name_errors(files)
    assert len(errors) == 1
    assert errors[0].startswith(next(iter(files)))


@pytest.mark.parametrize(
    "files",
    [
        pytest.param({"README.md": b"MoanArt and moanart and MOANART"}, id="new-name"),
        pytest.param({"README.md": b"See MOANA-037, MOANA-xxx and test_MOANA_037"}, id="issue-ids"),
        pytest.param({"docs/issues/MOANA-037.md": b""}, id="issue-path"),
        pytest.param({"assets/x.png": b"\x89PNG" + OLD.encode() + b"\xff"}, id="binary-content"),
        pytest.param({"README.md": f"https://github.com/xlCyanz/{OLD}/pull/1".encode()}, id="repo"),
        pytest.param({"CHANGELOG.md": f"## 0.1.0rc1\n{OLD}\n".encode()}, id="changelog"),
        pytest.param(
            {"docs/architecture/decisions/ADR-029-x.md": f"`{OLD}.project`".encode()},
            id="accepted-adr",
        ),
        pytest.param(
            {"src/moanart/project/manifest.py": f'"project.{OLD}.json" "{OLD}-project"'.encode()},
            id="migration-table",
        ),
        pytest.param(
            {
                "examples/a.moanart.json": json.dumps(
                    {"id": "a", "metadata": {"provenance": OLD.title()}}
                ).encode()
            },
            id="document-metadata",
        ),
        pytest.param(
            {
                "docs/issues/catalog.json": json.dumps(
                    {"issues": [{"id": "MOANA-037", "title": OLD}]}
                ).encode()
            },
            id="rename-issue",
        ),
    ],
)
def test_t1_audited_occurrences_are_allowed(files: dict[str, bytes]) -> None:
    assert legacy_name_errors(files) == []


def _sdist(path: Path, members: dict[str, bytes], prefix: str = "moanart-0.1.0rc2") -> Path:
    with tarfile.open(path, "w:gz") as archive:
        for name, data in members.items():
            info = tarfile.TarInfo(f"{prefix}/{name}")
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return path


def _complete_sdist() -> dict[str, bytes]:
    members = dict.fromkeys(SDIST_REQUIRED, b"x")
    members["PKG-INFO"] = b"Metadata-Version: 2.4\nLicense-Expression: MIT\n"
    return members


def test_t1_sdist_audit_reports_the_old_name(tmp_path: Path) -> None:
    assert audit_sdist(_sdist(tmp_path / "ok.tar.gz", _complete_sdist())) == []
    stray = _complete_sdist() | {"docs/x.md": f"pip install {OLD}\n".encode()}
    errors = audit_sdist(_sdist(tmp_path / "text.tar.gz", stray))
    assert len(errors) == 1 and errors[0].startswith("sdist: docs/x.md:1:")
    renamed = _sdist(tmp_path / "root.tar.gz", _complete_sdist(), prefix=f"{OLD}-0.1.0rc2")
    assert any(error.startswith(f"sdist: {OLD}-0.1.0rc2") for error in audit_sdist(renamed))


def _wheel(path: Path, members: dict[str, str]) -> Path:
    info = "moanart-0.1.0rc2.dist-info"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(f"{info}/METADATA", "Name: moanart\nLicense-Expression: MIT\n")
        archive.writestr(f"{info}/licenses/LICENSE", "MIT")
        for name, text in members.items():
            archive.writestr(name, text)
    return path


def test_t1_wheel_audit_reports_the_old_name(tmp_path: Path) -> None:
    clean = {"moanart/project/manifest.py": f'LEGACY = "{OLD}-project"\n'}
    assert audit_wheel(_wheel(tmp_path / "ok.whl", clean)) == []
    stray = {"moanart/api/__init__.py": f'"""The {OLD.title()} API."""\n'}
    errors = audit_wheel(_wheel(tmp_path / "bad.whl", stray))
    assert errors == [f'wheel: src/moanart/api/__init__.py:1: """The {OLD.title()} API."""']


@pytest.mark.parametrize(
    ("path", "text"),
    [
        ("README.md", f"{OLD.upper()}_HOME = 1"),  # an environment variable, not an issue ID
        ("README.md", f"{OLD.upper()}-ENGINE"),
        ("README.md", f"{OLD.upper()}-0371"),
        ("README.md", f"github.com/xlCyanz/{OLD}_old"),
        ("README.md", f"github.com/xlCyanz/{OLD}-fork"),
        ("src/moanart/project/manifest.py", f'"{OLD}-projectx"'),
        ("src/moanart/project/manifest.py", f'"x.{OLD}/escape"'),
        ("src/moanart/project/manifest.py", f'"x.{OLD}-y"'),
    ],
)
def test_t1_near_misses_of_the_allowed_forms_are_reported(path: str, text: str) -> None:
    assert len(legacy_name_errors({path: text.encode()})) == 1


def test_t1_reported_lines_are_the_lines_of_the_file() -> None:
    text = f"first\x0cstill first\nsecond {OLD}\n"
    assert legacy_name_errors({"README.md": text.encode()}) == [f"README.md:2: second {OLD}"]


def test_t1_rc1_fixtures_are_exempt_with_their_paths() -> None:
    manifest = f'{{"kind": "{OLD}-project"}}'.encode()
    files = {
        f"tests/fixtures/rename/rc1/project/project.{OLD}.json": manifest,
        f"tests/fixtures/other/project.{OLD}.json": b"{}",
    }
    assert legacy_name_errors(files) == [
        f"tests/fixtures/other/project.{OLD}.json: the path uses the old name"
    ]
