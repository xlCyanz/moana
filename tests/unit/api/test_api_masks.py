"""Masks and regions through the public facade (MOANA-013, ADR-020, ADR-022)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import moana.api
from moana.api import (
    MaskSummary,
    RegionSummary,
    ResolvedRegion,
    capabilities,
    inspect_document,
    load_document,
    render,
    resolve_region,
)
from moana.core.errors import ReferenceError
from moana.schema import Document

EXAMPLE = Path(__file__).resolve().parents[3] / "examples" / "specs" / "masked-eyes.moana.json"


def test_capabilities_list_masks_and_regions_as_available() -> None:
    listing = capabilities()
    assert listing.collections == ("masks", "regions")
    assert listing.mask_types == (
        "ellipse",
        "intersect",
        "line",
        "path",
        "pixel",
        "polygon",
        "rect",
        "subtract",
        "union",
        "xor",
    )
    assert listing.planned_mask_types == ()  # path arrived with MOANA-007 (ADR-023)
    assert "masks" not in listing.planned_collections
    assert "regions" not in listing.planned_collections
    assert "mask_id" not in listing.planned_layer_fields
    assert "resolve_region" in listing.functions
    assert listing.estimator_version == "budget-v8"
    mapping = listing.to_mapping()
    assert mapping["collections"] == ["masks", "regions"]
    assert list(mapping) == sorted(mapping)


def test_ac2_resolve_region_through_the_facade() -> None:
    document = load_document(EXAMPLE)
    region = resolve_region(document, "eye_left")
    assert isinstance(region, ResolvedRegion)
    assert (region.mask_id, region.operation_ids, region.layer_ids) == (
        "eye_left_shape",
        ("iris_left",),
        ("irises",),
    )
    with pytest.raises(ReferenceError):
        resolve_region(document, "nose")
    assert "resolve_region" in moana.api.__all__


def test_inspect_reports_masks_regions_and_layer_masks() -> None:
    report = inspect_document(load_document(EXAMPLE))
    assert report.masks[0] == MaskSummary("eyes_open", "subtract", ("eyes", "lid"))
    assert report.masks[2] == MaskSummary("eye_left_shape", "rect", ())
    assert report.regions[0] == RegionSummary("eye_left", "eye_left_shape", ("iris_left",))
    assert [layer.mask_id for layer in report.layers] == ["face_shape", "eyes_open", "eyes_open"]
    assert report.budget.within_limits and report.budget.estimator_version == "budget-v8"
    mapping = report.to_mapping()
    assert json.loads(json.dumps(mapping)) == mapping
    regions = mapping["regions"]
    assert isinstance(regions, list)
    assert regions[1] == {
        "id": "eye_right",
        "mask_id": "eye_right_shape",
        "operation_ids": ["iris_right"],
    }


def test_masked_example_renders_through_the_facade() -> None:
    result = render(load_document(EXAMPLE))
    assert result.pixel(5, 7) == (54, 175, 165, 255)  # iris inside the open eye
    assert result.pixel(5, 6) == (242, 194, 155, 255)  # lid row: the iris is clipped


def test_inspect_of_an_unvalidated_cycle_fails_fast() -> None:
    tree = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    tree["masks"].append({"id": "loop_a", "type": "union", "masks": ["loop_b", "lid"]})
    tree["masks"].append({"id": "loop_b", "type": "xor", "masks": ["loop_a", "lid"]})
    tree["layers"][0]["mask_id"] = "loop_a"
    document = Document.model_validate(tree)
    with pytest.raises(ReferenceError) as raised:
        inspect_document(document)
    assert raised.value.context["reason"] == "mask_cycle"
