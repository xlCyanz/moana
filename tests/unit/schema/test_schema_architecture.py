"""moanart.schema depends only on core and Pydantic and never executes document content."""

import ast
import subprocess
import sys
from pathlib import Path

SCHEMA = Path(__file__).resolve().parents[3] / "src/moanart/schema"
ALLOWED_THIRD_PARTY = {"pydantic", "pydantic_core"}
FORBIDDEN_CALLS = {"eval", "exec", "compile", "__import__"}
FORBIDDEN_MODULES = {"pickle", "importlib", "subprocess", "socket", "urllib", "os", "shutil"}


def imported_names(tree: ast.AST) -> list[str]:
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
        elif isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
    return names


def test_schema_imports_follow_dependency_table() -> None:
    for path in SCHEMA.glob("*.py"):
        for name in imported_names(ast.parse(path.read_text(encoding="utf-8"))):
            root = name.split(".")[0]
            assert root not in FORBIDDEN_MODULES, f"{path.name} imports {name}"
            assert (
                root in sys.stdlib_module_names
                or root in ALLOWED_THIRD_PARTY
                or name.startswith(("moanart.core", "moanart.schema"))
            ), f"{path.name} imports {name}"


def test_schema_never_evaluates_code() -> None:
    for path in SCHEMA.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in FORBIDDEN_CALLS, f"{path.name} calls {node.func.id}"


def test_importing_schema_loads_no_graphics_library() -> None:
    probe = (
        "import sys, moanart.schema; "
        "heavy = {'numpy', 'PIL', 'aggdraw'}; "
        "print(sorted(m for m in sys.modules if m.split('.')[0] in heavy))"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, encoding="utf-8", check=True
    )
    assert result.stdout.strip() == "[]"
