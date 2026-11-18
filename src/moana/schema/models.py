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
    Discriminator,
    Field,
    PrivateAttr,
    StringConstraints,
    Tag,
    WithJsonSchema,
)
from pydantic.json_schema import SkipJsonSchema
from pydantic_core import InitErrorDetails, PydanticCustomError
from pydantic_core import ValidationError as PydanticValidationError

from moana.core import ids
from moana.core.coordinates import (
    MAX_COORDINATE,
    MAX_DIMENSION,
    MIN_DIMENSION,
    Box,
    Dimensions,
    Point,
)
from moana.core.dither import DITHER_SIZES
from moana.core.errors import ValidationError as DomainValidationError
from moana.core.limits import (
    MAX_COLORS_RGBA,
    MAX_COLORS_STRICT,
    MAX_LAYERS,
    MAX_MASK_OPERANDS,
    MAX_MASKS,
    MAX_OPERATIONS,
    MAX_PATH_COMMANDS,
    MAX_REGIONS,
    MAX_VERTICES,
)
from moana.core.vector_path import (
    MAX_PATH_COORDINATE,
    MIN_PATH_COMMANDS,
    FixedPath,
    parse_path,
)

__all__ = [
    "DITHER_SIZES",
    "MAX_COLORS_RGBA",
    "MAX_COLORS_STRICT",
    "MAX_LAYERS",
    "MAX_MASKS",
    "MAX_MASK_OPERANDS",
    "MAX_METADATA_STRING_BYTES",
    "MAX_OPERATIONS",
    "MAX_PATH_COMMANDS",
    "MAX_REGIONS",
    "MAX_REVISION",
    "MAX_SEED",
    "MAX_TAGS",
    "MAX_VERTICES",
    "Canvas",
    "Color",
    "CombinationMask",
    "DitherOperation",
    "Document",
    "EllipseMask",
    "EllipseOperation",
    "IntersectMask",
    "Layer",
    "LineMask",
    "LineOperation",
    "MaskNode",
    "Metadata",
    "Operation",
    "Palette",
    "PathCommand",
    "PathMask",
    "PathOperation",
    "PixelMask",
    "PixelOperation",
    "PolygonMask",
    "PolygonOperation",
    "Ramp",
    "RectMask",
    "RectOperation",
    "Region",
    "ShapeMask",
    "ShapeOperation",
    "SubtractMask",
    "UnionMask",
    "XorMask",
]

MAX_METADATA_STRING_BYTES: Final = 4096
MAX_TAGS: Final = 32
MAX_SEED: Final = 2**64 - 1
MAX_REVISION: Final = 2**64 - 1

# Lexical languages are owned by core (ADR-014); re-exported under the schema names.
ID_PATTERN: Final = ids.ID_PATTERN
RGBA_PATTERN: Final = ids.RGBA_HEX_PATTERN


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


def _command_tag(value: object) -> str | None:
    """Discriminator of a path command: its first item, the command letter."""
    if isinstance(value, list | tuple) and value and isinstance(value[0], str):
        return value[0]
    return None


def _check_path(title: str, value: tuple[object, ...]) -> FixedPath:
    """Parse validated commands once: order and segment rules of ``parse_path``.

    A failure becomes a Pydantic error located at ``commands/{index}`` (or at
    ``commands`` when it concerns the whole path), like arity and type errors.
    """
    try:
        return parse_path(value)
    except DomainValidationError as error:
        context = {key: v for key, v in error.context.items() if isinstance(v, int)}
        index = error.context.get("index")
        location: tuple[str | int, ...] = ("commands",)
        if isinstance(index, int):
            location = ("commands", index)
        reason = PydanticCustomError(str(error.context["reason"]), error.message, context)
        detail = InitErrorDetails(type=reason, loc=location, input=value)
        raise PydanticValidationError.from_exception_data(title, [detail]) from None


class _CachedPath(_Model):
    """The :class:`FixedPath` of ``commands``, parsed once when the model is built.

    The cache remembers the very ``commands`` tuple it parsed: a copy whose
    ``commands`` were replaced without validation parses (and checks) them again.
    """

    _fixed: tuple[tuple[object, ...], FixedPath] | None = PrivateAttr(default=None)

    def _cache(self, commands: tuple[object, ...]) -> None:
        self._fixed = (commands, _check_path(type(self).__name__, commands))

    def _cached(self, commands: tuple[object, ...]) -> FixedPath:
        cached = self._fixed
        if cached is not None and cached[0] is commands:
            return cached[1]
        return parse_path(commands)


PathCoordinate = Annotated[int, Field(ge=-MAX_PATH_COORDINATE, le=MAX_PATH_COORDINATE)]
"""Path coordinate in 1/256 pixel units (fixed point, ADR-023)."""
_C = PathCoordinate
PathCommand = Annotated[
    Annotated[tuple[Literal["M"], _C, _C], BeforeValidator(_as_tuple), Tag("M")]
    | Annotated[tuple[Literal["L"], _C, _C], BeforeValidator(_as_tuple), Tag("L")]
    | Annotated[tuple[Literal["Q"], _C, _C, _C, _C], BeforeValidator(_as_tuple), Tag("Q")]
    | Annotated[tuple[Literal["C"], _C, _C, _C, _C, _C, _C], BeforeValidator(_as_tuple), Tag("C")]
    | Annotated[tuple[Literal["Z"]], BeforeValidator(_as_tuple), Tag("Z")],
    Discriminator(
        _command_tag,
        custom_error_type="path_command_invalid",
        custom_error_message="Path command must be an array starting with M, L, Q, C or Z",
    ),
]
"""``["M", x, y]``, ``["L", x, y]``, ``["Q", x1, y1, x, y]``, ``["C", x1, y1, x2, y2, x, y]``
or ``["Z"]``; coordinates in 1/256 pixel."""


def _command_array(value: object) -> object:
    """Array to tuple, rejecting fewer than two commands before reading any of them.

    ``min_length`` would count only the commands that validated, and report a short
    path next to the real error of an invalid command.
    """
    value = _as_tuple(value)
    if isinstance(value, tuple) and len(value) < MIN_PATH_COMMANDS:
        raise PydanticCustomError(
            "too_short",
            "Path should have at least {min_length} commands",
            {"min_length": MIN_PATH_COMMANDS},
        )
    return value


PathCommands = Annotated[
    tuple[PathCommand, ...],
    Field(max_length=MAX_PATH_COMMANDS, json_schema_extra={"minItems": MIN_PATH_COMMANDS}),
    BeforeValidator(_command_array),
]


class PathOperation(_Operation, _CachedPath):
    """Nonzero fill of a fixed-point path by the ``aggdraw-v1`` backend (ADR-023).

    Coverage at native scale is binarised (``>= 128``); subpaths close implicitly.
    """

    type: Literal["path"]
    backend: Literal["aggdraw-v1"]
    commands: PathCommands

    def model_post_init(self, context: Any, /) -> None:
        """Parse the commands once (order and segment rules)."""
        self._cache(self.commands)

    @property
    def path(self) -> FixedPath:
        """The validated, flattenable path as a ``core`` value (parsed once)."""
        return self._cached(self.commands)


def _check_dither_size(value: int) -> int:
    if value not in DITHER_SIZES:
        raise PydanticCustomError("unsupported_size", "Dither size should be 2 or 4")
    return value


class DitherOperation(_Model):
    """Ordered Bayer dithering of the pixels of mask ``mask_id`` (ADR-025).

    Pixel ``(x, y)`` of the mask takes ``color_b`` when
    ``M[(y - oy) mod size][(x - ox) mod size] < coverage`` (mathematical modulo,
    ``origin = [ox, oy]``) and ``color_a`` otherwise; nothing outside the mask is
    drawn. ``coverage`` is an integer in ``0..size^2``.
    """

    id: Id
    type: Literal["dither"]
    size: Annotated[
        int,
        AfterValidator(_check_dither_size),
        WithJsonSchema({"type": "integer", "enum": list(DITHER_SIZES)}),
    ]
    coverage: Annotated[int, Field(ge=0, le=max(DITHER_SIZES) ** 2)]
    origin: PointValue
    color_a: Id
    color_b: Id
    mask_id: Id

    def model_post_init(self, context: Any, /) -> None:
        """Bound ``coverage`` by ``size^2`` (it depends on two members)."""
        maximum = self.size * self.size
        if self.coverage > maximum:
            reason = PydanticCustomError(
                "less_than_equal",
                "Input should be less than or equal to {le}",
                {"le": maximum},
            )
            detail = InitErrorDetails(type=reason, loc=("coverage",), input=self.coverage)
            raise PydanticValidationError.from_exception_data(type(self).__name__, [detail])

    @property
    def anchor(self) -> Point:
        """The pattern origin as a ``core`` value."""
        return Point(*self.origin)


ShapeOperation = (
    PixelOperation
    | LineOperation
    | RectOperation
    | EllipseOperation
    | PolygonOperation
    | PathOperation
)
"""Operations that rasterise primitive geometry and paint it with one ``color``."""

Operation = Annotated[
    PixelOperation
    | LineOperation
    | RectOperation
    | EllipseOperation
    | PolygonOperation
    | PathOperation
    | DitherOperation,
    Field(discriminator="type"),
]
"""Operations of schema 1.0, discriminated by ``type``."""


class _Mask(_Model):
    id: Id


class PixelMask(_Mask):
    """Mask of exactly one pixel at ``at`` (canvas coordinates, ADR-022)."""

    type: Literal["pixel"]
    at: PointValue

    @property
    def point(self) -> Point:
        """The pixel as a ``core`` value."""
        return Point(*self.at)


class LineMask(_Mask):
    """Mask of a one-pixel line, inclusive at both ends (same rule as ``line``)."""

    type: Literal["line"]
    start: PointValue
    end: PointValue


class RectMask(_Mask):
    """Mask of a filled half-open box ``[x0, y0, x1, y1)``."""

    type: Literal["rect"]
    box: BoxValue

    @property
    def bbox(self) -> Box:
        """The box as a ``core`` value."""
        return Box(*self.box)


class EllipseMask(_Mask):
    """Mask of the ellipse inscribed in a half-open box (same rule as ``ellipse``)."""

    type: Literal["ellipse"]
    box: BoxValue

    @property
    def bbox(self) -> Box:
        """The box as a ``core`` value."""
        return Box(*self.box)


class PolygonMask(_Mask):
    """Mask of an even-odd filled polygon (same rule as ``polygon``)."""

    type: Literal["polygon"]
    points: Annotated[
        tuple[PointValue, ...],
        Field(min_length=3, max_length=MAX_VERTICES),
        BeforeValidator(_as_tuple),
    ]


class PathMask(_Mask, _CachedPath):
    """Mask of a fixed-point path filled by ``aggdraw-v1`` (same rule as ``path``)."""

    type: Literal["path"]
    backend: Literal["aggdraw-v1"]
    commands: PathCommands

    def model_post_init(self, context: Any, /) -> None:
        """Parse the commands once (order and segment rules)."""
        self._cache(self.commands)

    @property
    def path(self) -> FixedPath:
        """The validated, flattenable path as a ``core`` value (parsed once)."""
        return self._cached(self.commands)


class CombinationMask(_Mask):
    """Boolean node over 2 to 64 mask IDs, folded in array order.

    ``union``: in any operand; ``intersect``: in every operand; ``subtract``: in the
    first operand and none of the others; ``xor``: in an odd number of operands.
    """

    masks: Annotated[
        tuple[Id, ...],
        Field(min_length=2, max_length=MAX_MASK_OPERANDS),
        BeforeValidator(_as_tuple),
    ]


class UnionMask(CombinationMask):
    """Pixels of at least one operand."""

    type: Literal["union"]


class IntersectMask(CombinationMask):
    """Pixels of every operand."""

    type: Literal["intersect"]


class SubtractMask(CombinationMask):
    """Pixels of the first operand that are in none of the others."""

    type: Literal["subtract"]


class XorMask(CombinationMask):
    """Pixels of an odd number of operands."""

    type: Literal["xor"]


ShapeMask = PixelMask | LineMask | RectMask | EllipseMask | PolygonMask | PathMask
"""Mask leaves: primitive geometry in canvas coordinates, without colour."""

MaskNode = Annotated[
    PixelMask
    | LineMask
    | RectMask
    | EllipseMask
    | PolygonMask
    | PathMask
    | UnionMask
    | IntersectMask
    | SubtractMask
    | XorMask,
    Field(discriminator="type"),
]
"""Semantic mask nodes of schema 1.0 (ADR-022), discriminated by ``type``."""


class Region(_Model):
    """Semantic region: a stable ID bound to a mask and, optionally, operations.

    It lets an agent target "the left eye" by ID instead of inferring pixels.
    """

    id: Id
    mask_id: Id
    operation_ids: Annotated[
        tuple[Id, ...], Field(max_length=MAX_OPERATIONS), BeforeValidator(_as_tuple)
    ] = ()


OptionalId = Annotated[Id | SkipJsonSchema[None], BeforeValidator(_reject_null)]


class Layer(_Model):
    """Ordered operations drawn bottom-to-top; ``locked`` affects editing only.

    ``mask_id`` (optional) clips the whole layer to a semantic mask (ADR-022).
    """

    id: Id
    name: MetadataString
    visible: bool = True
    locked: bool = False
    opacity: Annotated[int, Field(ge=0, le=255)] = 255
    blend: Literal["normal"] = "normal"
    operations: Annotated[
        tuple[Operation, ...], Field(max_length=MAX_OPERATIONS), BeforeValidator(_as_tuple)
    ]
    mask_id: OptionalId = None


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
    masks: Annotated[
        tuple[MaskNode, ...], Field(max_length=MAX_MASKS), BeforeValidator(_as_tuple)
    ] = ()
    regions: Annotated[
        tuple[Region, ...], Field(max_length=MAX_REGIONS), BeforeValidator(_as_tuple)
    ] = ()
    materials: FutureCollection = ()
    animations: FutureCollection = ()
    metadata: Annotated[Metadata | SkipJsonSchema[None], BeforeValidator(_metadata_or_absent)] = (
        None
    )
