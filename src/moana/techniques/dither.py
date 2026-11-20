"""Ordered (Bayer) dithering with integer coverage and an explicit anchor (ADR-025).

Normative rule (MOANA.md section 10). For a Bayer matrix ``M`` of side ``N`` (2 or 4)
anchored at the canvas pixel ``origin = (ox, oy)``, pixel ``(x, y)`` has threshold::

    t(x, y) = M[(y - oy) mod N][(x - ox) mod N]

(row index from ``y``, column index from ``x``; ``mod`` is the mathematical modulo,
in ``[0, N)`` also for negative operands). With integer ``coverage`` ``c`` in
``0..N^2``, the pixel takes colour **B** when ``t < c`` and colour **A** otherwise.
So exactly ``c`` cells of every ``N x N`` period are B: coverage 0 is all A and
coverage ``N^2`` all B. The matrices are the standard recursive Bayer matrices:

* ``N = 2``: ``[[0, 2], [3, 1]]``.
* ``N = 4``: ``[[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]``.

Only pixels of the clipping mask are dithered: :func:`dither_mask` splits a mask into
its A part and its B part, which are disjoint and together equal the mask, so nothing
outside the mask is ever selected. The phase depends only on canvas coordinates and
``origin``: translating ``origin`` by a multiple of ``N`` changes nothing, adjacent
tiles that share ``origin`` meet without seams, and repeated renders (or frames that
keep ``origin``) never flicker. Everything is integer arithmetic; no seed, hash, clock
or float is involved.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal, get_args

from moana.core.coordinates import Point, require_int
from moana.core.dither import DITHER_SIZES
from moana.core.errors import ValidationError
from moana.geometry import CellTable, Mask, select_periodic

__all__ = [
    "BAYER_2X2",
    "BAYER_4X4",
    "DITHER_PARTS",
    "DITHER_SIZES",
    "DitherPart",
    "OrderedDither",
    "bayer_matrix",
    "dither_cells",
    "dither_mask",
    "split_dither",
]

BAYER_2X2: Final = ((0, 2), (3, 1))
"""Standard 2 x 2 Bayer thresholds, ``BAYER_2X2[row][column]``."""
BAYER_4X4: Final = (
    (0, 8, 2, 10),
    (12, 4, 14, 6),
    (3, 11, 1, 9),
    (15, 7, 13, 5),
)
"""Standard 4 x 4 Bayer thresholds, ``BAYER_4X4[row][column]``."""

DitherPart = Literal["a", "b"]
DITHER_PARTS: Final[tuple[DitherPart, ...]] = get_args(DitherPart)
"""``a``: pixels with ``threshold >= coverage``; ``b``: ``threshold < coverage``."""

_MATRICES: Final = {2: BAYER_2X2, 4: BAYER_4X4}


def _check_size(size: object) -> int:
    if type(size) is not int:
        raise ValidationError(
            "size must be an integer",
            context={"field": "size", "reason": "not_integer", "value_type": type(size).__name__},
        )
    if size not in _MATRICES:
        raise ValidationError(
            "size must be 2 or 4", context={"field": "size", "reason": "unsupported_size"}
        )
    return size


def bayer_matrix(size: int) -> tuple[tuple[int, ...], ...]:
    """The Bayer threshold matrix of side ``size`` (2 or 4), ``[row][column]``."""
    return _MATRICES[_check_size(size)]


def _check_part(part: object) -> DitherPart:
    for known in DITHER_PARTS:
        if part == known and type(part) is str:
            return known
    raise ValidationError(
        "part must be a or b", context={"field": "part", "reason": "unknown_part"}
    )


@dataclass(frozen=True, slots=True)
class OrderedDither:
    """A Bayer pattern of side ``size`` with ``coverage`` B cells per period, at ``origin``.

    ``size`` is 2 or 4 (``unsupported_size``); ``coverage`` an ``int`` in
    ``0..size^2`` (``out_of_range``). ``bool`` and floats are rejected
    (``not_integer``). ``origin`` is any canvas :class:`~moana.core.Point`.
    """

    size: int
    coverage: int
    origin: Point

    def __post_init__(self) -> None:
        size = _check_size(self.size)
        require_int(self.coverage, "coverage", minimum=0, maximum=size * size)
        if not isinstance(self.origin, Point):
            raise TypeError("origin must be a Point value")

    def threshold(self, point: Point) -> int:
        """Bayer threshold of the canvas pixel ``point`` (mathematical modulo)."""
        if not isinstance(point, Point):
            raise TypeError("point must be a Point value")
        size = self.size
        row = (point.y - self.origin.y) % size
        column = (point.x - self.origin.x) % size
        return _MATRICES[size][row][column]

    def part(self, point: Point) -> DitherPart:
        """``"b"`` if ``threshold(point) < coverage``, else ``"a"``."""
        return "b" if self.threshold(point) < self.coverage else "a"


def dither_cells(dither: OrderedDither, part: DitherPart) -> CellTable:
    """One period of ``part``: ``True`` where that colour is chosen, ``[row][column]``."""
    if not isinstance(dither, OrderedDither):
        raise TypeError("dither must be an OrderedDither value")
    wanted = _check_part(part) == "b"
    coverage = dither.coverage
    return tuple(
        tuple((threshold < coverage) is wanted for threshold in row)
        for row in _MATRICES[dither.size]
    )


def dither_mask(mask: Mask, dither: OrderedDither, part: DitherPart) -> Mask:
    """Pixels of ``mask`` that take colour ``part`` (``"a"`` or ``"b"``).

    The result is a subset of ``mask`` with the same storage box (or empty): the A
    and B parts are disjoint and their union is ``mask``.
    """
    if not isinstance(mask, Mask):
        raise TypeError("mask must be a Mask value")
    return select_periodic(mask, dither_cells(dither, part), dither.origin)


def split_dither(mask: Mask, dither: OrderedDither) -> tuple[Mask, Mask]:
    """``(A part, B part)`` of ``mask``; see :func:`dither_mask`."""
    return dither_mask(mask, dither, "a"), dither_mask(mask, dither, "b")
