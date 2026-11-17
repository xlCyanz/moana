"""moana.core stays at the bottom of the dependency table (MOANA.md section 3)."""

import ast
import subprocess
import sys
from pathlib import Path

CORE = Path(__file__).resolve().parents[3] / "src/moana/core"


def test_core_imports_only_stdlib_and_itself() -> None:
    for path in CORE.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            elif isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            else:
                continue
            for name in names:
                root = name.split(".")[0]
                assert root in sys.stdlib_module_names or name.startswith("moana.core"), (
                    f"{path.name} imports {name}"
                )


def test_importing_core_loads_no_graphics_library() -> None:
    probe = (
        "import sys, moana.core; "
        "heavy = {'numpy', 'PIL', 'aggdraw', 'pydantic'}; "
        "print(sorted(m for m in sys.modules if m.split('.')[0] in heavy))"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, encoding="utf-8", check=True
    )
    assert result.stdout.strip() == "[]"
