"""Validation pipeline, canonical normalisation and JSON Schema of documents.

Phases (MOANA.md sections 3, 12 and 20), each reported with its own error class:

1. **Read** — bounded bytes/mapping reading (:mod:`moana.schema._reader`).
2. **Version** — ``schema_version`` other than ``"1.0"`` raises ``UnsupportedVersion``
   through the registry of :mod:`moana.schema.versions` (ADR-031): ``future``,
   ``past`` or ``unknown`` versions, or ``migration_required`` for a registered older
   version; reading never migrates.
3. **Structure and capabilities** — strict models. Planned capabilities produce
   ``UNSUPPORTED_OPERATION`` details; any other problem makes it a ``ValidationError``.
4. **Semantics** — global ID uniqueness, profile and count limits (``VALIDATION_ERROR``),
   colour references (``REFERENCE_ERROR``) and the mask/region reference DAG
   (:mod:`moana.schema.references`: unknown references and cycles are
   ``REFERENCE_ERROR``; repeated references and excessive depth ``VALIDATION_ERROR``)
   and the animations (ADR-032): every override target names a layer, operation or
   mask (``unknown_target``), a ``set_color`` names a palette colour
   (``unknown_color``) and the pivot lies on the canvas (``pivot_out_of_canvas``).
   Whether a target has the right kind for its override is decided when the frame
   is evaluated, by the editor (:mod:`moana.animation`).

Every raised error lists all problems of its phase in ``details``, sorted by pointer
(array indexes compared numerically) and code; the error's own ``json_pointer`` is
the first detail's. Nothing in the document is executed, imported or opened.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator, Mapping
from typing import Final

from pydantic import ValidationError as PydanticValidationError

from moana.core.errors import (
    ErrorDetail,
    MoanaError,
    ReferenceError,
    UnsupportedOperation,
    ValidationError,
)
from moana.core.limits import MAX_COLORS_STRICT, MAX_OPERATIONS
from moana.schema._issues import pydantic_details
from moana.schema._pointers import detail_sort_key
from moana.schema._reader import DEFAULT_PARSE_LIMITS, ParseLimits, read_json_bytes, read_mapping
from moana.schema.capabilities import SCHEMA_VERSION
from moana.schema.members import OPERATION_MEMBERS
from moana.schema.models import Document, Operation, SetColorOverride
from moana.schema.references import reference_details
from moana.schema.versions import DOCUMENT_MIGRATIONS

__all__ = [
    "JSON_SCHEMA_DIALECT",
    "canonical_json",
    "document_ids",
    "document_json_schema",
    "normalize_document",
    "snapshot_digest",
    "validate_document",
]

JSON_SCHEMA_DIALECT: Final = "https://json-schema.org/draft/2020-12/schema"

# When one phase reports problems of several kinds, the most fundamental wins.
_PRECEDENCE: Final[tuple[type[MoanaError], ...]] = (
    ValidationError,
    UnsupportedOperation,
    ReferenceError,
)


def _raise_details(details: list[ErrorDetail]) -> None:
    if not details:
        return
    details.sort(key=detail_sort_key)
    codes = {detail.code for detail in details}
    error_type = next(kind for kind in _PRECEDENCE if kind.code in codes)
    count = len(details)
    raise error_type(
        f"document has {count} problem{'s' if count != 1 else ''}",
        json_pointer=details[0].json_pointer,
        context={"issue_count": count},
        details=details,
    )


def _identities(document: Document) -> Iterator[tuple[str, str]]:
    """Every declared ID with its pointer, in document order."""
    yield document.id, "/id"
    yield document.palette.id, "/palette/id"
    for index, color in enumerate(document.palette.colors):
        yield color.id, f"/palette/colors/{index}/id"
    for index, ramp in enumerate(document.palette.ramps):
        yield ramp.id, f"/palette/ramps/{index}/id"
    for layer_index, layer in enumerate(document.layers):
        yield layer.id, f"/layers/{layer_index}/id"
        for index, operation in enumerate(layer.operations):
            pointer = f"/layers/{layer_index}/operations/{index}"
            yield operation.id, f"{pointer}/id"
            for member, _ in OPERATION_MEMBERS[operation.type].items:
                for position, item in enumerate(getattr(operation, member)):
                    yield item.id, f"{pointer}/{member}/{position}/id"
    for index, mask in enumerate(document.masks):
        yield mask.id, f"/masks/{index}/id"
    for index, region in enumerate(document.regions):
        yield region.id, f"/regions/{index}/id"
    for animation_index, animation in enumerate(document.animations):
        yield animation.id, f"/animations/{animation_index}/id"
        for index, frame in enumerate(animation.frames):
            yield frame.id, f"/animations/{animation_index}/frames/{index}/id"


def document_ids(document: Document) -> frozenset[str]:
    """Every ID declared by ``document``: palette, colours, ramps, layers, operations,
    operation items such as ``shade`` bands (ADR-028), masks, regions, animations and
    frames (ADR-032).

    IDs are global (MOANA.md section 12), so this is the namespace a new ID must avoid.
    """
    return frozenset(identifier for identifier, _ in _identities(document))


def _color_references(operation: Operation) -> tuple[tuple[str, str], ...]:
    """``(member, colour ID)`` of every palette reference of ``operation``."""
    members = OPERATION_MEMBERS[operation.type].colors
    return tuple((member, str(getattr(operation, member))) for member in members)


def _animation_details(document: Document, color_ids: set[str]) -> Iterator[ErrorDetail]:
    """Override references and pivots of every animation (ADR-032)."""
    targets = {layer.id for layer in document.layers}
    targets.update(operation.id for layer in document.layers for operation in layer.operations)
    targets.update(mask.id for mask in document.masks)
    width, height = document.canvas.width, document.canvas.height
    for animation_index, animation in enumerate(document.animations):
        prefix = f"/animations/{animation_index}"
        x, y = animation.pivot
        if not (0 <= x <= width and 0 <= y <= height):
            yield ErrorDetail(
                ValidationError.code,
                "Pivot must lie on the canvas",
                json_pointer=f"{prefix}/pivot",
                context={"reason": "pivot_out_of_canvas", "width": width, "height": height},
            )
        for frame_index, frame in enumerate(animation.frames):
            for index, override in enumerate(frame.overrides):
                pointer = f"{prefix}/frames/{frame_index}/overrides/{index}"
                if override.target_id not in targets:
                    yield ErrorDetail(
                        ReferenceError.code,
                        "Override target does not exist",
                        json_pointer=f"{pointer}/target_id",
                        context={"reason": "unknown_target"},
                    )
                if isinstance(override, SetColorOverride) and override.color not in color_ids:
                    yield ErrorDetail(
                        ReferenceError.code,
                        "Referenced color does not exist in the palette",
                        json_pointer=f"{pointer}/color",
                        context={"reason": "unknown_color"},
                    )


def _semantic_details(document: Document) -> list[ErrorDetail]:
    details: list[ErrorDetail] = []

    def invalid(pointer: str, message: str, reason: str, **extra: object) -> None:
        details.append(
            ErrorDetail(
                ValidationError.code,
                message,
                json_pointer=pointer,
                context={"reason": reason, **extra},
            )
        )

    def missing_color(pointer: str) -> None:
        details.append(
            ErrorDetail(
                ReferenceError.code,
                "Referenced color does not exist in the palette",
                json_pointer=pointer,
                context={"reason": "unknown_color"},
            )
        )

    first_seen: dict[str, str] = {}
    for identifier, pointer in _identities(document):
        if identifier in first_seen:
            invalid(pointer, "ID is already used", "duplicate_id", first=first_seen[identifier])
        else:
            first_seen[identifier] = pointer

    palette = document.palette
    color_ids = {color.id for color in palette.colors}
    for ramp_index, ramp in enumerate(palette.ramps):
        seen: set[str] = set()
        for index, color_id in enumerate(ramp.colors):
            pointer = f"/palette/ramps/{ramp_index}/colors/{index}"
            if color_id not in color_ids:
                missing_color(pointer)
            elif color_id in seen:
                invalid(pointer, "Ramp repeats a color", "duplicate_ramp_color")
            seen.add(color_id)

    ramp_ids = {ramp.id for ramp in palette.ramps}
    total_operations = 0
    for layer_index, layer in enumerate(document.layers):
        total_operations += len(layer.operations)
        for index, operation in enumerate(layer.operations):
            pointer = f"/layers/{layer_index}/operations/{index}"
            for member, color_id in _color_references(operation):
                if color_id not in color_ids:
                    missing_color(f"{pointer}/{member}")
            for member in OPERATION_MEMBERS[operation.type].ramps:
                if getattr(operation, member) not in ramp_ids:
                    details.append(
                        ErrorDetail(
                            ReferenceError.code,
                            "Referenced ramp does not exist in the palette",
                            json_pointer=f"{pointer}/{member}",
                            context={"reason": "unknown_ramp"},
                        )
                    )
    if total_operations > MAX_OPERATIONS:
        invalid("/layers", "Document has too many operations", "too_many", maximum=MAX_OPERATIONS)

    details.extend(reference_details(document))
    details.extend(_animation_details(document, color_ids))
    if document.canvas.profile == "strict":
        details.extend(_strict_profile_details(document))
    return details


def _strict_profile_details(document: Document) -> Iterator[ErrorDetail]:
    """Strict profile: alpha in {0, 255}, opaque layers, at most 256 colors."""

    def strict(pointer: str, message: str, reason: str, **extra: int) -> ErrorDetail:
        return ErrorDetail(
            ValidationError.code,
            message,
            json_pointer=pointer,
            context={"reason": reason, "profile": "strict", **extra},
        )

    colors = document.palette.colors
    if len(colors) > MAX_COLORS_STRICT:
        yield strict("/palette/colors", "Too many colors", "too_many", maximum=MAX_COLORS_STRICT)
    for index, color in enumerate(colors):
        if color.rgba[7:] not in {"00", "FF"}:
            yield strict(f"/palette/colors/{index}/rgba", "Alpha must be 00 or FF", "partial_alpha")
    for index, layer in enumerate(document.layers):
        if layer.opacity != 255:
            yield strict(f"/layers/{index}/opacity", "Opacity must be 255", "partial_opacity")


def validate_document(
    source: bytes | Mapping[str, object], *, limits: ParseLimits = DEFAULT_PARSE_LIMITS
) -> Document:
    """Validate and normalise an untrusted document from JSON bytes or a mapping.

    Raises ``ValidationError``, ``UnsupportedVersion``, ``UnsupportedOperation`` or
    ``ReferenceError`` (see the module docstring for the phases). A ``str`` is not
    accepted: callers decide whether text is a path or JSON before reaching schema.
    """
    if isinstance(source, bytes):
        tree = read_json_bytes(source, limits)
    else:
        tree = read_mapping(source, limits)
    DOCUMENT_MIGRATIONS.check(tree)
    try:
        document = Document.model_validate(tree)
    except PydanticValidationError as exc:
        _raise_details(pydantic_details(tree, exc.errors(include_url=False)))
        raise  # pragma: no cover - Pydantic always reports at least one error
    _raise_details(_semantic_details(document))
    return document


def normalize_document(document: Document) -> dict[str, object]:
    """Canonical JSON tree: defaults materialised, ``null`` members omitted."""
    return document.model_dump(mode="json", exclude_none=True)


def canonical_json(document: Document) -> bytes:
    """Canonical encoding of section 14: sorted keys, no spaces, UTF-8, no floats."""
    return json.dumps(
        normalize_document(document),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def snapshot_digest(document: Document) -> str:
    """``sha256:<hex>`` of :func:`canonical_json`; identifies a snapshot (ADR-007)."""
    return "sha256:" + hashlib.sha256(canonical_json(document)).hexdigest()


def _without_null_defaults(node: dict[str, object]) -> dict[str, object]:
    """Drop ``"default": null``: optional members are omitted, and null is rejected."""
    cleaned: dict[str, object] = {}
    for key, value in node.items():
        if key == "default" and value is None:
            continue
        cleaned[key] = _without_null_defaults(value) if isinstance(value, dict) else value
    return cleaned


def document_json_schema() -> dict[str, object]:
    """JSON Schema (2020-12) of schema 1.0, generated from the models.

    It describes structure only. Duplicate member names, global ID uniqueness, colour
    references, profile rules and byte/depth/node limits are enforced by
    :func:`validate_document` and stated in the schema description.
    """
    schema = _without_null_defaults(Document.model_json_schema(mode="validation"))
    schema["$schema"] = JSON_SCHEMA_DIALECT
    schema["$id"] = f"moana-document-{SCHEMA_VERSION}.schema.json"
    schema["title"] = f"Moana document {SCHEMA_VERSION}"
    schema["description"] = (
        "Structural schema of a Moana sprite document. validate_document also rejects "
        "duplicate member names, NaN/Infinity, documents over 8 MiB, deeper than 32 or "
        "with more than 20000 nodes, repeated IDs, unknown color references, more than "
        "10000 operations, strict-profile violations (alpha other than 00/FF, layer "
        "opacity other than 255, more than 256 colors), unknown or repeated mask, "
        "region and operation references, mask reference cycles and mask reference "
        "chains longer than 16."
    )
    return schema
