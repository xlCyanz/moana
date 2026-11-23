"""Project values, limits and module boundaries of moanart.project (ADR-029)."""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Any

import pytest

from moanart.core.errors import BudgetExceeded, ValidationError
from moanart.core.limits import MAX_ASSET_PIXELS, MAX_PROJECT_ASSETS
from moanart.editing import History
from moanart.project import Asset, Project, ProjectLimits, encode_project, load_project
from moanart.schema import Document

from .conftest import BatchFactory, PngFactory

SRC = Path(__file__).resolve().parents[3] / "src/moanart"
PROJECT = SRC / "project"
ALLOWED_THIRD_PARTY = {"pydantic", "pydantic_core", "PIL"}


def _imports(path: Path) -> list[str]:
    names: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
        elif isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
    return names


def test_project_imports_only_core_schema_editing_and_pillow() -> None:
    for path in sorted(PROJECT.glob("*.py")):
        for name in _imports(path):
            root = name.split(".")[0]
            assert (
                root in sys.stdlib_module_names
                or root in ALLOWED_THIRD_PARTY
                or name.startswith(
                    ("moanart.core", "moanart.schema", "moanart.editing", "moanart.project")
                )
            ), f"{path.name} imports {name}"
            assert not name.startswith("moanart.schema._"), f"{path.name} imports {name}"


def test_lower_modules_never_import_project() -> None:
    checked = 0
    for path in sorted(SRC.rglob("*.py")):
        if PROJECT in path.parents:
            continue
        relative = path.relative_to(SRC).parts
        if relative[0] in ("api", "cli"):
            continue  # the facade and the CLI sit above project (MOANART.md section 3)
        assert not any(name.startswith("moanart.project") for name in _imports(path)), path
        checked += 1
    assert checked > 20


def test_no_eval_exec_pickle_or_network() -> None:
    forbidden = {"eval", "exec", "compile", "__import__"}
    for path in sorted(PROJECT.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in forbidden, path
        modules = {name.split(".")[0] for name in _imports(path)}
        assert not modules & {"pickle", "marshal", "socket", "urllib", "http", "subprocess"}


def test_project_values_are_checked(document: Document, png: PngFactory) -> None:
    asset = Asset.from_png("tex", png())
    with pytest.raises(TypeError):
        Project({})  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        Project(document, [asset])  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        Project(document, (), "history")  # type: ignore[arg-type]
    with pytest.raises(ValidationError) as caught:
        Project(document, (asset, asset))
    assert caught.value.context["reason"] == "duplicate_asset_id"
    with pytest.raises(ValidationError) as caught:
        Project(document, (Asset.from_png("ink", png()),))
    assert caught.value.context["reason"] == "id_collision"


def test_project_history_cursor_must_be_the_document(
    document: Document, batch: BatchFactory
) -> None:
    history = History.start(document)
    edited = history.edit(
        batch(document, {"type": "set_color", "target_id": "body_fill", "color": "ink"})
    )
    assert Project(edited.document, (), edited).history is edited
    with pytest.raises(ValidationError) as caught:
        Project(document, (), edited)
    assert caught.value.context["reason"] == "cursor_mismatch"


def test_project_asset_count_and_pixel_bounds(document: Document, png: PngFactory) -> None:
    tiny = png(1, 1)
    many = tuple(Asset.from_png(f"a{i}", tiny) for i in range(MAX_PROJECT_ASSETS + 1))
    assert len(Project(document, many[:-1]).assets) == MAX_PROJECT_ASSETS
    with pytest.raises(BudgetExceeded) as caught:
        Project(document, many)
    assert caught.value.context == {
        "resource": "project_assets",
        "limit": MAX_PROJECT_ASSETS,
        "estimated": MAX_PROJECT_ASSETS + 1,
    }
    full = png(2048, 2048, (0, 0, 0, 0))
    large = tuple(Asset.from_png(f"big{i}", full) for i in range(5))
    assert sum(asset.pixels for asset in large[:4]) == MAX_ASSET_PIXELS
    assert len(Project(document, large[:4]).assets) == 4  # exactly the budget is accepted
    with pytest.raises(BudgetExceeded) as caught:
        Project(document, large)
    assert caught.value.context["resource"] == "asset_pixels"


def test_encode_project_applies_the_save_budget(document: Document, png: PngFactory) -> None:
    assets = (Asset.from_png("a", png(4, 4)), Asset.from_png("b", png(4, 4, (1, 2, 3, 4))))
    project = Project(document, assets)
    cases = [
        (ProjectLimits(max_assets=1), "project_assets"),
        (ProjectLimits(max_asset_bytes=10), "asset_bytes"),
        (ProjectLimits(max_asset_pixels=20), "asset_pixels"),
    ]
    for limits, resource in cases:
        with pytest.raises(BudgetExceeded) as caught:
            encode_project(project, limits=limits)
        assert caught.value.context["resource"] == resource
    first, files = encode_project(project)
    assert encode_project(project) == (first, files)
    with pytest.raises(TypeError):
        encode_project(document)  # type: ignore[arg-type]


_LIMIT_FIELDS = (
    "max_manifest_bytes",
    "max_manifest_depth",
    "max_manifest_nodes",
    "max_assets",
    "max_asset_bytes",
    "max_asset_pixels",
    "max_archive_entries",
    "max_archive_bytes",
    "max_archive_expanded_bytes",
    "max_archive_ratio",
)


@pytest.mark.parametrize("field", _LIMIT_FIELDS)
def test_project_limits_can_only_be_lowered(field: str) -> None:
    default = getattr(ProjectLimits(), field)
    assert getattr(ProjectLimits(**{field: default - 1}), field) == default - 1
    with pytest.raises(ValidationError) as caught:
        ProjectLimits(**{field: default + 1})
    assert caught.value.context["reason"] == "out_of_range"


@pytest.mark.parametrize("field", _LIMIT_FIELDS)
@pytest.mark.parametrize("value", [True, 1.0])
def test_project_limits_reject_bool_and_float(field: str, value: object) -> None:
    arguments: dict[str, Any] = {field: value}
    with pytest.raises(ValidationError) as caught:
        ProjectLimits(**arguments)
    assert caught.value.context["reason"] == "not_integer"


def test_project_limits_types() -> None:
    with pytest.raises(TypeError):
        ProjectLimits(parse=None)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        ProjectLimits(history=None)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        load_project("x", limits=None)  # type: ignore[arg-type]
