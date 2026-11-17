"""moana.render respects the dependency table of MOANA.md section 3."""

import ast
import sys
from collections.abc import Iterator
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


def test_render_imports_only_allowed_modules() -> None:
    paths = sorted(RENDER.glob("*.py"))
    assert paths
    for path in paths:
        for name in imported_modules(path):
            root = name.split(".")[0]
            # ``moana.__version__`` only, for the provenance manifest
            assert (
                root in sys.stdlib_module_names
                or root == "numpy"
                or name.startswith(ALLOWED)
                or name == "moana.__version__"
            ), f"{path.name} imports {name}"


def test_render_never_imports_cli_project_export_or_pillow() -> None:
    for path in sorted(RENDER.glob("*.py")):
        for name in imported_modules(path):
            assert not name.startswith(("moana.cli", "moana.project", "moana.export", "PIL"))
