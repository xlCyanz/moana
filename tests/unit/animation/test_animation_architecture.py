"""moanart.animation respects MOANART.md section 3: core, schema, editing and render only."""

from __future__ import annotations

import ast
import sys
from collections.abc import Iterator
from pathlib import Path

SRC = Path(__file__).resolve().parents[3] / "src/moanart"
ANIMATION = SRC / "animation"
ALLOWED = (
    "moanart.core",
    "moanart.schema",
    "moanart.editing",
    "moanart.render",
    "moanart.animation",
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


def test_animation_imports_only_allowed_modules_and_public_names() -> None:
    paths = sorted(ANIMATION.glob("*.py"))
    assert {path.name for path in paths} == {"__init__.py", "frames.py", "timeline.py"}
    for path in paths:
        for name in imported_modules(path):
            root = name.split(".")[0]
            assert root in sys.stdlib_module_names or name.startswith(ALLOWED), name
            # Only public package APIs of the lower modules (no private submodules).
            if not name.startswith("moanart.animation") and root == "moanart":
                assert "._" not in name, name


def test_no_lower_module_imports_animation() -> None:
    for path in sorted(SRC.rglob("*.py")):
        if path.is_relative_to(ANIMATION) or path.is_relative_to(SRC / "api"):
            continue
        for name in imported_modules(path):
            assert not name.startswith("moanart.animation"), f"{path.name} imports {name}"


def test_no_eval_exec_pickle_or_dynamic_import() -> None:
    for path in sorted(ANIMATION.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        assert names.isdisjoint({"eval", "exec", "__import__", "compile", "open"}), path.name
        modules = set(imported_modules(path))
        assert modules.isdisjoint({"pickle", "importlib", "socket", "subprocess"}), path.name
