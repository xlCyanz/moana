"""Atomic application of an edit batch (MOANA.md section 15, ADR-024).

:func:`apply_batch` checks both preconditions of the batch against the source
document (``base_revision`` *and* ``base_snapshot``, so two branches with the same
revision number never accept each other's batch), applies every command in order to
a private working copy of the normalised tree, sets ``revision`` to the base plus
one and validates the whole result with :func:`moana.schema.validate_document`
(IDs, colour and mask references, the mask/region DAG, limits and profile). Any
failure raises before a document exists, so a batch is all or nothing and the source
``Document`` (frozen) is never touched. IDs, untouched members and the order of
untouched nodes are preserved because the copy is edited in place by ID.

What a command may read or change in an operation or mask comes from the type table
of :mod:`moana.editing._tree` (colour, mask and geometric members), never from
assumptions about one type.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

from pydantic import BaseModel, ConfigDict
from pydantic import ValidationError as PydanticValidationError

from moana.core.coordinates import MAX_COORDINATE
from moana.core.errors import (
    EditConflict,
    ErrorDetail,
    MoanaError,
    ReferenceError,
    UnsupportedOperation,
    ValidationError,
)
from moana.core.vector_path import MAX_PATH_COORDINATE, PATH_UNITS
from moana.editing._tree import (
    GEOMETRY_SHAPES,
    OPERATION_MEMBERS,
    Geometry,
    JsonObject,
    Node,
    NodeMembers,
    index_nodes,
    live_references,
    node_members,
)
from moana.editing.batch import (
    BatchInput,
    EditBatch,
    InsertOperation,
    Remove,
    Reorder,
    ReplacePaletteColor,
    SetColor,
    SetGeometry,
    SetVisibility,
    Translate,
    parse_edit_batch,
)
from moana.schema import (
    DEFAULT_PARSE_LIMITS,
    Document,
    MaskNode,
    Operation,
    ParseLimits,
    normalize_document,
    snapshot_digest,
    validate_document,
)
from moana.schema._issues import pydantic_details
from moana.schema.models import MAX_REVISION

__all__ = ["EditResult", "apply_batch"]

_REMOVABLE: Final = (
    "color",
    "combination_mask",
    "layer",
    "operation",
    "ramp",
    "region",
    "shape_mask",
)
"""Kinds ``remove`` and ``reorder`` accept: every node in a container."""
_GEOMETRIC: Final = ("combination_mask", "operation", "shape_mask")
"""Kinds with a member-table row; ``translate``/``set_geometry`` need geometry too."""
_PIXEL_RANGE: Final = (-MAX_COORDINATE, MAX_COORDINATE)
_EDGE_RANGE: Final = (-MAX_COORDINATE + 1, MAX_COORDINATE + 1)
_PATH_RANGE: Final = (-MAX_PATH_COORDINATE, MAX_PATH_COORDINATE)


@dataclass(frozen=True, slots=True)
class EditResult:
    """A successful batch: the new document, its identity and the IDs it touched.

    ``affected_ids`` lists, once and in command order, every target, inserted and
    removed ID (a removed layer adds its operations). Indirect consumers (operations
    using a replaced colour) and the difference bbox are not computed here: they
    belong to the history manifest of ``project`` (ADR-024).
    """

    document: Document
    base_revision: int
    base_snapshot: str
    snapshot: str
    affected_ids: tuple[str, ...]

    @property
    def revision(self) -> int:
        """Revision of the new document: ``base_revision + 1``."""
        return self.document.revision

    def to_mapping(self) -> dict[str, object]:
        """JSON-ready summary with the normalised new document under ``document``."""
        return {
            "affected_ids": list(self.affected_ids),
            "base_revision": self.base_revision,
            "base_snapshot": self.base_snapshot,
            "document": normalize_document(self.document),
            "document_id": self.document.id,
            "revision": self.revision,
            "snapshot_digest": self.snapshot,
        }


@dataclass(slots=True)
class _Work:
    """State of one batch: the working tree and the IDs removed so far (local)."""

    tree: JsonObject
    removed: set[str] = field(default_factory=set)


class _Wrapper(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


class _OperationNode(_Wrapper):
    """One operation validated alone with the schema models."""

    node: Operation


class _MaskNode(_Wrapper):
    """One mask node validated alone with the schema models."""

    node: MaskNode


_WRAPPED: Final = "/node"
"""Pointer prefix of the wrapper member, removed from every reported pointer."""


# --- errors -------------------------------------------------------------------------


def _invalid(pointer: str, message: str, reason: str, **extra: object) -> ValidationError:
    return ValidationError(message, json_pointer=pointer, context={"reason": reason, **extra})


def _missing(pointer: str, message: str, reason: str) -> ReferenceError:
    return ReferenceError(message, json_pointer=pointer, context={"reason": reason})


def _relocated(details: list[ErrorDetail], prefix: str) -> list[ErrorDetail]:
    return [
        ErrorDetail(
            detail.code,
            detail.message,
            json_pointer=prefix + (detail.json_pointer or "").removeprefix(_WRAPPED),
            context=detail.context,
        )
        for detail in details
    ]


def _node_error(message: str, details: list[ErrorDetail]) -> MoanaError:
    codes = {detail.code for detail in details}
    kind = ValidationError if ValidationError.code in codes else UnsupportedOperation
    return kind(
        message,
        json_pointer=details[0].json_pointer,
        context={"reason": "invalid_node", "issue_count": len(details)},
        details=details,
    )


def _validated(
    wrapper: type[_Wrapper], candidate: JsonObject, message: str, prefix: str
) -> JsonObject:
    """Validate one node with the schema models; pointers are moved under ``prefix``."""
    tree = {"node": candidate}
    try:
        model = wrapper.model_validate(tree)
    except PydanticValidationError as exc:
        details = _relocated(pydantic_details(tree, exc.errors(include_url=False)), prefix)
        raise _node_error(message, details) from None
    dumped: JsonObject = model.model_dump(mode="json", exclude_none=True)["node"]
    return dumped


# --- lookup -------------------------------------------------------------------------


def _target(index: dict[str, Node], key: str, pointer: str, kinds: tuple[str, ...]) -> Node:
    node = index.get(key)
    if node is None:
        raise _missing(pointer, "target ID does not exist", "unknown_target")
    if node.kind not in kinds:
        raise _invalid(
            pointer, "target has the wrong kind", "invalid_target", kind=node.kind, expected=kinds
        )
    return node


def _unlocked(node: Node, pointer: str) -> Node:
    layer = node.owning_layer
    if layer is not None and layer["locked"]:
        raise _invalid(pointer, "the layer is locked", "locked_layer")
    return node


def _replace(node: Node, value: JsonObject) -> None:
    assert node.container is not None
    node.container[node.position] = value


def _color_ids(tree: JsonObject) -> set[str]:
    return {color["id"] for color in tree["palette"]["colors"]}


def _anchor(index: dict[str, Node], after_id: str | None, pointer: str, siblings: object) -> int:
    """Insertion index after ``after_id`` among ``siblings`` (``None``: the start)."""
    if after_id is None:
        return 0
    node = index.get(after_id)
    if node is None:
        raise _missing(pointer, "after_id does not exist", "unknown_target")
    if node.container is not siblings:
        raise _invalid(pointer, "after_id is not in the same container", "not_in_container")
    return node.position + 1


# --- geometry -----------------------------------------------------------------------


def _ints(value: object) -> list[int]:
    if not isinstance(value, list) or not all(type(item) is int for item in value):
        raise TypeError("geometric member is not an array of integers")
    return value


def _lists(value: object) -> list[list[object]]:
    if not isinstance(value, list) or not all(isinstance(item, list) for item in value):
        raise TypeError("geometric member is not an array of arrays")
    return value


def _shift(values: list[int], dx: int, dy: int) -> list[int]:
    """Shift a flat ``x, y, x, y...`` list."""
    return [value + (dx if position % 2 == 0 else dy) for position, value in enumerate(values)]


def _within(values: list[int], bounds: tuple[int, int]) -> bool:
    low, high = bounds
    return all(low <= value <= high for value in values)


def _moved(shape: Geometry, value: object, dx: int, dy: int) -> tuple[object, bool]:
    """The member moved by ``(dx, dy)`` pixels and whether it stays in range."""
    if shape == "point":
        point = _shift(_ints(value), dx, dy)
        return point, _within(point, _PIXEL_RANGE)
    if shape == "box":
        box = _shift(_ints(value), dx, dy)
        return box, _within(box[:2], _PIXEL_RANGE) and _within(box[2:], _EDGE_RANGE)
    if shape == "points":
        points = [_shift(_ints(point), dx, dy) for point in _lists(value)]
        return points, all(_within(point, _PIXEL_RANGE) for point in points)
    ux, uy = dx * PATH_UNITS, dy * PATH_UNITS
    commands = [(item[0], _shift(_ints(item[1:]), ux, uy)) for item in _lists(value)]
    moved = [[letter, *coordinates] for letter, coordinates in commands]
    return moved, all(_within(coordinates, _PATH_RANGE) for _, coordinates in commands)


# --- commands -----------------------------------------------------------------------


def _set_color(work: _Work, command: SetColor, pointer: str) -> tuple[str, ...]:
    node = _target(
        index_nodes(work.tree), command.target_id, f"{pointer}/target_id", ("operation",)
    )
    _unlocked(node, pointer)
    colors = node_members(node).colors
    if len(colors) != 1:
        raise _invalid(
            f"{pointer}/target_id",
            "the operation does not have exactly one colour reference",
            "multiple_colors",
            color_members=len(colors),
        )
    if command.color not in _color_ids(work.tree):
        raise _missing(f"{pointer}/color", "color does not exist in the palette", "unknown_color")
    node.value[colors[0]] = command.color
    return (command.target_id,)


def _adapter(node: Node) -> type[_Wrapper]:
    return _OperationNode if node.kind == "operation" else _MaskNode


def _geometric(work: _Work, target_id: str, pointer: str) -> tuple[Node, NodeMembers]:
    """An unlocked operation or mask whose type has geometric members."""
    node = _target(index_nodes(work.tree), target_id, f"{pointer}/target_id", _GEOMETRIC)
    members = node_members(_unlocked(node, pointer))
    if not members.geometry:
        raise _invalid(f"{pointer}/target_id", "the target type has no geometry", "not_geometric")
    return node, members


def _set_geometry(work: _Work, command: SetGeometry, pointer: str) -> tuple[str, ...]:
    node, row = _geometric(work, command.target_id, pointer)
    members = row.geometry
    if set(command.geometry) != set(members):
        raise _invalid(
            f"{pointer}/geometry",
            "geometry must hold exactly the geometric members of the target type",
            "geometry_members",
            expected=members,
        )
    candidate = {**node.value, **command.geometry}
    prefix = f"{pointer}/geometry"
    _replace(node, _validated(_adapter(node), candidate, "geometry is invalid", prefix))
    return (command.target_id,)


def _translate(work: _Work, command: Translate, pointer: str) -> tuple[str, ...]:
    node, row = _geometric(work, command.target_id, pointer)
    moved: JsonObject = {}
    for member in row.geometry:
        value, within = _moved(GEOMETRY_SHAPES[member], node.value[member], command.dx, command.dy)
        if not within:
            raise _invalid(
                pointer, "the translated geometry is out of range", "out_of_range", member=member
            )
        moved[member] = value
    node.value.update(moved)
    return (command.target_id,)


def _set_visibility(work: _Work, command: SetVisibility, pointer: str) -> tuple[str, ...]:
    node = _target(index_nodes(work.tree), command.target_id, f"{pointer}/target_id", ("layer",))
    _unlocked(node, pointer).value["visible"] = command.visible
    return (command.target_id,)


def _replace_color(work: _Work, command: ReplacePaletteColor, pointer: str) -> tuple[str, ...]:
    # A palette colour belongs to no layer: locked layers that use it change too.
    node = _target(index_nodes(work.tree), command.target_id, f"{pointer}/target_id", ("color",))
    node.value["rgba"] = command.rgba.upper()
    return (command.target_id,)


def _insert(work: _Work, command: InsertOperation, pointer: str) -> tuple[str, ...]:
    index = index_nodes(work.tree)
    layer = _unlocked(_target(index, command.layer_id, f"{pointer}/layer_id", ("layer",)), pointer)
    prefix = f"{pointer}/operation"
    operation = _validated(_OperationNode, command.operation, "operation is invalid", prefix)
    if operation["id"] in work.removed:
        raise _invalid(f"{prefix}/id", "ID was removed earlier in this batch", "reused_id")
    if operation["id"] in index:
        raise _invalid(f"{prefix}/id", "ID is already used", "duplicate_id")
    palette = _color_ids(work.tree)
    for member in OPERATION_MEMBERS[operation["type"]].colors:
        if operation[member] not in palette:
            raise _missing(
                f"{prefix}/{member}", "color does not exist in the palette", "unknown_color"
            )
    siblings = layer.value["operations"]
    siblings.insert(_anchor(index, command.after_id, f"{pointer}/after_id", siblings), operation)
    return (operation["id"],)


def _live_reference_error(pointer: str, references: list[str]) -> ReferenceError:
    details = [
        ErrorDetail(
            ReferenceError.code,
            "Reference to a node the batch removes",
            json_pointer=reference,
            context={"reason": "live_reference"},
        )
        for reference in references
    ]
    return ReferenceError(
        "the target is still referenced",
        json_pointer=f"{pointer}/target_id",
        context={"reason": "live_reference", "reference_count": len(details)},
        details=details,
    )


def _remove(work: _Work, command: Remove, pointer: str) -> tuple[str, ...]:
    node = _target(index_nodes(work.tree), command.target_id, f"{pointer}/target_id", _REMOVABLE)
    _unlocked(node, pointer)
    removed = (command.target_id,)
    if node.kind == "layer":
        removed += tuple(operation["id"] for operation in node.value["operations"])
    references = live_references(work.tree, frozenset(removed))
    if references:
        raise _live_reference_error(pointer, references)
    assert node.container is not None
    del node.container[node.position]
    work.removed.update(removed)
    return removed


def _reorder(work: _Work, command: Reorder, pointer: str) -> tuple[str, ...]:
    index = index_nodes(work.tree)
    node = _unlocked(_target(index, command.target_id, f"{pointer}/target_id", _REMOVABLE), pointer)
    if command.after_id == command.target_id:
        raise _invalid(f"{pointer}/after_id", "a node cannot follow itself", "after_self")
    siblings = node.container
    assert siblings is not None
    _anchor(index, command.after_id, f"{pointer}/after_id", siblings)
    siblings.pop(node.position)
    siblings.insert(_anchor(index, command.after_id, f"{pointer}/after_id", siblings), node.value)
    return (command.target_id,)


def _apply(work: _Work, command: object, pointer: str) -> tuple[str, ...]:
    match command:
        case SetColor():
            return _set_color(work, command, pointer)
        case SetGeometry():
            return _set_geometry(work, command, pointer)
        case Translate():
            return _translate(work, command, pointer)
        case SetVisibility():
            return _set_visibility(work, command, pointer)
        case ReplacePaletteColor():
            return _replace_color(work, command, pointer)
        case InsertOperation():
            return _insert(work, command, pointer)
        case Remove():
            return _remove(work, command, pointer)
        case Reorder():
            return _reorder(work, command, pointer)
        case _:
            raise _invalid(pointer, "command is not part of the edit catalogue", "unknown_command")


# --- batch --------------------------------------------------------------------------


def _check_base(document: Document, batch: EditBatch, current: str) -> None:
    context: dict[str, object] = {
        "current_revision": document.revision,
        "current_snapshot": current,
    }
    if batch.base_revision != document.revision:
        raise EditConflict(
            "the batch was written against another revision",
            json_pointer="/base_revision",
            context={"reason": "stale_revision", **context},
        )
    if batch.base_snapshot != current:
        raise EditConflict(
            "the batch was written against another snapshot of this revision",
            json_pointer="/base_snapshot",
            context={"reason": "snapshot_mismatch", **context},
        )
    if document.revision >= MAX_REVISION:
        raise _invalid(
            "/base_revision",
            "the document is at the last revision number",
            "revision_overflow",
            maximum=MAX_REVISION,
        )


def _revalidated(tree: JsonObject, limits: ParseLimits) -> Document:
    try:
        return validate_document(tree, limits=limits)
    except MoanaError as error:
        details = error.details or (
            ErrorDetail(
                error.code, error.message, json_pointer=error.json_pointer, context=error.context
            ),
        )
        raise type(error)(
            "the edited document is invalid",
            json_pointer=error.json_pointer,
            context={"reason": "invalid_result", "issue_count": len(details)},
            details=details,
        ) from None


def _applied(work: _Work, batch: EditBatch) -> tuple[str, ...]:
    """Apply every command in order; the IDs it touched, once each."""
    affected: list[str] = []
    pointer = "/commands"
    try:
        for position, command in enumerate(batch.commands):
            pointer = f"/commands/{position}"
            affected.extend(_apply(work, command, pointer))
    except (AttributeError, IndexError, KeyError, TypeError):
        # Only reachable with unvalidated models (``model_construct``) or documents.
        raise _invalid(
            pointer, "the batch or the document is malformed", "invalid_source"
        ) from None
    return tuple(dict.fromkeys(affected))


def apply_batch(
    document: Document,
    batch: BatchInput,
    *,
    limits: ParseLimits = DEFAULT_PARSE_LIMITS,
) -> EditResult:
    """Apply ``batch`` atomically to ``document`` and return the new revision.

    Raises ``EditConflict`` when ``base_revision`` or ``base_snapshot`` is not the
    document's; ``ValidationError``, ``ReferenceError``, ``UnsupportedOperation`` or
    ``UnsupportedVersion`` for an invalid batch, command or result (pointers locate
    the batch member, or the result document when ``reason`` is ``invalid_result``).
    ``limits`` bound reading the batch and validating the result.
    """
    if not isinstance(document, Document):
        raise TypeError("document must be a moana.schema.Document")
    if not isinstance(limits, ParseLimits):
        raise TypeError("limits must be a ParseLimits value")
    parsed = parse_edit_batch(batch, limits=limits)
    base = snapshot_digest(document)
    _check_base(document, parsed, base)
    work = _Work(normalize_document(document))
    affected = _applied(work, parsed)
    work.tree["revision"] = document.revision + 1
    edited = _revalidated(work.tree, limits)
    return EditResult(edited, document.revision, base, snapshot_digest(edited), affected)
