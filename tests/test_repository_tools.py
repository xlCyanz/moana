"""Exercise failure cases in repository tools using temporary artifacts."""

import json
import re
import shlex
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from scripts.check_repository import check_links, check_skill
from scripts.planning import check_generated


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
