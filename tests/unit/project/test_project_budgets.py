"""T1/T3 of MOANA-020: what saves always loads, and budgets fail as ``BudgetExceeded``."""

from __future__ import annotations

import json
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from moanart.core.errors import BudgetExceeded, EditConflict, MoanArtError
from moanart.core.limits import MAX_ASSET_BYTES, MAX_HISTORY_SNAPSHOTS, MAX_PROJECT_ASSETS
from moanart.editing import History, HistoryLimits
from moanart.project import (
    MANIFEST_NAME,
    Asset,
    Project,
    ProjectLimits,
    encode_project,
    load_project,
    save_document,
    save_project,
    save_project_archive,
)
from moanart.project._json import measure_shape, read_json_object
from moanart.project.archive import _check_entries
from moanart.schema import DEFAULT_PARSE_LIMITS, Document, ParseLimits, canonical_json
from moanart.schema import validate_document as parse_document

from .conftest import encode_png, make_batch

_DENSE_OPERATIONS = 2163


def _dense_document(operations: int = _DENSE_OPERATIONS) -> Document:
    """128 layers without their optional members and ``operations`` rects.

    The source stays under the default node limit; the canonical form, which writes
    every layer member, does not: the probe of the ALTO 1 review finding.
    """
    layers: list[dict[str, Any]] = [
        {"id": f"l{index}", "name": "x", "operations": []} for index in range(128)
    ]
    for index in range(operations):
        layers[index % 128]["operations"].append(
            {"id": f"o{index}", "type": "rect", "box": [0, 0, 1, 1], "color": "ink"}
        )
    tree = {
        "schema_version": "1.0",
        "id": "dense",
        "revision": 0,
        "seed": 1,
        "canvas": {"width": 128, "height": 128},
        "palette": {"id": "p", "colors": [{"id": "ink", "rgba": "#000000FF"}]},
        "layers": layers,
    }
    return parse_document(json.dumps(tree).encode("utf-8"))


def test_t1_canonical_form_over_the_node_limit_is_refused_before_writing(
    tmp_path: Path,
) -> None:
    document = _dense_document()
    source_nodes = measure_shape(json.dumps(document.model_dump(exclude_unset=True)))[1]
    canonical_nodes = measure_shape(canonical_json(document).decode("utf-8"))[1]
    assert source_nodes <= DEFAULT_PARSE_LIMITS.max_nodes < canonical_nodes
    project = Project(document, (), History.start(document))
    saves: dict[str, Callable[[], object]] = {
        "directory": lambda: save_project(project, tmp_path / "p"),
        "archive": lambda: save_project_archive(project, tmp_path / "p.moanart"),
        "document": lambda: save_document(document, tmp_path / "d.moanart.json"),
    }
    for name, save in saves.items():
        with pytest.raises(BudgetExceeded) as caught:
            save()
        assert caught.value.context == {
            "resource": "document_nodes",
            "limit": DEFAULT_PARSE_LIMITS.max_nodes,
            "estimated": canonical_nodes,
        }, name
    assert list(tmp_path.iterdir()) == []


def test_t1_one_operation_less_saves_and_loads_in_every_format(tmp_path: Path) -> None:
    operations = _DENSE_OPERATIONS
    while True:  # the largest dense document whose canonical form still loads
        document = _dense_document(operations)
        nodes = measure_shape(canonical_json(document).decode("utf-8"))[1]
        if nodes <= DEFAULT_PARSE_LIMITS.max_nodes:
            break
        operations -= 1
    assert nodes > DEFAULT_PARSE_LIMITS.max_nodes - 9
    limits = ProjectLimits(max_manifest_nodes=32_768)
    project = Project(document)
    save_project(project, tmp_path / "p", limits=limits)
    save_project_archive(project, tmp_path / "p.moanart", limits=limits)
    save_document(document, tmp_path / "d.moanart.json")
    for name in ("p", "p.moanart", "d.moanart.json"):
        assert load_project(tmp_path / name, limits=limits) == project


def test_t1_every_stored_part_is_checked_with_the_reader_bounds(document: Document) -> None:
    moves = [{"type": "translate", "target_id": "body_fill", "dx": 1, "dy": 0} for _ in range(40)]
    history = History.start(document).edit(make_batch(document, *moves))
    project = Project(history.document, (), history)
    manifest, files = encode_project(project)
    documents = [data for name, data in files.items() if "snapshots" in name]
    batches = [data for name, data in files.items() if "batches" in name]
    document_nodes = max(measure_shape(data.decode("utf-8"))[1] for data in documents)
    batch_nodes = measure_shape(batches[0].decode("utf-8"))[1]
    depth, nodes = measure_shape(manifest.decode("utf-8"))
    assert batch_nodes > document_nodes
    cases = [
        (ProjectLimits(parse=ParseLimits(max_nodes=document_nodes)), "batch_nodes"),
        (ProjectLimits(parse=ParseLimits(max_bytes=len(batches[0]) - 1)), "batch_bytes"),
        (ProjectLimits(max_manifest_nodes=nodes - 1), "manifest_nodes"),
        (ProjectLimits(max_manifest_depth=depth - 1), "manifest_depth"),
        (ProjectLimits(max_manifest_bytes=len(manifest) - 1), "manifest_bytes"),
        (ProjectLimits(parse=ParseLimits(max_depth=3)), "document_depth"),
        (ProjectLimits(history=HistoryLimits(max_snapshots=1)), "history_snapshots"),
        (ProjectLimits(history=HistoryLimits(max_bytes=100)), "history_bytes"),
    ]
    for limits, resource in cases:
        with pytest.raises(BudgetExceeded) as caught:
            encode_project(project, limits=limits)
        assert caught.value.context["resource"] == resource
    exact = ProjectLimits(
        max_manifest_bytes=len(manifest),
        max_manifest_depth=depth,
        max_manifest_nodes=nodes,
        parse=ParseLimits(max_nodes=batch_nodes),
    )
    assert encode_project(project, limits=exact) == (manifest, files)
    with pytest.raises(BudgetExceeded) as caught:
        save_document(document, "unused.moanart.json", limits=ParseLimits(max_bytes=10))
    assert caught.value.context["resource"] == "document_bytes"


def test_t3_finite_floats_are_read_and_overflowing_ones_rejected() -> None:
    bounds = {"max_bytes": 100, "max_depth": 4, "max_nodes": 10}
    assert read_json_object(b'{"a": 1.5e3}', **bounds) == {"a": 1500.0}
    with pytest.raises(MoanArtError) as caught:
        read_json_object(b'{"a": 1e999}', **bounds)
    assert caught.value.context["reason"] == "non_finite_number"


# --- budgets read from a manifest -----------------------------------------------------


def _manifest_with(tmp_path: Path, document: Document, **members: Any) -> Path:
    root = tmp_path / "p"
    save_project(Project(document), root)
    tree = json.loads((root / MANIFEST_NAME).read_text(encoding="utf-8"))
    tree.update(members)
    (root / MANIFEST_NAME).write_text(json.dumps(tree), encoding="utf-8")
    return root


def _ref(index: int, byte_length: int = 10) -> dict[str, Any]:
    digest = f"{index:064x}"
    return {
        "id": f"asset_{index}",
        "path": f"assets/{digest}.png",
        "mime": "image/png",
        "byte_length": byte_length,
        "sha256": digest,
    }


def _load_budget(root: Path) -> dict[str, object]:
    with pytest.raises(BudgetExceeded) as caught:
        load_project(root)
    return dict(caught.value.context)


def test_t3_too_many_asset_references_is_a_budget(tmp_path: Path, document: Document) -> None:
    refs = [_ref(index) for index in range(MAX_PROJECT_ASSETS + 1)]
    root = _manifest_with(tmp_path, document, assets=refs)
    assert _load_budget(root) == {
        "resource": "project_assets",
        "limit": MAX_PROJECT_ASSETS,
        "estimated": MAX_PROJECT_ASSETS + 1,
    }


def test_t3_declared_asset_length_over_the_limit_is_a_budget(
    tmp_path: Path, document: Document
) -> None:
    root = _manifest_with(tmp_path, document, assets=[_ref(0, MAX_ASSET_BYTES + 1)])
    assert _load_budget(root) == {
        "resource": "asset_bytes",
        "limit": MAX_ASSET_BYTES,
        "estimated": MAX_ASSET_BYTES + 1,
    }


def test_t3_too_many_history_entries_is_a_budget(tmp_path: Path, document: Document) -> None:
    root_digest = f"sha256:{0:064x}"
    entries = [{"snapshot": root_digest, "parent": None, "batch": None, "redo": False}] + [
        {
            "snapshot": f"sha256:{index:064x}",
            "parent": root_digest,
            "batch": f"sha256:{index:064x}",
            "redo": False,
        }
        for index in range(1, MAX_HISTORY_SNAPSHOTS + 1)
    ]
    root = _manifest_with(tmp_path, document, history=entries)
    assert _load_budget(root) == {
        "resource": "history_snapshots",
        "limit": MAX_HISTORY_SNAPSHOTS,
        "estimated": MAX_HISTORY_SNAPSHOTS + 1,
    }


# --- archive borders ------------------------------------------------------------------


def _linear(document: Document, snapshots: int) -> Project:
    history = History.start(document)
    move = {"type": "translate", "target_id": "body_fill", "dx": 1, "dy": 0}
    for _ in range(snapshots - 1):
        history = history.edit(make_batch(history.document, move))
    return Project(history.document, (), history)


def test_t1_an_archive_holds_128_snapshots_but_not_129(tmp_path: Path, document: Document) -> None:
    """Manifest + n snapshots + (n - 1) batches must fit in 256 entries (ADR-029 §5)."""
    fits = _linear(document, 128)
    save_project_archive(fits, tmp_path / "fits.moanart")
    with zipfile.ZipFile(tmp_path / "fits.moanart") as archive:
        assert len(archive.infolist()) == 256
    assert load_project(tmp_path / "fits.moanart") == fits
    too_many = _linear(document, 129)
    with pytest.raises(BudgetExceeded) as caught:
        save_project_archive(too_many, tmp_path / "over.moanart")
    assert caught.value.context["resource"] == "archive_entries"
    assert not (tmp_path / "over.moanart").exists()
    save_project(too_many, tmp_path / "directory")  # a directory has no entry limit
    assert load_project(tmp_path / "directory") == too_many


def _info(name: str, size: int, compressed: int) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name)
    info.file_size = size
    info.compress_size = compressed
    return info


@pytest.mark.parametrize(
    ("size", "allowed"),
    [(100 * 50, True), (100 * 50 + 1, False), (100 * 50 - 1, True)],
)
def test_t2_expansion_ratio_border_is_exactly_100_to_1(size: int, allowed: bool) -> None:
    infos = [_info(f"assets/{0:064x}.png", size, 50)]
    if allowed:
        _check_entries(infos, ProjectLimits())
        return
    with pytest.raises(MoanArtError) as caught:
        _check_entries(infos, ProjectLimits())
    assert caught.value.context["reason"] == "unsafe_archive"
    assert caught.value.context["entry_reason"] == "expansion_ratio"


# --- property: whatever is saved loads back -------------------------------------------


_OPERATIONS = st.lists(
    st.sampled_from(["move", "recolor", "hide", "undo", "redo", "checkout"]), max_size=20
)
_PNGS = st.lists(
    st.tuples(
        st.integers(1, 4),
        st.integers(1, 4),
        st.tuples(*(st.integers(0, 255) for _ in range(4))),
    ),
    max_size=3,
)


def _play(document: Document, operations: list[str], seed: int) -> History:
    commands: dict[str, dict[str, object]] = {
        "move": {"type": "translate", "target_id": "body_fill", "dx": 1, "dy": 0},
        "recolor": {"type": "set_color", "target_id": "body_fill", "color": "ink"},
        "hide": {"type": "set_visibility", "target_id": "body", "visible": False},
    }
    history = History.start(document)
    for step, operation in enumerate(operations):
        if operation == "undo" and history.can_undo:
            history = history.undo()
        elif operation == "redo" and history.can_redo:
            history = history.redo()
        elif operation == "checkout":
            stored = list(history.snapshots)
            history = history.checkout(stored[(seed + step) % len(stored)])
        elif operation in commands:
            try:
                history = history.edit(make_batch(history.document, commands[operation]))
            except EditConflict:
                continue  # the same document under another parent (ADR-026 section 4)
            except MoanArtError:
                continue  # e.g. recoloring with the color it already has
    return history


@settings(
    max_examples=40,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(operations=_OPERATIONS, pngs=_PNGS, seed=st.integers(0, 1000))
def test_t1_property_any_saved_project_loads_back_identically(
    tmp_path_factory: pytest.TempPathFactory,
    document: Document,
    operations: list[str],
    pngs: list[tuple[int, int, tuple[int, int, int, int]]],
    seed: int,
) -> None:
    history = _play(document, operations, seed)
    assets = tuple(
        Asset.from_png(f"asset_{index}", encode_png(width, height, color))
        for index, (width, height, color) in enumerate(pngs)
    )
    project = Project(history.document, assets, history)
    first = encode_project(project)
    assert encode_project(project) == first
    folder = tmp_path_factory.mktemp("property")
    save_project(project, folder / "p")
    save_project_archive(project, folder / "p.moanart")
    for name in ("p", "p.moanart"):
        loaded = load_project(folder / name)
        assert loaded == project
        assert encode_project(loaded) == first
