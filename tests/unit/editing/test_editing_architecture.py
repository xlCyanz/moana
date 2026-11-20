"""moana.editing respects MOANA.md section 3: it depends only on core and schema."""

from __future__ import annotations

import ast
import sys
from collections.abc import Iterator
from pathlib import Path

EDITING = Path(__file__).resolve().parents[3] / "src/moana/editing"
ALLOWED_THIRD_PARTY = {"pydantic", "pydantic_core"}


def imported_modules(path: Path) -> Iterator[str]:
    """Every module a file imports; ``from moana import x`` yields ``moana.x``."""
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module == "moana":
                yield from (f"moana.{alias.name}" for alias in node.names)
            else:
                yield node.module
        elif isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)


def test_editing_imports_only_core_schema_and_pydantic() -> None:
    paths = sorted(EDITING.glob("*.py"))
    assert paths
    for path in paths:
        for name in imported_modules(path):
            root = name.split(".")[0]
            assert (
                root in sys.stdlib_module_names
                or root in ALLOWED_THIRD_PARTY
                or name.startswith(("moana.core", "moana.schema", "moana.editing"))
            ), f"{path.name} imports {name}"


PRIVATE_SCHEMA_IMPORTS = {
    "moana.schema._issues",
    "moana.schema._pointers",
    "moana.schema._reader",
    "moana.schema.models",
}
"""Internal schema modules editing may use, each justified in ADR-024."""


def test_private_schema_imports_are_exactly_the_allowed_list() -> None:
    used = {
        name
        for path in sorted(EDITING.glob("*.py"))
        for name in imported_modules(path)
        if name.startswith("moana.schema.")
    }
    assert used == PRIVATE_SCHEMA_IMPORTS


def test_no_eval_exec_pickle_or_dynamic_import() -> None:
    for path in sorted(EDITING.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        assert names.isdisjoint({"eval", "exec", "__import__", "compile"}), path.name
        assert "pickle" not in set(imported_modules(path)), path.name
        assert "importlib" not in set(imported_modules(path)), path.name
