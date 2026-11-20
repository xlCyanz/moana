"""api and cli respect MOANA.md section 3: nothing in the engine imports them."""

from __future__ import annotations

import ast
import sys
from collections.abc import Iterator
from pathlib import Path

SRC = Path(__file__).resolve().parents[3] / "src/moana"
DOMAIN = ("core", "schema", "palette", "geometry", "layers", "render", "export", "quality")


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


def test_api_composes_services_without_libraries_or_cli() -> None:
    paths = sorted((SRC / "api").glob("*.py"))
    assert paths
    for path in paths:
        for name in imported_modules(path):
            root = name.split(".")[0]
            assert (
                root in sys.stdlib_module_names
                or root == "_typeshed"
                or (name.startswith("moana.") and not name.startswith("moana.cli"))
            ), f"{path.name} imports {name}"
            assert root not in {"PIL", "numpy", "pydantic"}, f"{path.name} imports {name}"


def test_cli_depends_on_the_facade_not_on_libraries() -> None:
    for path in sorted((SRC / "cli").glob("*.py")):
        for name in imported_modules(path):
            root = name.split(".")[0]
            # Only the facade, the error classes and the package version.
            assert root in sys.stdlib_module_names or name in {
                "moana.api",
                "moana.core.errors",
                "moana.cli.commands",
                "moana.__version__",
            }, f"{path.name} imports {name}"


def test_no_domain_module_imports_api_or_cli() -> None:
    for package in DOMAIN:
        for path in sorted((SRC / package).rglob("*.py")):
            for name in imported_modules(path):
                assert not name.startswith(("moana.api", "moana.cli")), f"{path} imports {name}"
