"""Typed edit batches of MOANA.md section 15 and their bounded parsing (ADR-024).

An :class:`EditBatch` names the exact base it was written against
(``base_revision`` and ``base_snapshot``) and lists the typed commands of the
section 15 catalogue, in order. Nothing else is accepted: there is no generic JSON
Patch, no command that rewrites ``id``, ``schema_version`` or ``revision``, and no
dynamic import. Batches from bytes or mappings go through the same bounded reader as
documents (8 MiB, depth 32, 20 000 nodes) before the strict models see them.

``set_parameters`` (ADR-030) replaces plain value members of an operation that the
type table lists as ``parameters`` (a light, ``ramp_order``, a material's
``density``/``scale``/``origin``, an outline width...), so a material or a light is
tuned without replacing the operation and its IDs.

``geometry`` (``set_geometry``), ``parameters`` (``set_parameters``) and
``operation`` (``insert_operation``) are plain
JSON objects here: their grammar depends on the target, so they are validated with
the schema models when the command is applied, with pointers inside the command.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from types import MappingProxyType
from typing import Annotated, Final, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints
from pydantic import ValidationError as PydanticValidationError
from pydantic_core import ErrorDetails, PydanticCustomError

from moana.core import ids
from moana.core.coordinates import MAX_COORDINATE
from moana.core.errors import ErrorDetail, UnsupportedVersion, ValidationError
from moana.core.limits import MAX_EDIT_COMMANDS
from moana.editing._tree import JsonObject
from moana.schema import (
    DEFAULT_PARSE_LIMITS,
    SCHEMA_VERSION,
    SUPPORTED_SCHEMA_VERSIONS,
    ParseLimits,
)
from moana.schema._issues import pointer_for
from moana.schema._pointers import detail_sort_key
from moana.schema._reader import read_json_bytes, read_mapping
from moana.schema.models import MAX_REVISION

__all__ = [
    "COMMAND_TYPES",
    "MAX_TRANSLATION",
    "SNAPSHOT_PATTERN",
    "BatchInput",
    "EditBatch",
    "EditCommand",
    "InsertOperation",
    "Remove",
    "Reorder",
    "ReplacePaletteColor",
    "SetColor",
    "SetGeometry",
    "SetParameters",
    "SetVisibility",
    "Translate",
    "parse_edit_batch",
]

SNAPSHOT_PATTERN: Final = r"^sha256:[0-9a-f]{64}$"
"""``base_snapshot``: ``sha256:`` and the lower-case hex digest of section 14."""

MAX_TRANSLATION: Final = 2 * MAX_COORDINATE + 1
"""Largest ``|dx|``/``|dy|`` of ``translate``: any wider shift leaves every range."""

COMMAND_TYPES: Final = (
    "insert_operation",
    "remove",
    "reorder",
    "replace_palette_color",
    "set_color",
    "set_geometry",
    "set_parameters",
    "set_visibility",
    "translate",
)
"""The section 15 catalogue plus ``set_parameters`` (ADR-030); nothing else is a
command."""


def _command_array(value: object) -> object:
    """Array to tuple, rejecting an empty batch before reading any command.

    ``min_length`` would count only the commands that validated, and report an empty
    batch next to the real error of an invalid command.
    """
    value = tuple(value) if isinstance(value, list) else value
    if value == ():
        raise PydanticCustomError("too_short", "A batch should have at least 1 command")
    return value


Id = Annotated[str, StringConstraints(pattern=ids.ID_PATTERN)]
Shift = Annotated[int, Field(ge=-MAX_TRANSLATION, le=MAX_TRANSLATION)]


class _Command(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


class SetColor(_Command):
    """Point an operation at another palette colour (its reference only)."""

    type: Literal["set_color"]
    target_id: Id
    color: Id


class SetGeometry(_Command):
    """Replace every geometric member of an operation or mask leaf.

    ``geometry`` holds exactly the geometric members of the target's type in the
    editor's type table (``at``, ``start``/``end``, ``box``, ``points``,
    ``commands``...). Type, colours, mask references and backend are not geometry.
    """

    type: Literal["set_geometry"]
    target_id: Id
    geometry: JsonObject


class SetParameters(_Command):
    """Replace parameter members of an operation in place (ADR-030).

    ``parameters`` holds one or more members that the target type lists as
    ``parameters`` in the type table; IDs, references, items and geometry are never
    parameters. The patched operation is validated with the schema models.
    """

    type: Literal["set_parameters"]
    target_id: Id
    parameters: JsonObject


class Translate(_Command):
    """Move an operation or mask leaf by whole pixels (paths by ``256·d`` units)."""

    type: Literal["translate"]
    target_id: Id
    dx: Shift
    dy: Shift


class SetVisibility(_Command):
    """Show or hide a layer."""

    type: Literal["set_visibility"]
    target_id: Id
    visible: bool


class ReplacePaletteColor(_Command):
    """Change the value of a palette colour; every consumer sees the new value."""

    type: Literal["replace_palette_color"]
    target_id: Id
    rgba: Annotated[str, StringConstraints(pattern=ids.RGBA_HEX_PATTERN)]


class InsertOperation(_Command):
    """Insert a new operation into a layer after ``after_id`` (``null``: first)."""

    type: Literal["insert_operation"]
    layer_id: Id
    after_id: Id | None
    operation: JsonObject


class Remove(_Command):
    """Remove an operation, layer, mask, region, colour or ramp nobody references."""

    type: Literal["remove"]
    target_id: Id


class Reorder(_Command):
    """Move a node after ``after_id`` of the same container (``null``: first)."""

    type: Literal["reorder"]
    target_id: Id
    after_id: Id | None


EditCommand = Annotated[
    SetColor
    | SetGeometry
    | SetParameters
    | Translate
    | SetVisibility
    | ReplacePaletteColor
    | InsertOperation
    | Remove
    | Reorder,
    Field(discriminator="type"),
]
"""Commands of section 15, discriminated by ``type``."""


class EditBatch(_Command):
    """Ordered commands applied atomically to one exact base document.

    The model is frozen, but freezing is shallow: ``geometry`` and ``operation``
    payloads are plain ``dict`` values. They are never trusted as validated: the
    editor copies and validates them with the schema models when it applies them.
    """

    schema_version: Literal["1.0"]
    base_revision: Annotated[int, Field(ge=0, le=MAX_REVISION)]
    base_snapshot: Annotated[str, StringConstraints(pattern=SNAPSHOT_PATTERN)]
    commands: Annotated[
        tuple[EditCommand, ...],
        Field(max_length=MAX_EDIT_COMMANDS, json_schema_extra={"minItems": 1}),
        BeforeValidator(_command_array),
    ]


type BatchInput = EditBatch | bytes | Mapping[str, object]
"""A batch value, UTF-8 JSON bytes or an already parsed mapping."""

_OWN_MESSAGES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "union_tag_invalid": "Command type is not part of the edit catalogue",
        "union_tag_not_found": "Command requires a 'type' member",
    }
)


def _safe_context(error: ErrorDetails) -> dict[str, object]:
    context: dict[str, object] = {"reason": error["type"]}
    if error["type"] in _OWN_MESSAGES:
        context["expected"] = COMMAND_TYPES
    for key, value in (error.get("ctx") or {}).items():
        if isinstance(value, int) and not isinstance(value, bool):
            context[key] = value
    return context


def _batch_details(tree: object, errors: Iterable[ErrorDetails]) -> list[ErrorDetail]:
    """Located details that never echo untrusted strings (tags, IDs, colours)."""
    details: list[ErrorDetail] = []
    for error in errors:
        pointer = pointer_for(tree, error["loc"])
        if error["type"] == "union_tag_invalid":
            pointer += "/type"
        message = _OWN_MESSAGES.get(error["type"], error["msg"])
        details.append(
            ErrorDetail(
                ValidationError.code, message, json_pointer=pointer, context=_safe_context(error)
            )
        )
    details.sort(key=detail_sort_key)
    return details


def _check_version(tree: Mapping[str, object]) -> None:
    version = tree.get("schema_version")
    if isinstance(version, str) and version not in SUPPORTED_SCHEMA_VERSIONS:
        raise UnsupportedVersion(
            "edit batch schema_version is not supported by this reader",
            json_pointer="/schema_version",
            context={"reason": "unsupported_version", "supported": (SCHEMA_VERSION,)},
        )


def _read(source: bytes | Mapping[str, object], limits: ParseLimits) -> dict[str, object]:
    """The bounded reader of documents; its messages name the edit batch instead."""
    try:
        if isinstance(source, bytes):
            return read_json_bytes(source, limits)
        return read_mapping(source, limits)
    except ValidationError as error:
        raise ValidationError(
            error.message.replace("document", "edit batch", 1),
            json_pointer=error.json_pointer,
            context=error.context,
            details=error.details,
        ) from None


def parse_edit_batch(
    source: BatchInput, *, limits: ParseLimits = DEFAULT_PARSE_LIMITS
) -> EditBatch:
    """Validate an untrusted batch from UTF-8 JSON bytes or a mapping.

    An :class:`EditBatch` is returned as is. Raises ``ValidationError`` (bounded
    reading, structure; every problem in ``details``) or ``UnsupportedVersion``.
    """
    if isinstance(source, EditBatch):
        return source
    if not isinstance(source, bytes | Mapping):
        raise TypeError("batch must be an EditBatch, bytes or a mapping")
    tree = _read(source, limits)
    _check_version(tree)
    try:
        return EditBatch.model_validate(tree)
    except PydanticValidationError as exc:
        details = _batch_details(tree, exc.errors(include_url=False))
        raise ValidationError(
            f"edit batch has {len(details)} problem{'s' if len(details) != 1 else ''}",
            json_pointer=details[0].json_pointer,
            context={"issue_count": len(details)},
            details=details,
        ) from None
