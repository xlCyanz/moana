"""moanart.geometry imports only stdlib, NumPy and moanart.core (MOANART.md section 3)."""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

GEOMETRY = Path(__file__).resolve().parents[3] / "src/moanart/geometry"


def _imports(path: Path) -> list[str]:
    names: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
        elif isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
    return names


def test_geometry_imports_only_stdlib_numpy_core_and_itself() -> None:
    paths = sorted(GEOMETRY.glob("*.py"))
    assert paths
    for path in paths:
        for name in _imports(path):
            root = name.split(".")[0]
            assert (
                root in sys.stdlib_module_names
                or root == "numpy"
                or name.startswith(("moanart.core", "moanart.geometry"))
            ), f"{path.name} imports {name}"
            assert name != "moanart.core.pillow_adapter", f"{path.name} imports Pillow"


def test_importing_geometry_loads_neither_pillow_nor_pydantic() -> None:
    probe = (
        "import sys, moanart.geometry; "
        "heavy = {'PIL', 'aggdraw', 'pydantic'}; "
        "print(sorted(m for m in sys.modules if m.split('.')[0] in heavy))"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, encoding="utf-8", check=True
    )
    assert result.stdout.strip() == "[]"
