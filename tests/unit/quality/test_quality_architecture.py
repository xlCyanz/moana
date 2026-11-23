"""moanart.quality respects MOANART.md section 3 (ADR-036): it reads pixels, nothing more."""

from __future__ import annotations

import ast
import sys
from collections.abc import Iterator
from pathlib import Path

SRC = Path(__file__).resolve().parents[3] / "src/moanart"
ALLOWED = (
    "moanart.core",
    "moanart.palette",
    "moanart.geometry",
    "moanart.techniques",
    "moanart.quality",
)


def imported_modules(path: Path) -> Iterator[str]:
    """Every module a file imports; ``from moanart import x`` yields ``moanart.x``."""
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module == "moanart":
                yield from (f"moanart.{alias.name}" for alias in node.names)
            else:
                yield node.module
        elif isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)


def test_quality_imports_only_allowed_modules() -> None:
    paths = sorted((SRC / "quality").glob("*.py"))
    assert paths
    for path in paths:
        for name in imported_modules(path):
            root = name.split(".")[0]
            assert root in sys.stdlib_module_names or root == "numpy" or name.startswith(ALLOWED), (
                f"{path.name} imports {name}"
            )


def test_no_engine_module_imports_quality() -> None:
    for package in sorted(SRC.iterdir()):
        if package.name in {"quality", "api", "cli"} or not package.is_dir():
            continue
        for path in sorted(package.rglob("*.py")):
            for name in imported_modules(path):
                assert not name.startswith("moanart.quality"), f"{path} imports {name}"


def test_quality_has_no_eval_exec_or_pickle() -> None:
    for path in sorted((SRC / "quality").glob("*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        assert not names & {"eval", "exec", "compile", "__import__"}, path.name
        assert "pickle" not in set(imported_modules(path)), path.name
