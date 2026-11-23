"""Editing rules over the schema member table (MOANA-018, ADR-024, ADR-025).

That the table matches the schema unions is tested in
``tests/unit/schema/test_schema_members.py``; here only what editing adds: every
geometric member has a ``translate`` shape, and references held by removed nodes
are not live.
"""

from __future__ import annotations

from moanart.editing import _tree
from moanart.editing._tree import GEOMETRY_SHAPES, live_references
from moanart.schema import MASK_MEMBERS, OPERATION_MEMBERS


def test_editing_reads_the_schema_table() -> None:
    assert _tree.OPERATION_MEMBERS is OPERATION_MEMBERS
    assert _tree.MASK_MEMBERS is MASK_MEMBERS


def test_every_geometric_member_has_a_translate_shape() -> None:
    members = {
        name
        for table in (OPERATION_MEMBERS, MASK_MEMBERS)
        for row in table.values()
        for name in row.geometry
    }
    assert members == set(GEOMETRY_SHAPES)


def test_references_from_removed_nodes_are_not_live() -> None:
    tree = {
        "palette": {"id": "p", "colors": [], "ramps": []},
        "layers": [],
        "masks": [
            {"id": "a", "type": "rect", "box": [0, 0, 1, 1]},
            {"id": "b", "type": "rect", "box": [0, 0, 2, 2]},
            {"id": "both", "type": "union", "masks": ["a", "b"]},
        ],
        "regions": [{"id": "r", "mask_id": "a"}],
        "animations": [],
    }
    assert live_references(tree, frozenset({"a"})) == ["/masks/2/masks/0", "/regions/0/mask_id"]
    assert live_references(tree, frozenset({"a", "both"})) == ["/regions/0/mask_id"]
    assert live_references(tree, frozenset({"a", "both", "r"})) == []
