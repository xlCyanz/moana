"""Typed commands applied without a new revision (MOANA-022 T2; ADR-032).

``apply_commands`` is the editor entry point used to evaluate animation frames: the
same command rules as ``apply_batch``, no precondition, unchanged revision. Expected
trees are edits of the literal ``TREE`` below.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from typing import Any

import pytest

from moana.core import errors
from moana.core.limits import MAX_EDIT_COMMANDS
from moana.editing import (
    InsertOperation,
    Remove,
    Reorder,
    ReplacePaletteColor,
    SetColor,
    SetGeometry,
    SetParameters,
    SetVisibility,
    Translate,
    apply_commands,
)
from moana.schema import canonical_json, validate_document
from moana.schema.models import MAX_REVISION

TREE: dict[str, Any] = {
    "schema_version": "1.0",
    "id": "doc",
    "revision": MAX_REVISION,
    "canvas": {"width": 4, "height": 4},
    "palette": {
        "id": "pal",
        "colors": [{"id": "red", "rgba": "#FF0000FF"}, {"id": "blue", "rgba": "#0000FFFF"}],
    },
    "layers": [
        {
            "id": "body",
            "name": "Body",
            "operations": [{"id": "dot", "type": "pixel", "color": "red", "at": [1, 1]}],
        }
    ],
}


def test_t2_commands_apply_in_order_and_keep_the_revision() -> None:
    document = validate_document(TREE)
    commands = (
        Translate(type="translate", target_id="dot", dx=1, dy=2),
        SetColor(type="set_color", target_id="dot", color="blue"),
        SetVisibility(type="set_visibility", target_id="body", visible=False),
    )
    result = apply_commands(document, commands, pointer="/x")
    expected = copy.deepcopy(TREE)
    expected["layers"][0]["operations"][0].update(at=[2, 3], color="blue")
    expected["layers"][0]["visible"] = False
    tree = json.loads(canonical_json(result))
    assert tree == json.loads(canonical_json(validate_document(expected)))
    assert result.revision == MAX_REVISION  # no revision_overflow: none is created
    assert canonical_json(document) == canonical_json(validate_document(TREE))
    assert apply_commands(document, (), pointer="/x") == document


def test_t2_errors_are_located_under_the_caller_pointer() -> None:
    document = validate_document(TREE)
    commands = (
        SetColor(type="set_color", target_id="dot", color="blue"),
        Translate(type="translate", target_id="body", dx=1, dy=0),
    )
    with pytest.raises(errors.ValidationError) as raised:
        apply_commands(document, commands, pointer="/animations/0/frames/2/overrides")
    assert raised.value.json_pointer == "/animations/0/frames/2/overrides/1/target_id"
    assert raised.value.context["reason"] == "invalid_target"
    with pytest.raises(errors.ReferenceError) as missing:
        apply_commands(
            document, (SetColor(type="set_color", target_id="ghost", color="blue"),), pointer="/p"
        )
    assert missing.value.json_pointer == "/p/0/target_id"
    assert missing.value.context["reason"] == "unknown_target"


@pytest.mark.parametrize(
    "command",
    [
        Remove(type="remove", target_id="dot"),
        Reorder(type="reorder", target_id="dot", after_id=None),
        ReplacePaletteColor(type="replace_palette_color", target_id="red", rgba="#00FF00FF"),
        InsertOperation(
            type="insert_operation",
            layer_id="body",
            after_id=None,
            operation={"id": "new", "type": "pixel", "color": "red", "at": [0, 0]},
        ),
        SetGeometry(type="set_geometry", target_id="dot", geometry={"at": [0, 0]}),
        SetParameters(type="set_parameters", target_id="dot", parameters={}),
    ],
)
def test_t2_only_override_commands_are_accepted(command: object) -> None:
    # A structural edit must never yield another document under the same revision.
    document = validate_document(TREE)
    visible = SetVisibility(type="set_visibility", target_id="body", visible=True)
    with pytest.raises(TypeError, match="SetVisibility, Translate or SetColor"):
        apply_commands(document, (visible, command), pointer="/p")  # type: ignore[arg-type]


def test_t2_argument_checks() -> None:
    document = validate_document(TREE)
    visible = SetVisibility(type="set_visibility", target_id="body", visible=True)
    with pytest.raises(errors.ValidationError) as raised:
        apply_commands(document, (visible,) * (MAX_EDIT_COMMANDS + 1), pointer="/p")
    assert dict(raised.value.context) == {"reason": "too_many", "maximum": MAX_EDIT_COMMANDS}
    assert len(apply_commands(document, (visible,) * MAX_EDIT_COMMANDS, pointer="/p").layers) == 1
    calls: list[Callable[[], object]] = [
        lambda: apply_commands(TREE, (), pointer="/p"),  # type: ignore[arg-type]
        lambda: apply_commands(document, (), pointer="/p", limits=None),  # type: ignore[arg-type]
        lambda: apply_commands(document, (), pointer="p"),
        lambda: apply_commands(document, (), pointer=1),  # type: ignore[arg-type]
        lambda: apply_commands(document, "ab", pointer="/p"),  # type: ignore[arg-type]
        lambda: apply_commands(document, 5, pointer="/p"),  # type: ignore[arg-type]
        lambda: apply_commands(document, ({"type": "remove"},), pointer="/p"),  # type: ignore[arg-type]
    ]
    for call in calls:
        with pytest.raises(TypeError):
            call()
