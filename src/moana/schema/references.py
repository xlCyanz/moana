"""Resolution of mask and region references as a DAG (MOANA.md section 11, ADR-022).

Masks reference other masks by ID, layers reference a mask through ``mask_id`` and
regions reference a mask and, optionally, operations. :func:`reference_details`
checks every reference of a structurally valid document before any raster:

* an operand, ``mask_id`` (of a layer or of a ``dither`` operation, ADR-025) or
  region mask that names no mask is ``REFERENCE_ERROR``
  (``unknown_mask``), and a region operation that names no operation is
  ``unknown_operation``; a repeated operand or region operation is a
  ``VALIDATION_ERROR`` (``duplicate_reference``), since it has no meaning of its own;
* every operand edge inside a cycle (direct, ``a -> a``, or indirect) is
  ``REFERENCE_ERROR`` (``mask_cycle``), located at ``/masks/i/masks/j``;
* once acyclic, a mask whose longest reference chain exceeds
  :data:`~moana.core.limits.MAX_MASK_DEPTH` is ``VALIDATION_ERROR`` (``too_deep``).

Everything depends on IDs, never on array order or on the colour of a rendered
layer: masks may reference masks declared later. Traversals follow the operand
arrays, so results are deterministic. :func:`resolve_region` returns what an agent
needs to target a region ("the left eye") by ID.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from moana.core.errors import ErrorDetail, ReferenceError, ValidationError
from moana.core.limits import MAX_MASK_DEPTH
from moana.schema.members import OPERATION_MEMBERS
from moana.schema.models import CombinationMask, Document, MaskNode

__all__ = ["ResolvedRegion", "mask_dependencies", "reference_details", "resolve_region"]


@dataclass(frozen=True, slots=True)
class ResolvedRegion:
    """A region resolved by ID: its mask, the masks it depends on and its operations.

    ``mask_ids`` lists the mask and every mask it references, operands before the
    masks that use them, each once (the order in which they can be evaluated).
    ``layer_ids`` lists, in document order, the layers holding ``operation_ids``.
    """

    region_id: str
    mask_id: str
    mask_ids: tuple[str, ...]
    operation_ids: tuple[str, ...]
    layer_ids: tuple[str, ...]


def _operands(mask: MaskNode) -> tuple[str, ...]:
    return mask.masks if isinstance(mask, CombinationMask) else ()


def _reference(pointer: str, message: str, reason: str) -> ErrorDetail:
    return ErrorDetail(
        ReferenceError.code, message, json_pointer=pointer, context={"reason": reason}
    )


def _duplicate(pointer: str) -> ErrorDetail:
    return ErrorDetail(
        ValidationError.code,
        "Reference is repeated",
        json_pointer=pointer,
        context={"reason": "duplicate_reference"},
    )


def _unknown_mask(pointer: str) -> ErrorDetail:
    return _reference(pointer, "Referenced mask does not exist", "unknown_mask")


def _edge_details(masks: tuple[MaskNode, ...], index: dict[str, int]) -> Iterator[ErrorDetail]:
    """Unknown and repeated operands of every combination."""
    for mask_index, mask in enumerate(masks):
        seen: set[str] = set()
        for position, operand in enumerate(_operands(mask)):
            pointer = f"/masks/{mask_index}/masks/{position}"
            if operand not in index:
                yield _unknown_mask(pointer)
            elif operand in seen:
                yield _duplicate(pointer)
            seen.add(operand)


def _components(masks: tuple[MaskNode, ...], index: dict[str, int]) -> list[int]:
    """Strongly connected component of every mask (iterative Tarjan, array order)."""
    count = len(masks)
    order = [-1] * count
    low = [0] * count
    component = [-1] * count
    on_stack = [False] * count
    stack: list[int] = []
    counter = components = 0
    for start in range(count):
        if order[start] != -1:
            continue
        work: list[tuple[int, int]] = [(start, 0)]
        order[start] = low[start] = counter
        counter += 1
        stack.append(start)
        on_stack[start] = True
        while work:
            node, position = work[-1]
            operands = _operands(masks[node])
            if position < len(operands):
                work[-1] = (node, position + 1)
                target = index.get(operands[position])
                if target is None:
                    continue
                if order[target] == -1:
                    order[target] = low[target] = counter
                    counter += 1
                    stack.append(target)
                    on_stack[target] = True
                    work.append((target, 0))
                elif on_stack[target]:
                    low[node] = min(low[node], order[target])
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == order[node]:
                while True:
                    member = stack.pop()
                    on_stack[member] = False
                    component[member] = components
                    if member == node:
                        break
                components += 1
    return component


def _cycle_details(
    masks: tuple[MaskNode, ...], index: dict[str, int], component: list[int]
) -> Iterator[ErrorDetail]:
    """Every operand edge whose ends share a component: it closes a cycle."""
    for mask_index, mask in enumerate(masks):
        for position, operand in enumerate(_operands(mask)):
            target = index.get(operand)
            if target is not None and component[target] == component[mask_index]:
                yield _reference(
                    f"/masks/{mask_index}/masks/{position}",
                    "Mask references form a cycle",
                    "mask_cycle",
                )


def _depths(masks: tuple[MaskNode, ...], index: dict[str, int]) -> list[int]:
    """Longest reference chain of every mask of an acyclic graph (a leaf is 1)."""
    depth = [0] * len(masks)
    for start in range(len(masks)):
        work: list[tuple[int, bool]] = [(start, False)]
        while work:
            node, ready = work.pop()
            if depth[node]:
                continue
            targets = [index[name] for name in _operands(masks[node]) if name in index]
            if ready:
                depth[node] = 1 + max((depth[target] for target in targets), default=0)
            else:
                work.append((node, True))
                work.extend((target, False) for target in reversed(targets) if not depth[target])
    return depth


def _mask_details(document: Document, index: dict[str, int]) -> list[ErrorDetail]:
    masks = document.masks
    details = list(_edge_details(masks, index))
    cycles = list(_cycle_details(masks, index, _components(masks, index)))
    details.extend(cycles)
    if not cycles:
        for mask_index, depth in enumerate(_depths(masks, index)):
            if depth == MAX_MASK_DEPTH + 1:  # every deeper chain passes through one
                details.append(
                    ErrorDetail(
                        ValidationError.code,
                        "Mask references are nested too deeply",
                        json_pointer=f"/masks/{mask_index}",
                        context={"reason": "too_deep", "maximum": MAX_MASK_DEPTH},
                    )
                )
    return details


def _operation_layers(document: Document) -> dict[str, str]:
    return {operation.id: layer.id for layer in document.layers for operation in layer.operations}


def reference_details(document: Document) -> list[ErrorDetail]:
    """Every mask/region reference problem of ``document``, located by pointer."""
    index = {mask.id: position for position, mask in enumerate(document.masks)}
    details = _mask_details(document, index)
    for layer_index, layer in enumerate(document.layers):
        if layer.mask_id is not None and layer.mask_id not in index:
            details.append(_unknown_mask(f"/layers/{layer_index}/mask_id"))
        for position, operation in enumerate(layer.operations):
            for member in OPERATION_MEMBERS[operation.type].masks:
                if getattr(operation, member) not in index:
                    pointer = f"/layers/{layer_index}/operations/{position}/{member}"
                    details.append(_unknown_mask(pointer))
    operations = _operation_layers(document)
    for region_index, region in enumerate(document.regions):
        if region.mask_id not in index:
            details.append(_unknown_mask(f"/regions/{region_index}/mask_id"))
        seen: set[str] = set()
        for position, operation_id in enumerate(region.operation_ids):
            pointer = f"/regions/{region_index}/operation_ids/{position}"
            if operation_id not in operations:
                details.append(
                    _reference(pointer, "Referenced operation does not exist", "unknown_operation")
                )
            elif operation_id in seen:
                details.append(_duplicate(pointer))
            seen.add(operation_id)
    return details


def _missing(field: str, message: str, reason: str) -> ReferenceError:
    return ReferenceError(message, context={"field": field, "reason": reason})


def mask_dependencies(document: Document, mask_id: str) -> tuple[str, ...]:
    """``mask_id`` and every mask it references, operands first, each once.

    ``document`` should be valid (see :func:`moana.schema.validate_document`). An
    unknown ``mask_id`` or operand raises ``ReferenceError`` (``unknown_mask``) and,
    for a document that skipped validation, a cycle raises ``ReferenceError``
    (``mask_cycle``) instead of looping; time is linear in the references.
    """
    masks = {mask.id: mask for mask in document.masks}
    if type(mask_id) is not str or mask_id not in masks:
        raise _missing("mask_id", "mask does not exist", "unknown_mask")
    order: list[str] = []
    placed: set[str] = set()
    expanding: set[str] = set()  # the current path; membership only, never order
    work: list[tuple[str, bool]] = [(mask_id, False)]
    while work:
        name, ready = work.pop()
        if name in placed:
            continue
        if ready:
            expanding.discard(name)
            placed.add(name)
            order.append(name)
            continue
        if name not in masks:
            raise _missing("masks", "mask does not exist", "unknown_mask")
        if name in expanding:
            raise _missing("masks", "mask references form a cycle", "mask_cycle")
        expanding.add(name)
        work.append((name, True))
        work.extend((operand, False) for operand in reversed(_operands(masks[name])))
    return tuple(order)


def resolve_region(document: Document, region_id: str) -> ResolvedRegion:
    """Resolve a region by ID; ``ReferenceError`` (``unknown_region``) if it is absent.

    ``document`` should be valid; a region of an unvalidated document with a missing
    operation raises ``ReferenceError`` (``unknown_operation``) and a missing or
    cyclic mask reference behaves as in :func:`mask_dependencies`.
    """
    if not isinstance(document, Document):
        raise TypeError("document must be a moana.schema.Document")
    region = next((r for r in document.regions if r.id == region_id), None)
    if region is None or type(region_id) is not str:
        raise ReferenceError(
            "region does not exist", context={"field": "region_id", "reason": "unknown_region"}
        )
    owners = _operation_layers(document)
    if any(operation_id not in owners for operation_id in region.operation_ids):
        raise _missing("operation_ids", "operation does not exist", "unknown_operation")
    wanted = {owners[operation_id] for operation_id in region.operation_ids}
    return ResolvedRegion(
        region_id=region.id,
        mask_id=region.mask_id,
        mask_ids=mask_dependencies(document, region.mask_id),
        operation_ids=region.operation_ids,
        layer_ids=tuple(layer.id for layer in document.layers if layer.id in wanted),
    )
