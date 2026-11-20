"""Exercise failure cases in repository tools using temporary artifacts."""

import io
import json
import re
import shlex
import shutil
import tarfile
import zipfile
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

import moana
from scripts import release
from scripts.check_repository import check_links, check_skill
from scripts.check_wheel import (
    CORPUS,
    EDIT_EXAMPLE,
    EXAMPLE,
    GUIDE,
    SDIST_REQUIRED,
    SMOKE,
    audit_sdist,
    audit_wheel,
    built_artifacts,
)
from scripts.install_smoke import check_corpus, check_migrations, require
from scripts.install_smoke import main as smoke_main
from scripts.planning import check_generated
from scripts.tutorial import INPUTS as TUTORIAL_INPUTS


def test_stale_and_orphan_issue_documents_fail(tmp_path: Path) -> None:
    folder = tmp_path / "docs/issues"
    folder.mkdir(parents=True)
    (folder / "MOA-001.md").write_text("stale", encoding="utf-8")
    (folder / "MOA-999.md").write_text("orphan", encoding="utf-8")
    errors = check_generated(tmp_path, {"docs/issues/MOA-001.md": "current"})
    assert any("Stale" in error for error in errors)
    assert any("Orphan" in error for error in errors)


def test_links_detect_missing_and_escaping_targets(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "[missing](docs/missing.md) [escape](../external.md) "
        "[website](https://example.com/) [self](README.md)",
        encoding="utf-8",
    )
    assert len(check_links(tmp_path)) == 2


@pytest.mark.parametrize(
    "content",
    [
        "# No metadata",
        "---\nname: wrong-name\ndescription: A valid description\n---\nInstructions",
        "---\nname: moana-python\ndescription: ''\n---\nInstructions",
    ],
)
def test_invalid_skills_fail(tmp_path: Path, content: str) -> None:
    folder = tmp_path / "moana-python"
    folder.mkdir()
    entry = folder / "SKILL.md"
    entry.write_text(content, encoding="utf-8")
    with pytest.raises((ValueError, ValidationError)):
        check_skill(entry)


def _workflow() -> dict[str, Any]:
    text = (Path(__file__).resolve().parents[1] / ".github/workflows/ci.yml").read_text(
        encoding="utf-8"
    )
    value = yaml.load(text, Loader=yaml.BaseLoader)  # keeps the `on` key as a string
    assert isinstance(value, dict)
    return value


def test_ci_actions_are_pinned_and_permissions_minimal() -> None:
    workflow = _workflow()
    assert workflow["permissions"] == {"contents": "read"}
    for job in workflow["jobs"].values():
        assert "permissions" not in job  # no job widens the read-only token
        for step in job["steps"]:
            if "uses" in step:
                assert re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", step["uses"]), step["uses"]
            if step.get("uses", "").startswith("actions/checkout@"):
                assert step["with"]["persist-credentials"] == "false"
    uv_steps = [
        step
        for job in workflow["jobs"].values()
        for step in job["steps"]
        if step.get("uses", "").startswith("astral-sh/setup-uv@")
    ]
    assert len({(step["uses"], step["with"]["version"]) for step in uv_steps}) == 1


def test_ci_publishes_and_compares_determinism_reports() -> None:
    """MOANA-029 AC2: per-job report in the diagnostics artifact, then a read-only comparison."""
    jobs = _workflow()["jobs"]
    steps = jobs["verify"]["steps"]
    names = [step.get("name", step.get("uses", "")) for step in steps]
    report = names.index("Cross-process determinism report")
    upload = next(i for i, step in enumerate(steps) if "upload-artifact" in step.get("uses", ""))
    assert report < upload
    assert steps[report]["if"] == "${{ !cancelled() }}"
    assert "--output artifacts/determinism" in steps[report]["run"]
    assert steps[upload]["with"]["path"] == "artifacts/"
    assert steps[upload]["if"] == "always()"
    assert steps[upload]["with"]["name"].startswith("diagnostics-")

    compare = jobs["determinism"]
    assert compare["needs"] == "verify"
    assert compare["if"] == "${{ !cancelled() }}"
    download = next(s for s in compare["steps"] if "download-artifact" in s.get("uses", ""))
    assert download["with"]["pattern"] == "diagnostics-*"
    command = next(s["run"] for s in compare["steps"] if "compare" in s.get("run", ""))
    arguments = shlex.split(command)
    assert arguments[arguments.index("scripts.determinism") + 1] == "compare"
    matrix = jobs["verify"]["strategy"]["matrix"]
    count = arguments[arguments.index("--expected-reports") + 1]
    assert int(count) == len(matrix["os"]) * len(matrix["python"])
    systems = {"ubuntu": "Linux", "macos": "Darwin", "windows": "Windows"}
    platforms = arguments[arguments.index("--expected-platforms") + 1].split(",")
    assert sorted(platforms) == sorted(systems[os.split("-")[0]] for os in matrix["os"])
    assert "MOANA_UPDATE_GOLDENS" not in json.dumps(jobs)  # CI never rewrites baselines
    for step in compare["steps"]:  # the comparison never touches the reviewed manifest
        assert "tests/fixtures" not in json.dumps(step)


# MOANA-035: release candidate tooling.

REPOSITORY = Path(__file__).resolve().parents[1]


def _tar(path: Path, members: dict[str, bytes], prefix: str = "moana-0.1.0rc1") -> Path:
    with tarfile.open(path, "w:gz") as archive:
        for name, data in members.items():
            info = tarfile.TarInfo(f"{prefix}/{name}" if prefix else name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return path


def _complete_sdist() -> dict[str, bytes]:
    members = dict.fromkeys(SDIST_REQUIRED, b"x")
    members["PKG-INFO"] = b"Metadata-Version: 2.4\nLicense-Expression: MIT\n"
    return members


def test_t1_sdist_audit_accepts_a_clean_sdist(tmp_path: Path) -> None:
    members = _complete_sdist() | {".env.example": b"", "src/moana/build_info.py": b""}
    assert audit_sdist(_tar(tmp_path / "ok.tar.gz", members)) == []


@pytest.mark.parametrize(
    ("member", "reason"),
    [
        (".venv/bin/python", "environment, cache or output"),
        ("artifacts/coverage.xml", "environment, cache or output"),
        (".claude/worktrees/agent/README.md", "environment, cache or output"),
        ("src/moana/__pycache__/x.cpython-312.pyc", "environment, cache or output"),
        ("dist/old.whl", "environment, cache or output"),
        (".env", "environment file"),
        (".env.local", "environment file"),
        (".claude/settings.local.json", "forbidden file"),
        ("deploy.pem", "forbidden file"),
        (".DS_Store", "forbidden file"),
        ("../escape.txt", "unsafe sdist path"),
    ],
)
def test_t1_sdist_audit_rejects_environment_and_secret_paths(
    tmp_path: Path, member: str, reason: str
) -> None:
    errors = audit_sdist(_tar(tmp_path / "bad.tar.gz", _complete_sdist() | {member: b"x"}))
    assert errors and all(member in error for error in errors)
    assert any(reason in error for error in errors)


def test_t1_sdist_audit_requires_licence_and_sources(tmp_path: Path) -> None:
    members = _complete_sdist()
    del members["LICENSE"]
    members["PKG-INFO"] = b"Metadata-Version: 2.4\nLicense: MIT\n"
    errors = audit_sdist(_tar(tmp_path / "bad.tar.gz", members))
    assert "missing from sdist: LICENSE" in errors
    assert any("License-Expression: MIT" in error for error in errors)
    flat = _tar(tmp_path / "flat.tar.gz", {"a": b"", "b": b""}, prefix="")
    assert audit_sdist(flat) == ["sdist must have one top-level directory, found ['a', 'b']"]


def test_t1_wheel_audit_requires_licence_metadata(tmp_path: Path) -> None:
    info = "moana_pixel_engine-0.1.0rc1.dist-info"
    good = tmp_path / "good.whl"
    with zipfile.ZipFile(good, "w") as archive:
        archive.writestr("moana/__init__.py", "")
        archive.writestr(f"{info}/METADATA", "Name: x\nLicense-Expression: MIT\n")
        archive.writestr(f"{info}/licenses/LICENSE", "MIT")
    assert audit_wheel(good) == []
    bad = tmp_path / "bad.whl"
    with zipfile.ZipFile(bad, "w") as archive:
        archive.writestr("moana/__init__.py", "")
        archive.writestr("tests/test_x.py", "")
        archive.writestr(f"{info}/METADATA", "Name: x\n")
    errors = audit_wheel(bad)
    assert len(errors) == 3 and any("tests/test_x.py" in error for error in errors)


def test_t1_built_artifacts_need_one_wheel_and_one_sdist(tmp_path: Path) -> None:
    wheel = tmp_path / "a-1-py3-none-any.whl"
    wheel.write_bytes(b"")
    with pytest.raises(RuntimeError, match="one wheel and one sdist"):
        built_artifacts(tmp_path)
    sdist = tmp_path / "a-1.tar.gz"
    sdist.write_bytes(b"")
    assert built_artifacts(tmp_path) == (wheel, sdist)


def test_t1_migration_smoke_preserves_the_original(tmp_path: Path) -> None:
    example = REPOSITORY / "examples/specs/minimal.moana.json"
    before = example.read_bytes()
    summary = check_migrations(tmp_path / "first", example)
    assert "original preserved" in summary and example.read_bytes() == before
    (tmp_path / "second").mkdir()
    assert smoke_main(["migrations", str(tmp_path / "second"), str(example)]) == 0
    assert smoke_main(["unknown"]) == 2


def test_t1_corpus_smoke_detects_a_changed_pinned_digest(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    shutil.copytree(REPOSITORY / "examples/corpus", corpus)
    assert smoke_main(["corpus", str(corpus)]) == 0
    record_path = corpus / "chest" / "chest.corpus.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["render"]["digest"] = "sha256:" + "0" * 64
    record_path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(AssertionError, match="chest"):
        check_corpus(corpus)


def test_t2_release_document_is_in_sync_with_code_and_catalogs() -> None:
    assert release.check() == []
    assert release.main(["check"]) == 0
    assert release.main(["report"]) == 0


def test_t2_release_check_reports_stale_or_malformed_documents(tmp_path: Path) -> None:
    document = tmp_path / "RELEASE.md"
    block = f"{release.BEGIN}\nold\n{release.END}\n"
    document.write_text(f"# Release\n\n{block}\nhand-written\n", encoding="utf-8")
    assert len(release.check(document)) == 1
    release.write(document)
    assert release.check(document) == []
    text = document.read_text(encoding="utf-8")
    assert text.startswith("# Release\n\n") and text.endswith("\nhand-written\n")
    assert release.report() in text
    document.write_text("no generated block", encoding="utf-8")
    assert release.check(document) == ["RELEASE.md must contain one generated block"]


def test_t2_requirement_audit_does_not_confuse_planning_with_delivery(tmp_path: Path) -> None:
    (tmp_path / "docs/issues").mkdir(parents=True)
    requirements = [
        {"id": identifier, "description": f"req {identifier}"}
        for identifier in ("R001", "R002", "R003", "R005", "R009")
    ]
    issues = [
        {"id": "MOANA-001", "status": "done", "requirements": ["R001", "R002", "R005"]},
        {"id": "MOANA-002", "status": "review", "requirements": ["R002", "R003"]},
    ]
    (tmp_path / "docs/requirements.json").write_text(
        json.dumps({"requirements": requirements}), encoding="utf-8"
    )
    (tmp_path / "docs/issues/catalog.json").write_text(
        json.dumps({"issues": issues}), encoding="utf-8"
    )
    rows = {row[0]: row for row in release.requirement_rows(tmp_path)}
    assert rows["R001"][3] == "implementado"
    assert rows["R002"][3] == "parcial"  # covered in planning, one issue still in review
    assert rows["R003"][3] == "pendiente"
    assert rows["R005"][3] == "implementado con pendientes"
    assert "revisión artística humana" in rows["R005"][4]
    assert rows["R009"][2:4] == ("—", "pendiente")  # an orphan is never delivered


def test_t2_release_versions_and_licence_come_from_the_code() -> None:
    versions = {name: value for name, value, _ in release.version_rows()}
    assert versions["Paquete"] == f"`{moana.__version__}`" == "`0.1.0rc1`"
    assert versions["Migraciones de documento"].startswith("`1.0`; 0 migraciones")
    compatibility = {name: value for name, value, _ in release.compatibility_rows()}
    assert compatibility["Licencia"] == "`MIT` (`LICENSE`)"
    assert compatibility["Matriz CI: Python"] == "`3.12`, `3.13`, `3.14`"
    licence = (REPOSITORY / "LICENSE").read_text(encoding="utf-8")
    assert licence.startswith("MIT License\n\nCopyright (c) 2026 xlCyanz and Moana contributors\n")


@pytest.mark.parametrize("kind", [tarfile.SYMTYPE, tarfile.LNKTYPE])
def test_t1_sdist_audit_rejects_links(tmp_path: Path, kind: bytes) -> None:
    path = _tar(tmp_path / "links.tar.gz", _complete_sdist())
    with tarfile.open(path, "r:gz") as source:
        members = [(member, source.extractfile(member)) for member in source.getmembers()]
        linked = tmp_path / "linked.tar.gz"
        with tarfile.open(linked, "w:gz") as archive:
            for member, stream in members:
                archive.addfile(member, stream)
            link = tarfile.TarInfo("moana-0.1.0rc1/src/moana/escape.py")
            link.type = kind
            link.linkname = "../../../../etc/passwd" if kind == tarfile.SYMTYPE else "LICENSE"
            archive.addfile(link)
    assert audit_sdist(linked) == ["sdist member is a link: src/moana/escape.py"]


def test_t1_sdist_and_wheel_audits_need_their_metadata(tmp_path: Path) -> None:
    members = _complete_sdist()
    del members["PKG-INFO"]
    assert audit_sdist(_tar(tmp_path / "no-info.tar.gz", members)) == [
        "missing from sdist: PKG-INFO"
    ]
    wheel = tmp_path / "no-metadata.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("moana/__init__.py", "")
    assert audit_wheel(wheel) == ["wheel has no METADATA"]


def test_t1_sdist_ships_every_input_of_the_installed_checks() -> None:
    # The sdist run copies these from the extracted sdist (scripts/check_wheel.py).
    for name in (EXAMPLE, EDIT_EXAMPLE, SMOKE, GUIDE, *TUTORIAL_INPUTS):
        assert name in SDIST_REQUIRED and (REPOSITORY / name).is_file()
    assert (REPOSITORY / CORPUS).is_dir()


@pytest.mark.parametrize(
    "text",
    [
        f"{release.BEGIN}\n{release.BEGIN}\n{release.END}\n",
        f"{release.BEGIN}\n{release.END}\n{release.END}\n",
        f"{release.END}\n{release.BEGIN}\n",
        f"{release.BEGIN}\n",
    ],
)
def test_t2_release_check_rejects_duplicated_or_misordered_markers(
    tmp_path: Path, text: str
) -> None:
    document = tmp_path / "RELEASE.md"
    document.write_text(text, encoding="utf-8")
    assert release.check(document) == ["RELEASE.md must contain one generated block"]
    with pytest.raises(ValueError, match="one generated block"):
        release.write(document)


@pytest.mark.parametrize(
    ("workflow", "missing"),
    [
        ("jobs: {}\n", "'verify'"),
        ("jobs:\n  verify:\n    runs-on: x\n", "'strategy'"),
        (
            "jobs:\n  verify:\n    strategy:\n      matrix:\n        os: [a]\n",
            "matrix 'python'",
        ),
    ],
)
def test_t2_release_reports_a_moved_ci_matrix_clearly(
    tmp_path: Path, workflow: str, missing: str
) -> None:
    (tmp_path / ".github/workflows").mkdir(parents=True)
    (tmp_path / ".github/workflows/ci.yml").write_text(workflow, encoding="utf-8")
    with pytest.raises(ValueError, match=missing):
        release.ci_matrix(tmp_path)


def test_t1_install_smoke_failures_are_explicit() -> None:
    with pytest.raises(AssertionError, match="boom"):
        require(False, "boom")
    require(True, "never raised")
