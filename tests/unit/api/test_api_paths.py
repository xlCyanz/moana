"""Facade and CLI view of paths and their backend (MOANA-007, ADR-023).

AC2: ``capabilities()`` reports ``path`` as available only when ``aggdraw-v1``
imports with a tested version; otherwise ``path`` moves to the planned lists (it
never just disappears) and ``backends`` says why.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from moanart.api import BackendSummary, capabilities, inspect_document, load_document, render
from moanart.cli import main
from moanart.geometry import TESTED_AGGDRAW_VERSIONS

ROOT = Path(__file__).resolve().parents[3]
EXAMPLE = ROOT / "examples" / "specs" / "path-sail.moanart.json"


def test_capabilities_with_the_tested_backend() -> None:
    listing = capabilities()
    assert "path" in listing.operations and "path" not in listing.planned_operations
    assert "path" in listing.mask_types and "path" not in listing.planned_mask_types
    (backend,) = listing.backends
    assert isinstance(backend, BackendSummary)
    assert (backend.name, backend.available, backend.reason) == ("aggdraw-v1", True, None)
    assert backend.version in TESTED_AGGDRAW_VERSIONS
    assert backend.tested_versions == TESTED_AGGDRAW_VERSIONS
    assert backend.capabilities == ("path",)
    mapping = listing.to_mapping()
    assert mapping["backends"] == [
        {
            "available": True,
            "capabilities": ["path"],
            "name": "aggdraw-v1",
            "pillow_version": backend.pillow_version,
            "reason": None,
            "tested_versions": list(TESTED_AGGDRAW_VERSIONS),
            "version": backend.version,
        }
    ]
    assert listing.estimator_version == "budget-v8"


@pytest.mark.parametrize("breakage", ["missing", "untested_version"])
def test_capabilities_move_path_to_planned_without_the_backend(
    monkeypatch: pytest.MonkeyPatch, breakage: str
) -> None:
    if breakage == "missing":
        monkeypatch.setitem(sys.modules, "aggdraw", None)
    else:
        monkeypatch.setattr(importlib.import_module("aggdraw"), "VERSION", "0.1")
    listing = capabilities()
    assert "path" not in listing.operations and "path" in listing.planned_operations
    assert "path" not in listing.mask_types and listing.planned_mask_types == ("path",)
    assert (listing.backends[0].available, listing.backends[0].reason) == (False, breakage)
    assert set(listing.operations).isdisjoint(listing.planned_operations)
    assert set(listing.mask_types).isdisjoint(listing.planned_mask_types)


def test_cli_capabilities_reports_the_backend(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["capabilities"]) == 0
    listing: dict[str, Any] = json.loads(capsys.readouterr().out)["capabilities"]
    assert "path" in listing["operations"]
    assert listing["backends"][0]["name"] == "aggdraw-v1"


def test_cli_render_without_backend_is_unsupported_operation(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setitem(sys.modules, "aggdraw", None)
    assert main(["render", str(EXAMPLE)]) == 2
    payload: dict[str, Any] = json.loads(capsys.readouterr().out)
    assert payload["error"]["code"] == "UNSUPPORTED_OPERATION"
    assert payload["error"]["context"]["reason"] == "backend_unavailable"


def test_example_with_paths_loads_inspects_and_renders() -> None:
    document = load_document(EXAMPLE)
    report = inspect_document(document)
    assert report.budget.within_limits and report.budget.estimator_version == "budget-v8"
    assert [op.type for layer in report.layers for op in layer.operations].count("path") >= 1
    assert any(mask.type == "path" for mask in report.masks)
    result = render(document)
    assert result.provenance.vector_backend == "aggdraw-v1"
    colours = {result.rgba[i : i + 4] for i in range(0, len(result.rgba), 4)}
    palette = {bytes.fromhex(color.rgba[1:]) for color in document.palette.colors}
    assert colours <= palette | {bytes(4)}  # no antialiasing colour
