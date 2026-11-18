"""Which members of each operation and mask type are colours, masks or geometry.

A data-only table, keyed by the ``type`` literal of every model in the
:data:`~moana.schema.Operation` and :data:`~moana.schema.MaskNode` unions (ADR-025).
Consumers (colour and mask reference checks, inspection, editing) read the member
names from here instead of testing model classes, so a new type only adds a row:

* ``colors``: members holding a palette colour ID;
* ``masks``: members holding mask IDs (a single ID or, for combinations, a tuple);
* ``geometry``: members holding the pixel geometry of the node;
* ``ramps``: members holding a palette ramp ID (ADR-028);
* ``items``: ``(member, row)`` pairs of members holding an array of objects with an
  ``id`` of their own, whose references the nested ``row`` describes (ADR-028).

A ``dither`` has two colours and one mask reference; its ``origin`` anchors a
pattern phase and is deliberately not listed as geometry (a later ADR decides how
editing treats it). An ``outline`` (ADR-027) has one colour, one mask reference and
no geometry: its ``width`` and ``side`` derive pixels from the mask and are not
coordinates. A ``shade`` (ADR-028) has no colour member: it names one ramp and an
array of ``bands``, each with its own ID and one mask reference. Every listed member
exists on its model; a test enforces both that and that the keys match the unions
exactly.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

__all__ = ["MASK_MEMBERS", "OPERATION_MEMBERS", "NodeMembers"]


@dataclass(frozen=True, slots=True)
class NodeMembers:
    """Member names of one node type, by role."""

    colors: tuple[str, ...]
    masks: tuple[str, ...]
    geometry: tuple[str, ...]
    ramps: tuple[str, ...] = ()
    items: tuple[tuple[str, NodeMembers], ...] = ()


_GEOMETRY: Final = {
    "pixel": ("at",),
    "line": ("start", "end"),
    "rect": ("box",),
    "ellipse": ("box",),
    "polygon": ("points",),
    "path": ("commands",),
}

OPERATION_MEMBERS: Final[MappingProxyType[str, NodeMembers]] = MappingProxyType(
    {
        **{
            kind: NodeMembers(colors=("color",), masks=(), geometry=geometry)
            for kind, geometry in _GEOMETRY.items()
        },
        "dither": NodeMembers(colors=("color_a", "color_b"), masks=("mask_id",), geometry=()),
        "outline": NodeMembers(colors=("color",), masks=("mask_id",), geometry=()),
        "shade": NodeMembers(
            colors=(),
            masks=(),
            geometry=(),
            ramps=("ramp",),
            items=(("bands", NodeMembers(colors=(), masks=("mask_id",), geometry=())),),
        ),
    }
)
"""Members of every operation ``type`` of schema 1.0."""

MASK_MEMBERS: Final[MappingProxyType[str, NodeMembers]] = MappingProxyType(
    {
        **{
            kind: NodeMembers(colors=(), masks=(), geometry=geometry)
            for kind, geometry in _GEOMETRY.items()
        },
        **{
            kind: NodeMembers(colors=(), masks=("masks",), geometry=())
            for kind in ("union", "intersect", "subtract", "xor")
        },
    }
)
"""Members of every mask ``type`` of schema 1.0 (leaves and combinations)."""
