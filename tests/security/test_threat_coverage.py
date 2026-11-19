"""Every boundary of the threat model has a reproducible case (AC1).

The table of ``docs/architecture/SECURITY_MODEL.md`` is parsed, not copied: adding a
boundary there without tests here, or naming a test that does not exist, fails.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from .corpus import CORPUS, ROOT
from .coverage import COVERAGE

pytestmark = pytest.mark.security

HERE = Path(__file__).resolve().parent


_HEADER = "| Amenaza | Frontera |"


def _boundaries() -> list[str]:
    """The *Frontera* column of the threat table: from its header to the first blank line."""
    lines = (ROOT / "docs/architecture/SECURITY_MODEL.md").read_text(encoding="utf-8")
    rows = lines.splitlines()
    (start,) = [index for index, line in enumerate(rows) if line.startswith(_HEADER)]
    body: list[str] = []
    for line in rows[start + 2 :]:  # header and separator
        if not line.strip():
            break
        assert line.startswith("| "), line
        body.append(line.strip("|").split("|")[1].strip())
    return body


def _functions(module: str) -> set[str]:
    tree = ast.parse((HERE / f"{module}.py").read_text(encoding="utf-8"))
    return {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}


def test_ac1_every_threat_boundary_has_tests() -> None:
    boundaries = _boundaries()
    assert len(boundaries) == 10
    assert len(set(boundaries)) == len(boundaries)
    assert set(COVERAGE) == set(boundaries)
    for boundary in boundaries:
        assert COVERAGE[boundary].tests, boundary


def test_ac1_every_mapped_test_exists_and_is_documented() -> None:
    readme = (HERE / "README.md").read_text(encoding="utf-8")
    for boundary, coverage in COVERAGE.items():
        assert boundary in readme
        for reference in coverage.tests:
            module, function = reference.split("::")
            assert function in _functions(module), reference
            assert function in readme, reference


def test_ac1_corpus_boundaries_belong_to_the_threat_model() -> None:
    boundaries = set(_boundaries())
    assert {case.boundary for case in CORPUS} <= boundaries
