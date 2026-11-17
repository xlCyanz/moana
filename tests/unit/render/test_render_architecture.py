"""moana.render respects the dependency table of MOANA.md section 3."""

import ast
import sys
from pathlib import Path

RENDER = Path(__file__).resolve().parents[3] / "src/moana/render"
ALLOWED: tuple[str, ...] = (
    "moana.core",
    "moana.schema",
    "moana.palette",
    "moana.geometry",
    "moana.layers",
    "moana.techniques",
    "moana.render",
)


def test_render_imports_only_allowed_modules() -> None:
    for path in RENDER.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            elif isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            else:
                continue
            for name in names:
                root = name.split(".")[0]
                assert root in sys.stdlib_module_names or name.startswith(ALLOWED), (
                    f"{path.name} imports {name}"
                )
