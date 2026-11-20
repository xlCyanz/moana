"""Fixed-point path commands and their integer flattening (MOANA.md section 6, ADR-023).

A path is a list of commands ``M``/``L``/``Q``/``C``/``Z`` whose coordinates are
integers in units of 1/256 pixel (:data:`PATH_UNITS`). This module owns everything
about a path that is pure integer arithmetic, so that ``schema`` (validation),
``render.budget`` (cost, without NumPy) and the AggDraw adapter of ``geometry``
(rasterisation) share one definition:

* **Grammar.** ``M x y``, ``L x y``, ``Q x1 y1 x y``, ``C x1 y1 x2 y2 x y`` and ``Z``.
  The first command is ``M``; every subpath (``M`` up to the next ``M`` or the end)
  has at least one drawing command (``L``/``Q``/``C``); ``Z`` ends its subpath, so
  only ``M`` may follow it. A subpath without ``Z`` is closed implicitly: both forms
  fill the same area (a path is a filled outline, never a stroke).
* **Flattening.** Curves become line segments here, never in the backend. A curve
  with second differences ``D`` (largest Manhattan norm of ``P0 - 2P1 + P2``, and of
  ``P1 - 2P2 + P3`` for cubics) takes ``n`` uniform steps in ``t``, the least with
  ``64 n^2 >= D`` (quadratic) or ``64 n^2 >= 3 D`` (cubic), clamped to
  ``1..MAX_PATH_CURVE_SEGMENTS``. That bounds the chord error by
  :data:`FLATNESS_UNITS` (1/16 px) below the clamp. Each point is the exact
  Bernstein rational rounded half to even, so flattening is invariant under whole-
  pixel translations and mirror images about pixel edges.
* **Segments.** Every flattened line segment plus one closing edge per subpath; at
  most :data:`~moana.core.limits.MAX_PATH_SEGMENTS`.
* **Cost.** The coverage buffer of a path is its clipped storage box plus
  :data:`PATH_BUFFER_MARGIN` on every side; :func:`path_raster_visits` and
  :func:`path_raster_bytes` are the ``budget-v4`` formulas, shared by the cost plan
  and the AggDraw adapter so that both read the same numbers.

:class:`PathCommand` and :class:`FixedPath` validate themselves on construction, so a
value built by hand obeys the same rules as one from :func:`parse_path`. Nothing here
allocates per pixel; work is linear in commands and segments.
"""

from __future__ import annotations

import math
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Final

from moana.core.coordinates import MAX_COORDINATE, Box
from moana.core.errors import ValidationError
from moana.core.limits import (
    MAX_PATH_COMMANDS,
    MAX_PATH_CURVE_SEGMENTS,
    MAX_PATH_SEGMENTS,
)

__all__ = [
    "FLATNESS_UNITS",
    "MAX_PATH_COORDINATE",
    "MIN_PATH_COMMANDS",
    "PATH_BACKEND_FIXED_BYTES",
    "PATH_BUFFER_MARGIN",
    "PATH_CELL_BYTES",
    "PATH_COMMAND_BYTES",
    "PATH_COMMAND_POINTS",
    "PATH_UNITS",
    "FixedPath",
    "FixedPoint",
    "PathCommand",
    "curve_steps",
    "parse_path",
    "path_buffer_box",
    "path_raster_bytes",
    "path_raster_visits",
]

PATH_UNITS: Final = 256
"""Fixed-point units per pixel: a path coordinate ``v`` is the position ``v / 256``."""
MAX_PATH_COORDINATE: Final = MAX_COORDINATE * PATH_UNITS
"""Largest absolute path coordinate: the pixel range of section 5 in 1/256 units."""
FLATNESS_UNITS: Final = 16
"""Chord error bound of the flattening (1/16 px) for curves under the step clamp."""
MIN_PATH_COMMANDS: Final = 2
PATH_COMMAND_POINTS: Final[Mapping[str, int]] = MappingProxyType(
    {"M": 1, "L": 1, "Q": 2, "C": 3, "Z": 0}
)
"""Points (coordinate pairs) of each command letter (read-only)."""
PATH_BUFFER_MARGIN: Final = 1
"""Pixels of coverage buffer around a path's storage box (the outline grows ~1/4 px)."""
PATH_CELL_BYTES: Final = 24
"""Bytes of one AGG coverage cell plus its sorted pointer (``budget-v4``)."""
PATH_COMMAND_BYTES: Final = 256
"""Bytes of one parsed command and its backend vertices (``budget-v4``)."""
PATH_BACKEND_FIXED_BYTES: Final = 128 * 1024
"""Native heap AGG reserves per drawn path whatever its size (measured ~79 KB on
AggDraw 1.4.1 for a 1-pixel triangle); ``tracemalloc`` does not see it."""

FixedPoint = tuple[int, int]


def _invalid(message: str, reason: str, index: int | None = None, **extra: int) -> ValidationError:
    context: dict[str, object] = {"field": "commands", "reason": reason, **extra}
    if index is not None:
        context["index"] = index
    return ValidationError(message, context=context)


@dataclass(frozen=True, slots=True)
class PathCommand:
    """One command: its letter and its points in 1/256 pixel units.

    Construction checks the letter, the number of points and every coordinate (an
    exact ``int`` within :data:`MAX_PATH_COORDINATE`); a failure is a
    :class:`ValidationError` without ``index`` (the command stands alone).
    """

    op: str
    points: tuple[FixedPoint, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.op, str) or self.op not in PATH_COMMAND_POINTS:
            raise _invalid("unknown path command", "unknown_command")
        points = self.points
        if not isinstance(points, tuple) or len(points) != PATH_COMMAND_POINTS[self.op]:
            raise _invalid("wrong number of path coordinates", "wrong_arity")
        for point in points:
            if not isinstance(point, tuple) or len(point) != 2:
                raise _invalid("wrong number of path coordinates", "wrong_arity")
            for value in point:
                _coordinate(value, None)


def _round_half_even(numerator: int, denominator: int) -> int:
    """Nearest integer to ``numerator / denominator`` (``denominator > 0``), ties to even."""
    quotient, remainder = divmod(numerator, denominator)
    twice = 2 * remainder
    if twice > denominator or (twice == denominator and quotient % 2 == 1):
        quotient += 1
    return quotient


def _manhattan(a: FixedPoint, b: FixedPoint, c: FixedPoint) -> int:
    """Manhattan norm of the second difference ``a - 2b + c``."""
    return abs(a[0] - 2 * b[0] + c[0]) + abs(a[1] - 2 * b[1] + c[1])


def curve_steps(points: Sequence[FixedPoint]) -> int:
    """Uniform steps of a quadratic (3 points) or cubic (4 points) Bezier curve.

    The least ``n`` with ``64 n^2 >= k D`` (``k`` 1 for quadratics, 3 for cubics),
    clamped to ``1..MAX_PATH_CURVE_SEGMENTS``; see the module docstring.
    """
    if len(points) == 3:
        need = _manhattan(*points)
    elif len(points) == 4:
        a, b, c, d = points
        need = 3 * max(_manhattan(a, b, c), _manhattan(b, c, d))
    else:
        raise ValueError("a curve has 3 (quadratic) or 4 (cubic) points")
    target = -(-need // (4 * FLATNESS_UNITS))  # ceil(k D / 64)
    steps = math.isqrt(target)
    if steps * steps < target:
        steps += 1
    return min(MAX_PATH_CURVE_SEGMENTS, max(1, steps))


def _bezier_point(points: Sequence[FixedPoint], step: int, steps: int) -> FixedPoint:
    """Exact Bernstein point at ``t = step / steps`` rounded half to even."""
    degree = len(points) - 1
    s, t = steps - step, step
    weights = [math.comb(degree, i) * s ** (degree - i) * t**i for i in range(degree + 1)]
    denominator = steps**degree
    x = sum(w * p[0] for w, p in zip(weights, points, strict=True))
    y = sum(w * p[1] for w, p in zip(weights, points, strict=True))
    return _round_half_even(x, denominator), _round_half_even(y, denominator)


def _coordinate(value: object, index: int | None) -> int:
    if type(value) is not int:
        raise _invalid("path coordinates must be integers", "not_integer", index)
    if not -MAX_PATH_COORDINATE <= value <= MAX_PATH_COORDINATE:
        raise _invalid(
            "path coordinate out of range",
            "out_of_range",
            index,
            minimum=-MAX_PATH_COORDINATE,
            maximum=MAX_PATH_COORDINATE,
        )
    return value


def _command(raw: object, index: int) -> PathCommand:
    if isinstance(raw, str | bytes) or not isinstance(raw, Sequence) or not raw:
        raise _invalid("a path command is a non-empty array", "not_command", index)
    op = raw[0]
    if not isinstance(op, str) or op not in PATH_COMMAND_POINTS:
        raise _invalid("unknown path command", "unknown_command", index)
    count = PATH_COMMAND_POINTS[op]
    if len(raw) != 1 + 2 * count:
        raise _invalid("wrong number of path coordinates", "wrong_arity", index)
    values = [_coordinate(value, index) for value in raw[1:]]
    points = tuple((values[i], values[i + 1]) for i in range(0, len(values), 2))
    return PathCommand(op, points)


def _check_order(commands: Sequence[PathCommand]) -> None:
    """First ``M``; no empty subpath; only ``M`` after ``Z``."""
    drawn = False  # the current subpath has a drawing command
    closed = False
    for index, command in enumerate(commands):
        if index == 0 and command.op != "M":
            raise _invalid("a path starts with M", "path_start", index)
        if closed and command.op != "M":
            raise _invalid("only M may follow Z", "command_after_close", index)
        if command.op in {"M", "Z"} and index > 0 and not drawn:
            raise _invalid("a subpath needs a drawing command", "empty_subpath", index)
        drawn = command.op in {"L", "Q", "C"} or (drawn and command.op != "M")
        closed = command.op == "Z"
    if not drawn:
        raise _invalid("a subpath needs a drawing command", "empty_subpath", len(commands) - 1)


def _segment_count(commands: Sequence[PathCommand]) -> int:
    """Flattened segments plus one closing edge per subpath; fails past the limit."""
    segments = 0
    current: FixedPoint = (0, 0)
    for index, command in enumerate(commands):
        if command.op in {"M", "L"}:
            segments += 1  # an M stands for the closing edge of its subpath
        elif command.op in {"Q", "C"}:
            segments += curve_steps((current, *command.points))
        if command.points:
            current = command.points[-1]
        if segments > MAX_PATH_SEGMENTS:
            raise _invalid(
                "path has too many segments once flattened",
                "too_many_segments",
                index,
                maximum=MAX_PATH_SEGMENTS,
            )
    return segments


def _check_count(count: int) -> None:
    if not MIN_PATH_COMMANDS <= count <= MAX_PATH_COMMANDS:
        raise _invalid(
            f"a path has {MIN_PATH_COMMANDS} to {MAX_PATH_COMMANDS} commands",
            "out_of_range",
            minimum=MIN_PATH_COMMANDS,
            maximum=MAX_PATH_COMMANDS,
        )


@dataclass(frozen=True, slots=True)
class FixedPath:
    """A validated path: build it with :func:`parse_path` or from :class:`PathCommand`.

    Construction checks the count, the order rules and the flattened segments, so a
    hand-built value is as safe for the adapter as a parsed one. ``segments`` is
    derived (never passed): the edges of the flattened outline, closing edges
    included.
    """

    commands: tuple[PathCommand, ...]
    segments: int = field(init=False, compare=False)

    def __post_init__(self) -> None:
        commands = self.commands
        if not isinstance(commands, tuple):
            raise _invalid("path commands must be an array", "not_sequence")
        _check_count(len(commands))
        for index, command in enumerate(commands):
            if not isinstance(command, PathCommand):
                raise _invalid("a path command is a PathCommand value", "not_command", index)
        _check_order(commands)
        object.__setattr__(self, "segments", _segment_count(commands))

    @property
    def bounds(self) -> Box | None:
        """Pixel box ``[floor(min / 256), ceil(max / 256))`` of every point; ``None`` if flat.

        Every flattened point is a rounded convex combination of command points, so
        the outline lies within this box. The *mask* is ``coverage >= 128`` cut to
        this box clipped to the canvas: the adapter crops the coverage buffer (whose
        margin does receive the outline's growth) to it, so it is that crop, not the
        backend, that keeps pixels outside the box out of the mask. The box belongs
        to the whole path, so the cut is not local: a far subpath widens the box and
        can let in threshold pixels of the grown outline next to another subpath.
        """
        xs = [x for command in self.commands for x, _ in command.points]
        ys = [y for command in self.commands for _, y in command.points]
        x0, y0 = min(xs) // PATH_UNITS, min(ys) // PATH_UNITS
        x1, y1 = -(-max(xs) // PATH_UNITS), -(-max(ys) // PATH_UNITS)
        if x0 == x1 or y0 == y1:
            return None
        return Box(x0, y0, x1, y1)

    @property
    def reach(self) -> int:
        """Largest absolute pixel position any point names, rounded up."""
        return max(-(-abs(v) // PATH_UNITS) for c in self.commands for p in c.points for v in p)

    @property
    def manhattan_length(self) -> int:
        """Manhattan length of the control polygons and closing edges, in pixels (ceil).

        It bounds the length of the flattened outline: Bezier coordinates have no
        more variation than their control points.
        """
        total = 0
        start = current = (0, 0)
        for command in self.commands:
            if command.op == "M":
                total += abs(current[0] - start[0]) + abs(current[1] - start[1])
                start = current = command.points[0]
                continue
            for point in command.points:
                total += abs(point[0] - current[0]) + abs(point[1] - current[1])
                current = point
        total += abs(current[0] - start[0]) + abs(current[1] - start[1])
        return -(-total // PATH_UNITS)

    def cell_bound(self, box: Box) -> int:
        """Upper bound of the coverage cells the backend accumulates in ``box``.

        A segment clipped to the buffer splits into at most three pieces (the
        visible part and its projections on the side edges), each crossing at most
        ``width + height + 1`` cells; a piece also crosses at most its Manhattan
        length plus one cell, and the projections at most the segment's own length.
        The factor 2 between :data:`~moana.core.limits.MAX_PATH_CELLS` and AGG's
        real capacity also covers the extra cells of the ~1/4 px growth at joins.
        """
        by_length = 2 * self.manhattan_length + 3 * self.segments
        by_box = 3 * self.segments * (box.width + box.height + 1)
        return min(by_length, by_box)

    def outline(self) -> Iterator[tuple[bool, FixedPoint]]:
        """Vertices of the flattened outline; ``True`` starts a new (closed) subpath."""
        current: FixedPoint = (0, 0)
        for command in self.commands:
            if command.op == "M":
                current = command.points[0]
                yield True, current
            elif command.op == "L":
                current = command.points[0]
                yield False, current
            elif command.op in {"Q", "C"}:
                points = (current, *command.points)
                steps = curve_steps(points)
                for step in range(1, steps + 1):
                    yield False, _bezier_point(points, step, steps)
                current = command.points[-1]


def path_buffer_box(box: Box) -> Box:
    """Coverage buffer of a storage ``box``, with :data:`PATH_BUFFER_MARGIN` per side.

    The result is placed at the origin; only its size matters.
    """
    margin = 2 * PATH_BUFFER_MARGIN
    return Box(0, 0, box.width + margin, box.height + margin)


def path_raster_visits(path: FixedPath, box: Box | None) -> int:
    """``budget-v4`` visits of rasterising ``path`` into its clipped storage ``box``.

    Flattened segments (unclipped) plus, when the box is not empty, the bounded
    cells and three passes over the buffer (clear, sweep, threshold).
    """
    if box is None:
        return path.segments
    buffer = path_buffer_box(box)
    return path.segments + path.cell_bound(buffer) + 3 * buffer.area


def path_raster_bytes(path: FixedPath, box: Box | None) -> int:
    """``budget-v4`` peak bytes of rasterising ``path`` into its storage ``box``.

    Mask, coverage buffer and its copy, cells, commands and the backend's fixed
    native heap (:data:`PATH_BACKEND_FIXED_BYTES`); ``0`` when the box is empty,
    because the backend is not called.
    """
    if box is None:
        return 0
    buffer = path_buffer_box(box)
    return (
        box.area
        + 2 * buffer.area
        + PATH_CELL_BYTES * path.cell_bound(buffer)
        + PATH_COMMAND_BYTES * len(path.commands)
        + PATH_BACKEND_FIXED_BYTES
    )


def parse_path(commands: object) -> FixedPath:
    """Validate raw commands (``("M", x, y)``, ...) into a :class:`FixedPath`.

    Raises :class:`ValidationError` with ``field`` ``commands``, a ``reason``
    (``not_sequence``, ``out_of_range``, ``not_command``, ``unknown_command``,
    ``wrong_arity``, ``not_integer``, ``path_start``, ``empty_subpath``,
    ``command_after_close``, ``too_many_segments``) and, for one command, its
    ``index``. The count is checked before any command is read.
    """
    if isinstance(commands, str | bytes) or not isinstance(commands, Sequence):
        raise _invalid("path commands must be an array", "not_sequence")
    _check_count(len(commands))
    return FixedPath(tuple(_command(raw, index) for index, raw in enumerate(commands)))
