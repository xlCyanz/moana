"""Pixel clusters of an RGBA image and their artistic warnings (MOANART.md section 8, ADR-027).

A *cluster* is a connected component of opaque pixels (alpha > 0) of exactly the
same RGBA value. Connectivity is explicit: ``4`` (edge neighbours, the default
analysis of section 8) or ``8`` (edges and corners, the option for diagonals).
Transparent pixels are background and belong to no cluster.

The analysis labels horizontal runs of equal colour (grouped per row in C) with a
union-find whose root is always the smallest run index, so clusters come out in
row-major order of their first pixel (``seed``). Runs of adjacent rows join when
they share an edge (``4``) or an edge or a corner (``8``). The number of opaque runs
is checked against :data:`~moanart.core.limits.MAX_CLUSTER_RUNS` after every row,
before labelling starts (``BudgetExceeded``, ``cluster_runs``). Runs, parents and
labels live in compact ``array`` buffers; the memory of a whole analysis is at most
:func:`cluster_bytes` of the canvas. No NumPy is imported here.

Findings are warnings, never failures, and nothing is ever modified or cleaned:

* ``singleton``: a cluster of exactly one pixel (an eye, a glint, a particle or an
  accident; the metric cannot tell, section 8).
* ``irregular_steps``: an abrupt step change in a one-pixel *stair*. A cluster is a
  stair when each of its rows (consecutive) holds one run and either every run
  starts where the previous one ends, to the right or to the left (a horizontal
  stair whose steps are the runs), or every run is one pixel long and ``x`` moves by
  ``0`` or by one fixed ``±1`` per row (a vertical stair whose steps are the
  columns). Stairs only form one cluster with connectivity ``8``. With at least four
  steps, two consecutive *interior* steps (the first and last are partial ends)
  whose lengths differ by more than one pixel are a finding. Every digital straight
  segment (such as a Bresenham ``line``) has interior steps of two consecutive
  lengths, so it never warns. Closed contours and arcs that turn from runs into
  columns are not stairs, so the rule rarely fires on them; doubling curves (steps
  1, 1, 2, 4) do warn and can be silenced by region.

A :class:`ClusterException` names a semantic region and the rules it silences; the
caller supplies the region masks. A finding whose pixels all lie in such a region is
moved to ``suppressed`` with that ``region_id`` (the first matching exception wins).
The masks are folded into a :class:`~moanart.geometry.MaskCover` (one bit per
exception and pixel, at most :data:`~moanart.core.limits.MAX_CLUSTER_EXCEPTIONS`), so
suppression costs the pixels of the findings, not findings x exceptions. Findings
are ordered by rule, region, ``y``, ``x`` (section 19). No sets, ``hash()`` or
floats decide anything.
"""

from __future__ import annotations

import sys
from array import array
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from itertools import groupby, pairwise
from typing import Final, Literal, get_args

from moanart.core.budget import Deadline
from moanart.core.coordinates import MAX_DIMENSION, Box, Dimensions, Point
from moanart.core.errors import BudgetExceeded, ReferenceError, ValidationError
from moanart.core.ids import check_id
from moanart.core.limits import MAX_CLUSTER_EXCEPTIONS, MAX_CLUSTER_RUNS
from moanart.geometry import Mask, MaskCover

__all__ = [
    "CLUSTER_FIXED_BYTES",
    "CLUSTER_RULES",
    "CLUSTER_RUN_BYTES",
    "CONNECTIVITIES",
    "Cluster",
    "ClusterException",
    "ClusterFinding",
    "ClusterReport",
    "ClusterRule",
    "Connectivity",
    "Severity",
    "analyze_clusters",
    "check_cluster_settings",
    "cluster_bytes",
]

Connectivity = Literal[4, 8]
CONNECTIVITIES: Final[tuple[Connectivity, ...]] = get_args(Connectivity)
ClusterRule = Literal["irregular_steps", "singleton"]
CLUSTER_RULES: Final[tuple[ClusterRule, ...]] = get_args(ClusterRule)
"""Rule IDs of the cluster findings, in order."""
Severity = Literal["warning"]
SEVERITY: Final[Severity] = "warning"
CLUSTER_RUN_BYTES: Final = 512
"""Upper bound of the bytes an analysis holds per opaque run (ADR-027).

Covers the run buffers, the union-find, the labels and, in the worst case of one
singleton cluster per run, its :class:`Cluster`, its :class:`ClusterFinding`, their
boxes and points and the list and tuple slots of the report. Measured peaks: 346
bytes per run for a 512 x 512 checkerboard (262 144 singletons) and about 300 for
dense irregular stairs; coordinates, messages and evidence pairs are shared.
"""
CLUSTER_FIXED_BYTES: Final = 64 * 1024
"""Fixed overhead of one analysis (one row of pixel values, small tables)."""
_MIN_STEPS: Final = 4
_CHECK_EVERY: Final = 4096
_NO_X: Final = 2**31 - 1  # larger than any canvas x; replaced by the first run
_SINGLETON_MESSAGE: Final = "isolated pixel: a cluster of exactly one pixel"
# One shared tuple: the pixel is the finding's box, and a finding per run must stay small.
_SINGLETON_EVIDENCE: Final[tuple[tuple[str, int | str], ...]] = (("area", 1),)
# Shared coordinate objects: every Box and Point of a report reuses them, so a
# cluster costs its own objects only (an immutable table, not mutable state).
_INTS: Final = tuple(range(MAX_DIMENSION + 1))

Evidence = tuple[tuple[str, int | str], ...]


@dataclass(frozen=True, slots=True)
class Cluster:
    """One connected component of equal colour: ``#RRGGBBAA``, bounds, pixels, seed.

    ``index`` is its position in :attr:`ClusterReport.clusters`; ``seed`` its first
    pixel in row-major order.
    """

    index: int
    color: str
    box: Box
    area: int
    seed: Point


@dataclass(frozen=True, slots=True)
class ClusterFinding:
    """An artistic warning about cluster ``cluster`` (section 19 incident fields).

    ``region_id`` is the region of the exception that suppressed it, else ``None``.
    ``evidence`` holds sorted ``(name, value)`` pairs.
    """

    rule_id: ClusterRule
    severity: Severity
    box: Box
    cluster: int
    color: str
    message: str
    evidence: Evidence
    region_id: str | None


@dataclass(frozen=True, slots=True)
class ClusterException:
    """Silence ``rules`` for findings that lie entirely in region ``region_id``.

    Part of the evaluation configuration (section 19), never of the document.
    """

    region_id: str
    rules: tuple[ClusterRule, ...]

    def __post_init__(self) -> None:
        check_id(self.region_id, "region_id")
        if type(self.rules) is not tuple or not self.rules:
            raise _invalid("rules", "rules must be a non-empty tuple of rule IDs", "empty")
        for rule in self.rules:
            if type(rule) is not str or rule not in CLUSTER_RULES:
                raise _invalid("rules", "unknown cluster rule", "unknown_rule")
        if len(dict.fromkeys(self.rules)) != len(self.rules):
            raise _invalid("rules", "repeated cluster rule", "duplicate_reference")


@dataclass(frozen=True, slots=True)
class ClusterReport:
    """Clusters, active warnings and suppressed findings of one image."""

    width: int
    height: int
    connectivity: Connectivity
    clusters: tuple[Cluster, ...]
    warnings: tuple[ClusterFinding, ...]
    suppressed: tuple[ClusterFinding, ...]

    @property
    def singletons(self) -> int:
        """Number of one-pixel clusters."""
        return sum(1 for cluster in self.clusters if cluster.area == 1)


@dataclass(frozen=True, slots=True)
class _Run:
    y: int
    x0: int
    x1: int
    key: int


class _Runs:
    """Opaque runs in row-major order, as parallel compact arrays."""

    __slots__ = ("keys", "x0", "x1", "y")

    def __init__(self) -> None:
        self.y, self.x0, self.x1 = array("i"), array("i"), array("i")
        self.keys = array("I")

    def __len__(self) -> int:
        return len(self.y)

    def run(self, index: int) -> _Run:
        y, x0, x1 = self.y[index], self.x0[index], self.x1[index]
        return _Run(_INTS[y], _INTS[x0], _INTS[x1], self.keys[index])


def cluster_bytes(dimensions: Dimensions) -> int:
    """Upper bound of the bytes :func:`analyze_clusters` holds for ``dimensions``.

    Runs never outnumber pixels, and labelling stops past
    :data:`~moanart.core.limits.MAX_CLUSTER_RUNS` (checked after every row, so at most
    one row more is held): ``CLUSTER_RUN_BYTES·min(area, MAX + width) + fixed``.
    The RGBA input and the region cover belong to the caller.
    """
    if not isinstance(dimensions, Dimensions):
        raise TypeError("dimensions must be a Dimensions value")
    runs = min(dimensions.area, MAX_CLUSTER_RUNS + dimensions.width)
    return CLUSTER_RUN_BYTES * runs + CLUSTER_FIXED_BYTES


def _invalid(field: str, message: str, reason: str) -> ValidationError:
    return ValidationError(message, context={"field": field, "reason": reason})


def _check_connectivity(connectivity: object) -> Connectivity:
    for known in CONNECTIVITIES:
        if type(connectivity) is int and connectivity == known:
            return known
    raise _invalid("connectivity", "connectivity must be 4 or 8", "unsupported_connectivity")


def check_cluster_settings(
    connectivity: object, exceptions: object
) -> tuple[Connectivity, tuple[ClusterException, ...]]:
    """Validate the evaluation configuration before anything is rendered or scanned.

    Raises ``ValidationError`` (``unsupported_connectivity``; ``exceptions``:
    ``duplicate_reference`` for a region with two exceptions, ``too_many_exceptions``
    past :data:`~moanart.core.limits.MAX_CLUSTER_EXCEPTIONS`) and ``TypeError`` for a
    sequence that does not hold :class:`ClusterException` values.
    """
    checked = _check_connectivity(connectivity)
    if isinstance(exceptions, str | bytes) or not isinstance(exceptions, Sequence):
        raise TypeError("exceptions must be a sequence of ClusterException values")
    if len(exceptions) > MAX_CLUSTER_EXCEPTIONS:
        raise _invalid("exceptions", "too many cluster exceptions", "too_many_exceptions")
    seen: dict[str, None] = {}
    for exception in exceptions:
        if not isinstance(exception, ClusterException):
            raise TypeError("exceptions must be a sequence of ClusterException values")
        if exception.region_id in seen:
            raise _invalid("exceptions", "region has several exceptions", "duplicate_reference")
        seen[exception.region_id] = None
    return checked, tuple(exceptions)


def _too_many_runs(count: int) -> BudgetExceeded:
    return BudgetExceeded(
        "image has too many colour runs to analyse",
        context={"resource": "cluster_runs", "limit": MAX_CLUSTER_RUNS, "estimated": count},
    )


def _alpha(key: int) -> int:
    """Alpha byte of a pixel read as a native-endian ``uint32``."""
    return key.to_bytes(4, sys.byteorder)[3]


def _hex(key: int) -> str:
    """``#RRGGBBAA`` of a pixel read as a native-endian ``uint32``."""
    return "#" + key.to_bytes(4, sys.byteorder).hex().upper()


def _checkpoint(deadline: Deadline | None, stage: str) -> None:
    if deadline is not None:
        deadline.checkpoint(stage)


def _scan(
    rgba: bytes, dimensions: Dimensions, deadline: Deadline | None
) -> tuple[_Runs, list[int]]:
    """Opaque runs of equal RGBA and the index of each row's first run.

    Each row is grouped in C (``itertools.groupby`` over ``uint32`` pixels), so the
    Python work is per run; the count and the deadline are checked after every row.
    """
    width = dimensions.width
    pixels = memoryview(rgba).cast("I")
    runs = _Runs()
    starts: list[int] = []
    for y in range(dimensions.height):
        starts.append(len(runs))
        x = 0
        for key, group in groupby(pixels[y * width : (y + 1) * width].tolist()):
            length = sum(1 for _ in group)
            if _alpha(key):
                runs.y.append(y)
                runs.x0.append(x)
                runs.x1.append(x + length)
                runs.keys.append(key)
            x += length
        if len(runs) > MAX_CLUSTER_RUNS:
            raise _too_many_runs(len(runs))
        _checkpoint(deadline, "cluster_runs")
    starts.append(len(runs))
    return runs, starts


def _find(parent: array[int], index: int) -> int:
    while parent[index] != index:
        parent[index] = parent[parent[index]]
        index = parent[index]
    return index


def _link_rows(
    runs: _Runs, previous: range, current: range, slack: int, parent: array[int]
) -> None:
    """Join runs of two adjacent rows that touch (``slack`` 1 adds corners) and match."""
    x0, x1, keys = runs.x0, runs.x1, runs.keys
    start, stop = previous.start, previous.stop
    for b in current:
        low, high = x0[b], x1[b]
        while start < stop and x1[start] + slack <= low:
            start += 1
        k = start
        while k < stop and x0[k] < high + slack:
            if keys[k] == keys[b]:
                first, second = _find(parent, k), _find(parent, b)
                if first != second:
                    parent[max(first, second)] = min(first, second)
            k += 1


def _labels(
    runs: _Runs, starts: list[int], connectivity: Connectivity, deadline: Deadline | None
) -> tuple[array[int], int]:
    """Cluster index of every run (clusters ordered by their first run) and their count."""
    parent = array("i", range(len(runs)))
    slack = 1 if connectivity == 8 else 0
    for y in range(1, len(starts) - 1):
        previous, current = range(starts[y - 1], starts[y]), range(starts[y], starts[y + 1])
        _link_rows(runs, previous, current, slack, parent)
        _checkpoint(deadline, "cluster_labels")
    # Every parent precedes its child (unions keep the smaller index), so one forward
    # pass flattens the forest, and a second relabels it in place: when run ``i`` is
    # read, its root (``<= i``) already holds its cluster index.
    for index in range(len(parent)):
        parent[index] = parent[parent[index]]
    count = 0
    for index in range(len(parent)):
        root = parent[index]
        if root == index:
            parent[index] = count
            count += 1
        else:
            parent[index] = parent[root]
    return parent, count


@dataclass(slots=True)
class _Tally:
    """Bounds, area and run count of every cluster, as compact arrays."""

    first: array[int]
    x0: array[int]
    x1: array[int]
    y1: array[int]
    area: array[int]
    runs: array[int]


def _tally(runs: _Runs, labels: array[int], count: int) -> _Tally:
    tally = _Tally(
        array("i", [-1]) * count,
        array("i", [_NO_X]) * count,
        array("i", [0]) * count,
        array("i", [0]) * count,
        array("i", [0]) * count,
        array("i", [0]) * count,
    )
    for index in range(len(runs)):
        label = labels[index]
        if tally.first[label] < 0:
            tally.first[label] = index
        tally.x0[label] = min(tally.x0[label], runs.x0[index])
        tally.x1[label] = max(tally.x1[label], runs.x1[index])
        tally.y1[label] = runs.y[index] + 1
        tally.area[label] += runs.x1[index] - runs.x0[index]
        tally.runs[label] += 1
    return tally


def _stair_members(runs: _Runs, labels: array[int], tally: _Tally) -> dict[int, array[int]]:
    """Run indices of the clusters that may be stairs: enough runs, one per row."""
    candidates: dict[int, array[int]] = {}
    for index in range(len(runs)):
        label = labels[index]
        height = tally.y1[label] - runs.y[tally.first[label]]
        if tally.runs[label] >= _MIN_STEPS and tally.runs[label] == height:
            candidates.setdefault(label, array("i")).append(index)
    return candidates


def _column_steps(members: list[_Run]) -> list[Box]:
    """Steps of a vertical stair (one-pixel runs, ``x`` moving by 0 or one fixed ±1)."""
    moves = [b.x0 - a.x0 for a, b in pairwise(members)]
    direction = [move for move in moves if move]
    if not direction or direction[0] not in (-1, 1) or any(m != direction[0] for m in direction):
        return []
    steps: list[Box] = []
    top = members[0]
    for previous, run in pairwise(members):
        if run.x0 != previous.x0:
            steps.append(Box(previous.x0, top.y, previous.x0 + 1, previous.y + 1))
            top = run
    last = members[-1]
    steps.append(Box(last.x0, top.y, last.x0 + 1, last.y + 1))
    return steps


def _stair_steps(members: list[_Run]) -> list[Box]:
    """Steps of a one-pixel stair in order, or ``[]`` if the cluster is not a stair."""
    if all(run.x1 - run.x0 == 1 for run in members):
        return _column_steps(members)
    pairs = list(pairwise(members))
    if all(b.x0 == a.x1 for a, b in pairs) or all(b.x1 == a.x0 for a, b in pairs):
        return [Box(run.x0, run.y, run.x1, run.y + 1) for run in members]
    return []


def _length(step: Box) -> int:
    return max(step.width, step.height)


def _hull(first: Box, second: Box) -> Box:
    return Box(
        min(first.x0, second.x0),
        min(first.y0, second.y0),
        max(first.x1, second.x1),
        max(first.y1, second.y1),
    )


class _Texts:
    """Messages and evidence pairs of one analysis, built once per distinct value."""

    __slots__ = ("_messages", "_pairs")

    def __init__(self) -> None:
        self._messages: dict[tuple[int, int], str] = {}
        self._pairs: dict[tuple[str, int], tuple[str, int]] = {}

    def message(self, first: int, second: int) -> str:
        key = (first, second)
        text = self._messages.get(key)
        if text is None:
            text = f"abrupt step change in a one-pixel stair: {first} then {second} pixels"
            self._messages[key] = text
        return text

    def pair(self, name: str, value: int) -> tuple[str, int]:
        key = (name, value)
        return self._pairs.setdefault(key, key)


def _step_findings(
    cluster: Cluster, members: list[_Run], texts: _Texts
) -> Iterator[tuple[ClusterFinding, tuple[Box, ...]]]:
    """``irregular_steps`` findings of one stair with the boxes holding their pixels."""
    steps = _stair_steps(members)
    if len(steps) < _MIN_STEPS:
        return
    for k in range(1, len(steps) - 2):
        first, second = steps[k], steps[k + 1]
        a, b = _length(first), _length(second)
        if abs(a - b) > 1:
            evidence: Evidence = (
                texts.pair("first_length", a),
                texts.pair("second_length", b),
                texts.pair("step", k),
                texts.pair("steps", len(steps)),
            )
            message = texts.message(a, b)
            finding = ClusterFinding(
                "irregular_steps",
                SEVERITY,
                _hull(first, second),
                cluster.index,
                cluster.color,
                message,
                evidence,
                None,
            )
            yield finding, (first, second)


def _singleton(cluster: Cluster) -> ClusterFinding:
    return ClusterFinding(
        "singleton",
        SEVERITY,
        cluster.box,
        cluster.index,
        cluster.color,
        _SINGLETON_MESSAGE,
        _SINGLETON_EVIDENCE,
        None,
    )


class _Suppressor:
    """First exception whose region holds every pixel of a finding, by rule."""

    __slots__ = ("_cover", "_regions", "_rules")

    def __init__(self, exceptions: tuple[ClusterException, ...], cover: MaskCover | None) -> None:
        self._cover = cover
        self._regions = tuple(exception.region_id for exception in exceptions)
        self._rules = {
            rule: sum(1 << i for i, e in enumerate(exceptions) if rule in e.rules)
            for rule in CLUSTER_RULES
        }

    def region(self, finding: ClusterFinding, boxes: tuple[Box, ...]) -> str | None:
        wanted = self._rules[finding.rule_id]
        if self._cover is None or not wanted:
            return None
        matches = self._cover.common(boxes) & wanted
        if not matches:
            return None
        return self._regions[(matches & -matches).bit_length() - 1]


def _cover(
    exceptions: tuple[ClusterException, ...],
    regions: Mapping[str, Mask] | None,
    dimensions: Dimensions,
    deadline: Deadline | None,
) -> MaskCover | None:
    """Fold the region mask of every exception, in order; each is read once."""
    if regions is None:
        regions = {}
    if not isinstance(regions, Mapping):
        raise TypeError("regions must be a mapping of region IDs to Mask values")
    for exception in exceptions:
        if exception.region_id not in regions:
            raise ReferenceError(
                "exception region has no mask",
                context={"field": "region_id", "reason": "unknown_region"},
            )
    if not exceptions:
        return None
    masks = (regions[exception.region_id] for exception in exceptions)
    try:
        return MaskCover.build(masks, dimensions, deadline=deadline)
    except TypeError:
        raise TypeError("regions must map region IDs to Mask values") from None


def _sort_key(finding: ClusterFinding) -> tuple[str, str, int, int, int, int, int]:
    box = finding.box
    region = finding.region_id or ""
    return (finding.rule_id, region, box.y0, box.x0, box.y1, box.x1, finding.cluster)


def _ordered(findings: list[ClusterFinding]) -> tuple[ClusterFinding, ...]:
    """``findings`` sorted by :func:`_sort_key`, without a key per finding at once.

    Findings are grouped by ``(rule, region)`` in arrival order; a group already in
    order (singletons arrive in seed order, which is their box order) is kept as is,
    so only the few out-of-order groups pay for their sort keys.
    """
    groups: dict[tuple[str, str], list[ClusterFinding]] = {}
    for finding in findings:
        groups.setdefault((finding.rule_id, finding.region_id or ""), []).append(finding)
    findings.clear()
    ordered: list[ClusterFinding] = []
    for name in sorted(groups):
        group = groups.pop(name)
        if any(_sort_key(a) > _sort_key(b) for a, b in pairwise(group)):
            group.sort(key=_sort_key)
        ordered.extend(group)
        del group
    return tuple(ordered)


def _clusters(
    runs: _Runs, labels: array[int], count: int, deadline: Deadline | None
) -> tuple[list[Cluster], _Tally]:
    tally = _tally(runs, labels, count)
    colors: dict[int, str] = {}
    clusters: list[Cluster] = []
    for index in range(count):
        if index % _CHECK_EVERY == 0:
            _checkpoint(deadline, "cluster_tally")
        first = tally.first[index]
        key, y0, x0 = runs.keys[first], runs.y[first], runs.x0[first]
        color = colors.get(key)
        if color is None:
            color = colors[key] = _hex(key)
        x1, y1 = tally.x1[index], tally.y1[index]
        box = Box(_INTS[tally.x0[index]], _INTS[y0], _INTS[x1], _INTS[y1])
        area = tally.area[index]
        if area <= MAX_DIMENSION:
            area = _INTS[area]
        clusters.append(Cluster(index, color, box, area, Point(_INTS[x0], _INTS[y0])))
    return clusters, tally


def _findings(
    clusters: list[Cluster],
    runs: _Runs,
    stairs: dict[int, array[int]],
    suppressor: _Suppressor,
    deadline: Deadline | None,
) -> tuple[list[ClusterFinding], list[ClusterFinding]]:
    """Findings of every cluster, split into active and suppressed, in cluster order."""
    warnings: list[ClusterFinding] = []
    suppressed: list[ClusterFinding] = []
    texts = _Texts()
    for cluster in clusters:
        if cluster.index % _CHECK_EVERY == 0:
            _checkpoint(deadline, "cluster_findings")
        found: list[tuple[ClusterFinding, tuple[Box, ...]]] = []
        if cluster.area == 1:
            found.append((_singleton(cluster), (cluster.box,)))
        indices = stairs.pop(cluster.index, None)
        if indices is not None:  # one stair's runs exist at a time
            members = [runs.run(index) for index in indices]
            found.extend(_step_findings(cluster, members, texts))
        for finding, boxes in found:
            region = suppressor.region(finding, boxes)
            if region is None:
                warnings.append(finding)
            else:
                suppressed.append(_with_region(finding, region))
    return warnings, suppressed


def analyze_clusters(
    rgba: bytes,
    dimensions: Dimensions,
    *,
    connectivity: Connectivity = 4,
    exceptions: Sequence[ClusterException] = (),
    regions: Mapping[str, Mask] | None = None,
    deadline: Deadline | None = None,
) -> ClusterReport:
    """Clusters and warnings of a row-major RGBA image of ``dimensions``.

    ``rgba`` holds ``4 x width x height`` bytes (``RenderResult.rgba``). The settings
    are checked first (:func:`check_cluster_settings`); each exception's
    ``region_id`` must have a mask in ``regions`` (``ReferenceError``,
    ``unknown_region``), read once. Raises ``ValidationError`` (``rgba``:
    ``size_mismatch``) and ``BudgetExceeded`` (``cluster_runs``; ``time`` when
    ``deadline`` expires, checked per row and every 4096 clusters). It holds at most
    :func:`cluster_bytes` besides its input and the cover of the region masks.
    """
    if not isinstance(dimensions, Dimensions):
        raise TypeError("dimensions must be a Dimensions value")
    if type(rgba) is not bytes:
        raise TypeError("rgba must be bytes")
    if len(rgba) != 4 * dimensions.area:
        raise _invalid("rgba", "rgba must hold 4 bytes per canvas pixel", "size_mismatch")
    if deadline is not None and not isinstance(deadline, Deadline):
        raise TypeError("deadline must be a Deadline or None")
    checked, rules = check_cluster_settings(connectivity, exceptions)
    suppressor = _Suppressor(rules, _cover(rules, regions, dimensions, deadline))
    runs, starts = _scan(rgba, dimensions, deadline)
    labels, count = _labels(runs, starts, checked, deadline)
    clusters, tally = _clusters(runs, labels, count, deadline)
    stairs = _stair_members(runs, labels, tally)
    del labels, tally
    warnings, suppressed = _findings(clusters, runs, stairs, suppressor, deadline)
    del runs
    return ClusterReport(
        dimensions.width,
        dimensions.height,
        checked,
        tuple(clusters),
        _ordered(warnings),
        _ordered(suppressed),
    )


def _with_region(finding: ClusterFinding, region_id: str) -> ClusterFinding:
    return ClusterFinding(
        finding.rule_id,
        finding.severity,
        finding.box,
        finding.cluster,
        finding.color,
        finding.message,
        finding.evidence,
        region_id,
    )
