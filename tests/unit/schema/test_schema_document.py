"""Document validation: T1 table of valid/invalid inputs, mapping/bytes equivalence, AC1/AC2.

Each invalid case states the expected (code, pointer, reason) independently of the
implementation, from MOANA.md sections 9, 11, 12 and 20.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pytest

from moana.core import errors
from moana.core.coordinates import Box, Point
from moana.schema import (
    PLANNED_OPERATION_TYPES,
    SUPPORTED_OPERATION_TYPES,
    Document,
    ParseLimits,
    PixelOperation,
    RectOperation,
    canonical_json,
    normalize_document,
    snapshot_digest,
    validate_document,
)
from moana.schema.document import _semantic_details

Mutation = Callable[[dict[str, Any]], None]

# Contract value published in examples/specs/recolor.edit.json (ADR-007).
MINIMAL_SNAPSHOT = "sha256:f2faa0b919ff3daa701d8e87962415881fa9085f9e28f15f9388da6ffe4e4059"


def op(document: dict[str, Any], index: int = 0) -> dict[str, Any]:
    operation: dict[str, Any] = document["layers"][0]["operations"][index]
    return operation


def add_op(**fields: Any) -> Mutation:
    def mutate(document: dict[str, Any]) -> None:
        document["layers"][0]["operations"].append({"id": "extra", "color": "ink", **fields})

    return mutate


def setter(path: tuple[str | int, ...], value: Any) -> Mutation:
    def mutate(document: dict[str, Any]) -> None:
        target: Any = document
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value

    return mutate


def deleter(path: tuple[str | int, ...]) -> Mutation:
    def mutate(document: dict[str, Any]) -> None:
        target: Any = document
        for key in path[:-1]:
            target = target[key]
        del target[path[-1]]

    return mutate


def both(*mutations: Mutation) -> Mutation:
    def mutate(document: dict[str, Any]) -> None:
        for mutation in mutations:
            mutation(document)

    return mutate


VALID: dict[str, Mutation] = {
    "minimal": lambda document: None,
    "defaults_omitted": both(
        deleter(("seed",)),
        deleter(("revision",)),
        deleter(("canvas", "profile")),
        *(deleter(("layers", 0, key)) for key in ("visible", "locked", "opacity", "blend")),
    ),
    "all_primitives": both(
        setter(("masks",), [{"id": "area", "type": "rect", "box": [0, 0, 4, 4]}]),
        setter(
            ("layers", 0, "operations"),
            [
                {"id": "p", "type": "pixel", "at": [-1_048_576, 1_048_576], "color": "ink"},
                {"id": "l", "type": "line", "start": [0, 0], "end": [5, 9], "color": "ink"},
                {"id": "r", "type": "rect", "box": [0, 0, 1_048_577, 1], "color": "ink"},
                {"id": "e", "type": "ellipse", "box": [-3, -3, 3, 3], "color": "cloth"},
                {"id": "g", "type": "polygon", "points": [[0, 0], [4, 0], [0, 4]], "color": "ink"},
                {
                    "id": "v",
                    "type": "path",
                    "backend": "aggdraw-v1",
                    "commands": [["M", 0, 0], ["L", 1024, 0], ["Q", 1024, 1024, 0, 1024], ["Z"]],
                    "color": "ink",
                },
                {
                    "id": "d",
                    "type": "dither",
                    "size": 4,
                    "coverage": 16,
                    "origin": [-1_048_576, 1_048_576],
                    "color_a": "ink",
                    "color_b": "cloth",
                    "mask_id": "area",
                },
                {
                    "id": "o",
                    "type": "outline",
                    "mask_id": "area",
                    "width": 16,
                    "side": "inner",
                    "color": "ink",
                },
                {
                    "id": "s",
                    "type": "shade",
                    "ramp": "tones",
                    "ramp_order": "stylized",
                    "light": {"direction": "front", "height": 3, "intensity": 4095, "ambient": 0},
                    "bands": [
                        {"id": "s_band", "mask_id": "area", "facing": "none", "offset": -4095}
                    ],
                },
                {
                    "id": "m",
                    "type": "material",
                    "preset": "stone",
                    "version": 1,
                    "ramp": "tones",
                    "ramp_order": "monotonic",
                    "light": {"direction": "nw", "height": 0, "intensity": 0, "ambient": 4095},
                    "density": 32,
                    "scale": 4,
                    "origin": [-2048, 2048],
                    "bands": [{"id": "m_band", "mask_id": "area", "facing": "nw", "offset": 4095}],
                },
                {
                    "id": "so",
                    "type": "selective_outline",
                    "mask_id": "area",
                    "width": 1,
                    "side": "outer",
                    "color": "ink",
                    "ramp": "tones",
                    "ramp_order": "stylized",
                    "light": {"direction": "s", "height": 2, "intensity": 1, "ambient": 1},
                    "segments": [{"id": "so_seg", "mask_id": "area", "facing": "s", "offset": 0}],
                },
            ],
        ),
        setter(("palette", "ramps"), [{"id": "tones", "colors": ["ink", "cloth"]}]),
    ),
    "rgba_profile_partial_alpha": both(
        setter(("canvas", "profile"), "rgba"),
        setter(("palette", "colors", 0, "rgba"), "#18233880"),
        setter(("layers", 0, "opacity"), 10),
    ),
    "ramp_and_metadata": both(
        setter(("palette", "ramps"), [{"id": "skin", "colors": ["ink", "cloth"]}]),
        setter(("metadata",), {"title": "Demo", "tags": ["a", "ñ" * 2048]}),
    ),
    "empty_layers_and_future_collections": both(
        setter(("layers",), []),
        *(setter((name,), []) for name in ("masks", "regions", "materials", "animations")),
    ),
    "extreme_canvas": setter(("canvas",), {"width": 2048, "height": 2048}),
    "max_seed": setter(("seed",), 2**64 - 1),
}

INVALID: dict[str, tuple[Mutation, str, str, str]] = {
    # AC2: duplicated IDs, unknown colors, bool as integer, extra members.
    "duplicate_operation_id": (
        add_op(type="pixel", at=[0, 0], id="body_fill"),
        "VALIDATION_ERROR",
        "/layers/0/operations/1/id",
        "duplicate_id",
    ),
    "id_shared_by_color_and_layer": (
        setter(("layers", 0, "id"), "ink"),
        "VALIDATION_ERROR",
        "/layers/0/id",
        "duplicate_id",
    ),
    "unknown_color": (
        setter(("layers", 0, "operations", 0, "color"), "missing"),
        "REFERENCE_ERROR",
        "/layers/0/operations/0/color",
        "unknown_color",
    ),
    "layer_id_used_as_color": (
        setter(("layers", 0, "operations", 0, "color"), "body"),
        "REFERENCE_ERROR",
        "/layers/0/operations/0/color",
        "unknown_color",
    ),
    "unknown_ramp_color": (
        setter(("palette", "ramps"), [{"id": "r", "colors": ["ink", "nope"]}]),
        "REFERENCE_ERROR",
        "/palette/ramps/0/colors/1",
        "unknown_color",
    ),
    "bool_as_integer": (
        setter(("canvas", "width"), True),
        "VALIDATION_ERROR",
        "/canvas/width",
        "int_type",
    ),
    "bool_in_box": (
        setter(("layers", 0, "operations", 0, "box", 2), False),
        "VALIDATION_ERROR",
        "/layers/0/operations/0/box/2",
        "int_type",
    ),
    "extra_root_member": (
        setter(("assets",), []),
        "VALIDATION_ERROR",
        "/assets",
        "extra_forbidden",
    ),
    "extra_operation_member": (
        setter(("layers", 0, "operations", 0, "antialias"), True),
        "VALIDATION_ERROR",
        "/layers/0/operations/0/antialias",
        "extra_forbidden",
    ),
    # Other structural rules.
    "float_as_integer": (
        setter(("seed",), 1.0),
        "VALIDATION_ERROR",
        "/seed",
        "int_type",
    ),
    "numeric_string": (
        setter(("revision",), "1"),
        "VALIDATION_ERROR",
        "/revision",
        "int_type",
    ),
    "negative_revision": (
        setter(("revision",), -1),
        "VALIDATION_ERROR",
        "/revision",
        "greater_than_equal",
    ),
    "seed_over_64_bits": (
        setter(("seed",), 2**64),
        "VALIDATION_ERROR",
        "/seed",
        "less_than_equal",
    ),
    "missing_canvas": (deleter(("canvas",)), "VALIDATION_ERROR", "/canvas", "missing"),
    "canvas_too_wide": (
        setter(("canvas", "width"), 2049),
        "VALIDATION_ERROR",
        "/canvas/width",
        "less_than_equal",
    ),
    "unknown_profile": (
        setter(("canvas", "profile"), "indexed"),
        "VALIDATION_ERROR",
        "/canvas/profile",
        "literal_error",
    ),
    "bad_id_pattern": (
        setter(("id",), "Sprite"),
        "VALIDATION_ERROR",
        "/id",
        "string_pattern_mismatch",
    ),
    "id_too_long": (
        setter(("id",), "a" * 65),
        "VALIDATION_ERROR",
        "/id",
        "string_pattern_mismatch",
    ),
    "rgb_without_alpha": (
        setter(("palette", "colors", 0, "rgba"), "#182338"),
        "VALIDATION_ERROR",
        "/palette/colors/0/rgba",
        "string_pattern_mismatch",
    ),
    "empty_palette": (
        setter(("palette", "colors"), []),
        "VALIDATION_ERROR",
        "/palette/colors",
        "too_short",
    ),
    "inverted_box": (
        setter(("layers", 0, "operations", 0, "box"), [88, 32, 40, 104]),
        "VALIDATION_ERROR",
        "/layers/0/operations/0/box",
        "box_empty_or_inverted",
    ),
    "empty_box": (
        setter(("layers", 0, "operations", 0, "box"), [5, 5, 5, 9]),
        "VALIDATION_ERROR",
        "/layers/0/operations/0/box",
        "box_empty_or_inverted",
    ),
    "box_wrong_arity": (
        setter(("layers", 0, "operations", 0, "box"), [0, 0, 1]),
        "VALIDATION_ERROR",
        "/layers/0/operations/0/box/3",
        "missing",
    ),
    "coordinate_out_of_range": (
        add_op(type="pixel", at=[1_048_577, 0]),
        "VALIDATION_ERROR",
        "/layers/0/operations/1/at/0",
        "less_than_equal",
    ),
    "polygon_two_points": (
        add_op(type="polygon", points=[[0, 0], [1, 1]]),
        "VALIDATION_ERROR",
        "/layers/0/operations/1/points",
        "too_short",
    ),
    "polygon_too_many_vertices": (
        add_op(type="polygon", points=[[0, 0]] * 4097),
        "VALIDATION_ERROR",
        "/layers/0/operations/1/points",
        "too_long",
    ),
    "unknown_operation_type": (
        add_op(type="spray"),
        "VALIDATION_ERROR",
        "/layers/0/operations/1/type",
        "union_tag_invalid",
    ),
    "operation_without_type": (
        add_op(),
        "VALIDATION_ERROR",
        "/layers/0/operations/1",
        "union_tag_not_found",
    ),
    "null_metadata": (
        setter(("metadata",), None),
        "VALIDATION_ERROR",
        "/metadata",
        "null_not_allowed",
    ),
    "null_title": (
        setter(("metadata",), {"title": None}),
        "VALIDATION_ERROR",
        "/metadata/title",
        "null_not_allowed",
    ),
    "metadata_unknown_member": (
        setter(("metadata",), {"license": "x"}),
        "VALIDATION_ERROR",
        "/metadata/license",
        "extra_forbidden",
    ),
    "metadata_string_over_4096_bytes": (
        setter(("metadata",), {"title": "ñ" * 2049}),
        "VALIDATION_ERROR",
        "/metadata/title",
        "string_too_many_bytes",
    ),
    "too_many_tags": (
        setter(("metadata",), {"tags": ["t"] * 33}),
        "VALIDATION_ERROR",
        "/metadata/tags",
        "too_long",
    ),
    "too_many_layers": (
        setter(
            ("layers",),
            [{"id": f"l{i}", "name": "L", "operations": []} for i in range(129)],
        ),
        "VALIDATION_ERROR",
        "/layers",
        "too_long",
    ),
    "ramp_repeats_color": (
        setter(("palette", "ramps"), [{"id": "r", "colors": ["ink", "ink"]}]),
        "VALIDATION_ERROR",
        "/palette/ramps/0/colors/1",
        "duplicate_ramp_color",
    ),
    # Strict profile (MOANA.md section 9).
    "strict_partial_alpha": (
        setter(("palette", "colors", 1, "rgba"), "#36AFA580"),
        "VALIDATION_ERROR",
        "/palette/colors/1/rgba",
        "partial_alpha",
    ),
    "strict_partial_opacity": (
        setter(("layers", 0, "opacity"), 254),
        "VALIDATION_ERROR",
        "/layers/0/opacity",
        "partial_opacity",
    ),
    "strict_too_many_colors": (
        setter(
            ("palette", "colors"),
            [{"id": f"c{i}", "rgba": "#000000FF"} for i in range(257)]
            + [{"id": "cloth", "rgba": "#36AFA5FF"}],
        ),
        "VALIDATION_ERROR",
        "/palette/colors",
        "too_many",
    ),
    # Planned capabilities: recognised, never ignored (MOANA.md section 12).
    "planned_flood_fill": (
        add_op(type="flood_fill", at=[0, 0]),
        "UNSUPPORTED_OPERATION",
        "/layers/0/operations/1/type",
        "planned_capability",
    ),
    "planned_blend": (
        setter(("layers", 0, "blend"), "multiply"),
        "UNSUPPORTED_OPERATION",
        "/layers/0/blend",
        "planned_capability",
    ),
    "planned_materials": (
        setter(("materials",), [{"id": "m"}]),
        "UNSUPPORTED_OPERATION",
        "/materials",
        "planned_capability",
    ),
    "planned_group_children": (
        setter(("layers", 0, "children"), []),
        "UNSUPPORTED_OPERATION",
        "/layers/0/children",
        "planned_capability",
    ),
    "planned_group_transform": (
        setter(("layers", 0, "transform"), {}),
        "UNSUPPORTED_OPERATION",
        "/layers/0/transform",
        "planned_capability",
    ),
}

ERROR_TYPES = {
    "VALIDATION_ERROR": errors.ValidationError,
    "REFERENCE_ERROR": errors.ReferenceError,
    "UNSUPPORTED_OPERATION": errors.UnsupportedOperation,
}


def build(minimal: dict[str, Any], mutation: Mutation) -> dict[str, Any]:
    mutation(minimal)
    return minimal


def as_bytes(document: dict[str, Any]) -> bytes:
    return json.dumps(document, ensure_ascii=False).encode("utf-8")


@pytest.mark.parametrize("name", sorted(VALID))
def test_valid_table_accepts_bytes_and_mapping_identically(
    name: str, minimal: dict[str, Any]
) -> None:
    document = build(minimal, VALID[name])
    from_mapping = validate_document(document)
    from_bytes = validate_document(as_bytes(document))
    assert from_mapping == from_bytes
    assert canonical_json(from_mapping) == canonical_json(from_bytes)


@pytest.mark.parametrize("name", sorted(INVALID))
def test_invalid_table_reports_code_pointer_and_reason(name: str, minimal: dict[str, Any]) -> None:
    mutation, code, pointer, reason = INVALID[name]
    document = build(minimal, mutation)
    outcomes = []
    for source in (document, as_bytes(document)):
        with pytest.raises(errors.MoanaError) as raised:
            validate_document(source)
        error = raised.value
        assert type(error) is ERROR_TYPES[code]
        assert error.code == code
        matching = [d for d in error.details if (d.code, d.json_pointer) == (code, pointer)]
        assert [d.context["reason"] for d in matching] == [reason], error.details
        assert error.json_pointer == error.details[0].json_pointer
        assert error.context["issue_count"] == len(error.details)
        outcomes.append(error.details)
    assert outcomes[0] == outcomes[1]  # mapping/bytes equivalence of errors


def test_all_primitives_case_really_covers_every_supported_type(minimal: dict[str, Any]) -> None:
    document = validate_document(build(minimal, VALID["all_primitives"]))
    types = {operation.type for operation in document.layers[0].operations}
    assert types == SUPPORTED_OPERATION_TYPES
    assert not types & PLANNED_OPERATION_TYPES


def test_minimal_example_normalises_to_published_snapshot(minimal: dict[str, Any]) -> None:
    """AC1: normalisation is idempotent and matches the contract digest of ADR-007."""
    document = validate_document(minimal)
    normalized = normalize_document(document)
    assert snapshot_digest(document) == MINIMAL_SNAPSHOT
    again = validate_document(normalized)
    assert again == document
    assert normalize_document(again) == normalized
    assert canonical_json(again) == canonical_json(document)


def test_normalisation_materialises_section_12_defaults(minimal: dict[str, Any]) -> None:
    document = validate_document(build(minimal, VALID["defaults_omitted"]))
    normalized = normalize_document(document)
    assert (normalized["seed"], normalized["revision"]) == (0, 0)
    assert normalized["canvas"] == {"width": 128, "height": 128, "profile": "strict"}
    layer = normalized["layers"][0]  # type: ignore[index]
    assert {key: layer[key] for key in ("visible", "locked", "opacity", "blend")} == {
        "visible": True,
        "locked": False,
        "opacity": 255,
        "blend": "normal",
    }
    for name in ("masks", "regions", "materials", "animations"):
        assert normalized[name] == []
    assert "metadata" not in normalized


def test_canonical_json_is_compact_sorted_utf8(minimal: dict[str, Any]) -> None:
    minimal["layers"][0]["name"] = "Cuerpo ñ"
    minimal["palette"]["colors"][0]["rgba"] = "#18233aff"
    document = validate_document(minimal)
    encoded = canonical_json(document)
    assert b" " not in encoded.replace("Cuerpo ñ".encode(), b"")
    assert "Cuerpo ñ".encode() in encoded
    assert b"#18233AFF" in encoded
    assert encoded.startswith(b'{"animations":[],"canvas":{"height":128,')
    empties: tuple[dict[str, object], ...] = ({}, {"tags": []})
    for empty in empties:
        same = validate_document({**minimal, "metadata": empty})
        assert same.metadata is None
        assert canonical_json(same) == encoded
    tagged = validate_document({**minimal, "metadata": {"title": "t"}})
    assert normalize_document(tagged)["metadata"] == {"title": "t", "tags": []}


def test_models_are_frozen_and_expose_core_values(minimal: dict[str, Any]) -> None:
    minimal["layers"][0]["operations"].append(
        {"id": "dot", "type": "pixel", "at": [3, 4], "color": "ink"}
    )
    document = validate_document(minimal)
    rect, pixel = document.layers[0].operations
    assert isinstance(rect, RectOperation) and isinstance(pixel, PixelOperation)
    assert rect.bbox == Box(40, 32, 88, 104)
    assert pixel.point == Point(3, 4)
    assert document.canvas.dimensions.area == 128 * 128
    assert isinstance(document.layers, tuple) and isinstance(rect.box, tuple)
    with pytest.raises(Exception, match="frozen"):
        document.seed = 1


def test_unsupported_version_is_its_own_phase(minimal: dict[str, Any]) -> None:
    minimal["schema_version"] = "2.0"
    minimal["unknown"] = True  # not reported: the 2.0 grammar is unknown
    with pytest.raises(errors.UnsupportedVersion) as raised:
        validate_document(minimal)
    assert raised.value.json_pointer == "/schema_version"
    assert raised.value.context["supported"] == ("1.0",)
    minimal["schema_version"] = 1
    with pytest.raises(errors.ValidationError):
        validate_document(minimal)


def test_errors_are_sorted_by_pointer_with_numeric_indexes(minimal: dict[str, Any]) -> None:
    operations = [
        {"id": f"o{i}", "type": "pixel", "at": [0, 0], "color": "nope"} for i in range(11)
    ]
    minimal["layers"][0]["operations"] = operations
    minimal["palette"]["ramps"] = [{"id": "r", "colors": ["ink", "nope"]}]
    with pytest.raises(errors.ReferenceError) as raised:
        validate_document(minimal)
    pointers = [detail.json_pointer for detail in raised.value.details]
    assert pointers == [
        *(f"/layers/0/operations/{i}/color" for i in range(11)),
        "/palette/ramps/0/colors/1",
    ]


def test_validation_outranks_references_in_one_phase(minimal: dict[str, Any]) -> None:
    minimal["layers"][0]["operations"].append(
        {"id": "body_fill", "type": "pixel", "at": [0, 0], "color": "nope"}
    )
    with pytest.raises(errors.ValidationError) as raised:
        validate_document(minimal)
    assert [d.code for d in raised.value.details] == ["REFERENCE_ERROR", "VALIDATION_ERROR"]


def test_unsupported_capability_alone_raises_unsupported_operation(
    minimal: dict[str, Any],
) -> None:
    # ``animations`` has a 1.0 grammar since ADR-032; ``materials`` is still planned.
    minimal["materials"] = [{"id": "skin"}]
    with pytest.raises(errors.UnsupportedOperation) as raised:
        validate_document(minimal)
    capabilities = [d.context["capability"] for d in raised.value.details]
    assert capabilities == ["materials"]


def test_error_messages_do_not_echo_untrusted_strings(minimal: dict[str, Any]) -> None:
    secret = "zz_secret_token_value"
    minimal["layers"][0]["operations"][0]["type"] = secret
    minimal["id"] = secret.upper()
    minimal[secret] = 1
    with pytest.raises(errors.ValidationError) as raised:
        validate_document(minimal)
    for detail in raised.value.details:
        rendered = (detail.message, repr(dict(detail.context)))
        assert secret not in repr(rendered) and secret.upper() not in repr(rendered)


def test_operation_count_is_limited_across_layers(minimal: dict[str, Any]) -> None:
    def layer(index: int, count: int) -> dict[str, Any]:
        operations = [
            {"id": f"o{index}x{i}", "type": "pixel", "at": [0, 0], "color": "ink"}
            for i in range(count)
        ]
        return {"id": f"layer{index}", "name": "L", "operations": operations}

    minimal["layers"] = [layer(0, 5000), layer(1, 5001)]
    limits = ParseLimits()
    with pytest.raises(errors.ValidationError) as raised:
        validate_document(minimal, limits=limits)  # 20 000 nodes is not enough
    assert raised.value.context["reason"] == "too_many_nodes"
    # The operation limit is a model contract checked after structure; exercise it
    # directly on a document built from validated parts.
    document = Document.model_validate({**minimal, "layers": [layer(0, 5000), layer(1, 5001)]})
    reasons = [d.context["reason"] for d in _semantic_details(document)]
    assert reasons == ["too_many"]


def test_str_source_is_rejected(minimal: dict[str, Any]) -> None:
    with pytest.raises(errors.ValidationError) as raised:
        validate_document(json.dumps(minimal))  # type: ignore[arg-type]  # runtime guard
    assert raised.value.context["reason"] == "root_not_object"
