"""The ``project.moanart.json`` envelope, separate from ``Document`` (MOANART.md section 16).

``{kind: "moanart-project", project_version: "1.0", document, assets, history}``: the
reader distinguishes the envelope by ``kind`` and applies its own strict model with
``extra='forbid'``; ``Document`` and its JSON Schema are unchanged, and the embedded
document is validated by :func:`moanart.schema.validate_document` with its own limits.

* :class:`AssetRef`: ``id`` (document ID grammar), ``path`` (always the immutable
  ``assets/<sha256>.png``), ``mime`` (``image/png``), ``byte_length`` and ``sha256``.
* :class:`HistoryEntry`: ``snapshot`` and ``parent`` digests (``sha256:<hex>``,
  ``parent`` ``null`` only at the root), ``batch`` (``sha256:<hex>`` of the canonical
  batch file, ``null`` only at the root) and ``redo`` (whether it is the active redo
  child of its parent). Entries keep the insertion order of the history, so a parent
  always precedes its children; the cursor is the embedded document.
* :class:`MigrationRecord` (ADR-031): one explicit migration that produced this
  project: ``source_kind`` (``document`` or ``project``: the shape of the original),
  ``member`` (the migrated version member, ``schema_version`` or ``project_version``,
  or ``kind`` for the rename of ADR-041), ``source_version`` < ``target_version`` of
  that member (for ``kind``: exactly :data:`LEGACY_PROJECT_KIND` and
  :data:`PROJECT_KIND`), the applied ``steps``
  (1 to ``MAX_MIGRATION_STEPS`` migration IDs) and the preserved copy of the original
  JSON, ``path`` (always the immutable ``migrations/<sha256>.json``), ``byte_length``
  and ``sha256``, unique among the records. ``migrations`` is optional and omitted
  when empty, so a project that was never migrated encodes exactly as before.

``project_version`` is checked against :data:`PROJECT_MIGRATIONS` before the model:
1.0 is the only envelope version, so any other string is ``UnsupportedVersion``
(``future``, ``past`` or ``unknown``) and its unknown grammar is never reported.

A project saved before the rename of ADR-041 (manifest :data:`LEGACY_MANIFEST_NAME`,
``kind`` :data:`LEGACY_PROJECT_KIND`) is ``UnsupportedVersion`` (``legacy_name``, with
the ``replacement``): only :func:`~moanart.project.migrate_project` reads it.

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

from moanart.core.errors import ErrorDetail, MoanArtError, UnsupportedVersion, ValidationError
from moanart.core.ids import ID_PATTERN
from moanart.core.limits import MAX_MIGRATION_STEPS
from moanart.project.assets import asset_path
from moanart.schema import (
    Document,
    MigrationRegistry,
    ParseLimits,
    parse_version,
    validate_document,
)

__all__ = [
    "LEGACY_MANIFEST_NAME",
    "LEGACY_PROJECT_KIND",
    "MANIFEST_NAME",
    "PROJECT_KIND",
    "PROJECT_MIGRATIONS",
    "PROJECT_VERSION",
    "AssetRef",
    "HistoryEntry",
    "MigrationRecord",
    "ProjectManifest",
    "legacy_name_error",
    "migration_path",
    "parse_manifest",
    "relocated",
]

MANIFEST_NAME: Final = "project.moanart.json"
PROJECT_KIND: Final = "moanart-project"
# Identifiers of 0.1.0rc1, before the rename of ADR-041: read only by migrate_project.
LEGACY_MANIFEST_NAME: Final = "project.moana.json"
LEGACY_PROJECT_KIND: Final = "moana-project"
RENAME_STEP: Final = "rename-to-moanart"
PROJECT_VERSION: Final = "1.0"
PROJECT_MIGRATIONS: Final = MigrationRegistry(member="project_version", current=PROJECT_VERSION)
"""Envelope versions: only 1.0 exists, so no envelope migration is registered."""

# A major.minor version, or one of the two kinds of a ``kind`` record (ADR-041).
_VERSION: Final = r"^(?:(0|[1-9][0-9]{0,3})\.(0|[1-9][0-9]{0,3})|moana-project|moanart-project)$"
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


Version = Annotated[str, StringConstraints(pattern=_VERSION)]


def migration_path(sha256: str) -> str:
    """Immutable path of the preserved original of a migration: ``migrations/<hex>.json``."""
    return f"migrations/{sha256}.json"


class MigrationRecord(BaseModel):
    """Provenance of one explicit migration and its preserved original (ADR-031)."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    source_kind: Literal["document", "project"]
    member: Literal["schema_version", "project_version", "kind"]
    source_version: Version
    target_version: Version
    steps: Annotated[
        tuple[Annotated[str, StringConstraints(pattern=ID_PATTERN)], ...],
        Field(min_length=1, max_length=MAX_MIGRATION_STEPS),
        BeforeValidator(_as_tuple),
    ]
    path: str
    byte_length: Annotated[int, Field(ge=1)]
    sha256: Annotated[str, StringConstraints(pattern=_HEX)]

    @model_validator(mode="after")
    def _immutable_path(self) -> MigrationRecord:
        if self.path != migration_path(self.sha256):
            raise ValueError("path must be migrations/<sha256>.json")
        if self.member == "kind":
            if (self.source_kind, self.source_version, self.target_version, self.steps) != (
                "project",
                LEGACY_PROJECT_KIND,
                PROJECT_KIND,
                (RENAME_STEP,),
            ):
                raise ValueError("a kind migration renames the legacy project kind")
            return self
        source = parse_version(self.source_version)
        target = parse_version(self.target_version)
        if source is None or target is None:
            raise ValueError("a version migration names major.minor versions")
        if source >= target:
            raise ValueError("a migration goes to a newer version")
        return self


class ProjectManifest(BaseModel):
    """The envelope of a project; ``document`` is a validated :class:`Document`."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    kind: Literal["moanart-project"]
    project_version: Literal["1.0"]
    document: Document
    # Counts and sizes are budgets (``ProjectLimits``, ``BudgetExceeded``), checked by
    # the loader; the manifest reader already bounds the nodes of these arrays.
    assets: Annotated[tuple[AssetRef, ...], BeforeValidator(_as_tuple)]
    history: Annotated[tuple[HistoryEntry, ...], BeforeValidator(_as_tuple)] = ()
    migrations: Annotated[tuple[MigrationRecord, ...], BeforeValidator(_as_tuple)] = ()

    @model_validator(mode="after")
    def _distinct_originals(self) -> ProjectManifest:
        hashes = [record.sha256 for record in self.migrations]
        if len(set(hashes)) != len(hashes):
            raise ValueError("each migration preserves a distinct original")
        if sum(record.member == "kind" for record in self.migrations) > 1:
            raise ValueError("a project is renamed at most once")
        return self

    def to_tree(self) -> dict[str, Any]:
        """JSON tree of the envelope with the normalised document (section 14).

        ``migrations`` is omitted when empty (ADR-031): a project that was never
        migrated keeps the bytes and hash of its manifest.
        """
        tree = self.model_dump(mode="json", exclude_none=False) | {
            "document": self.document.model_dump(mode="json", exclude_none=True)
        }
        if not self.migrations:
            del tree["migrations"]
        return tree


_KNOWN_MEMBERS: Final = frozenset(
    set(ProjectManifest.model_fields)
    | set(AssetRef.model_fields)
    | set(HistoryEntry.model_fields)
    | set(MigrationRecord.model_fields)
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


def relocated(error: MoanArtError) -> MoanArtError:
    """The same error with every pointer under ``/document``.

    Shared with :mod:`moanart.project.migrate`, which reports the errors of an embedded
    document exactly as :func:`parse_manifest` does.
    """

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


def legacy_name_error(field: str, replacement: str, json_pointer: str | None) -> UnsupportedVersion:
    """A file saved before the rename of ADR-041; ``migrate_project`` reads it."""
    return UnsupportedVersion(
        "the project was saved before the MoanArt rename; migrate it with migrate_project",
        json_pointer=json_pointer,
        context={"field": field, "reason": "legacy_name", "replacement": replacement},
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

    Document errors keep their codes with pointers under ``/document``. A
    ``project_version`` other than 1.0 is ``UnsupportedVersion`` before anything else
    is validated (ADR-031).
    """
    if not isinstance(tree, Mapping):
        raise _invalid("the project manifest must be a JSON object")
    values = dict(tree)
    if values.get("kind") == LEGACY_PROJECT_KIND:
        raise legacy_name_error("kind", PROJECT_KIND, "/kind")
    if values.get("kind") != PROJECT_KIND:
        raise _invalid(
            "the project manifest has no supported kind",
            [ErrorDetail(ValidationError.code, "unsupported kind", json_pointer="/kind")],
        )
    PROJECT_MIGRATIONS.check(values)
    document = values.get("document")
    if isinstance(document, Mapping):
        try:
            values["document"] = validate_document(document, limits=limits)
        except MoanArtError as exc:
            raise relocated(exc) from exc
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
