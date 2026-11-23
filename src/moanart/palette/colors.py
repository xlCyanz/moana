"""RGBA colour values, profiles and luminance ordering (MOANART.md section 9, ADR-014).

Colours are straight sRGB-encoded RGBA with integer channels. The only textual form
is canonical ``#RRGGBBAA`` in upper case; ``#RRGGBB`` and other notations are
rejected rather than guessed. A colour whose alpha is zero is *transparent*: its
RGB is irrelevant to the image (MOANART.md section 5), so value comparisons use
:meth:`Rgba.normalized`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Literal, final

from moanart.core.coordinates import require_int
from moanart.core.errors import ValidationError
from moanart.core.ids import is_rgba_hex
from moanart.core.limits import MAX_COLORS_RGBA, MAX_COLORS_STRICT

__all__ = [
    "LINEAR_SCALE",
    "LUMINANCE_SCALE",
    "PROFILES",
    "PROFILE_MAX_COLORS",
    "SRGB_TO_LINEAR",
    "TRANSPARENT",
    "ColorProfile",
    "Rgba",
]

ColorProfile = Literal["strict", "rgba"]
PROFILES: Final[tuple[ColorProfile, ...]] = ("strict", "rgba")
PROFILE_MAX_COLORS: Final[Mapping[ColorProfile, int]] = MappingProxyType(
    {"strict": MAX_COLORS_STRICT, "rgba": MAX_COLORS_RGBA}
)

LINEAR_SCALE: Final = 65_535
# round(65535 * linear(v / 255)) with the IEC 61966-2-1 sRGB transfer function.
# Written out instead of computed with pow() at import so no libm rounding can
# differ between platforms; tests check it against the formula.
SRGB_TO_LINEAR: Final[tuple[int, ...]] = (
    0,
    20,
    40,
    60,
    80,
    99,
    119,
    139,
    159,
    179,
    199,
    219,
    241,
    264,
    288,
    313,
    340,
    367,
    396,
    427,
    458,
    491,
    526,
    562,
    599,
    637,
    677,
    718,
    761,
    805,
    851,
    898,
    947,
    997,
    1048,
    1101,
    1156,
    1212,
    1270,
    1330,
    1391,
    1453,
    1517,
    1583,
    1651,
    1720,
    1790,
    1863,
    1937,
    2013,
    2090,
    2170,
    2250,
    2333,
    2418,
    2504,
    2592,
    2681,
    2773,
    2866,
    2961,
    3058,
    3157,
    3258,
    3360,
    3464,
    3570,
    3678,
    3788,
    3900,
    4014,
    4129,
    4247,
    4366,
    4488,
    4611,
    4736,
    4864,
    4993,
    5124,
    5257,
    5392,
    5530,
    5669,
    5810,
    5953,
    6099,
    6246,
    6395,
    6547,
    6700,
    6856,
    7014,
    7174,
    7335,
    7500,
    7666,
    7834,
    8004,
    8177,
    8352,
    8528,
    8708,
    8889,
    9072,
    9258,
    9445,
    9635,
    9828,
    10022,
    10219,
    10417,
    10619,
    10822,
    11028,
    11235,
    11446,
    11658,
    11873,
    12090,
    12309,
    12530,
    12754,
    12980,
    13209,
    13440,
    13673,
    13909,
    14146,
    14387,
    14629,
    14874,
    15122,
    15371,
    15623,
    15878,
    16135,
    16394,
    16656,
    16920,
    17187,
    17456,
    17727,
    18001,
    18277,
    18556,
    18837,
    19121,
    19407,
    19696,
    19987,
    20281,
    20577,
    20876,
    21177,
    21481,
    21787,
    22096,
    22407,
    22721,
    23038,
    23357,
    23678,
    24002,
    24329,
    24658,
    24990,
    25325,
    25662,
    26001,
    26344,
    26688,
    27036,
    27386,
    27739,
    28094,
    28452,
    28813,
    29176,
    29542,
    29911,
    30282,
    30656,
    31033,
    31412,
    31794,
    32179,
    32567,
    32957,
    33350,
    33745,
    34143,
    34544,
    34948,
    35355,
    35764,
    36176,
    36591,
    37008,
    37429,
    37852,
    38278,
    38706,
    39138,
    39572,
    40009,
    40449,
    40891,
    41337,
    41785,
    42236,
    42690,
    43147,
    43606,
    44069,
    44534,
    45002,
    45473,
    45947,
    46423,
    46903,
    47385,
    47871,
    48359,
    48850,
    49344,
    49841,
    50341,
    50844,
    51349,
    51858,
    52369,
    52884,
    53401,
    53921,
    54445,
    54971,
    55500,
    56032,
    56567,
    57105,
    57646,
    58190,
    58737,
    59287,
    59840,
    60396,
    60955,
    61517,
    62082,
    62650,
    63221,
    63795,
    64372,
    64952,
    65535,
)
LUMINANCE_SCALE: Final = 10_000 * LINEAR_SCALE
""":attr:`Rgba.luminance` of opaque white."""

_CHANNELS: Final = ("r", "g", "b", "a")


@final
@dataclass(frozen=True, slots=True)
class Rgba:
    """Straight RGBA colour with each channel an ``int`` in ``0..255``."""

    r: int
    g: int
    b: int
    a: int

    def __post_init__(self) -> None:
        for name in _CHANNELS:
            require_int(getattr(self, name), name, minimum=0, maximum=255)

    @classmethod
    def parse(cls, text: object) -> Rgba:
        """Parse ``#RRGGBBAA`` (either case); any other form is a ``ValidationError``.

        Only an exact ``str`` is accepted, and the rejected text is never echoed.
        """
        if not is_rgba_hex(text):
            raise ValidationError(
                "color must be #RRGGBBAA",
                context={"field": "rgba", "reason": "not_rgba_hex"},
            )
        value = str(text)
        r, g, b, a = (int(value[i : i + 2], 16) for i in range(1, 9, 2))
        return cls(r, g, b, a)

    @property
    def hex(self) -> str:
        """Canonical ``#RRGGBBAA`` in upper case."""
        return f"#{self.r:02X}{self.g:02X}{self.b:02X}{self.a:02X}"

    @property
    def is_transparent(self) -> bool:
        """Whether alpha is zero."""
        return self.a == 0

    @property
    def is_opaque(self) -> bool:
        """Whether alpha is 255."""
        return self.a == 255

    def normalized(self) -> Rgba:
        """This colour, or ``TRANSPARENT`` when alpha is zero (MOANART.md section 5)."""
        return TRANSPARENT if self.a == 0 else self

    def as_tuple(self) -> tuple[int, int, int, int]:
        """``(r, g, b, a)``."""
        return (self.r, self.g, self.b, self.a)

    @property
    def luminance(self) -> int:
        """Relative luminance ``Y`` of the RGB, as an integer up to :data:`LUMINANCE_SCALE`.

        ``2126 R + 7152 G + 722 B`` over the *linearised* channels
        (:data:`SRGB_TO_LINEAR`), so saturated blues and reds order correctly
        against greys. CIE L* is monotonic in ``Y``, so ``Y`` orders ramps exactly
        as L* would without floating point. Alpha is ignored: callers decide how
        transparent and translucent steps are treated.
        """
        lin = SRGB_TO_LINEAR
        return 2126 * lin[self.r] + 7152 * lin[self.g] + 722 * lin[self.b]


TRANSPARENT: Final = Rgba(0, 0, 0, 0)
