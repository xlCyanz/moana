"""Masks and regions of schema 1.0: payloads, reference DAG and region resolution.

MOANA-013 (ADR-022). T2: direct and indirect cycles and missing references are
rejected with pointers to the offending member, independent of array order. AC2: a
region such as ``eye_left`` resolves by ID. Expected values are written by hand.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from moana.core import errors
from moana.core.limits import MAX_MASK_DEPTH, MAX_MASK_OPERANDS
from moana.schema import (
    SUPPORTED_COLLECTIONS,
    SUPPORTED_MASK_TYPES,
    CombinationMask,
    Document,
    RectMask,
    ResolvedRegion,
    UnionMask,
    canonical_json,
    document_json_schema,
    mask_dependencies,
    resolve_region,
    snapshot_digest,
    validate_document,
)

ROOT = Path(__file__).resolve().parents[3]
EXAMPLE = ROOT / "examples" / "specs" / "masked-eyes.moana.json"


def example() -> dict[str, Any]:
    tree: dict[str, Any] = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    return tree


def with_masks(minimal: dict[str, Any], masks: list[dict[str, Any]]) -> dict[str, Any]:
    minimal["masks"] = masks
    return minimal


def rect(name: str, box: list[int] | None = None) -> dict[str, Any]:
    return {"id": name, "type": "rect", "box": box or [0, 0, 4, 4]}


def combo(name: str, kind: str, *operands: str) -> dict[str, Any]:
    return {"id": name, "type": kind, "masks": list(operands)}


def problems(source: dict[str, Any]) -> list[tuple[str, str | None, object]]:
    with pytest.raises(errors.MoanaError) as raised:
        validate_document(source)
    return [(d.code, d.json_pointer, d.context.get("reason")) for d in raised.value.details]


# --- Payloads --------------------------------------------------------------------------


def test_example_document_validates_with_the_real_model() -> None:
    document = validate_document(EXAMPLE.read_bytes())
    assert [mask.id for mask in document.masks][:2] == ["eyes_open", "eyes"]
    assert isinstance(document.masks[0], CombinationMask)
    assert isinstance(document.masks[2], RectMask)
    assert [layer.mask_id for layer in document.layers] == ["face_shape", "eyes_open", "eyes_open"]
    assert document.regions[0].operation_ids == ("iris_left",)
    assert validate_document(example()) == document  # bytes and mapping agree


def test_every_mask_type_is_accepted(minimal: dict[str, Any]) -> None:
    masks = [
        {"id": "p", "type": "pixel", "at": [1, 1]},
        {"id": "l", "type": "line", "start": [0, 0], "end": [5, 3]},
        rect("r"),
        {"id": "e", "type": "ellipse", "box": [0, 0, 6, 4]},
        {"id": "g", "type": "polygon", "points": [[0, 0], [6, 0], [3, 5]]},
        combo("u", "union", "p", "l"),
        combo("i", "intersect", "r", "e"),
        combo("s", "subtract", "g", "p", "l"),
        combo("x", "xor", "u", "i", "s"),
    ]
    document = validate_document(with_masks(minimal, masks))
    assert {mask.type for mask in document.masks} == SUPPORTED_MASK_TYPES
    assert {"masks", "regions"} == SUPPORTED_COLLECTIONS


def test_defaults_and_canonical_form(minimal: dict[str, Any]) -> None:
    before = snapshot_digest(validate_document(copy.deepcopy(minimal)))
    explicit = copy.deepcopy(minimal)
    explicit["masks"], explicit["regions"] = [], []
    assert snapshot_digest(validate_document(explicit)) == before  # 1.0 documents unchanged
    minimal["masks"] = [rect("m")]
    minimal["regions"] = [{"id": "zone", "mask_id": "m"}]
    minimal["layers"][0]["mask_id"] = "m"
    document = validate_document(minimal)
    canonical = json.loads(canonical_json(document))
    assert canonical["regions"] == [{"id": "zone", "mask_id": "m", "operation_ids": []}]
    assert canonical["layers"][0]["mask_id"] == "m"
    unmasked = json.loads(canonical_json(validate_document(explicit)))
    assert "mask_id" not in unmasked["layers"][0]  # absent optional member stays absent


def test_json_schema_describes_masks_and_regions() -> None:
    schema = document_json_schema()
    properties = schema["properties"]
    assert isinstance(properties, dict)
    mapping = properties["masks"]["items"]["discriminator"]["mapping"]
    assert set(mapping) == SUPPORTED_MASK_TYPES
    assert properties["regions"]["items"] == {"$ref": "#/$defs/Region"}
    definitions = schema["$defs"]
    assert isinstance(definitions, dict)
    assert "mask_id" in definitions["Layer"]["properties"]
    assert "mask_id" not in definitions["Layer"]["required"]
    union = definitions["UnionMask"]["properties"]["masks"]
    assert (union["minItems"], union["maxItems"]) == (2, MAX_MASK_OPERANDS)


@pytest.mark.parametrize(
    ("mask", "pointer", "reason"),
    [
        ({"id": "m", "type": "union", "masks": ["a"]}, "/masks/0/masks", "too_short"),
        ({"id": "m", "type": "union"}, "/masks/0/masks", "missing"),
        ({"id": "m", "type": "rect", "box": [4, 4, 4, 8]}, "/masks/0/box", "box_empty_or_inverted"),
        (
            {"id": "m", "type": "rect", "box": [0, 0, 1, 1], "color": "ink"},
            "/masks/0/color",
            "extra_forbidden",
        ),
        ({"id": "m", "type": "blur", "box": [0, 0, 1, 1]}, "/masks/0/type", "union_tag_invalid"),
        ({"id": "m"}, "/masks/0", "union_tag_not_found"),
        ({"id": "M", "type": "pixel", "at": [0, 0]}, "/masks/0/id", "string_pattern_mismatch"),
    ],
)
def test_structural_mask_errors_are_located(
    minimal: dict[str, Any], mask: dict[str, Any], pointer: str, reason: str
) -> None:
    found = problems(with_masks(minimal, [mask]))
    assert ("VALIDATION_ERROR", pointer, reason) in found


def test_unknown_mask_type_lists_mask_types(minimal: dict[str, Any]) -> None:
    with pytest.raises(errors.ValidationError) as raised:
        validate_document(with_masks(minimal, [{"id": "m", "type": "blur"}]))
    detail = raised.value.details[0]
    assert detail.message == "Mask type is not part of schema 1.0"
    assert detail.context["expected"] == tuple(sorted(SUPPORTED_MASK_TYPES))
    with pytest.raises(errors.ValidationError) as raised:
        validate_document(with_masks(minimal, [{"id": "m"}]))
    assert raised.value.details[0].message == "Mask requires a 'type' member"


def test_path_mask_is_a_planned_capability(minimal: dict[str, Any]) -> None:
    with pytest.raises(errors.UnsupportedOperation) as raised:
        validate_document(with_masks(minimal, [{"id": "m", "type": "path", "commands": []}]))
    detail = raised.value.details[0]
    assert (detail.json_pointer, detail.context["capability"]) == ("/masks/0/type", "path")


def test_null_mask_id_is_rejected(minimal: dict[str, Any]) -> None:
    minimal["layers"][0]["mask_id"] = None
    assert problems(minimal) == [("VALIDATION_ERROR", "/layers/0/mask_id", "null_not_allowed")]


def test_mask_and_region_ids_are_globally_unique(minimal: dict[str, Any]) -> None:
    minimal["masks"] = [rect("body"), rect("cloth")]  # a layer ID and a colour ID
    minimal["regions"] = [{"id": "body_fill", "mask_id": "body"}]  # an operation ID
    found = problems(minimal)
    assert ("VALIDATION_ERROR", "/masks/0/id", "duplicate_id") in found
    assert ("VALIDATION_ERROR", "/masks/1/id", "duplicate_id") in found
    assert ("VALIDATION_ERROR", "/regions/0/id", "duplicate_id") in found


# --- T2: references, cycles and depth ----------------------------------------------------


def test_t2_missing_references_point_to_the_member(minimal: dict[str, Any]) -> None:
    minimal["masks"] = [rect("a"), combo("u", "union", "a", "ghost")]
    minimal["layers"][0]["mask_id"] = "nowhere"
    minimal["regions"] = [
        {"id": "eye", "mask_id": "missing", "operation_ids": ["body_fill", "nope"]}
    ]
    assert problems(minimal) == [
        ("REFERENCE_ERROR", "/layers/0/mask_id", "unknown_mask"),
        ("REFERENCE_ERROR", "/masks/1/masks/1", "unknown_mask"),
        ("REFERENCE_ERROR", "/regions/0/mask_id", "unknown_mask"),
        ("REFERENCE_ERROR", "/regions/0/operation_ids/1", "unknown_operation"),
    ]


def test_t2_references_to_non_masks_are_missing_references(minimal: dict[str, Any]) -> None:
    # A layer, an operation or a colour is never a mask: masks cannot use a layer render.
    minimal["masks"] = [rect("a"), combo("u", "union", "a", "body"), combo("v", "xor", "a", "ink")]
    minimal["layers"][0]["mask_id"] = "body_fill"
    with pytest.raises(errors.ReferenceError) as raised:
        validate_document(minimal)
    assert [d.json_pointer for d in raised.value.details] == [
        "/layers/0/mask_id",
        "/masks/1/masks/1",
        "/masks/2/masks/1",
    ]


def test_t2_direct_cycle_is_rejected(minimal: dict[str, Any]) -> None:
    minimal["masks"] = [rect("a"), combo("self", "union", "a", "self")]
    with pytest.raises(errors.ReferenceError) as raised:
        validate_document(minimal)
    assert [(d.json_pointer, d.context["reason"]) for d in raised.value.details] == [
        ("/masks/1/masks/1", "mask_cycle")
    ]


def test_t2_indirect_cycle_marks_every_edge_of_the_loop(minimal: dict[str, Any]) -> None:
    minimal["masks"] = [
        combo("c", "subtract", "a", "leaf"),
        rect("leaf"),
        combo("a", "union", "leaf", "b"),
        combo("b", "intersect", "c", "leaf"),
        combo("user", "xor", "a", "leaf"),  # depends on the cycle, is not part of it
    ]
    assert problems(minimal) == [
        ("REFERENCE_ERROR", "/masks/0/masks/0", "mask_cycle"),
        ("REFERENCE_ERROR", "/masks/2/masks/1", "mask_cycle"),
        ("REFERENCE_ERROR", "/masks/3/masks/0", "mask_cycle"),
    ]


def test_t2_resolution_is_independent_of_array_order(minimal: dict[str, Any]) -> None:
    masks = [combo("top", "union", "mid", "leaf"), combo("mid", "xor", "leaf", "other")]
    masks += [rect("leaf"), rect("other", [2, 2, 6, 6])]
    forward = with_masks(copy.deepcopy(minimal), masks)
    backward = with_masks(copy.deepcopy(minimal), list(reversed(masks)))
    for source in (forward, backward):
        document = validate_document(source)
        assert mask_dependencies(document, "top") == ("leaf", "other", "mid", "top")
    cyclic = [combo("x", "union", "y", "leaf"), combo("y", "union", "x", "leaf"), rect("leaf")]
    for order in (cyclic, list(reversed(cyclic))):
        found = problems(with_masks(copy.deepcopy(minimal), order))
        assert [reason for _, _, reason in found] == ["mask_cycle", "mask_cycle"]


def test_t2_repeated_references_are_validation_errors(minimal: dict[str, Any]) -> None:
    minimal["masks"] = [rect("a"), rect("b"), combo("u", "union", "a", "b", "a")]
    minimal["regions"] = [{"id": "z", "mask_id": "u", "operation_ids": ["body_fill"] * 2}]
    with pytest.raises(errors.ValidationError) as raised:
        validate_document(minimal)
    assert [(d.json_pointer, d.context["reason"]) for d in raised.value.details] == [
        ("/masks/2/masks/2", "duplicate_reference"),
        ("/regions/0/operation_ids/1", "duplicate_reference"),
    ]


def test_t2_mask_depth_limit(minimal: dict[str, Any]) -> None:
    def chain(length: int) -> list[dict[str, Any]]:
        masks = [rect("m1"), rect("leaf")]
        masks += [combo(f"m{n}", "union", f"m{n - 1}", "leaf") for n in range(2, length + 1)]
        return masks

    validate_document(with_masks(copy.deepcopy(minimal), chain(MAX_MASK_DEPTH)))
    found = problems(with_masks(copy.deepcopy(minimal), chain(MAX_MASK_DEPTH + 2)))
    # Only the first mask over the limit is reported: deeper ones pass through it.
    assert found == [("VALIDATION_ERROR", f"/masks/{MAX_MASK_DEPTH + 1}", "too_deep")]


def test_t2_mask_outside_the_canvas_is_valid(minimal: dict[str, Any]) -> None:
    minimal["masks"] = [
        rect("off", [500, 500, 600, 600]),
        {"id": "neg", "type": "pixel", "at": [-5, 2]},
    ]
    minimal["layers"][0]["mask_id"] = "off"
    assert validate_document(minimal).layers[0].mask_id == "off"  # clipped at render time


# --- AC2: regions by ID ----------------------------------------------------------------


def test_ac2_left_eye_resolves_by_id() -> None:
    document = validate_document(example())
    region = resolve_region(document, "eye_left")
    assert region == ResolvedRegion(
        region_id="eye_left",
        mask_id="eye_left_shape",
        mask_ids=("eye_left_shape",),
        operation_ids=("iris_left",),
        layer_ids=("irises",),
    )
    eyes = resolve_region(document, "eyes_region")
    assert eyes.mask_ids == ("eye_left_shape", "eye_right_shape", "eyes", "lid", "eyes_open")
    assert eyes.layer_ids == ("whites", "irises")


def test_ac2_region_resolution_does_not_depend_on_array_order() -> None:
    tree = example()
    tree["masks"].reverse()
    tree["regions"].reverse()
    region = resolve_region(validate_document(tree), "eye_left")
    assert (region.mask_id, region.operation_ids) == ("eye_left_shape", ("iris_left",))


def test_ac2_unknown_region_or_mask_is_a_reference_error() -> None:
    document = validate_document(example())
    for bad in ("eye_middle", 3):
        with pytest.raises(errors.ReferenceError) as raised:
            resolve_region(document, bad)  # type: ignore[arg-type]
        assert raised.value.context["reason"] == "unknown_region"
    for missing in ("ghost", None):
        with pytest.raises(errors.ReferenceError) as raised:
            mask_dependencies(document, missing)  # type: ignore[arg-type]
        assert raised.value.context["reason"] == "unknown_mask"
    with pytest.raises(TypeError):
        resolve_region(example(), "eye_left")  # type: ignore[arg-type]


def test_region_without_operations(minimal: dict[str, Any]) -> None:
    minimal["masks"] = [rect("zone_mask")]
    minimal["regions"] = [{"id": "zone", "mask_id": "zone_mask"}]
    region = resolve_region(validate_document(minimal), "zone")
    assert (region.operation_ids, region.layer_ids) == ((), ())


def test_models_built_directly_skip_reference_checks(minimal: dict[str, Any]) -> None:
    minimal["masks"] = [rect("a"), combo("loop", "union", "a", "loop")]
    document = Document.model_validate(minimal)  # structure only
    assert isinstance(document.masks[1], UnionMask)
    with pytest.raises(errors.ReferenceError):
        validate_document(minimal)


def _unvalidated(minimal: dict[str, Any], masks: list[dict[str, Any]]) -> Document:
    """A model built without reference checks: ``region`` targets ``a``."""
    minimal["masks"] = masks
    minimal["regions"] = [{"id": "region", "mask_id": "a"}]
    return Document.model_validate(minimal)


CYCLE = [combo("a", "union", "b", "leaf"), combo("b", "xor", "a", "leaf"), rect("leaf")]
BROKEN = [combo("a", "union", "leaf", "ghost"), rect("leaf")]


@pytest.mark.parametrize(("masks", "reason"), [(CYCLE, "mask_cycle"), (BROKEN, "unknown_mask")])
def test_unvalidated_cycles_and_broken_references_fail_fast(
    minimal: dict[str, Any], masks: list[dict[str, Any]], reason: str
) -> None:
    document = _unvalidated(minimal, masks)
    with pytest.raises(errors.ReferenceError) as raised:
        mask_dependencies(document, "a")
    assert raised.value.context["reason"] == reason
    with pytest.raises(errors.ReferenceError) as raised:
        resolve_region(document, "region")
    assert raised.value.context["reason"] == reason


def test_unvalidated_region_with_a_missing_operation(minimal: dict[str, Any]) -> None:
    document = _unvalidated(minimal, [rect("a")])
    broken = document.model_copy(
        update={"regions": (document.regions[0].model_copy(update={"operation_ids": ("x",)}),)}
    )
    with pytest.raises(errors.ReferenceError) as raised:
        resolve_region(broken, "region")
    assert raised.value.context["reason"] == "unknown_operation"


def test_shared_operands_are_not_cycles(minimal: dict[str, Any]) -> None:
    masks = [
        combo("a", "union", "b", "c"),
        combo("b", "union", "c", "leaf"),
        combo("c", "xor", "leaf", "other"),
        rect("leaf"),
        rect("other"),
    ]
    document = _unvalidated(minimal, masks)
    assert mask_dependencies(document, "a") == ("leaf", "other", "c", "b", "a")
