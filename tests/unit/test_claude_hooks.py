"""Exercise the Claude Code hook guards and the Claude configuration checker."""

import io
import json
import shutil
from collections.abc import Mapping
from pathlib import Path

import pytest

from scripts import claude_hooks
from scripts.check_repository import check_claude_config
from scripts.planning import ROOT


def run_hook(monkeypatch: pytest.MonkeyPatch, handler: str, payload: Mapping[str, object]) -> int:
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    return claude_hooks.main([handler])


@pytest.mark.parametrize(
    "command",
    [
        "git push --force origin main",
        "git push -f",
        "cd src && git push origin x --force-with-lease",
        "git reset --hard HEAD~1",
        "git clean -fdx",
        "git commit -m wip --no-verify",
        "git checkout -- .",
        "rm -rf src",
        "rm -rf / ",
        "uv run pytest && rm -fr docs",
    ],
)
def test_dangerous_commands_are_blocked(monkeypatch: pytest.MonkeyPatch, command: str) -> None:
    assert run_hook(monkeypatch, "pre-bash", {"tool_input": {"command": command}}) == 2


@pytest.mark.parametrize(
    "command",
    [
        "git push origin feat/MOANA-001-coordinates",
        "git status --short",
        "rm -rf artifacts dist",
        "rm -rf ./build/",
        "uv run pytest -q",
        "rm notes.txt",
    ],
)
def test_ordinary_commands_pass(monkeypatch: pytest.MonkeyPatch, command: str) -> None:
    assert run_hook(monkeypatch, "pre-bash", {"tool_input": {"command": command}}) == 0


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (str(ROOT / "uv.lock"), 2),
        (".env", 2),
        ("config/.env.production", 2),
        (str(ROOT / "pyproject.toml"), 0),
        ("docs/environment.md", 0),
    ],
)
def test_pre_edit_protects_generated_and_secret_files(
    monkeypatch: pytest.MonkeyPatch, path: str, expected: int
) -> None:
    assert run_hook(monkeypatch, "pre-edit", {"tool_input": {"file_path": path}}) == expected


def test_malformed_payload_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    assert claude_hooks.main(["pre-bash"]) == 0
    assert claude_hooks.main(["unknown"]) == 1


def test_post_edit_reports_ruff_problems_only_for_python(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(claude_hooks, "ROOT", tmp_path)
    clean = tmp_path / "clean.py"
    clean.write_text('"""Clean module."""\n\nVALUE = 1\n', encoding="utf-8")
    dirty = tmp_path / "dirty.py"
    dirty.write_text("import os\nx=1\n", encoding="utf-8")
    notes = tmp_path / "notes.md"
    notes.write_text("x=1\n", encoding="utf-8")
    assert run_hook(monkeypatch, "post-edit", {"tool_input": {"file_path": str(clean)}}) == 0
    assert run_hook(monkeypatch, "post-edit", {"tool_input": {"file_path": str(dirty)}}) == 2
    assert run_hook(monkeypatch, "post-edit", {"tool_input": {"file_path": str(notes)}}) == 0
    outside = {"tool_input": {"file_path": "/nonexistent/elsewhere.py"}}
    assert run_hook(monkeypatch, "post-edit", outside) == 0


def copy_claude_layer(destination: Path) -> None:
    for item in (".claude", ".agents"):
        shutil.copytree(ROOT / item, destination / item)
    shutil.copy(ROOT / "CLAUDE.md", destination / "CLAUDE.md")


def test_claude_config_of_repository_is_valid() -> None:
    assert check_claude_config(ROOT) == []


def test_claude_config_detects_drift(tmp_path: Path) -> None:
    copy_claude_layer(tmp_path)
    wrapper = tmp_path / ".claude/skills/moanart-python/SKILL.md"
    wrapper.write_text(
        wrapper.read_text(encoding="utf-8").replace("description:", "description: Drift"),
        encoding="utf-8",
    )
    reviewer = tmp_path / ".claude/agents/moanart-architect.md"
    reviewer.write_text(
        reviewer.read_text(encoding="utf-8").replace("tools: Read,", "tools: Edit, Read,"),
        encoding="utf-8",
    )
    (tmp_path / ".claude/rules/issues.md").unlink()
    (tmp_path / "CLAUDE.md").write_text("# No import\n", encoding="utf-8")
    errors = check_claude_config(tmp_path)
    assert any("metadata differs" in error for error in errors)
    assert any("Only the documentation agent" in error for error in errors)
    assert any("eight named Claude rules" in error for error in errors)
    assert any("import @AGENTS.md" in error for error in errors)
