"""Schema 1.0 grammar of ``animations`` (MOANA-022 T1, T2; ADR-032).

Every tree below is written by hand; expected pointers, reasons and limits come from
MOANART.md section 17 and ADR-032, never from the validator's own output.
"""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest

from moanart.core import errors
from moanart.core.coordinates import MAX_COORDINATE, Point
from moanart.core.limits import (
    MAX_ANIMATION_DURATION_MS,
    MAX_ANIMATION_FRAMES,
    MAX_ANIMATIONS,
    MAX_FRAME_DURATION_MS,
    MAX_FRAME_OVERRIDES,
    MAX_LOOP_COUNT,
    MIN_FRAME_DURATION_MS,
)
from moanart.schema import (
    MAX_OVERRIDE_SHIFT,
    PLANNED_COLLECTIONS,
    SUPPORTED_COLLECTIONS,
    SUPPORTED_OVERRIDE_TYPES,
    SetColorOverride,
    SetVisibilityOverride,
    TranslateOverride,
    canonical_json,
    document_ids,
    document_json_schema,
    normalize_document,
    validate_document,
)

type Tree = dict[str, Any]


def sprite() -> Tree:
    """An 8x8 document with one animation of two frames."""
    return {
        "schema_version": "1.0",
        "id": "doc",
        "canvas": {"width": 8, "height": 8},
        "palette": {
            "id": "pal",
            "colors": [
                {"id": "red", "rgba": "#FF0000FF"},
                {"id": "blue", "rgba": "#0000FFFF"},
            ],
        },
        "layers": [
            {
                "id": "body",
                "name": "Body",
                "operations": [{"id": "r1", "type": "rect", "color": "red", "box": [1, 1, 3, 3]}],
            }
        ],
        "masks": [{"id": "m1", "type": "rect", "box": [0, 0, 4, 4]}],
        "animations": [
            {
                "id": "walk",
                "loop_count": 0,
                "pivot": [4, 8],
                "frames": [
                    {"id": "f0", "duration_ms": 100},
                    {
                        "id": "f1",
                        "duration_ms": 120,
                        "overrides": [
                            {"type": "translate", "target_id": "r1", "dx": 2, "dy": -1},
                            {"type": "set_color", "target_id": "r1", "color": "blue"},
                            {"type": "set_visibility", "target_id": "body", "visible": False},
                            {"type": "translate", "target_id": "m1", "dx": 1, "dy": 0},
                        ],
                    },
                ],
            }
        ],
    }


def frame(index: int, **members: object) -> Tree:
    return {"id": f"f{index}", "duration_ms": 10, **members}


def problems(tree: Tree) -> list[tuple[str | None, str, object]]:
    with pytest.raises(errors.MoanArtError) as raised:
        validate_document(tree)
    return [
        (detail.json_pointer, detail.code, detail.context.get("reason"))
        for detail in raised.value.details
    ]


def test_t2_animation_grammar_is_typed_and_frozen() -> None:
    document = validate_document(sprite())
    (animation,) = document.animations
    assert animation.id == "walk"
    assert animation.loop_count == 0
    assert animation.pivot == (4, 8)
    assert animation.pivot_point == Point(4, 8)
    first, second = animation.frames
    assert (first.id, first.duration_ms, first.overrides) == ("f0", 100, ())
    assert second.overrides == (
        TranslateOverride(type="translate", target_id="r1", dx=2, dy=-1),
        SetColorOverride(type="set_color", target_id="r1", color="blue"),
        SetVisibilityOverride(type="set_visibility", target_id="body", visible=False),
        TranslateOverride(type="translate", target_id="m1", dx=1, dy=0),
    )
    assert {"set_color", "set_visibility", "translate"} == SUPPORTED_OVERRIDE_TYPES
    assert "animations" in SUPPORTED_COLLECTIONS
    assert "animations" not in PLANNED_COLLECTIONS


def test_t2_normalisation_materialises_empty_overrides_and_roundtrips() -> None:
    document = validate_document(sprite())
    tree: Tree = json.loads(json.dumps(normalize_document(document)))
    assert tree["animations"][0]["frames"][0] == {"duration_ms": 100, "id": "f0", "overrides": []}
    again = validate_document(json.loads(canonical_json(document)))
    assert canonical_json(again) == canonical_json(document)


def test_t2_animation_and_frame_ids_are_global() -> None:
    ids = document_ids(validate_document(sprite()))
    assert {"walk", "f0", "f1"} <= ids
    tree = sprite()
    tree["animations"][0]["frames"][1]["id"] = "r1"
    tree["animations"][0]["id"] = "body"
    assert problems(tree) == [
        ("/animations/0/frames/1/id", "VALIDATION_ERROR", "duplicate_id"),
        ("/animations/0/id", "VALIDATION_ERROR", "duplicate_id"),
    ]
    tree = sprite()
    tree["animations"].append(copy.deepcopy(tree["animations"][0]))
    tree["animations"][1]["id"] = "run"
    assert problems(tree) == [
        ("/animations/1/frames/0/id", "VALIDATION_ERROR", "duplicate_id"),
        ("/animations/1/frames/1/id", "VALIDATION_ERROR", "duplicate_id"),
    ]


def test_t2_override_references_must_exist() -> None:
    tree = sprite()
    overrides = tree["animations"][0]["frames"][1]["overrides"]
    overrides[0]["target_id"] = "ghost"
    overrides[1]["color"] = "green"
    overrides[2]["target_id"] = "pal"  # an ID, but not a layer, operation or mask
    assert problems(tree) == [
        ("/animations/0/frames/1/overrides/0/target_id", "REFERENCE_ERROR", "unknown_target"),
        ("/animations/0/frames/1/overrides/1/color", "REFERENCE_ERROR", "unknown_color"),
        ("/animations/0/frames/1/overrides/2/target_id", "REFERENCE_ERROR", "unknown_target"),
    ]


@pytest.mark.parametrize(
    ("pivot", "valid"),
    [
        ([0, 0], True),
        ([8, 8], True),
        ([4, 0], True),
        ([9, 8], False),
        ([8, 9], False),
        ([-1, 0], False),
        ([0, -1], False),
    ],
)
def test_t1_pivot_lies_on_the_canvas_edges_included(pivot: list[int], valid: bool) -> None:
    tree = sprite()
    tree["animations"][0]["pivot"] = pivot
    if valid:
        assert validate_document(tree).animations[0].pivot == tuple(pivot)
    else:
        with pytest.raises(errors.ValidationError) as raised:
            validate_document(tree)
        assert raised.value.json_pointer == "/animations/0/pivot"
        assert dict(raised.value.details[0].context) == {
            "reason": "pivot_out_of_canvas",
            "width": 8,
            "height": 8,
        }


def test_t1_frame_count_is_one_to_256() -> None:
    tree = sprite()
    tree["animations"][0]["frames"] = [frame(0)]
    assert len(validate_document(tree).animations[0].frames) == 1
    tree["animations"][0]["frames"] = [frame(i) for i in range(MAX_ANIMATION_FRAMES)]
    assert len(validate_document(tree).animations[0].frames) == 256
    tree["animations"][0]["frames"].append(frame(MAX_ANIMATION_FRAMES))
    assert problems(tree) == [("/animations/0/frames", "VALIDATION_ERROR", "too_long")]
    tree["animations"][0]["frames"] = []
    assert problems(tree) == [("/animations/0/frames", "VALIDATION_ERROR", "too_short")]


def test_t1_empty_timeline_is_reported_alone_beside_invalid_members() -> None:
    tree = sprite()
    tree["animations"][0]["frames"] = []
    tree["animations"][0]["loop_count"] = -1
    assert problems(tree) == [
        ("/animations/0/frames", "VALIDATION_ERROR", "too_short"),
        ("/animations/0/loop_count", "VALIDATION_ERROR", "greater_than_equal"),
    ]


@pytest.mark.parametrize(
    ("duration", "reason"),
    [
        (MIN_FRAME_DURATION_MS, None),
        (MAX_FRAME_DURATION_MS, None),
        (0, "greater_than_equal"),
        (60_001, "less_than_equal"),
        (True, "int_type"),
        (10.0, "int_type"),
    ],
)
def test_t1_duration_is_a_whole_millisecond_count_1_to_60000(
    duration: object, reason: str | None
) -> None:
    assert (MIN_FRAME_DURATION_MS, MAX_FRAME_DURATION_MS) == (1, 60_000)
    tree = sprite()
    tree["animations"][0]["frames"][0]["duration_ms"] = duration
    if reason is None:
        assert validate_document(tree).animations[0].frames[0].duration_ms == duration
    else:
        expected = [("/animations/0/frames/0/duration_ms", "VALIDATION_ERROR", reason)]
        assert problems(tree) == expected


def test_t1_longest_timeline_is_bounded() -> None:
    assert MAX_ANIMATION_DURATION_MS == 256 * 60_000
    tree = sprite()
    tree["animations"][0]["frames"] = [
        frame(i, duration_ms=MAX_FRAME_DURATION_MS) for i in range(MAX_ANIMATION_FRAMES)
    ]
    animation = validate_document(tree).animations[0]
    assert sum(f.duration_ms for f in animation.frames) == MAX_ANIMATION_DURATION_MS


@pytest.mark.parametrize(
    ("loop_count", "reason"),
    [
        (0, None),
        (1, None),
        (MAX_LOOP_COUNT, None),
        (-1, "greater_than_equal"),
        (65_536, "less_than_equal"),
        (False, "int_type"),
    ],
)
def test_t1_loop_count_zero_is_infinite_playback(loop_count: object, reason: str | None) -> None:
    tree = sprite()
    tree["animations"][0]["loop_count"] = loop_count
    if reason is None:
        assert validate_document(tree).animations[0].loop_count == loop_count
    else:
        assert problems(tree) == [("/animations/0/loop_count", "VALIDATION_ERROR", reason)]


def test_t1_required_members_and_unknown_members() -> None:
    tree = sprite()
    del tree["animations"][0]["pivot"]
    del tree["animations"][0]["loop_count"]
    tree["animations"][0]["frames"][0]["base_revision"] = 0
    assert problems(tree) == [
        ("/animations/0/frames/0/base_revision", "VALIDATION_ERROR", "extra_forbidden"),
        ("/animations/0/loop_count", "VALIDATION_ERROR", "missing"),
        ("/animations/0/pivot", "VALIDATION_ERROR", "missing"),
    ]


def test_t1_animation_and_override_counts_are_bounded() -> None:
    assert (MAX_ANIMATIONS, MAX_FRAME_OVERRIDES) == (64, 1024)
    tree = sprite()
    visibility = {"type": "set_visibility", "target_id": "body", "visible": True}
    tree["animations"][0]["frames"][0]["overrides"] = [visibility] * MAX_FRAME_OVERRIDES
    assert len(validate_document(tree).animations[0].frames[0].overrides) == 1024
    tree["animations"][0]["frames"][0]["overrides"].append(visibility)
    expected = [("/animations/0/frames/0/overrides", "VALIDATION_ERROR", "too_long")]
    assert problems(tree) == expected
    tree = sprite()
    tree["animations"] = [
        {"id": f"a{i}", "loop_count": 0, "pivot": [0, 0], "frames": [frame(i)]}
        for i in range(MAX_ANIMATIONS + 1)
    ]
    assert problems(tree) == [("/animations", "VALIDATION_ERROR", "too_long")]


def test_t2_translate_shift_is_bounded_like_the_edit_command() -> None:
    assert MAX_OVERRIDE_SHIFT == 2 * MAX_COORDINATE + 1
    tree = sprite()
    override = tree["animations"][0]["frames"][1]["overrides"][0]
    override["dx"], override["dy"] = MAX_OVERRIDE_SHIFT, -MAX_OVERRIDE_SHIFT
    assert validate_document(tree).animations[0].frames[1].overrides[0] == TranslateOverride(
        type="translate", target_id="r1", dx=MAX_OVERRIDE_SHIFT, dy=-MAX_OVERRIDE_SHIFT
    )
    override["dx"], override["dy"] = MAX_OVERRIDE_SHIFT + 1, True
    assert problems(tree) == [
        ("/animations/0/frames/1/overrides/0/dx", "VALIDATION_ERROR", "less_than_equal"),
        ("/animations/0/frames/1/overrides/0/dy", "VALIDATION_ERROR", "int_type"),
    ]


def test_t2_override_types_outside_the_mvp_are_rejected_as_validation_errors() -> None:
    tree = sprite()
    overrides = tree["animations"][0]["frames"][1]["overrides"]
    overrides[0] = {"type": "remove", "target_id": "r1"}
    overrides[1] = {"type": "flood_fill", "target_id": "r1"}  # a planned *operation*
    overrides[2] = {"target_id": "body", "visible": False}
    with pytest.raises(errors.ValidationError) as raised:
        validate_document(tree)
    details = raised.value.details
    expected = ("set_color", "set_visibility", "translate")
    assert [(d.json_pointer, d.message, dict(d.context)) for d in details] == [
        (
            "/animations/0/frames/1/overrides/0/type",
            "Override type is not part of schema 1.0",
            {"reason": "union_tag_invalid", "expected": expected},
        ),
        (
            "/animations/0/frames/1/overrides/1/type",
            "Override type is not part of schema 1.0",
            {"reason": "union_tag_invalid", "expected": expected},
        ),
        (
            "/animations/0/frames/1/overrides/2",
            "Override requires a 'type' member",
            {"reason": "union_tag_not_found", "expected": expected},
        ),
    ]


def test_t2_invalid_member_of_an_override_is_located_without_the_tag() -> None:
    tree = sprite()
    tree["animations"][0]["frames"][1]["overrides"][2]["visible"] = "no"
    assert problems(tree) == [
        ("/animations/0/frames/1/overrides/2/visible", "VALIDATION_ERROR", "bool_type")
    ]


def test_t2_json_schema_describes_the_timeline() -> None:
    schema = document_json_schema()
    definitions = schema["$defs"]
    assert isinstance(definitions, dict)
    frame_schema = definitions["Frame"]["properties"]
    assert frame_schema["duration_ms"]["minimum"] == 1
    assert frame_schema["duration_ms"]["maximum"] == 60_000
    animation = definitions["Animation"]["properties"]
    assert animation["frames"]["minItems"] == 1
    assert animation["frames"]["maxItems"] == 256
    assert animation["loop_count"]["maximum"] == 65_535
    assert set(definitions) >= {"SetColorOverride", "SetVisibilityOverride", "TranslateOverride"}
