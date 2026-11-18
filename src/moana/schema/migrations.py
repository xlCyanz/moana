"""Pure, offline migration of documents to the current schema (MOANA.md section 16, ADR-031).

:func:`migrate_document` has no I/O, clock or global state. It copies the source
under the parse limits, applies each registered step of a
:class:`~moana.schema.versions.MigrationRegistry` to a fresh bounded copy, sets
``schema_version`` to the step's target and validates the result with
:func:`~moana.schema.validate_document`. A document already in the current version is
returned validated with no steps, so migrating a migrated document is the identity.

The source must be a JSON-shaped tree: every leaf is ``str``, ``int``, ``float``,
``bool`` or ``None`` (another value, such as a ``set``, is ``ValidationError``
``invalid_value`` at its pointer), so the bounded copy shares nothing mutable with the
caller and the input is never modified.

A step that raises any ``Exception`` other than a ``MoanaError`` (which passes through
with its own code), or returns something other than a JSON-shaped mapping within the
limits (a cycle, a non-JSON leaf, too deep or too many nodes), is a
``ValidationError`` with reason ``migration_failed``, the step's ID and, for the
returned tree, the bounding ``cause``. The original exception is neither chained nor
quoted: it may carry document data.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from moana.core.errors import MoanaError, ValidationError
from moana.schema._reader import DEFAULT_PARSE_LIMITS, ParseLimits, read_mapping
from moana.schema.capabilities import SCHEMA_VERSION
from moana.schema.document import validate_document
from moana.schema.models import Document
from moana.schema.versions import DOCUMENT_MIGRATIONS, Migration, MigrationRegistry

__all__ = ["DocumentMigration", "migrate_document"]


@dataclass(frozen=True, slots=True)
class DocumentMigration:
    """A migrated, validated document and where it came from.

    ``steps`` lists the applied migration IDs in order; it is empty (and
    ``source_version == target_version``) when the source was already current.
    """

    document: Document
    source_version: str
    target_version: str
    steps: tuple[str, ...]


def _escape(token: str | int) -> str:
    return str(token).replace("~", "~0").replace("/", "~1")


def _check_leaves(tree: dict[str, object]) -> None:
    """Every leaf of a copied tree is a JSON scalar (``invalid_value`` otherwise)."""
    stack: list[tuple[object, str]] = [(tree, "")]
    while stack:
        value, pointer = stack.pop()
        if isinstance(value, dict):
            stack.extend((child, f"{pointer}/{_escape(name)}") for name, child in value.items())
        elif isinstance(value, list):
            stack.extend((child, f"{pointer}/{index}") for index, child in enumerate(value))
        elif value is not None and not isinstance(value, str | int | float):
            raise ValidationError(
                "document values must be JSON scalars, objects or arrays",
                json_pointer=pointer,
                context={"reason": "invalid_value"},
            )


def _bounded(source: Mapping[str, object], limits: ParseLimits) -> dict[str, object]:
    """A private JSON-shaped copy of ``source`` within ``limits``."""
    tree = read_mapping(source, limits)
    _check_leaves(tree)
    return tree


def _failed(step: Migration, member: str, cause: object = None) -> ValidationError:
    context: dict[str, object] = {
        "field": member,
        "reason": "migration_failed",
        "migration": step.id,
    }
    if cause is not None:
        context["cause"] = cause
    return ValidationError(
        "a migration step cannot migrate this document",
        json_pointer=f"/{member}",
        context=context,
    )


def _apply(
    step: Migration, tree: dict[str, object], member: str, limits: ParseLimits
) -> dict[str, object]:
    try:
        result = step.apply(tree)
    except MoanaError:
        raise
    except Exception:  # any step failure; never chained: it may quote document data
        failed = True
    else:
        failed = not isinstance(result, Mapping)
    if failed:
        raise _failed(step, member) from None
    try:
        migrated = _bounded(result, limits)
    except ValidationError as exc:  # a cycle, a non-JSON leaf or a tree over the limits
        raise _failed(step, member, exc.context.get("reason")) from None
    migrated[member] = step.target
    return migrated


def migrate_document(
    source: Mapping[str, object],
    *,
    registry: MigrationRegistry = DOCUMENT_MIGRATIONS,
    limits: ParseLimits = DEFAULT_PARSE_LIMITS,
) -> DocumentMigration:
    """Migrate a document tree to the current schema with the registered steps.

    Pure and offline: ``source`` is never modified and nothing is read or written;
    its leaves must be JSON scalars (``invalid_value``).
    Every intermediate tree is bounded by ``limits`` (depth and nodes) and the result
    is validated with :func:`~moana.schema.validate_document`. Raises
    ``UnsupportedVersion`` for an unknown or future version, ``ValidationError``
    (``migration_failed``) for a step that cannot migrate the source, or the
    validation errors of the result.
    """
    if not isinstance(registry, MigrationRegistry) or registry.member != "schema_version":
        raise TypeError("registry must be a schema_version MigrationRegistry")
    if registry.current != SCHEMA_VERSION:
        raise ValueError("registry must migrate to the current schema version")
    tree = _bounded(source, limits)
    version = tree.get(registry.member)
    steps = registry.path(version) if isinstance(version, str) else ()
    for step in steps:
        tree = _apply(step, tree, registry.member, limits)
    document = validate_document(tree, limits=limits)
    origin = version if steps and isinstance(version, str) else document.schema_version
    return DocumentMigration(
        document=document,
        source_version=origin,
        target_version=document.schema_version,
        steps=tuple(step.id for step in steps),
    )
