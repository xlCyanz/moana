"""Check the pure parts of the GitHub backlog mirror and the agent guide."""

import pytest

from scripts.agent_guide import MODULES, branch_name, module_guides
from scripts.github_sync import (
    _paginated,
    github_body,
    issue_labels,
    label_specs,
    milestone_title,
)
from scripts.planning import generated_documents, load_catalog

REPO = "owner/repo"


def test_body_rewrites_issue_and_relative_links() -> None:
    markdown = (
        "# MOANA-002 — Title\n\n> Generado por `scripts/planning.py`; editar.\n\n"
        "Deps: [MOANA-001](MOANA-001.md), [old](MOA-001.md), [unknown](MOANA-099.md)\n"
        "[spec](../../MOANA.md) [ctx](../architecture/module-contracts.md#core) "
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
    assert "https://github.com/owner/repo/blob/main/MOANA.md" in body
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
