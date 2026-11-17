"""Integer points, canvas dimensions and half-open boxes (MOANA.md section 5, ADR-010).

Conventions:

* Origin at the top-left corner; ``x`` grows right and ``y`` grows down.
* Only real Python ``int`` values are coordinates. ``bool`` (a subclass of ``int``),
  floats, numeric strings and NumPy scalars are rejected.
* Pixel coordinates satisfy ``abs(c) <= MAX_COORDINATE``.
* A :class:`Box` ``[x0, y0, x1, y1)`` includes ``x0``/``y0`` and excludes ``x1``/``y1``.
  Its included corner is a pixel coordinate; its excluded edge may reach
  ``MAX_COORDINATE + 1`` so every valid pixel has a 1x1 box.
* A box is never empty: ``x0 < x1`` and ``y0 < y1``. An empty intersection or clip is
  ``None`` rather than an invalid box.

These types are pure values: no NumPy, no buffers, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from moana.core.errors import OutOfBoundsError, ValidationError

__all__ = [
    "DEFAULT_SIZE",
    "MAX_AREA",
    "MAX_COORDINATE",
    "MAX_DIMENSION",
    "MIN_DIMENSION",
    "Box",
    "Dimensions",
    "Point",
    "require_int",
]

MIN_DIMENSION: Final = 1
MAX_DIMENSION: Final = 2048
MAX_AREA: Final = 4_194_304
MAX_COORDINATE: Final = 1_048_576
DEFAULT_SIZE: Final = 128


def require_int(value: object, field: str, *, minimum: int, maximum: int) -> int:
    """Return ``value`` if it is a real ``int`` within ``[minimum, maximum]``.

    Raises :class:`ValidationError` whose context names the field, the reason and the
    bounds; the rejected value is not echoed. ``minimum > maximum`` is a programming
    error and raises :class:`ValueError`.
    """
    if minimum > maximum:
        raise ValueError(f"invalid bounds for {field}: {minimum} > {maximum}")
    if type(value) is not int:
        raise ValidationError(
            f"{field} must be an integer",
            context={"field": field, "reason": "not_integer", "value_type": type(value).__name__},
        )
    if not minimum <= value <= maximum:
        raise ValidationError(
            f"{field} must be between {minimum} and {maximum}",
            context={
                "field": field,
                "reason": "out_of_range",
                "minimum": minimum,
                "maximum": maximum,
            },
        )
    return value


def check_box_corners(
    x0: object, y0: object, x1: object, y1: object, *, max_coordinate: int
) -> None:
    """Validate box corners: included corner within ``±max_coordinate``, excluded edge +1."""
    for field, value in (("x0", x0), ("y0", y0)):
        require_int(value, field, minimum=-max_coordinate, maximum=max_coordinate)
    for field, value in (("x1", x1), ("y1", y1)):
        require_int(value, field, minimum=-max_coordinate + 1, maximum=max_coordinate + 1)


@dataclass(frozen=True, slots=True)
class Point:
    """A pixel position; ``Point(x, y)`` maps to ``array[y, x]`` in canvas buffers."""

    x: int
    y: int

    def __post_init__(self) -> None:
        for field, value in (("x", self.x), ("y", self.y)):
            require_int(value, field, minimum=-MAX_COORDINATE, maximum=MAX_COORDINATE)


@dataclass(frozen=True, slots=True)
class Dimensions:
    """Canvas size: each axis in ``1..2048`` and area at most 4,194,304 pixels."""

    width: int
    height: int

    def __post_init__(self) -> None:
        require_int(self.width, "width", minimum=MIN_DIMENSION, maximum=MAX_DIMENSION)
        require_int(self.height, "height", minimum=MIN_DIMENSION, maximum=MAX_DIMENSION)
        # Unreachable with the current maxima (2048 * 2048 == MAX_AREA) but kept so the
        # area contract holds if the per-axis maximum is ever raised.
        if self.area > MAX_AREA:  # pragma: no cover
            raise ValidationError(
                "canvas area exceeds the maximum",
                context={"field": "area", "reason": "out_of_range", "maximum": MAX_AREA},
            )

    @classmethod
    def default(cls) -> Dimensions:
        """The reference 128 x 128 canvas."""
        return cls(DEFAULT_SIZE, DEFAULT_SIZE)

    @property
    def area(self) -> int:
        """Number of pixels, ``width * height``."""
        return self.width * self.height

    def check_pixel(self, point: Point) -> None:
        """Raise :class:`OutOfBoundsError` unless ``point`` is a pixel of this canvas."""
        if not (0 <= point.x < self.width and 0 <= point.y < self.height):
            raise OutOfBoundsError(
                "pixel is outside the canvas",
                context={"x": point.x, "y": point.y, "width": self.width, "height": self.height},
            )


@dataclass(frozen=True, slots=True)
class Box:
    """Non-empty half-open rectangle ``[x0, y0, x1, y1)``; corners may lie off-canvas."""

    x0: int
    y0: int
    x1: int
    y1: int

    def __post_init__(self) -> None:
        check_box_corners(self.x0, self.y0, self.x1, self.y1, max_coordinate=MAX_COORDINATE)
        if not (self.x0 < self.x1 and self.y0 < self.y1):
            raise ValidationError(
                "box requires x0 < x1 and y0 < y1",
                context={"field": "box", "reason": "empty_or_inverted"},
            )

    @classmethod
    def from_point(cls, point: Point) -> Box:
        """The 1x1 box holding exactly ``point``; valid for every pixel coordinate."""
        return cls(point.x, point.y, point.x + 1, point.y + 1)

    @classmethod
    def from_dimensions(cls, dimensions: Dimensions) -> Box:
        """The box covering a whole canvas."""
        return cls(0, 0, dimensions.width, dimensions.height)

    @property
    def width(self) -> int:
        """Number of columns, ``x1 - x0`` (at least 1)."""
        return self.x1 - self.x0

    @property
    def height(self) -> int:
        """Number of rows, ``y1 - y0`` (at least 1)."""
        return self.y1 - self.y0

    @property
    def area(self) -> int:
        """Number of pixels covered."""
        return self.width * self.height

    def contains(self, point: Point) -> bool:
        """Whether ``point`` lies inside, honouring the excluded right/bottom edges."""
        return self.x0 <= point.x < self.x1 and self.y0 <= point.y < self.y1

    def intersection(self, other: Box) -> Box | None:
        """Shared pixels of both boxes, or ``None`` when they do not overlap.

        Boxes that only touch along an edge share no pixel and return ``None``.
        """
        x0, y0 = max(self.x0, other.x0), max(self.y0, other.y0)
        x1, y1 = min(self.x1, other.x1), min(self.y1, other.y1)
        if x0 >= x1 or y0 >= y1:
            return None
        return Box(x0, y0, x1, y1)

    def clip_to(self, dimensions: Dimensions) -> Box | None:
        """Clip to a canvas without wraparound; ``None`` if nothing remains visible."""
        return self.intersection(Box.from_dimensions(dimensions))
