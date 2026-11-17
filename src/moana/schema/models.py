"""Strict Pydantic models of the schema 1.0 document (MOANA.md sections 6, 9, 11, 12).

Models check structure only: types, ranges, lengths, identifiers and discriminators.
Global ID uniqueness, colour references and profile rules are semantic checks done by
:func:`moana.schema.validate_document`, which is the only entry point that guarantees
a fully valid :class:`Document`. Every model is frozen and stores sequences as tuples.

Strict mode rejects ``bool`` for integers, numbers for strings and any coercion. JSON
arrays arrive as lists and become tuples through an explicit before-validator, so the
same tree validates identically from bytes or from a mapping.
"""

from __future__ import annotations

from typing import Annotated, Any, Final, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    WithJsonSchema,
)
from pydantic.json_schema import SkipJsonSchema
from pydantic_core import PydanticCustomError

from moana.core.coordinates import (
    MAX_COORDINATE,
    MAX_DIMENSION,
    MIN_DIMENSION,
    Box,
    Dimensions,
    Point,
)
from moana.core.limits import (
    MAX_COLORS_RGBA,
    MAX_COLORS_STRICT,
    MAX_LAYERS,
    MAX_OPERATIONS,
    MAX_VERTICES,
)

__all__ = [
    "MAX_COLORS_RGBA",
    "MAX_COLORS_STRICT",
    "MAX_LAYERS",
    "MAX_METADATA_STRING_BYTES",
    "MAX_OPERATIONS",
    "MAX_REVISION",
    "MAX_SEED",
    "MAX_TAGS",
    "MAX_VERTICES",
    "Canvas",
    "Color",
    "Document",
    "EllipseOperation",
    "Layer",
    "LineOperation",
    "Metadata",
    "Operation",
    "Palette",
    "PixelOperation",
    "PolygonOperation",
    "Ramp",
    "RectOperation",
]

MAX_METADATA_STRING_BYTES: Final = 4096
MAX_TAGS: Final = 32
MAX_SEED: Final = 2**64 - 1
MAX_REVISION: Final = 2**64 - 1

ID_PATTERN: Final = r"^[a-z][a-z0-9_-]{0,63}$"
RGBA_PATTERN: Final = r"^#[0-9A-Fa-f]{8}$"


def _as_tuple(value: object) -> object:
    """Accept a JSON array (``list``) where the model stores an immutable tuple."""
    return tuple(value) if isinstance(value, list) else value


def _check_utf8_bytes(value: str) -> str:
    if len(value.encode("utf-8")) > MAX_METADATA_STRING_BYTES:
        raise PydanticCustomError(
            "string_too_many_bytes",
            "String should have at most {max_bytes} UTF-8 bytes",
            {"max_bytes": MAX_METADATA_STRING_BYTES},
        )
    return value


def _reject_null(value: object) -> object:
    """Optional members are omitted, never ``null``: there is one canonical form."""
    if value is None:
        raise PydanticCustomError("null_not_allowed", "Omit the member instead of using null")
    return value


def _metadata_or_absent(value: object) -> object:
    """Metadata without any value is the same document as no metadata (one form)."""
    value = _reject_null(value)
    if isinstance(value, dict) and set(value) <= {"tags"} and value.get("tags", []) in ([], ()):
        return None
    return value


def _require_empty(value: tuple[Any, ...]) -> tuple[Any, ...]:
    if value:
        raise PydanticCustomError(
            "unsupported_capability", "This collection is not supported by schema 1.0 yet"
        )
    return value


def _check_box(value: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = value
    if not (x0 < x1 and y0 < y1):
        raise PydanticCustomError("box_empty_or_inverted", "Box should satisfy x0 < x1 and y0 < y1")
    return value


Id = Annotated[str, StringConstraints(pattern=ID_PATTERN)]
"""Stable identifier, unique in the whole document; human names are not keys."""

PixelCoordinate = Annotated[int, Field(ge=-MAX_COORDINATE, le=MAX_COORDINATE)]
EdgeCoordinate = Annotated[int, Field(ge=-MAX_COORDINATE + 1, le=MAX_COORDINATE + 1)]
PointValue = Annotated[tuple[PixelCoordinate, PixelCoordinate], BeforeValidator(_as_tuple)]
BoxValue = Annotated[
    tuple[PixelCoordinate, PixelCoordinate, EdgeCoordinate, EdgeCoordinate],
    BeforeValidator(_as_tuple),
    AfterValidator(_check_box),
]
MetadataString = Annotated[
    str, Field(max_length=MAX_METADATA_STRING_BYTES), AfterValidator(_check_utf8_bytes)
]
OptionalText = Annotated[MetadataString | SkipJsonSchema[None], BeforeValidator(_reject_null)]
FutureCollection = Annotated[
    tuple[Any, ...],
    BeforeValidator(_as_tuple),
    AfterValidator(_require_empty),
    WithJsonSchema({"type": "array", "maxItems": 0}),
]


class _Model(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


class Canvas(_Model):
    """Canvas size and colour profile (``strict`` or ``rgba``, MOANA.md section 9)."""

    width: Annotated[int, Field(ge=MIN_DIMENSION, le=MAX_DIMENSION)]
    height: Annotated[int, Field(ge=MIN_DIMENSION, le=MAX_DIMENSION)]
    profile: Literal["strict", "rgba"] = "strict"

    @property
    def dimensions(self) -> Dimensions:
        """The canvas size as a ``core`` value."""
        return Dimensions(self.width, self.height)


class Color(_Model):
    """A palette entry; ``rgba`` is ``#RRGGBBAA`` and is stored upper-case."""

    id: Id
    rgba: Annotated[str, StringConstraints(pattern=RGBA_PATTERN), AfterValidator(str.upper)]


class Ramp(_Model):
    """Ordered colour IDs from shadow to light; at least two distinct entries."""

    id: Id
    colors: Annotated[
        tuple[Id, ...], Field(min_length=2, max_length=MAX_COLORS_RGBA), BeforeValidator(_as_tuple)
    ]


class Palette(_Model):
    """Palette with stable colour IDs and optional authored ramps."""

    id: Id
    colors: Annotated[
        tuple[Color, ...],
        Field(min_length=1, max_length=MAX_COLORS_RGBA),
        BeforeValidator(_as_tuple),
    ]
    ramps: Annotated[tuple[Ramp, ...], BeforeValidator(_as_tuple)] = ()


class _Operation(_Model):
    id: Id
    color: Id


class PixelOperation(_Operation):
    """Exactly one pixel at ``at``."""

    type: Literal["pixel"]
    at: PointValue

    @property
    def point(self) -> Point:
        """The target pixel as a ``core`` value."""
        return Point(*self.at)


class LineOperation(_Operation):
    """One-pixel line, inclusive at both ends (MOANA.md section 6)."""

    type: Literal["line"]
    start: PointValue
    end: PointValue


class RectOperation(_Operation):
    """Filled half-open box ``[x0, y0, x1, y1)``."""

    type: Literal["rect"]
    box: BoxValue

    @property
    def bbox(self) -> Box:
        """The box as a ``core`` value."""
        return Box(*self.box)


class EllipseOperation(_Operation):
    """Ellipse inscribed in a half-open box, by pixel-centre inclusion."""

    type: Literal["ellipse"]
    box: BoxValue

    @property
    def bbox(self) -> Box:
        """The box as a ``core`` value."""
        return Box(*self.box)


class PolygonOperation(_Operation):
    """Even-odd filled polygon of at least three vertices."""

    type: Literal["polygon"]
    points: Annotated[
        tuple[PointValue, ...],
        Field(min_length=3, max_length=MAX_VERTICES),
        BeforeValidator(_as_tuple),
    ]


Operation = Annotated[
    PixelOperation | LineOperation | RectOperation | EllipseOperation | PolygonOperation,
    Field(discriminator="type"),
]
"""Operations of schema 1.0, discriminated by ``type``."""


class Layer(_Model):
    """Ordered operations drawn bottom-to-top; ``locked`` affects editing only."""

    id: Id
    name: MetadataString
    visible: bool = True
    locked: bool = False
    opacity: Annotated[int, Field(ge=0, le=255)] = 255
    blend: Literal["normal"] = "normal"
    operations: Annotated[
        tuple[Operation, ...], Field(max_length=MAX_OPERATIONS), BeforeValidator(_as_tuple)
    ]


class Metadata(_Model):
    """Descriptive metadata; it never changes the rendered pixels."""

    title: OptionalText = None
    description: OptionalText = None
    author: OptionalText = None
    provenance: OptionalText = None
    tags: Annotated[
        tuple[MetadataString, ...], Field(max_length=MAX_TAGS), BeforeValidator(_as_tuple)
    ] = ()


class Document(_Model):
    """A schema 1.0 sprite document; layers are ordered bottom-to-top.

    Build it through :func:`moana.schema.validate_document`: constructing the model
    directly checks structure but not ID uniqueness, references or profile rules.
    """

    schema_version: Literal["1.0"]
    id: Id
    revision: Annotated[int, Field(ge=0, le=MAX_REVISION)] = 0
    seed: Annotated[int, Field(ge=0, le=MAX_SEED)] = 0
    canvas: Canvas
    palette: Palette
    layers: Annotated[tuple[Layer, ...], Field(max_length=MAX_LAYERS), BeforeValidator(_as_tuple)]
    masks: FutureCollection = ()
    regions: FutureCollection = ()
    materials: FutureCollection = ()
    animations: FutureCollection = ()
    metadata: Annotated[Metadata | SkipJsonSchema[None], BeforeValidator(_metadata_or_absent)] = (
        None
    )
