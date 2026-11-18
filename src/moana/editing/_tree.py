"""Member table, ID index and reference scan over a working copy of a document.

The editor works on the JSON tree of :func:`moana.schema.normalize_document`, a
fresh copy that shares nothing with the frozen source :class:`Document`. Every node
with an ID is located by that ID, never by its position, and each container is the
very list that holds the node, so a reorder can only move a node among its siblings.

What the editor may assume about an operation or a mask node comes only from
:data:`OPERATION_MEMBERS` and :data:`MASK_MEMBERS`: which members reference palette
colours, which reference masks and which are geometry. A new type needs exactly one
new row, and a test fails while a schema type has no row (ADR-024).

The table is :data:`moana.schema.OPERATION_MEMBERS` / :data:`moana.schema.MASK_MEMBERS`
(ADR-025), re-bound here so the editor reads it from one module. A ``dither`` has
two colours, a mask reference and no geometry: ``set_color`` rejects it
(``multiple_colors``) and ``translate``/``set_geometry`` reject it (``not_geometric``).
:data:`GEOMETRY_SHAPES` stays here: how ``translate`` moves a geometric member is an
editing rule.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final, Literal

from moana.schema import MASK_MEMBERS, OPERATION_MEMBERS, NodeMembers

__all__ = [
    "GEOMETRY_SHAPES",
    "MASK_MEMBERS",
    "OPERATION_MEMBERS",
    "Geometry",
    "JsonObject",
    "Node",
    "NodeMembers",
    "index_nodes",
    "live_references",
    "node_members",
]

type JsonObject = dict[str, Any]
"""A JSON object of the working tree (or of a command payload)."""

type Geometry = Literal["point", "box", "points", "commands"]
"""Shape of a geometric member: ``[x, y]``, ``[x0, y0, x1, y1]``, ``[[x, y], ...]``
or path commands ``[["M", x, y], ...]`` in 1/256 pixel."""


GEOMETRY_SHAPES: Final[Mapping[str, Geometry]] = MappingProxyType(
    {
        "at": "point",
        "box": "box",
        "commands": "commands",
        "end": "point",
        "points": "points",
        "start": "point",
    }
)
"""How ``translate`` moves each geometric member of the tables."""


@dataclass(frozen=True, slots=True)
class Node:
    """A node with an ID: its kind, the list that holds it and its owning layer.

    ``kind`` is ``document``, ``palette``, ``color``, ``ramp``, ``layer``,
    ``operation``, ``shape_mask``, ``combination_mask`` or ``region``. ``container``
    is ``None`` for the document and the palette, which are not in a list.
    """

    kind: str
    value: JsonObject
    container: list[JsonObject] | None
    layer: JsonObject | None = None

    @property
    def position(self) -> int:
        """Current index of the node in its container (identity, not equality)."""
        assert self.container is not None
        return next(i for i, item in enumerate(self.container) if item is self.value)

    @property
    def owning_layer(self) -> JsonObject | None:
        """The layer whose ``locked`` flag protects this node, if any."""
        return self.value if self.kind == "layer" else self.layer


def node_members(node: Node) -> NodeMembers:
    """Table row of an operation or mask node (only those kinds have a row)."""
    table = OPERATION_MEMBERS if node.kind == "operation" else MASK_MEMBERS
    return table[node.value["type"]]


def _mask_kind(mask: JsonObject) -> str:
    return "shape_mask" if MASK_MEMBERS[mask["type"]].geometry else "combination_mask"


def _members(tree: JsonObject) -> Iterator[Node]:
    yield Node("document", tree, None)
    palette = tree["palette"]
    yield Node("palette", palette, None)
    yield from (Node("color", item, palette["colors"]) for item in palette["colors"])
    yield from (Node("ramp", item, palette["ramps"]) for item in palette["ramps"])
    for layer in tree["layers"]:
        yield Node("layer", layer, tree["layers"])
        operations = layer["operations"]
        yield from (Node("operation", item, operations, layer) for item in operations)
    yield from (Node(_mask_kind(item), item, tree["masks"]) for item in tree["masks"])
    yield from (Node("region", item, tree["regions"]) for item in tree["regions"])


def index_nodes(tree: JsonObject) -> dict[str, Node]:
    """Every ID of the working document; the first declaration wins on a duplicate."""
    index: dict[str, Node] = {}
    for node in _members(tree):
        index.setdefault(node.value["id"], node)
    return index


type _Reference = tuple[str, str]
"""The pointer of a reference and the ID it names."""


def _references(node: JsonObject, members: tuple[str, ...], pointer: str) -> Iterator[_Reference]:
    """Every ID held by ``members`` (an ID or an array of IDs; absent when optional)."""
    for member in members:
        value = node.get(member)
        if isinstance(value, list):
            yield from ((f"{pointer}/{member}/{i}", item) for i, item in enumerate(value))
        elif value is not None:
            yield f"{pointer}/{member}", value


def _all_references(tree: JsonObject) -> Iterator[_Reference]:
    """Every reference of ramps, layers, operations, masks and regions, by the table."""
    for index, ramp in enumerate(tree["palette"]["ramps"]):
        yield from _references(ramp, ("colors",), f"/palette/ramps/{index}")
    for layer_index, layer in enumerate(tree["layers"]):
        yield from _references(layer, ("mask_id",), f"/layers/{layer_index}")
        for index, operation in enumerate(layer["operations"]):
            row = OPERATION_MEMBERS[operation["type"]]
            pointer = f"/layers/{layer_index}/operations/{index}"
            yield from _references(operation, row.colors + row.masks, pointer)
    for index, mask in enumerate(tree["masks"]):
        yield from _references(mask, MASK_MEMBERS[mask["type"]].masks, f"/masks/{index}")
    for index, region in enumerate(tree["regions"]):
        yield from _references(region, ("mask_id", "operation_ids"), f"/regions/{index}")


def live_references(tree: JsonObject, removed: frozenset[str]) -> list[str]:
    """Pointers of every reference to ``removed`` from a node that is not removed."""
    pointers: list[str] = []
    for pointer, target in _all_references(tree):
        if target in removed and not _inside_removed(tree, pointer, removed):
            pointers.append(pointer)
    return pointers


def _inside_removed(tree: JsonObject, pointer: str, removed: frozenset[str]) -> bool:
    """Whether the reference at ``pointer`` belongs to a node that is removed too."""
    tokens = pointer.split("/")[1:]
    node: Any = tree
    for token in tokens[:-1]:
        node = node[int(token)] if isinstance(node, list) else node[token]
        if isinstance(node, dict) and node.get("id") in removed:
            return True
    return False
