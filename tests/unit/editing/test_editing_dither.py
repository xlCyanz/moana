"""Edits on documents with ``dither`` operations (MOANA-018 with MOANA-016; ADR-024, ADR-025).

A ``dither`` has two colour members (``color_a``, ``color_b``), one mask reference
(``mask_id``) and no geometry (``origin`` anchors the pattern phase only). Expected
trees are edits of ``examples/specs/dither-dusk.moanart.json`` written by hand.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from moanart.core import errors
from moanart.editing import apply_batch
from moanart.schema import normalize_document, snapshot_digest, validate_document

type Tree = dict[str, Any]

EXAMPLE = Path(__file__).resolve().parents[3] / "examples/specs/dither-dusk.moanart.json"
SOURCE: Tree = json.loads(EXAMPLE.read_text(encoding="utf-8"))

NEW_DITHER: Tree = {
    "id": "sky_extra",
    "type": "dither",
    "size": 2,
    "coverage": 1,
    "origin": [0, 0],
    "color_a": "glow",
    "color_b": "ember",
    "mask_id": "band_ember_glow",
}


def edit(*commands: Tree) -> Tree:
    """Apply ``commands`` to the example and return the normalized result."""
    document = validate_document(copy.deepcopy(SOURCE))
    batch = {
        "schema_version": "1.0",
        "base_revision": document.revision,
        "base_snapshot": snapshot_digest(document),
        "commands": list(commands),
    }
    return normalize_document(apply_batch(document, batch).document)


def expected() -> Tree:
    """The normalized example with the revision of a successful edit."""
    tree = normalize_document(validate_document(copy.deepcopy(SOURCE)))
    tree["revision"] = 1
    return tree


def failure(kind: type[errors.MoanArtError], *commands: Tree) -> errors.MoanArtError:
    with pytest.raises(kind) as caught:
        edit(*commands)
    return caught.value


def operations(tree: Tree, layer: int) -> list[Tree]:
    result: list[Tree] = tree["layers"][layer]["operations"]
    return result


@pytest.mark.parametrize(
    ("target", "pointers"),
    [
        ("band_night_dusk", {"/layers/0/operations/1/mask_id"}),
        ("dune_shoulder", {"/layers/1/operations/1/mask_id", "/regions/0/mask_id"}),
        (
            "dusk",
            {
                "/palette/ramps/0/colors/1",
                "/layers/0/operations/1/color_b",
                "/layers/0/operations/2/color_a",
            },
        ),
        (
            "sand_shadow",
            {
                "/palette/ramps/1/colors/0",
                "/layers/1/operations/1/color_b",
                "/layers/1/operations/2/color",
            },
        ),
    ],
)
def test_removing_what_a_dither_uses_is_a_live_reference(target: str, pointers: set[str]) -> None:
    error = failure(errors.ReferenceError, {"type": "remove", "target_id": target})
    assert (error.json_pointer, error.context["reason"]) == (
        "/commands/0/target_id",
        "live_reference",
    )
    assert {detail.json_pointer for detail in error.details} == pointers


def test_removing_other_nodes_next_to_dithers_succeeds() -> None:
    result = edit(
        {"type": "remove", "target_id": "sky_glow"},
        {"type": "remove", "target_id": "dune_shading"},
        {"type": "remove", "target_id": "sky_ember_glow"},
        {"type": "remove", "target_id": "band_ember_glow"},
    )
    tree = expected()
    del operations(tree, 0)[3:5]
    del tree["masks"][2]
    tree["regions"] = []
    assert result == tree


def test_removing_a_layer_drops_its_dithers_with_it() -> None:
    result = edit(
        {"type": "remove", "target_id": "sky"},
        {"type": "remove", "target_id": "band_night_dusk"},
    )
    tree = expected()
    del tree["layers"][0]
    del tree["masks"][0]
    assert result == tree


def test_set_color_on_a_dither_is_ambiguous() -> None:
    error = failure(
        errors.ValidationError,
        {"type": "set_color", "target_id": "dune_dither", "color": "glow"},
    )
    assert error.json_pointer == "/commands/0/target_id"
    assert (error.context["reason"], error.context["color_members"]) == ("multiple_colors", 2)


@pytest.mark.parametrize(
    "command",
    [
        {"type": "translate", "target_id": "dune_dither", "dx": 1, "dy": 0},
        {"type": "set_geometry", "target_id": "sky_night_dusk", "geometry": {"origin": [1, 1]}},
    ],
)
def test_a_dither_has_no_geometry(command: Tree) -> None:
    error = failure(errors.ValidationError, command)
    assert (error.json_pointer, error.context["reason"]) == (
        "/commands/0/target_id",
        "not_geometric",
    )


def test_insert_a_valid_dither() -> None:
    command = {
        "type": "insert_operation",
        "layer_id": "sky",
        "after_id": "sky_ember_glow",
        "operation": NEW_DITHER,
    }
    tree = expected()
    operations(tree, 0).insert(4, copy.deepcopy(NEW_DITHER))
    assert edit(command) == tree


@pytest.mark.parametrize("member", ["color_a", "color_b"])
def test_insert_a_dither_with_a_missing_colour(member: str) -> None:
    operation = {**NEW_DITHER, member: "ghost"}
    command = {
        "type": "insert_operation",
        "layer_id": "sky",
        "after_id": None,
        "operation": operation,
    }
    error = failure(errors.ReferenceError, command)
    assert error.json_pointer == f"/commands/0/operation/{member}"
    assert error.context["reason"] == "unknown_color"


def test_insert_a_dither_with_a_missing_mask_fails_in_the_final_validation() -> None:
    operation = {**NEW_DITHER, "mask_id": "ghost_mask"}
    command = {
        "type": "insert_operation",
        "layer_id": "sky",
        "after_id": None,
        "operation": operation,
    }
    error = failure(errors.ReferenceError, command)
    assert error.context["reason"] == "invalid_result"
    assert [d.json_pointer for d in error.details] == ["/layers/0/operations/0/mask_id"]


def test_reorder_a_dither() -> None:
    result = edit({"type": "reorder", "target_id": "sky_ember_glow", "after_id": None})
    tree = expected()
    sky = operations(tree, 0)
    sky.insert(0, sky.pop(3))
    assert result == tree
