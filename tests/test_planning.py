"""Negative tests protect the dependency/traceability gate from false success."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from scripts.planning import (
    Issue,
    Requirement,
    Status,
    critical_path,
    dependency_waves,
    validate_graph,
)


def issue(identifier: str, dependencies: list[str] | None = None) -> Issue:
    return Issue(
        id=identifier,
        aliases=[],
        title="An independently testable module",
        phase="P1",
        status="todo",
        priority="P1",
        complexity="M",
        modules=["core"],
        dependencies=dependencies or [],
        requirements=["R001"],
        context="A contract shared by modules",
        objective="A validated foundation",
        scope="One observable result",
        out_of_scope="Unrelated modules",
        technical=["Bounded memory", "Immutable output"],
        proposed_implementation=["Define contract", "Implement invariant"],
        acceptance=["Valid case succeeds", "Invalid case rejects before allocation"],
        tests=["Exact positive fixture", "Adversarial rejection"],
        deliverables=["Module", "Tests"],
        risks=["Integer overflow"],
        blocking_reason=None,
        acceptance_evidence={},
        test_evidence={},
        evidence=[],
    )


def requirement(identifier: str = "R001") -> Requirement:
    return Requirement(
        id=identifier, description="A requirement", sections=[1], verification="Observable test"
    )


def test_dependency_order_is_deterministic_and_dependency_first() -> None:
    first = issue("MOANA-001")
    second = issue("MOANA-002", [first.id])
    third = issue("MOANA-003", [first.id, second.id])
    assert validate_graph([third, first, second], [requirement()]) == [
        "MOANA-001",
        "MOANA-002",
        "MOANA-003",
    ]


@pytest.mark.parametrize(
    "nodes, message",
    [
        ([issue("MOANA-001", ["MOANA-001"])], "cycle"),
        ([issue("MOANA-001", ["MOANA-002"]), issue("MOANA-002", ["MOANA-001"])], "cycle"),
        ([issue("MOANA-001", ["MOANA-999"])], "Unknown"),
        ([issue("MOANA-001"), issue("MOANA-001")], "Duplicate issue"),
        (
            [issue("MOANA-001"), issue("MOANA-002", ["MOANA-001", "MOANA-001"])],
            "Duplicate dependencies",
        ),
    ],
)
def test_invalid_graphs_fail(nodes: list[Issue], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        validate_graph(nodes, [requirement()])


def test_uncovered_and_unknown_requirements_fail() -> None:
    with pytest.raises(ValueError, match="Uncovered"):
        validate_graph([issue("MOANA-001")], [requirement(), requirement("R002")])
    with pytest.raises(ValueError, match="Unknown"):
        validate_graph([issue("MOANA-001")], [requirement("R002")])


def test_duplicate_requirement_ids_fail() -> None:
    with pytest.raises(ValueError, match="Duplicate requirement"):
        validate_graph([issue("MOANA-001")], [requirement(), requirement()])


def test_completed_issue_requires_evidence_and_completed_dependencies() -> None:
    parent = issue("MOANA-001")
    child = issue("MOANA-002", [parent.id])
    child.status = "done"
    with pytest.raises(ValueError, match="without evidence"):
        validate_graph([parent, child], [requirement()])
    child.evidence = ["Command and observed result"]
    with pytest.raises(ValueError, match="unfinished dependencies"):
        validate_graph([parent, child], [requirement()])
    parent.status = "done"
    parent.evidence = ["Observed test result"]
    for node in (parent, child):
        node.acceptance_evidence = {"AC1": "Positive fixture passed", "AC2": "Rejection passed"}
        node.test_evidence = {"T1": "pytest fixture: passed", "T2": "pytest invalid: passed"}
    assert validate_graph([parent, child], [requirement()]) == [parent.id, child.id]


def test_phase_inversion_is_rejected() -> None:
    parent = issue("MOANA-001")
    parent.phase = "P5"
    with pytest.raises(ValueError, match="Phase inversion"):
        validate_graph([parent, issue("MOANA-002", [parent.id])], [requirement()])


def test_empty_acceptance_and_unknown_fields_are_rejected() -> None:
    data = issue("MOANA-001").model_dump()
    data["acceptance"] = []
    with pytest.raises(ValidationError):
        Issue.model_validate(data)
    data = issue("MOANA-001").model_dump()
    data["unreviewed_setting"] = True
    with pytest.raises(ValidationError):
        Issue.model_validate(data)


def test_active_statuses_require_finished_dependencies() -> None:
    parent = issue("MOANA-001")
    child = issue("MOANA-002", [parent.id])
    active: tuple[Status, ...] = ("ready", "in_progress", "review")
    for status in active:
        child.status = status
        with pytest.raises(ValueError, match="unfinished dependencies"):
            validate_graph([parent, child], [requirement()])


def test_blocked_status_requires_a_reason_and_clears_it_on_ready() -> None:
    node = issue("MOANA-001")
    node.status = "blocked"
    with pytest.raises(ValueError, match="without reason"):
        validate_graph([node], [requirement()])
    node.blocking_reason = "External fixture license pending"
    validate_graph([node], [requirement()])
    node.status = "ready"
    with pytest.raises(ValueError, match="blocking reason"):
        validate_graph([node], [requirement()])


def test_done_requires_evidence_for_each_criterion_and_test() -> None:
    node = issue("MOANA-001")
    node.status = "done"
    node.evidence = ["Recorded command result"]
    with pytest.raises(ValueError, match="Incomplete AC"):
        validate_graph([node], [requirement()])
    node.acceptance_evidence = {"AC1": "Pass", "AC2": "Pass"}
    with pytest.raises(ValueError, match="Incomplete T"):
        validate_graph([node], [requirement()])
    node.test_evidence = {"T1": "Pass", "T2": "Pass", "T99": "Unknown"}
    with pytest.raises(ValueError, match="Unknown T"):
        validate_graph([node], [requirement()])


def test_alias_cannot_identify_two_issues() -> None:
    first, second = issue("MOANA-001"), issue("MOANA-002")
    first.aliases = second.aliases = ["MOA-001"]
    with pytest.raises(ValueError, match="Duplicate alias"):
        validate_graph([first, second], [requirement()])


def test_critical_chain_and_parallel_levels_follow_dependencies() -> None:
    nodes = [
        issue("MOANA-001"),
        issue("MOANA-002", ["MOANA-001"]),
        issue("MOANA-003", ["MOANA-001"]),
        issue("MOANA-004", ["MOANA-002", "MOANA-003"]),
    ]
    order = validate_graph(nodes, [requirement()])
    assert critical_path(nodes, order) == ["MOANA-001", "MOANA-002", "MOANA-004"]
    assert dependency_waves(nodes, order) == [
        ["MOANA-001"],
        ["MOANA-002", "MOANA-003"],
        ["MOANA-004"],
    ]
