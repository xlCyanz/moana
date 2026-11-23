"""Check the pure parts of the GitHub backlog mirror and the agent guide."""

import subprocess
from collections.abc import Sequence
from typing import Any

import pytest

from scripts.agent_guide import MODULES, branch_name, module_guides
from scripts.github_sync import (
    MAX_ATTEMPTS,
    GitHub,
    Label,
    _paginated,
    github_body,
    is_retryable,
    issue_labels,
    issue_update,
    label_specs,
    label_update,
    milestone_title,
    milestone_update,
    sync_labels,
)
from scripts.planning import generated_documents, load_catalog

REPO = "owner/repo"


def test_body_rewrites_issue_and_relative_links() -> None:
    markdown = (
        "# MOANA-002 — Title\n\n> Generado por `scripts/planning.py`; editar.\n\n"
        "Deps: [MOANA-001](MOANA-001.md), [old](MOA-001.md), [unknown](MOANA-099.md)\n"
        "[spec](../../MOANART.md) [ctx](../architecture/module-contracts.md#core) "
        "[web](https://example.com) Closes #<número>"
    )
    body = github_body(
        markdown,
        repository=REPO,
        numbers={"MOANA-001": 7},
        aliases={"MOA-001": "MOANA-001"},
        own_number=8,
    )
    assert not body.startswith("# ")
    assert "Sincronizado desde" in body and "Generado por" not in body
    assert body.count("https://github.com/owner/repo/issues/7") == 2
    assert "https://github.com/owner/repo/blob/main/docs/issues/MOANA-099.md" in body
    assert "https://github.com/owner/repo/blob/main/MOANART.md" in body
    assert "blob/main/docs/architecture/module-contracts.md#core" in body
    assert "[web](https://example.com)" in body
    assert "Closes #8" in body


def test_labels_and_milestones_cover_catalog() -> None:
    issues, _ = load_catalog()
    names = {label.name for label in label_specs(issues)}
    for issue in issues:
        assert set(issue_labels(issue)) <= names
    assert len(names) == len(label_specs(issues))
    assert all(len(name) <= 50 for name in names)
    assert milestone_title("P1") == "P1 — Contratos y core"


def test_every_issue_body_fits_github_limits() -> None:
    issues, requirements = load_catalog()
    documents = generated_documents(issues, requirements)
    for issue in issues:
        body = github_body(
            documents[f"docs/issues/{issue.id}.md"],
            repository=REPO,
            numbers={},
            aliases={},
            own_number=None,
        )
        assert len(body) < 65_536
        assert "## Guía para agentes de IA" in body


def test_paginated_merges_concatenated_arrays() -> None:
    assert _paginated('[{"a": 1}]\n[{"a": 2}, {"a": 3}]') == [{"a": 1}, {"a": 2}, {"a": 3}]
    assert _paginated("[]") == []


def test_branch_names_are_ascii_and_unique() -> None:
    issues, _ = load_catalog()
    branches = [branch_name(issue) for issue in issues]
    assert len(set(branches)) == len(branches)
    assert all(branch.isascii() and " " not in branch for branch in branches)
    assert branch_name(issues[1]) == "feat/MOANA-001-definir-tipos-coordenadas"


def test_unknown_module_is_rejected() -> None:
    issues, _ = load_catalog()
    broken = issues[1].model_copy(update={"modules": ["nonexistent"]})
    with pytest.raises(ValueError, match="Unknown module"):
        module_guides(broken)
    assert {module for issue in issues for module in issue.modules} <= set(MODULES)


DIAL_TIMEOUT = 'Get "https://api.github.com/x": dial tcp 140.82.113.6:443: i/o timeout'
READ_TIMEOUT = 'Patch "https://api.github.com/x": read tcp 10.0.0.2:5->1.2.3.4:443: i/o timeout'


class FakeGh:
    """Scripted `gh` runner: returns each (returncode, stdout, stderr) in order."""

    def __init__(self, *results: tuple[int, str, str]) -> None:
        self.results = list(results)
        self.commands: list[list[str]] = []

    def __call__(self, command: Sequence[str], **_: Any) -> subprocess.CompletedProcess[str]:
        self.commands.append(list(command))
        code, stdout, stderr = self.results.pop(0)
        return subprocess.CompletedProcess(list(command), code, stdout, stderr)


def _github(fake: FakeGh, sleeps: list[float]) -> GitHub:
    return GitHub("owner/repo", apply=True, run=fake, sleep=sleeps.append)


@pytest.mark.parametrize(
    ("method", "stderr", "expected"),
    [
        ("POST", DIAL_TIMEOUT, True),
        ("POST", "dial tcp: lookup api.github.com: no such host", True),
        ("POST", READ_TIMEOUT, False),
        ("POST", "gh: Server Error (HTTP 502)", False),
        ("PATCH", READ_TIMEOUT, True),
        ("GET", "gh: Server Error (HTTP 503)", True),
        ("GET", "You have exceeded a secondary rate limit", True),
        ("PATCH", "gh: Not Found (HTTP 404)", False),
        ("GET", "gh: Validation Failed (HTTP 422)", False),
    ],
)
def test_only_safe_failures_are_retried(method: str, stderr: str, expected: bool) -> None:
    assert is_retryable(method, stderr) is expected


def test_transient_failure_is_retried_with_exponential_backoff() -> None:
    fake = FakeGh((1, "", DIAL_TIMEOUT), (1, "", DIAL_TIMEOUT), (0, '{"ok": true}', ""))
    sleeps: list[float] = []
    assert _github(fake, sleeps).call("GET", "repos/{repo}/labels") == {"ok": True}
    assert len(fake.commands) == 3
    assert sleeps == [2.0, 4.0]
    assert fake.commands[0][-1] == "repos/owner/repo/labels"


def test_retries_stop_after_the_last_attempt() -> None:
    fake = FakeGh(*[(1, "", DIAL_TIMEOUT)] * MAX_ATTEMPTS)
    sleeps: list[float] = []
    with pytest.raises(RuntimeError, match="i/o timeout"):
        _github(fake, sleeps).call("GET", "repos/{repo}/labels")
    assert len(fake.commands) == MAX_ATTEMPTS
    assert sleeps == [2.0, 4.0, 8.0]


def test_post_that_may_have_reached_github_is_not_repeated() -> None:
    fake = FakeGh((1, "", READ_TIMEOUT))
    with pytest.raises(RuntimeError):
        _github(fake, []).call("POST", "repos/{repo}/issues", {"title": "t"})
    assert len(fake.commands) == 1


def test_permanent_failure_is_not_retried_and_missing_is_allowed() -> None:
    fake = FakeGh((1, "", "gh: Not Found (HTTP 404)"))
    github = _github(fake, [])
    assert github.call("GET", "repos/{repo}/x", allow_missing=True) is None
    assert len(fake.commands) == 1


def test_dry_run_counts_writes_without_running_them() -> None:
    fake = FakeGh()
    github = GitHub("owner/repo", apply=False, run=fake, sleep=lambda _: None)
    assert github.call("PATCH", "repos/{repo}/issues/1", {"title": "t"}) is None
    assert github.writes == 1 and fake.commands == []


def test_unchanged_label_and_milestone_need_no_write() -> None:
    label = Label("phase:P1", "c5def5", "Fase P1")
    assert label_update({"color": "C5DEF5", "description": "Fase P1"}, label) == {}
    assert label_update({"color": "ffffff", "description": None}, label) == {
        "color": "c5def5",
        "description": "Fase P1",
    }
    desired = {"title": "P1 — x", "description": "Puerta", "state": "open"}
    assert milestone_update({**desired, "number": 2}, desired) == {}
    assert milestone_update({**desired, "state": "closed"}, desired) == {"state": "open"}


def _desired(**changes: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "title": "MOANA-001 — t",
        "body": "Body\n",
        "labels": ["moanart", "status:done"],
        "milestone": 2,
        "state": "closed",
        "state_reason": "completed",
    }
    return {**payload, **changes}


def _current(**changes: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "title": "MOANA-001 — t",
        "body": "Body\r\n",
        "labels": [{"name": "status:done"}, {"name": "moanart"}],
        "milestone": {"number": 2},
        "state": "closed",
        "state_reason": "completed",
    }
    return {**item, **changes}


def test_unchanged_issue_needs_no_write() -> None:
    assert issue_update(_current(), _desired()) == {}
    open_issue = _desired(state="open")
    del open_issue["state_reason"]
    assert issue_update(_current(state="open", state_reason=None), open_issue) == {}


@pytest.mark.parametrize(
    ("current", "expected"),
    [
        (_current(title="old"), {"title": "MOANA-001 — t"}),
        (_current(body="Old"), {"body": "Body\n"}),
        (_current(labels=[{"name": "moanart"}]), {"labels": ["moanart", "status:done"]}),
        (_current(milestone=None), {"milestone": 2}),
        (
            _current(state="open", state_reason=None),
            {"state": "closed", "state_reason": "completed"},
        ),
        (
            _current(state_reason="not_planned"),
            {"state": "closed", "state_reason": "completed"},
        ),
    ],
)
def test_issue_update_sends_only_changed_fields(
    current: dict[str, Any], expected: dict[str, Any]
) -> None:
    assert issue_update(current, _desired()) == expected


def test_reopening_an_issue_sends_only_the_state() -> None:
    desired = _desired(state="open")
    del desired["state_reason"]
    assert issue_update(_current(), desired) == {"state": "open"}


def test_sync_labels_writes_only_differences() -> None:
    wanted = [Label("a", "000000", "A"), Label("b:x", "111111", "B"), Label("c", "222222", "C")]
    listing = '[{"name": "a", "color": "000000", "description": "A"}, '
    listing += '{"name": "b:x", "color": "999999", "description": "B"}]'
    fake = FakeGh((0, listing, ""), (0, "{}", ""), (0, "{}", ""))
    github = _github(fake, [])
    sync_labels(github, wanted)
    writes = [command[3:5] for command in fake.commands[1:]]
    assert writes == [
        ["PATCH", "repos/owner/repo/labels/b%3Ax"],
        ["POST", "repos/owner/repo/labels"],
    ]
    assert github.writes == 2
