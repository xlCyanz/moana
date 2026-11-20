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
A ``shade`` (ADR-028) has no colour, a ramp reference and ``bands`` whose IDs are
indexed as ``item`` nodes (so a new ID cannot reuse them) and whose masks are live
references; no command targets an ``item``.
:data:`GEOMETRY_SHAPES` stays here: how ``translate`` moves a geometric member is an
editing rule.

:class:`WorkingIndex` is the index of one batch (ADR-040): built once, at the first
lookup, and kept equal to :func:`index_nodes` of the working tree by the commands
that add, remove, replace or move nodes, instead of being rebuilt per command.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
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
    "WorkingIndex",
    "index_nodes",
    "item_ids",
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
    ``operation``, ``item`` (an object with its own ID inside an operation, such as a
    ``shade`` band, ADR-028), ``shape_mask``, ``combination_mask``, ``region``,
    ``animation`` or ``frame`` (ADR-032; indexed so that a new ID cannot reuse them,
    never targeted by a command). ``container``
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


def _operation_nodes(
    operation: JsonObject, container: list[JsonObject], layer: JsonObject
) -> Iterator[Node]:
    """An operation and its items (``shade`` bands...), in declaration order."""
    yield Node("operation", operation, container, layer)
    for member, _ in OPERATION_MEMBERS[operation["type"]].items:
        items = operation[member]
        yield from (Node("item", item, items, layer) for item in items)


def _members(tree: JsonObject) -> Iterator[Node]:
    yield Node("document", tree, None)
    palette = tree["palette"]
    yield Node("palette", palette, None)
    yield from (Node("color", item, palette["colors"]) for item in palette["colors"])
    yield from (Node("ramp", item, palette["ramps"]) for item in palette["ramps"])
    for layer in tree["layers"]:
        yield Node("layer", layer, tree["layers"])
        operations = layer["operations"]
        for operation in operations:
            yield from _operation_nodes(operation, operations, layer)
    yield from (Node(_mask_kind(item), item, tree["masks"]) for item in tree["masks"])
    yield from (Node("region", item, tree["regions"]) for item in tree["regions"])
    for animation in tree["animations"]:  # IDs only: no command targets them (ADR-032)
        yield Node("animation", animation, tree["animations"])
        yield from (Node("frame", item, animation["frames"]) for item in animation["frames"])


def item_ids(operation: JsonObject) -> tuple[str, ...]:
    """IDs of the items of an operation (``shade`` bands, ADR-028), in order."""
    return tuple(
        item["id"]
        for member, _ in OPERATION_MEMBERS[operation["type"]].items
        for item in operation[member]
    )


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
    """Every reference of ramps, layers, operations, masks, regions and frame overrides
    (their ``target_id`` and ``set_color`` colour, ADR-032), by the table."""
    for index, ramp in enumerate(tree["palette"]["ramps"]):
        yield from _references(ramp, ("colors",), f"/palette/ramps/{index}")
    for layer_index, layer in enumerate(tree["layers"]):
        yield from _references(layer, ("mask_id",), f"/layers/{layer_index}")
        for index, operation in enumerate(layer["operations"]):
            row = OPERATION_MEMBERS[operation["type"]]
            pointer = f"/layers/{layer_index}/operations/{index}"
            yield from _references(operation, row.colors + row.masks + row.ramps, pointer)
            for member, item_row in row.items:
                for position, item in enumerate(operation[member]):
                    item_pointer = f"{pointer}/{member}/{position}"
                    yield from _references(item, item_row.masks, item_pointer)
    for index, mask in enumerate(tree["masks"]):
        yield from _references(mask, MASK_MEMBERS[mask["type"]].masks, f"/masks/{index}")
    for index, region in enumerate(tree["regions"]):
        yield from _references(region, ("mask_id", "operation_ids"), f"/regions/{index}")
    for animation_index, animation in enumerate(tree["animations"]):
        for frame_index, frame in enumerate(animation["frames"]):
            for index, override in enumerate(frame["overrides"]):
                pointer = f"/animations/{animation_index}/frames/{frame_index}/overrides/{index}"
                yield from _references(override, ("target_id", "color"), pointer)


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


class WorkingIndex:
    """The ID index of one batch, equal to ``index_nodes(tree)`` after every command.

    It is built from the tree at the first lookup (so a malformed source fails inside
    the command that first needs it, as a per-command rebuild did) and then updated
    by the command that changed the structure: :meth:`inserted`, :meth:`removed`,
    :meth:`replaced` and :meth:`reordered`, each called after the tree has changed.
    Lookups and updates cost O(1) per ID, plus the items of an operation. What a
    command does around the index is not covered by that bound: :attr:`Node.position`
    scans the node's container (O(siblings)) and ``remove`` scans the whole tree for
    live references (O(nodes)).

    While every ID is unique an update is local: a node keeps its own entry wherever
    it moves. A tree with a duplicate ID (only an unvalidated source can have one;
    no command adds one) is rebuilt in full after each structural change instead,
    because removing or moving the first declaration can hand the ID to another node.

    An update never raises ``KeyError``: the editor reports a ``KeyError`` as a
    malformed source (``invalid_source``), so a desynchronised index must fail as an
    internal error instead of being masked as one.
    """

    __slots__ = ("_nodes", "_tree", "_unique")

    def __init__(self, tree: JsonObject) -> None:
        self._tree = tree
        self._nodes: dict[str, Node] | None = None
        self._unique = True

    def _built(self) -> dict[str, Node]:
        if self._nodes is None:
            self._rebuild()
        assert self._nodes is not None
        return self._nodes

    def _rebuild(self) -> None:
        nodes: dict[str, Node] = {}
        count = 0
        for node in _members(self._tree):
            nodes.setdefault(node.value["id"], node)
            count += 1
        self._nodes, self._unique = nodes, count == len(nodes)

    def _local(self) -> dict[str, Node] | None:
        """The entries to update in place, or ``None`` after a full rebuild."""
        nodes = self._built()
        if self._unique:
            return nodes
        self._rebuild()
        return None

    def get(self, key: str) -> Node | None:
        """The node declaring ``key`` first, if any."""
        return self._built().get(key)

    def __contains__(self, key: str) -> bool:
        return key in self._built()

    def entries(self) -> dict[str, Node]:
        """A copy of every entry (for equivalence checks against :func:`index_nodes`)."""
        return dict(self._built())

    def is_color(self, key: str) -> bool:
        """Whether ``key`` is the ID of a palette colour."""
        nodes = self._built()
        if self._unique:
            node = nodes.get(key)
            return node is not None and node.kind == "color"
        return key in {color["id"] for color in self._tree["palette"]["colors"]}

    def inserted(
        self, operation: JsonObject, container: list[JsonObject], layer: JsonObject
    ) -> None:
        """Index an operation, and its items, just inserted into ``container``."""
        nodes = self._local()
        if nodes is not None:
            for node in _operation_nodes(operation, container, layer):
                nodes[node.value["id"]] = node

    def removed(self, keys: Iterable[str]) -> None:
        """Forget ``keys``: a removed node and every ID it held."""
        nodes = self._local()
        if nodes is not None:
            for key in keys:
                forgotten = nodes.pop(key, None)
                assert forgotten is not None, "removed ID was not indexed"

    def replaced(self, node: Node, value: JsonObject) -> None:
        """Index ``value``, which took the place of ``node.value``.

        ``set_geometry`` and ``set_parameters`` never change an ID, so the entries of
        the node and of its items (new objects in new lists) are overwritten in place.
        """
        nodes = self._local()
        if nodes is None:
            return
        if node.kind != "operation":
            nodes[value["id"]] = Node(node.kind, value, node.container, node.layer)
            return
        assert node.container is not None and node.layer is not None
        for entry in _operation_nodes(value, node.container, node.layer):
            nodes[entry.value["id"]] = entry

    def reordered(self) -> None:
        """A node moved among its siblings: its entry, which holds the list, stays."""
        self._local()
