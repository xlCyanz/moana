"""The editor knows animation frames (MOANA-022 T2; ADR-032).

Override targets and ``set_color`` colours are live references; animation and frame
IDs are taken. Expected pointers and reasons follow ADR-024 and ADR-032.
"""

from __future__ import annotations

from typing import Any

import pytest

from moanart.core import errors
from moanart.editing import apply_batch
from moanart.schema import Document, snapshot_digest, validate_document

TREE: dict[str, Any] = {
    "schema_version": "1.0",
    "id": "doc",
    "canvas": {"width": 4, "height": 4},
    "palette": {
        "id": "pal",
        "colors": [
            {"id": "red", "rgba": "#FF0000FF"},
            {"id": "blue", "rgba": "#0000FFFF"},
            {"id": "spare", "rgba": "#00FF00FF"},
        ],
    },
    "masks": [{"id": "hole", "type": "rect", "box": [0, 0, 2, 2]}],
    "layers": [
        {
            "id": "body",
            "name": "Body",
            "operations": [
                {"id": "dot", "type": "pixel", "color": "red", "at": [1, 1]},
                {"id": "still", "type": "pixel", "color": "red", "at": [2, 2]},
            ],
        },
        {"id": "aside", "name": "Aside", "operations": []},
    ],
    "animations": [
        {
            "id": "walk",
            "loop_count": 0,
            "pivot": [0, 0],
            "frames": [
                {
                    "id": "step",
                    "duration_ms": 10,
                    "overrides": [
                        {"type": "translate", "target_id": "dot", "dx": 1, "dy": 0},
                        {"type": "set_color", "target_id": "still", "color": "blue"},
                        {"type": "translate", "target_id": "hole", "dx": 1, "dy": 0},
                    ],
                }
            ],
        }
    ],
}
OVERRIDES = "/animations/0/frames/0/overrides"


def edit(document: Document, *commands: dict[str, Any]) -> Document:
    batch = {
        "schema_version": "1.0",
        "base_revision": document.revision,
        "base_snapshot": snapshot_digest(document),
        "commands": list(commands),
    }
    return apply_batch(document, batch).document


@pytest.mark.parametrize(
    ("target_id", "references"),
    [
        ("dot", [f"{OVERRIDES}/0/target_id"]),
        ("hole", [f"{OVERRIDES}/2/target_id"]),
        ("blue", [f"{OVERRIDES}/1/color"]),  # a colour used only by set_color
        ("body", [f"{OVERRIDES}/0/target_id", f"{OVERRIDES}/1/target_id"]),
    ],
)
def test_t2_removing_an_animated_node_or_colour_is_a_live_reference(
    target_id: str, references: list[str]
) -> None:
    document = validate_document(TREE)
    with pytest.raises(errors.ReferenceError) as raised:
        edit(document, {"type": "remove", "target_id": target_id})
    assert raised.value.context["reason"] == "live_reference"
    assert raised.value.json_pointer == "/commands/0/target_id"
    assert [d.json_pointer for d in raised.value.details] == references
    assert {d.context["reason"] for d in raised.value.details} == {"live_reference"}


def test_t2_unanimated_nodes_and_colours_stay_removable() -> None:
    document = validate_document(TREE)
    edited = edit(
        document,
        {"type": "remove", "target_id": "aside"},
        {"type": "remove", "target_id": "spare"},
    )
    assert [layer.id for layer in edited.layers] == ["body"]
    assert edited.animations == document.animations


@pytest.mark.parametrize("new_id", ["walk", "step"])
def test_t2_new_ids_cannot_reuse_animation_or_frame_ids(new_id: str) -> None:
    document = validate_document(TREE)
    operation = {"id": new_id, "type": "pixel", "color": "red", "at": [0, 0]}
    with pytest.raises(errors.ValidationError) as raised:
        edit(
            document,
            {
                "type": "insert_operation",
                "layer_id": "aside",
                "after_id": None,
                "operation": operation,
            },
        )
    assert raised.value.json_pointer == "/commands/0/operation/id"
    assert raised.value.context["reason"] == "duplicate_id"


@pytest.mark.parametrize("target_id", ["walk", "step"])
def test_t2_no_command_targets_an_animation_or_frame(target_id: str) -> None:
    document = validate_document(TREE)
    for command in (
        {"type": "remove", "target_id": target_id},
        {"type": "set_visibility", "target_id": target_id, "visible": False},
    ):
        with pytest.raises(errors.ValidationError) as raised:
            edit(document, command)
        assert raised.value.context["reason"] == "invalid_target"


def test_t2_editing_an_animated_document_keeps_its_timeline() -> None:
    document = validate_document(TREE)
    edited = edit(document, {"type": "translate", "target_id": "dot", "dx": 1, "dy": 1})
    assert edited.revision == document.revision + 1
    assert edited.animations == document.animations
