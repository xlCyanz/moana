"""instalación/CI: a compromised dependency cannot slip in unnoticed (AC1).

The lock pins every registry artifact by SHA-256 and only the HTTPS PyPI index is a
source; CI runs with a read-only token, actions pinned by commit and no secrets.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml

from .corpus import ROOT

pytestmark = pytest.mark.security

_HASH = re.compile(r"sha256:[0-9a-f]{64}")
_PINNED = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")
_DOCKER = re.compile(r"^docker://[\w./:-]+@sha256:[0-9a-f]{64}$")
_READ_ONLY = {"read", "none"}
_WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))


def _lock() -> dict[str, Any]:
    return tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))


def test_ac1_every_locked_artifact_is_pinned_by_sha256() -> None:
    packages = _lock()["package"]
    registry = [package for package in packages if "registry" in package["source"]]
    assert registry
    for package in packages:
        source = package["source"]
        assert set(source) <= {"registry", "editable", "virtual"}, package["name"]
        if "registry" not in source:
            assert source.get("editable", source.get("virtual")) == "."
            continue
        assert source["registry"] == "https://pypi.org/simple", package["name"]
        artifacts = [
            *package.get("wheels", []),
            *([package["sdist"]] if "sdist" in package else []),
        ]
        assert artifacts, package["name"]
        for artifact in artifacts:
            assert _HASH.fullmatch(artifact["hash"]), package["name"]
            assert artifact["url"].startswith("https://files.pythonhosted.org/")


def _pinned(uses: str) -> bool:
    """A step action is local, or pinned by commit (actions) or by digest (docker)."""
    return uses.startswith("./") or bool(_PINNED.match(uses) or _DOCKER.match(uses))


def _read_only(permissions: object) -> bool:
    return isinstance(permissions, dict) and set(permissions.values()) <= _READ_ONLY


def test_ac1_uses_pinning_accepts_only_local_commit_or_digest() -> None:
    assert _pinned("actions/checkout@" + "a" * 40)
    assert _pinned("./.github/actions/setup")
    assert _pinned("docker://alpine@sha256:" + "0" * 64)
    for floating in ("actions/checkout@v4", "actions/checkout@main", "docker://alpine:3"):
        assert not _pinned(floating)


def test_ac1_workflows_exist() -> None:
    assert _WORKFLOWS  # an empty glob would make the parametrised check vacuous


@pytest.mark.parametrize("path", _WORKFLOWS, ids=[path.name for path in _WORKFLOWS])
def test_ac1_ci_has_a_read_only_token_pinned_actions_and_no_secrets(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    workflow = yaml.safe_load(text)
    assert _read_only(workflow["permissions"])
    assert "secrets." not in text
    for job in workflow["jobs"].values():
        assert _read_only(job.get("permissions", {}))
        if "uses" in job:  # a reusable workflow call
            assert _pinned(job["uses"]), job["uses"]
        for step in job.get("steps", []):
            if "uses" in step:
                assert _pinned(step["uses"]), step["uses"]
