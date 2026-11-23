"""Palettes with stable colour IDs, authored ramps and explicit remaps (MOANART.md §9).

A :class:`Palette` is an immutable value: editing returns a new palette with the
same IDs in the same order, so consumers that reference a colour by ID follow its
new value and nobody is renumbered. Validation mirrors the palette rules of the
document schema without importing it (``palette`` depends only on ``core``,
MOANART.md section 3); errors use the same codes, reasons, ordering and root context.
Pointers in error details are relative to the palette object (``/colors/0/rgba``);
a caller embedding it in a document prefixes ``/palette``. Uniqueness of IDs across
the whole document (layers, operations) remains the schema's job (ADR-014).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Final, final

from moanart.core.errors import ErrorDetail, ReferenceError, ValidationError, detail_sort_key
from moanart.core.ids import check_id, is_id
from moanart.core.limits import MAX_COLORS_RGBA, MAX_RAMP_ENTRIES
from moanart.palette.colors import PROFILE_MAX_COLORS, PROFILES, ColorProfile, Rgba

__all__ = [
    "MIN_RAMP_LENGTH",
    "RAMP_LUMINANCE_NOT_INCREASING",
    "RAMP_PARTIAL_ALPHA_STEP",
    "RAMP_TRANSPARENT_STEP",
    "ColorRemap",
    "Palette",
    "PaletteColor",
    "PaletteWarning",
    "Ramp",
]

RAMP_LUMINANCE_NOT_INCREASING: Final = "RAMP_LUMINANCE_NOT_INCREASING"
RAMP_TRANSPARENT_STEP: Final = "RAMP_TRANSPARENT_STEP"
RAMP_PARTIAL_ALPHA_STEP: Final = "RAMP_PARTIAL_ALPHA_STEP"
MIN_RAMP_LENGTH: Final = 2


@final
@dataclass(frozen=True, slots=True)
class PaletteColor:
    """A palette entry: stable ``id`` and its value."""

    id: str
    rgba: Rgba

    def __post_init__(self) -> None:
        check_id(self.id)
        if not isinstance(self.rgba, Rgba):
            raise TypeError("rgba must be an Rgba value")


@final
@dataclass(frozen=True, slots=True)
class Ramp:
    """Colour IDs ordered from shadow to light (length checked by :class:`Palette`)."""

    id: str
    colors: tuple[str, ...]

    def __post_init__(self) -> None:
        check_id(self.id)
        if type(self.colors) is not tuple:
            raise TypeError("colors must be a tuple of color IDs")
        if len(self.colors) > MAX_COLORS_RGBA:
            raise ValidationError(
                "ramp has too many colors",
                context={"field": "colors", "reason": "too_many", "maximum": MAX_COLORS_RGBA},
            )
        for color_id in self.colors:
            check_id(color_id, "colors")


@final
@dataclass(frozen=True, slots=True)
class PaletteWarning:
    """Non-blocking finding about a ramp step, located by pointer and by IDs.

    ``reason`` is ``decreasing``, ``equal`` or ``duplicate_value`` for
    :data:`RAMP_LUMINANCE_NOT_INCREASING`, ``transparent`` for
    :data:`RAMP_TRANSPARENT_STEP` and ``partial_alpha`` for
    :data:`RAMP_PARTIAL_ALPHA_STEP`. Luminances are :attr:`Rgba.luminance`.
    """

    code: str
    reason: str
    message: str
    json_pointer: str
    ramp_id: str
    color_id: str
    previous_color_id: str | None = None
    previous_luminance: int | None = None
    luminance: int | None = None


class _Details:
    """Collects problems; raises like the schema (sorted, precedence, issue count)."""

    def __init__(self) -> None:
        self.items: list[ErrorDetail] = []

    def invalid(self, pointer: str | None, message: str, reason: str, **extra: object) -> None:
        context: dict[str, object] = {"reason": reason, **extra}
        self.items.append(
            ErrorDetail(ValidationError.code, message, json_pointer=pointer, context=context)
        )

    def missing(self, pointer: str | None, **extra: object) -> None:
        self.items.append(
            ErrorDetail(
                ReferenceError.code,
                "Referenced color does not exist in the palette",
                json_pointer=pointer,
                context={"reason": "unknown_color", **extra},
            )
        )

    def raise_if_any(self, subject: str) -> None:
        if not self.items:
            return
        self.items.sort(key=detail_sort_key)
        codes = {detail.code for detail in self.items}
        error = ValidationError if ValidationError.code in codes else ReferenceError
        count = len(self.items)
        raise error(
            f"{subject} has {count} problem{'s' if count != 1 else ''}",
            json_pointer=self.items[0].json_pointer,
            context={"issue_count": count},
            details=self.items,
        )


@final
@dataclass(frozen=True, slots=True)
class Palette:
    """Validated palette for one colour profile; immutable, compared by value."""

    id: str
    profile: ColorProfile
    colors: tuple[PaletteColor, ...]
    ramps: tuple[Ramp, ...] = ()
    _index: Mapping[str, int] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        check_id(self.id)
        if self.profile not in PROFILES:
            raise ValidationError(
                "profile must be strict or rgba",
                context={"field": "profile", "reason": "unknown_profile"},
            )
        if type(self.colors) is not tuple or not all(
            isinstance(color, PaletteColor) for color in self.colors
        ):
            raise TypeError("colors must be a tuple of PaletteColor")
        if type(self.ramps) is not tuple or not all(isinstance(r, Ramp) for r in self.ramps):
            raise TypeError("ramps must be a tuple of Ramp")
        details = _Details()
        _check_ramp_budget(len(self.ramps), sum(len(r.colors) for r in self.ramps), details)
        details.raise_if_any("palette")
        first = {self.id: "/id"}
        index = _check_colors(self.profile, self.colors, details, first)
        _check_ramps(self.ramps, index, details, first)
        details.raise_if_any("palette")
        object.__setattr__(self, "_index", MappingProxyType(index))

    # Immutable values: copies are the value itself; pickling re-validates.
    def __copy__(self) -> Palette:
        return self

    def __deepcopy__(self, memo: dict[int, object]) -> Palette:
        return self

    def __reduce__(self) -> tuple[type[Palette], tuple[object, ...]]:
        return (Palette, (self.id, self.profile, self.colors, self.ramps))

    # --- lookup -------------------------------------------------------------------

    def index_of(self, color_id: str) -> int:
        """Declaration position of ``color_id``; stable across value edits."""
        position = self._index.get(color_id) if type(color_id) is str else None
        if position is None:
            raise ReferenceError(
                "color does not exist in the palette", context={"reason": "unknown_color"}
            )
        return position

    def color(self, color_id: str) -> Rgba:
        """Value of ``color_id``; ``ReferenceError`` if the palette has no such ID."""
        return self.colors[self.index_of(color_id)].rgba

    def __contains__(self, color_id: object) -> bool:
        return type(color_id) is str and color_id in self._index

    def ramp(self, ramp_id: str) -> tuple[Rgba, ...]:
        """Values of a ramp, shadow to light."""
        for ramp in self.ramps:
            if ramp.id == ramp_id:
                return tuple(self.color(color_id) for color_id in ramp.colors)
        raise ReferenceError(
            "ramp does not exist in the palette", context={"reason": "unknown_ramp"}
        )

    def ids_with_value(self, rgba: Rgba) -> tuple[str, ...]:
        """IDs whose value equals ``rgba`` after transparency normalisation, in order.

        Several IDs may share a value: each one is an independently editable colour.
        """
        target = rgba.normalized()
        return tuple(c.id for c in self.colors if c.rgba.normalized() == target)

    def contains_value(self, rgba: Rgba) -> bool:
        """Whether ``rgba`` (normalised) is one of the palette values."""
        return bool(self.ids_with_value(rgba))

    # --- edits (new palette, same IDs and order) ----------------------------------

    def replace_color(self, color_id: str, rgba: Rgba) -> Palette:
        """Change one value; every consumer of ``color_id`` follows, nobody renumbers."""
        position = self.index_of(color_id)
        colors = list(self.colors)
        colors[position] = PaletteColor(color_id, rgba)
        return Palette(self.id, self.profile, tuple(colors), self.ramps)

    def duplicate_color(self, source_id: str, new_id: str, rgba: Rgba | None = None) -> Palette:
        """Append ``new_id`` with the value of ``source_id`` (or ``rgba``) for local edits.

        Existing positions are unchanged. The new ID joins no ramp: ramps keep
        referencing the source until a ramp is edited explicitly.
        """
        value = self.color(source_id) if rgba is None else rgba
        colors = (*self.colors, PaletteColor(new_id, value))
        return Palette(self.id, self.profile, colors, self.ramps)

    # --- diagnostics --------------------------------------------------------------

    def luminance_warnings(self) -> tuple[PaletteWarning, ...]:
        """Non-blocking ramp findings, in ramp and step order.

        MOANART.md section 9 recommends shadow-to-light ramps but allows documented
        stylised exceptions, so nothing here rejects the palette; suppressing a
        warning per ramp belongs to the evaluation configuration (section 19).
        Transparent steps are reported and skipped for ordering; translucent steps
        are reported (their perceived value depends on the background) and ordered
        by their RGB.
        """
        return tuple(
            warning
            for ramp_index, ramp in enumerate(self.ramps)
            for warning in self._ramp_warnings(ramp_index, ramp)
        )

    def ramp_warnings(self, ramp_id: str) -> tuple[PaletteWarning, ...]:
        """The :meth:`luminance_warnings` of one ramp, in step order (ADR-028).

        Raises ``ReferenceError`` (``unknown_ramp``) when the palette has no such ramp.
        """
        for ramp_index, ramp in enumerate(self.ramps):
            if ramp.id == ramp_id:
                return tuple(self._ramp_warnings(ramp_index, ramp))
        raise ReferenceError(
            "ramp does not exist in the palette",
            context={"field": "ramp_id", "reason": "unknown_ramp"},
        )

    def _ramp_warnings(self, ramp_index: int, ramp: Ramp) -> Iterator[PaletteWarning]:
        previous: tuple[str, Rgba] | None = None
        for step, color_id in enumerate(ramp.colors):
            rgba = self.color(color_id)
            pointer = f"/ramps/{ramp_index}/colors/{step}"
            if rgba.is_transparent:
                yield PaletteWarning(
                    RAMP_TRANSPARENT_STEP,
                    "transparent",
                    "transparent ramp step would open holes when shading by index",
                    pointer,
                    ramp.id,
                    color_id,
                )
                continue
            if not rgba.is_opaque:
                yield PaletteWarning(
                    RAMP_PARTIAL_ALPHA_STEP,
                    "partial_alpha",
                    "translucent ramp step: its perceived value depends on the background",
                    pointer,
                    ramp.id,
                    color_id,
                )
            if previous is not None:
                reason = _order_problem(previous[1], rgba)
                if reason is not None:
                    yield PaletteWarning(
                        RAMP_LUMINANCE_NOT_INCREASING,
                        reason,
                        "ramp luminance does not increase from shadow to light",
                        pointer,
                        ramp.id,
                        color_id,
                        previous[0],
                        previous[1].luminance,
                        rgba.luminance,
                    )
            previous = (color_id, rgba)

    # --- serialisation ------------------------------------------------------------

    def to_mapping(self) -> dict[str, object]:
        """JSON-ready palette object, the shape of the document ``palette`` field."""
        return {
            "id": self.id,
            "colors": [{"id": c.id, "rgba": c.rgba.hex} for c in self.colors],
            "ramps": [{"id": r.id, "colors": list(r.colors)} for r in self.ramps],
        }

    @classmethod
    def from_mapping(cls, data: object, *, profile: ColorProfile) -> Palette:
        """Build from a parsed JSON palette object (exact ``dict``/``list``/``str``).

        Structure problems are reported together as error details with relative
        pointers before any semantic check; counts are bounded before walking items.
        """
        details = _Details()
        root = _object(data, "", {"id", "colors"}, {"ramps"}, details)
        palette_id = colors = ramps = None
        if root is not None:
            palette_id = _id_field(root, "", "id", details)
            colors = _read_colors(root.get("colors"), details)
            ramps = _read_ramps(root.get("ramps", []), details)
        details.raise_if_any("palette")
        if palette_id is None or colors is None or ramps is None:  # pragma: no cover
            raise AssertionError("structure accepted without values")
        return cls(palette_id, profile, colors, ramps)


@final
class ColorRemap:
    """Explicit, single-step colour substitution inside one palette.

    Every source and target must be a palette ID, so a remap never introduces a
    colour the palette does not have (it can still turn an opaque colour into a
    transparent one if asked to). Unmapped IDs map to themselves; mappings are not
    chained (``a -> b`` and ``b -> c`` send ``a`` to ``b``). Remaps have no document
    form yet, so problems carry no JSON pointer: ``context`` names the ``side``
    and the ``position`` in the given mapping.
    """

    __slots__ = ("_mapping", "_pairs", "_palette")

    def __init__(self, palette: Palette, mapping: Mapping[str, str]) -> None:
        """Validate and snapshot ``mapping``."""
        if not isinstance(palette, Palette):
            raise TypeError("palette must be a Palette")
        if not isinstance(mapping, Mapping):
            raise TypeError("mapping must be a mapping of color IDs")
        if len(mapping) > len(palette.colors):  # keys are unique palette IDs
            raise ValidationError(
                "remap has more entries than the palette has colors",
                context={"reason": "too_many", "maximum": len(palette.colors)},
            )
        details = _Details()
        frozen: dict[str, str] = {}
        for position, (source, target) in enumerate(mapping.items()):
            for side, value in (("source", source), ("target", target)):
                if type(value) is not str:
                    details.invalid(
                        None, "color ID must be a string", "not_id", side=side, position=position
                    )
                elif value not in palette:
                    details.missing(None, side=side, position=position)
            frozen[str(source)] = str(target)
        details.raise_if_any("remap")
        self._palette = palette
        self._mapping = MappingProxyType(frozen)
        self._pairs = tuple(sorted(frozen.items()))

    @property
    def palette(self) -> Palette:
        """The palette both sides belong to."""
        return self._palette

    @property
    def mapping(self) -> Mapping[str, str]:
        """Read-only snapshot of the explicit substitutions."""
        return self._mapping

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ColorRemap):
            return NotImplemented
        return self._palette == other._palette and self._pairs == other._pairs

    def __hash__(self) -> int:
        return hash((self._palette, self._pairs))

    def __repr__(self) -> str:
        return f"ColorRemap(palette={self._palette.id!r}, entries={len(self._pairs)})"

    def __copy__(self) -> ColorRemap:
        return self

    def __deepcopy__(self, memo: dict[int, object]) -> ColorRemap:
        return self

    def __reduce__(self) -> tuple[type[ColorRemap], tuple[object, ...]]:
        return (ColorRemap, (self._palette, dict(self._mapping)))

    def resolve(self, color_id: str) -> str:
        """Target ID of ``color_id``."""
        self._palette.index_of(color_id)
        return self._mapping.get(color_id, color_id)

    def color(self, color_id: str) -> Rgba:
        """Value ``color_id`` takes after the remap."""
        return self._palette.color(self.resolve(color_id))

    def used_ids(self, color_ids: Sequence[str]) -> tuple[str, ...]:
        """Distinct target IDs for ``color_ids``, in first-use order."""
        seen: dict[str, None] = {}
        for color_id in color_ids:
            seen.setdefault(self.resolve(color_id))
        return tuple(seen)


# --- validation helpers ---------------------------------------------------------------


def _order_problem(previous: Rgba, current: Rgba) -> str | None:
    if current.normalized() == previous.normalized():
        return "duplicate_value"
    if current.luminance == previous.luminance:
        return "equal"
    if current.luminance < previous.luminance:
        return "decreasing"
    return None


def _check_ramp_budget(ramp_count: int, entries: int, details: _Details) -> None:
    if ramp_count > MAX_RAMP_ENTRIES or entries > MAX_RAMP_ENTRIES:
        details.invalid(
            "/ramps", "Ramps exceed the palette budget", "too_many", maximum=MAX_RAMP_ENTRIES
        )


def _check_colors(
    profile: ColorProfile,
    colors: tuple[PaletteColor, ...],
    details: _Details,
    first: dict[str, str],
) -> dict[str, int]:
    """Check colours; ``first`` maps every ID seen so far to its first pointer."""
    maximum = PROFILE_MAX_COLORS[profile]
    strict: dict[str, object] = {"profile": "strict"} if profile == "strict" else {}
    if not colors:
        details.invalid("/colors", "Palette needs at least one color", "too_short", minimum=1)
    if len(colors) > maximum:
        # Same reasons as the schema: a strict-profile rule vs the array length.
        reason = "too_many" if strict else "too_long"
        details.invalid("/colors", "Too many colors", reason, maximum=maximum, **strict)
    index: dict[str, int] = {}
    for position, color in enumerate(colors):
        pointer = f"/colors/{position}/id"
        if color.id in first:
            details.invalid(pointer, "ID is already used", "duplicate_id", first=first[color.id])
        else:
            first[color.id] = pointer
            index[color.id] = position
        if profile == "strict" and color.rgba.a not in (0, 255):
            details.invalid(
                f"/colors/{position}/rgba", "Alpha must be 00 or FF", "partial_alpha", **strict
            )
    return index


def _check_ramps(
    ramps: tuple[Ramp, ...], index: Mapping[str, int], details: _Details, first: dict[str, str]
) -> None:
    for ramp_index, ramp in enumerate(ramps):
        pointer = f"/ramps/{ramp_index}/id"
        if ramp.id in first:
            details.invalid(pointer, "ID is already used", "duplicate_id", first=first[ramp.id])
        else:
            first[ramp.id] = pointer
        if len(ramp.colors) < MIN_RAMP_LENGTH:
            details.invalid(
                f"/ramps/{ramp_index}/colors",
                "Ramp needs at least two colors",
                "too_short",
                minimum=MIN_RAMP_LENGTH,
            )
        seen: set[str] = set()
        for position, color_id in enumerate(ramp.colors):
            step = f"/ramps/{ramp_index}/colors/{position}"
            if color_id not in index:
                details.missing(step)
            elif color_id in seen:
                details.invalid(step, "Ramp repeats a color", "duplicate_ramp_color")
            seen.add(color_id)


def _object(
    data: object, pointer: str, required: set[str], optional: set[str], details: _Details
) -> dict[str, object] | None:
    if type(data) is not dict or not all(type(key) is str for key in data):
        details.invalid(pointer, "expected an object", "wrong_type")
        return None
    for key in sorted(required - data.keys()):
        details.invalid(f"{pointer}/{key}", "field is required", "missing")
    if data.keys() - required - optional:
        details.invalid(pointer, "object has unknown fields", "unknown_field")
    return data


def _id_field(data: dict[str, object], pointer: str, key: str, details: _Details) -> str | None:
    if key not in data:
        return None
    value = data[key]
    if not is_id(value):
        details.invalid(f"{pointer}/{key}", "must be a MoanArt ID", "invalid_id")
        return None
    return str(value)


def _array(value: object, pointer: str, details: _Details, *, maximum: int) -> list[object] | None:
    if type(value) is not list:
        details.invalid(pointer, "expected an array", "wrong_type")
        return None
    if len(value) > maximum:  # checked before walking untrusted items
        details.invalid(pointer, "too many items", "too_long", maximum=maximum)
        return None
    return value


def _read_colors(value: object, details: _Details) -> tuple[PaletteColor, ...] | None:
    if value is None:
        return None
    items = _array(value, "/colors", details, maximum=MAX_COLORS_RGBA)
    if items is None:
        return None
    colors: list[PaletteColor] = []
    for position, item in enumerate(items):
        pointer = f"/colors/{position}"
        entry = _object(item, pointer, {"id", "rgba"}, set(), details)
        if entry is None:
            continue
        color_id = _id_field(entry, pointer, "id", details)
        rgba = None
        if "rgba" in entry:
            try:
                rgba = Rgba.parse(entry["rgba"])
            except ValidationError:
                details.invalid(f"{pointer}/rgba", "color must be #RRGGBBAA", "not_rgba_hex")
        if color_id is not None and rgba is not None:
            colors.append(PaletteColor(color_id, rgba))
    return tuple(colors)


def _ramp_entries(items: list[object]) -> int:
    """Total members of well-formed ramp objects, counted without walking members."""
    total = 0
    for item in items:
        members = item.get("colors") if type(item) is dict else None
        if type(members) is list:
            total += len(members)
    return total


def _read_ramps(value: object, details: _Details) -> tuple[Ramp, ...] | None:
    items = _array(value, "/ramps", details, maximum=MAX_RAMP_ENTRIES)
    if items is None:
        return None
    entries = _ramp_entries(items)
    if entries > MAX_RAMP_ENTRIES:  # whole budget before walking any member
        _check_ramp_budget(len(items), entries, details)
        return None
    ramps: list[Ramp] = []
    for position, item in enumerate(items):
        pointer = f"/ramps/{position}"
        entry = _object(item, pointer, {"id", "colors"}, set(), details)
        if entry is None:
            continue
        ramp_id = _id_field(entry, pointer, "id", details)
        members = (
            _array(entry["colors"], f"{pointer}/colors", details, maximum=MAX_COLORS_RGBA)
            if "colors" in entry
            else None
        )
        ids: list[str] = []
        for index, member in enumerate(members or ()):
            if is_id(member):
                ids.append(str(member))
            else:
                details.invalid(f"{pointer}/colors/{index}", "must be a MoanArt ID", "invalid_id")
        if ramp_id is not None and members is not None:
            ramps.append(Ramp(ramp_id, tuple(ids)))
    return tuple(ramps)
