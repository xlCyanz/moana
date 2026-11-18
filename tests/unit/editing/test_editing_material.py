"""AC1 (MOANA-017): a material is edited without losing IDs or leaving its ramp (ADR-030).

``set_parameters`` replaces whitelisted value members of an operation in place; the
band and segment IDs, the masks and every other member stay. Expected trees are the
source tree with the edited members changed by hand; colours are checked against the
ramp of the palette.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from moana.core import errors
from moana.editing import History, apply_batch
from moana.render import render
from moana.render.budget import mask_estimates
from moana.schema import Document, normalize_document, snapshot_digest, validate_document

type Tree = dict[str, Any]

ROOT = Path(__file__).resolve().parents[3]
EXAMPLES = ["skin", "cloth", "metal", "wood", "stone"]


def example(name: str) -> Document:
    path = ROOT / "examples" / "specs" / f"material-{name}.moana.json"
    return validate_document(json.loads(path.read_text(encoding="utf-8")))


def batch(base: Document, *commands: Tree) -> Tree:
    return {
        "schema_version": "1.0",
        "base_revision": base.revision,
        "base_snapshot": snapshot_digest(base),
        "commands": list(commands),
    }


def set_parameters(target: str, **parameters: Any) -> Tree:
    return {"type": "set_parameters", "target_id": target, "parameters": parameters}


def ids(tree: object) -> list[str]:
    found: list[str] = []
    if isinstance(tree, dict):
        if isinstance(tree.get("id"), str):
            found.append(tree["id"])
        for value in tree.values():
            found.extend(ids(value))
    elif isinstance(tree, list):
        for value in tree:
            found.extend(ids(value))
    return found


def colours(document: Document) -> set[tuple[int, int, int, int]]:
    result = render(document)
    return {result.pixel(x, y) for x in range(result.width) for y in range(result.height)}


def allowed(document: Document) -> set[tuple[int, int, int, int]]:
    """The example's profile: its ramp, the outline's colour and transparency."""
    (ramp,) = document.palette.ramps
    names = {*ramp.colors, "ink"}
    found: set[tuple[int, int, int, int]] = {(0, 0, 0, 0)}
    for color in document.palette.colors:
        if color.id in names:
            r, g, b, a = (int(color.rgba[i : i + 2], 16) for i in (1, 3, 5, 7))
            found.add((r, g, b, a))
    return found


@pytest.mark.parametrize("name", EXAMPLES)
def test_ac1_tuning_a_material_keeps_ids_and_stays_in_the_palette(name: str) -> None:
    base = example(name)
    row_max = {
        "skin": (4, 2),
        "cloth": (64, 4),
        "metal": (64, 4),
        "wood": (64, 4),
        "stone": (32, 4),
    }
    density, scale = row_max[name]
    light = {"direction": "se", "height": 2, "intensity": 2, "ambient": 1}
    commands = [
        set_parameters(f"{name}_material", density=density, scale=scale, origin=[5, -3]),
        set_parameters(f"{name}_material", light=light, ramp_order="stylized"),
        set_parameters(f"{name}_outline", light=light, width=2),
        {"type": "set_geometry", "target_id": "body_down_right", "geometry": {"box": [0, 0, 1, 1]}}
        if name in {"skin", "wood"}
        else {"type": "translate", "target_id": "body_down_right", "dx": 1, "dy": 0},
        {"type": "replace_palette_color", "target_id": f"{name}_2", "rgba": "#808080FF"},
    ]
    result = apply_batch(base, batch(base, *commands))
    assert result.affected_ids == (
        f"{name}_material",
        f"{name}_outline",
        "body_down_right",
        f"{name}_2",
    )
    edited = normalize_document(result.document)
    expected = normalize_document(base)
    operation = expected["layers"][0]["operations"][0]  # type: ignore[index]  # JSON tree
    operation.update(density=density, scale=scale, origin=[5, -3], light=light)
    operation["ramp_order"] = "stylized"
    outline = expected["layers"][0]["operations"][2]  # type: ignore[index]  # JSON tree
    outline.update(light=light, width=2)
    expected["masks"][1] = edited["masks"][1]  # type: ignore[index]  # moved by hand above
    expected["palette"]["colors"][3]["rgba"] = "#808080FF"  # type: ignore[index]  # JSON tree
    expected["revision"] = 1
    assert edited == expected
    assert ids(edited) == ids(normalize_document(base))
    assert colours(result.document) <= allowed(result.document)
    assert colours(base) <= allowed(base)


def _extra(op_id: str, mask_id: str, band_id: str) -> Tree:
    return {
        "id": op_id,
        "type": "material",
        "preset": "cloth",
        "version": 1,
        "ramp": "stone_ramp",
        "ramp_order": "monotonic",
        "light": {"direction": "se", "height": 0, "intensity": 2, "ambient": 1},
        "density": 64,
        "scale": 1,
        "origin": [0, 0],
        "bands": [{"id": band_id, "mask_id": mask_id, "facing": "front", "offset": 0}],
    }


def _insert(after_id: str | None, operation: Tree) -> Tree:
    return {
        "type": "insert_operation",
        "layer_id": "object",
        "after_id": after_id,
        "operation": operation,
    }


def _pixels(document: Document) -> list[tuple[int, int, int, int]]:
    result = render(document)
    return [result.pixel(x, y) for y in range(result.height) for x in range(result.width)]


def test_ac2_inserted_operation_keeps_existing_texture() -> None:
    """Inserting another material, before or after, never changes the existing one."""
    base = example("stone")
    before = apply_batch(base, batch(base, _insert(None, _extra("extra", "body", "x_band"))))
    assert [o.id for o in before.document.layers[0].operations][:2] == ["extra", "stone_material"]
    # the existing material repaints the whole body over the new one: identical pixels
    assert _pixels(before.document) == _pixels(base)
    after = apply_batch(
        base, batch(base, _insert("stone_material", _extra("extra", "body_down_right", "x_band")))
    )
    box = mask_estimates(base)["body_down_right"].box
    assert box is not None
    old, new = render(base), render(after.document)
    outside = [
        (x, y)
        for y in range(old.height)
        for x in range(old.width)
        if not (box.x0 <= x < box.x1 and box.y0 <= y < box.y1)
    ]
    textured = {old.pixel(x, y) for x, y in outside} - {(0, 0, 0, 0)}
    assert len(textured) >= 3  # body pixels of the existing material are compared
    assert all(new.pixel(x, y) == old.pixel(x, y) for x, y in outside)


def test_ac1_material_edits_are_undoable_in_the_history() -> None:
    base = example("stone")
    history = History.start(base).edit(batch(base, set_parameters("stone_material", density=0)))
    assert history.current.document.layers[0].operations[0].density == 0  # type: ignore[union-attr]
    assert history.undo().current.document == base


@pytest.mark.parametrize(
    ("command", "pointer", "reason"),
    [
        (
            set_parameters("stone_material", density=33),
            "/commands/0/parameters/density",
            "less_than_equal",
        ),
        (
            set_parameters("stone_material", preset="lava"),
            "/commands/0/parameters",
            "not_parameter",
        ),
        (
            set_parameters("stone_material", bands=[]),
            "/commands/0/parameters",
            "not_parameter",
        ),
        (set_parameters("stone_material", id="x"), "/commands/0/parameters", "not_parameter"),
        (set_parameters("stone_material"), "/commands/0/parameters", "empty_parameters"),
        (
            set_parameters("stone_outline", color="stone_0"),
            "/commands/0/parameters",
            "not_parameter",
        ),
        (
            set_parameters("stone_outline", width=17),
            "/commands/0/parameters/width",
            "less_than_equal",
        ),
        (
            set_parameters("stone_outline", side="both"),
            "/commands/0/parameters/side",
            "literal_error",
        ),
    ],
)
def test_set_parameters_rejects_what_is_not_a_valid_parameter(
    command: Tree, pointer: str, reason: str
) -> None:
    base = example("stone")
    with pytest.raises(errors.ValidationError) as raised:
        apply_batch(base, batch(base, command))
    error = raised.value
    found = error.details[0] if error.details else error
    assert (found.json_pointer, found.context["reason"]) == (pointer, reason)


@pytest.mark.parametrize("key", ["a/b", "x~1y", "~0", "density/../preset", "k" * 4096])
def test_not_parameter_never_echoes_the_key(key: str) -> None:
    """An unknown key is untrusted input: the error names the parameters object."""
    base = example("stone")
    command = {"type": "set_parameters", "target_id": "stone_material", "parameters": {key: 1}}
    with pytest.raises(errors.ValidationError) as raised:
        apply_batch(base, batch(base, command))
    error = raised.value
    assert error.json_pointer == "/commands/0/parameters"
    assert error.context["reason"] == "not_parameter"
    assert error.context["expected"] == ("light", "ramp_order", "density", "scale", "origin")
    assert key not in str(error) and key not in repr(error.context)
    assert key not in (error.json_pointer or "")


def test_set_parameters_targets_only_unlocked_operations_with_parameters() -> None:
    base = example("wood")
    tree = copy.deepcopy(normalize_document(base))
    tree["layers"][0]["operations"].append(  # type: ignore[index]  # JSON tree
        {"id": "dot", "type": "pixel", "at": [0, 0], "color": "ink"}
    )
    with_dot = validate_document(tree)
    with pytest.raises(errors.ValidationError) as raised:
        apply_batch(with_dot, batch(with_dot, set_parameters("dot", at=[1, 1])))
    assert raised.value.context["reason"] == "no_parameters"
    with pytest.raises(errors.ValidationError) as raised:
        apply_batch(base, batch(base, set_parameters("band_body", offset=1)))
    assert raised.value.context["reason"] == "invalid_target"
    with pytest.raises(errors.ReferenceError) as missing:
        apply_batch(base, batch(base, set_parameters("ghost", density=1)))
    assert missing.value.context["reason"] == "unknown_target"
    tree["layers"][0]["locked"] = True  # type: ignore[index]  # JSON tree
    locked = validate_document(tree)
    with pytest.raises(errors.ValidationError) as raised:
        apply_batch(locked, batch(locked, set_parameters("wood_material", density=1)))
    assert raised.value.context["reason"] == "locked_layer"


def test_shade_light_is_a_parameter_too() -> None:
    path = ROOT / "examples" / "specs" / "shaded-orb.moana.json"
    base = validate_document(json.loads(path.read_text(encoding="utf-8")))
    light = {"direction": "se", "height": 1, "intensity": 3, "ambient": 1}
    result = apply_batch(base, batch(base, set_parameters("orb_shading", light=light)))
    assert result.affected_ids == ("orb_shading",)
    assert ids(normalize_document(result.document)) == ids(normalize_document(base))


def test_band_and_segment_ids_are_items_of_the_edit_index() -> None:
    base = example("cloth")
    removed = apply_batch(
        base,
        batch(
            base,
            {"type": "remove", "target_id": "cloth_outline"},
            {"type": "remove", "target_id": "upper_left"},
        ),
    )
    assert removed.affected_ids == ("cloth_outline", "outline_lit", "upper_left")
    with pytest.raises(errors.ReferenceError) as live:
        apply_batch(base, batch(base, {"type": "remove", "target_id": "upper_left"}))
    assert live.value.context["reason"] == "live_reference"
    operation = normalize_document(base)["layers"][0]["operations"][2]  # type: ignore[index]  # JSON tree
    copied = {**operation, "id": "rim_2"}
    with pytest.raises(errors.ValidationError) as raised:
        apply_batch(
            base,
            batch(
                base,
                {
                    "type": "insert_operation",
                    "layer_id": "object",
                    "after_id": None,
                    "operation": copied,
                },
            ),
        )
    assert raised.value.json_pointer == "/commands/0/operation/segments/0/id"
    assert raised.value.context["reason"] == "duplicate_id"
