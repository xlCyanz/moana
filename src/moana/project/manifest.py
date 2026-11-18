"""The ``project.moana.json`` envelope, separate from ``Document`` (MOANA.md section 16).

``{kind: "moana-project", project_version: "1.0", document, assets, history}``: the
reader distinguishes the envelope by ``kind`` and applies its own strict model with
``extra='forbid'``; ``Document`` and its JSON Schema are unchanged, and the embedded
document is validated by :func:`moana.schema.validate_document` with its own limits.

* :class:`AssetRef`: ``id`` (document ID grammar), ``path`` (always the immutable
  ``assets/<sha256>.png``), ``mime`` (``image/png``), ``byte_length`` and ``sha256``.
* :class:`HistoryEntry`: ``snapshot`` and ``parent`` digests (``sha256:<hex>``,
  ``parent`` ``null`` only at the root), ``batch`` (``sha256:<hex>`` of the canonical
  batch file, ``null`` only at the root) and ``redo`` (whether it is the active redo
  child of its parent). Entries keep the insertion order of the history, so a parent
  always precedes its children; the cursor is the embedded document.

Errors are ``ValidationError`` (``invalid_manifest``) with one detail per problem; a
pointer names only members of the envelope, never an unknown member name.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any, Final, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)
from pydantic import ValidationError as PydanticValidationError

from moana.core.errors import ErrorDetail, MoanaError, ValidationError
from moana.core.ids import ID_PATTERN
from moana.project.assets import asset_path
from moana.schema import Document, ParseLimits, validate_document

__all__ = [
    "MANIFEST_NAME",
    "PROJECT_KIND",
    "PROJECT_VERSION",
    "AssetRef",
    "HistoryEntry",
    "ProjectManifest",
    "parse_manifest",
]

MANIFEST_NAME: Final = "project.moana.json"
PROJECT_KIND: Final = "moana-project"
PROJECT_VERSION: Final = "1.0"

_HEX: Final = r"^[0-9a-f]{64}$"
_DIGEST: Final = r"^sha256:[0-9a-f]{64}$"

Digest = Annotated[str, StringConstraints(pattern=_DIGEST)]


def _as_tuple(value: object) -> object:
    return tuple(value) if isinstance(value, list) else value


class AssetRef(BaseModel):
    """One declared asset; its path is derived from its hash and never chosen."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    id: Annotated[str, StringConstraints(pattern=ID_PATTERN)]
    path: str
    mime: Literal["image/png"]
    byte_length: Annotated[int, Field(ge=1)]
    sha256: Annotated[str, StringConstraints(pattern=_HEX)]

    @model_validator(mode="after")
    def _immutable_path(self) -> AssetRef:
        if self.path != asset_path(self.sha256):
            raise ValueError("path must be assets/<sha256>.png")
        return self


class HistoryEntry(BaseModel):
    """One persisted snapshot of the history, in insertion order."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    snapshot: Digest
    parent: Digest | None
    batch: Digest | None
    redo: bool

    @model_validator(mode="after")
    def _root_shape(self) -> HistoryEntry:
        if (self.parent is None) != (self.batch is None):
            raise ValueError("only the root has neither parent nor batch")
        if self.parent is None and self.redo:
            raise ValueError("the root is not a redo child")
        return self


class ProjectManifest(BaseModel):
    """The envelope of a project; ``document`` is a validated :class:`Document`."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    kind: Literal["moana-project"]
    project_version: Literal["1.0"]
    document: Document
    # Counts and sizes are budgets (``ProjectLimits``, ``BudgetExceeded``), checked by
    # the loader; the manifest reader already bounds the nodes of these arrays.
    assets: Annotated[tuple[AssetRef, ...], BeforeValidator(_as_tuple)]
    history: Annotated[tuple[HistoryEntry, ...], BeforeValidator(_as_tuple)] = ()

    def to_tree(self) -> dict[str, Any]:
        """JSON tree of the envelope with the normalised document (section 14)."""
        return self.model_dump(mode="json", exclude_none=False) | {
            "document": self.document.model_dump(mode="json", exclude_none=True)
        }


_KNOWN_MEMBERS: Final = frozenset(
    set(ProjectManifest.model_fields) | set(AssetRef.model_fields) | set(HistoryEntry.model_fields)
)


def _pointer(location: tuple[int | str, ...]) -> str:
    """RFC 6901 pointer over envelope members and indexes only."""
    tokens: list[str] = []
    for item in location:
        if isinstance(item, int):
            tokens.append(str(item))
        elif item in _KNOWN_MEMBERS:
            tokens.append(item)
        else:
            break
    return "".join(f"/{token}" for token in tokens)


def _relocated(error: MoanaError) -> MoanaError:
    """The same error with every pointer under ``/document``."""

    def moved(pointer: str | None) -> str | None:
        return None if pointer is None else f"/document{pointer}"

    details = [
        ErrorDetail(d.code, d.message, json_pointer=moved(d.json_pointer), context=d.context)
        for d in error.details
    ]
    return type(error)(
        error.message,
        json_pointer=moved(error.json_pointer),
        context=error.context,
        details=details,
    )


def _invalid(message: str, details: list[ErrorDetail] | None = None) -> ValidationError:
    pointer = details[0].json_pointer if details else ""
    return ValidationError(
        message,
        json_pointer=pointer,
        context={"reason": "invalid_manifest", "issue_count": len(details or ())},
        details=details or (),
    )


def parse_manifest(tree: object, *, limits: ParseLimits) -> ProjectManifest:
    """Validate an envelope tree: the document with ``limits``, then the envelope.

    Document errors keep their codes with pointers under ``/document``.
    """
    if not isinstance(tree, Mapping):
        raise _invalid("the project manifest must be a JSON object")
    values = dict(tree)
    if values.get("kind") != PROJECT_KIND:
        raise _invalid(
            "the project manifest has no supported kind",
            [ErrorDetail(ValidationError.code, "unsupported kind", json_pointer="/kind")],
        )
    document = values.get("document")
    if isinstance(document, Mapping):
        try:
            values["document"] = validate_document(document, limits=limits)
        except MoanaError as exc:
            raise _relocated(exc) from exc
    try:
        return ProjectManifest.model_validate(values)
    except PydanticValidationError as exc:
        details = [
            ErrorDetail(
                ValidationError.code,
                "invalid project manifest member",
                json_pointer=_pointer(tuple(error["loc"])),
                context={"reason": error["type"]},
            )
            for error in exc.errors(include_url=False)
        ]
        raise _invalid("the project manifest is invalid", details) from None
