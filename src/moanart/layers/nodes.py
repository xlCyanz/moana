"""Immutable layer tree: fills, layers, groups and the validated tree (ADR-017).

A :class:`Layer` holds an ordered tuple of :class:`Fill` (a binary
:class:`~moanart.geometry.Mask` painted with one :class:`~moanart.palette.Rgba`); a
:class:`Group` holds ordered children. Children are listed bottom to top. ``locked``
is kept for editing and never changes the render. :class:`LayerTree` validates the
whole tree once: unique IDs, group depth, at most 128 layers and groups, masks inside
the canvas and, in the ``strict`` profile, opacity 255 and fully opaque or
transparent fill colours. Validation stops at the first problem in bottom-to-top,
depth-first order (the tree is built by code, not edited as a document).

A fill may carry a :class:`DeferredMask` instead of a mask: a declared box plus a
builder called during composition, so a caller with thousands of operations never
holds more than one rasterised mask at a time (ADR-018).

A layer may also carry a semantic ``mask`` (ADR-022): a :class:`MaskShape` leaf or a
:class:`MaskCombination` of union/intersect/subtract/xor over other mask nodes. Mask
nodes are immutable and built bottom-up, so the expression is a DAG by construction
(cycles are rejected earlier, by ``schema``). Masks are in canvas coordinates: they
never depend on a layer render and are not moved by the geometry of the layer.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Final, Literal

from moanart.core.coordinates import Box, Dimensions, require_int
from moanart.core.errors import ValidationError
from moanart.core.ids import check_id
from moanart.core.limits import (
    MAX_GROUP_DEPTH,
    MAX_LAYERS,
    MAX_MASK_DEPTH,
    MAX_MASK_OPERANDS,
    MAX_OPERATIONS,
)
from moanart.geometry import MASK_OPERATORS, Mask, MaskOperator
from moanart.palette import ColorProfile, Rgba

__all__ = [
    "BLEND_MODES",
    "MAX_NAME_BYTES",
    "DeferredMask",
    "Fill",
    "Group",
    "Layer",
    "LayerTree",
    "MaskCombination",
    "MaskNode",
    "MaskShape",
    "Node",
    "mask_leaves",
]

MAX_NAME_BYTES: Final = 4096
BLEND_MODES: Final = ("normal",)


def _invalid(message: str, **context: object) -> ValidationError:
    return ValidationError(message, context=context)


def _check_name(value: object) -> None:
    if type(value) is not str:
        raise _invalid("name must be a string", field="name", reason="not_string")
    try:
        size = len(value.encode("utf-8"))
    except UnicodeEncodeError:
        raise _invalid("name must be valid UTF-8", field="name", reason="invalid_utf8") from None
    if size > MAX_NAME_BYTES:
        raise _invalid("name is too long", field="name", reason="too_long")


def _check_flag(value: object, field: str) -> None:
    if type(value) is not bool:
        raise _invalid(f"{field} must be a boolean", field=field, reason="not_boolean")


def _check_children(children: object) -> None:
    if type(children) is not tuple:
        raise TypeError("children must be a tuple of Layer or Group values")
    for child in children:
        if not isinstance(child, Layer | Group):
            raise TypeError("children must be a tuple of Layer or Group values")


def _check_node_fields(
    node_id: object, name: object, visible: object, locked: object, opacity: object
) -> None:
    check_id(node_id)
    _check_name(name)
    _check_flag(visible, "visible")
    _check_flag(locked, "locked")
    require_int(opacity, "opacity", minimum=0, maximum=255)


@dataclass(frozen=True, slots=True, eq=False)
class DeferredMask:
    """A mask built only when its fill is painted, inside a declared ``box``.

    ``box`` (``None`` when nothing can be drawn) bounds the storage box of the mask
    that ``build`` returns; it is what validation and :func:`composition_cost`
    use. :func:`~moanart.layers.compose` calls ``build`` once per visible fill, right
    before painting it, and rejects a result outside ``box``. Equality is identity.
    """

    box: Box | None
    build: Callable[[], Mask]

    def __post_init__(self) -> None:
        if self.box is not None and not isinstance(self.box, Box):
            raise TypeError("box must be a Box value or None")
        if not callable(self.build):
            raise TypeError("build must be callable")


@dataclass(frozen=True, slots=True)
class Fill:
    """Pixels of ``mask`` painted with ``color`` (source-over at full opacity)."""

    mask: Mask | DeferredMask
    color: Rgba

    def __post_init__(self) -> None:
        if not isinstance(self.mask, Mask | DeferredMask):
            raise TypeError("mask must be a Mask or DeferredMask value")
        if not isinstance(self.color, Rgba):
            raise TypeError("color must be an Rgba value")

    @property
    def box(self) -> Box | None:
        """Storage box of the mask (declared box for a deferred mask)."""
        return self.mask.box


@dataclass(frozen=True, slots=True)
class MaskShape:
    """Leaf of a semantic mask: primitive geometry already in canvas coordinates."""

    id: str
    mask: Mask | DeferredMask

    def __post_init__(self) -> None:
        check_id(self.id)
        if not isinstance(self.mask, Mask | DeferredMask):
            raise TypeError("mask must be a Mask or DeferredMask value")

    @property
    def box(self) -> Box | None:
        """Storage box of the mask (declared box for a deferred mask)."""
        return self.mask.box

    @property
    def depth(self) -> int:
        """Length of the longest reference chain below and including this node."""
        return 1


@dataclass(frozen=True, slots=True, eq=False)
class MaskCombination:
    """Boolean node: ``operator`` over 2 to 64 ``operands``, folded in order.

    ``depth`` (derived) is one more than the deepest operand and at most 16.
    Equality is identity, as for :class:`DeferredMask`: a structural ``==`` or hash
    of a DAG with shared nodes would cost as much as expanding it.
    """

    id: str
    operator: MaskOperator
    operands: tuple[MaskNode, ...]
    depth: int = field(init=False, compare=False)

    def __post_init__(self) -> None:
        check_id(self.id)
        if self.operator not in MASK_OPERATORS:
            raise _invalid(
                "operator must be union, intersect, subtract or xor",
                field="operator",
                reason="unknown_operator",
            )
        if type(self.operands) is not tuple:
            raise TypeError("operands must be a tuple of mask nodes")
        for operand in self.operands:
            if not isinstance(operand, MaskShape | MaskCombination):
                raise TypeError("operands must be a tuple of mask nodes")
        if not 2 <= len(self.operands) <= MAX_MASK_OPERANDS:
            raise _invalid(
                f"a mask combination needs 2 to {MAX_MASK_OPERANDS} operands",
                field="operands",
                reason="out_of_range",
                minimum=2,
                maximum=MAX_MASK_OPERANDS,
            )
        depth = 1 + max(operand.depth for operand in self.operands)
        if depth > MAX_MASK_DEPTH:
            raise _invalid(
                "mask references are nested too deeply",
                field="operands",
                reason="too_deep",
                maximum=MAX_MASK_DEPTH,
            )
        object.__setattr__(self, "depth", depth)


MaskNode = MaskShape | MaskCombination


def mask_leaves(root: MaskNode) -> Iterator[MaskShape]:
    """Distinct leaves of a mask DAG, depth first in operand order (shared nodes once)."""
    seen: set[int] = set()  # identities only deduplicate; the order comes from operands
    stack: list[MaskNode] = [root]
    while stack:
        node = stack.pop()
        if id(node) in seen:
            continue
        seen.add(id(node))
        if isinstance(node, MaskShape):
            yield node
        else:
            stack.extend(reversed(node.operands))


@dataclass(frozen=True, slots=True)
class Layer:
    """Leaf node: ordered fills composited onto a transparent layer buffer.

    With ``mask``, the layer buffer is cleared outside the mask before it is
    composited, so the layer changes no pixel outside it (ADR-022).
    """

    id: str
    name: str
    fills: tuple[Fill, ...] = ()
    visible: bool = True
    locked: bool = False
    opacity: int = 255
    blend: Literal["normal"] = "normal"
    mask: MaskNode | None = None

    def __post_init__(self) -> None:
        _check_node_fields(self.id, self.name, self.visible, self.locked, self.opacity)
        if self.mask is not None and not isinstance(self.mask, MaskShape | MaskCombination):
            raise TypeError("mask must be a MaskShape, a MaskCombination or None")
        if type(self.fills) is not tuple:
            raise TypeError("fills must be a tuple of Fill values")
        if len(self.fills) > MAX_OPERATIONS:
            raise _invalid(
                "a layer has too many fills",
                field="fills",
                reason="out_of_range",
                maximum=MAX_OPERATIONS,
            )
        for fill in self.fills:
            if not isinstance(fill, Fill):
                raise TypeError("fills must be a tuple of Fill values")
        if self.blend not in BLEND_MODES:
            raise _invalid(
                "only the normal blend mode is supported",
                field="blend",
                reason="unsupported_blend",
            )


@dataclass(frozen=True, slots=True)
class Group:
    """Inner node: children composited in an isolated buffer, then ``opacity`` once."""

    id: str
    name: str
    children: tuple[Node, ...] = ()
    visible: bool = True
    locked: bool = False
    opacity: int = 255

    def __post_init__(self) -> None:
        _check_node_fields(self.id, self.name, self.visible, self.locked, self.opacity)
        _check_children(self.children)
        if len(self.children) > MAX_LAYERS:
            raise _invalid(
                "a group has too many children",
                field="children",
                reason="out_of_range",
                maximum=MAX_LAYERS,
            )


Node = Layer | Group


def _iter_nodes(children: tuple[Node, ...]) -> Iterator[tuple[Node, int]]:
    """Nodes bottom to top, depth first, with the number of enclosing groups."""
    stack: list[tuple[Node, int]] = [(child, 0) for child in reversed(children)]
    while stack:
        node, depth = stack.pop()
        yield node, depth
        if isinstance(node, Group):
            stack.extend((child, depth + 1) for child in reversed(node.children))


@dataclass(frozen=True, slots=True)
class LayerTree:
    """Validated bottom-to-top tree over a canvas of ``dimensions``.

    ``profile`` follows the document colour profile: ``strict`` rejects opacity other
    than 255 and fill colours with partial alpha. Errors carry ``node_id`` (and
    ``fill`` index) instead of a document pointer, since the tree has no JSON form.
    """

    dimensions: Dimensions
    children: tuple[Node, ...]
    profile: ColorProfile = "rgba"

    def __post_init__(self) -> None:
        if not isinstance(self.dimensions, Dimensions):
            raise TypeError("dimensions must be a Dimensions value")
        _check_children(self.children)
        if self.profile not in ("strict", "rgba"):
            raise _invalid(
                "profile must be strict or rgba", field="profile", reason="unknown_profile"
            )
        self._validate_nodes()

    def _validate_nodes(self) -> None:
        canvas = Box.from_dimensions(self.dimensions)
        seen: set[str] = set()
        for count, (node, depth) in enumerate(_iter_nodes(self.children), start=1):
            if count > MAX_LAYERS:
                raise _invalid(
                    "the tree has too many layers and groups",
                    field="layers",
                    reason="out_of_range",
                    maximum=MAX_LAYERS,
                )
            if node.id in seen:
                raise _invalid(
                    "node IDs must be unique", field="id", reason="duplicate_id", node_id=node.id
                )
            seen.add(node.id)
            if self.profile == "strict" and node.opacity != 255:
                raise _invalid(
                    "opacity must be 255 in the strict profile",
                    field="opacity",
                    reason="partial_opacity",
                    profile="strict",
                    node_id=node.id,
                )
            if isinstance(node, Group) and depth + 1 > MAX_GROUP_DEPTH:
                raise _invalid(
                    "groups are nested too deeply",
                    field="children",
                    reason="too_deep",
                    node_id=node.id,
                    maximum=MAX_GROUP_DEPTH,
                )
            if isinstance(node, Layer):
                self._check_fills(node, canvas)

    def _check_fills(self, layer: Layer, canvas: Box) -> None:
        if layer.mask is not None:
            for leaf in mask_leaves(layer.mask):
                box = leaf.box
                if box is not None and box.intersection(canvas) != box:
                    raise _invalid(
                        "layer mask lies outside the canvas",
                        field="mask",
                        reason="outside_canvas",
                        node_id=layer.id,
                        mask_id=leaf.id,
                    )
        for index, fill in enumerate(layer.fills):
            box = fill.box
            if box is not None and box.intersection(canvas) != box:
                raise _invalid(
                    "fill mask lies outside the canvas",
                    field="mask",
                    reason="outside_canvas",
                    node_id=layer.id,
                    fill=index,
                )
            alpha = fill.color.a
            if self.profile == "strict" and alpha not in (0, 255):
                raise _invalid(
                    "fill colours must be opaque or transparent in the strict profile",
                    field="color",
                    reason="partial_alpha",
                    profile="strict",
                    node_id=layer.id,
                    fill=index,
                )

    def walk(self) -> tuple[tuple[Node, int], ...]:
        """Every node bottom to top, depth first, with its number of enclosing groups."""
        return tuple(_iter_nodes(self.children))
