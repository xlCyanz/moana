"""Strict schema 1.0 of Moana documents (MOANA.md section 12, ADR-011).

Entry point: :func:`validate_document` turns untrusted JSON bytes or a mapping into a
frozen :class:`Document`, or raises a ``moana.core`` error whose ``details`` locate
every problem by JSON Pointer. :func:`canonical_json` and :func:`snapshot_digest`
implement the canonical normalisation of section 14; :func:`document_json_schema`
generates the versioned JSON Schema stored in ``schemas/``.
"""

from moana.schema._reader import DEFAULT_PARSE_LIMITS, ParseLimits
from moana.schema.capabilities import (
    PLANNED_BLEND_MODES,
    PLANNED_COLLECTIONS,
    PLANNED_LAYER_FIELDS,
    PLANNED_OPERATION_TYPES,
    SCHEMA_VERSION,
    SUPPORTED_BLEND_MODES,
    SUPPORTED_OPERATION_TYPES,
    SUPPORTED_PROFILES,
    SUPPORTED_SCHEMA_VERSIONS,
)
from moana.schema.document import (
    JSON_SCHEMA_DIALECT,
    canonical_json,
    document_json_schema,
    normalize_document,
    snapshot_digest,
    validate_document,
)
from moana.schema.models import (
    Canvas,
    Color,
    Document,
    EllipseOperation,
    Layer,
    LineOperation,
    Metadata,
    Operation,
    Palette,
    PixelOperation,
    PolygonOperation,
    Ramp,
    RectOperation,
)

__all__ = [
    "DEFAULT_PARSE_LIMITS",
    "JSON_SCHEMA_DIALECT",
    "PLANNED_BLEND_MODES",
    "PLANNED_COLLECTIONS",
    "PLANNED_LAYER_FIELDS",
    "PLANNED_OPERATION_TYPES",
    "SCHEMA_VERSION",
    "SUPPORTED_BLEND_MODES",
    "SUPPORTED_OPERATION_TYPES",
    "SUPPORTED_PROFILES",
    "SUPPORTED_SCHEMA_VERSIONS",
    "Canvas",
    "Color",
    "Document",
    "EllipseOperation",
    "Layer",
    "LineOperation",
    "Metadata",
    "Operation",
    "Palette",
    "ParseLimits",
    "PixelOperation",
    "PolygonOperation",
    "Ramp",
    "RectOperation",
    "canonical_json",
    "document_json_schema",
    "normalize_document",
    "snapshot_digest",
    "validate_document",
]
