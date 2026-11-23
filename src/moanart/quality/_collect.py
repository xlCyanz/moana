"""Bounded collection and fair capping of quality findings (ADR-036 §6 and §8).

Findings are kept per list (active or suppressed) and per rule. Each rule keeps at
most :data:`MAX_QUALITY_FINDINGS` findings in memory: when its buffer grows past
that plus :data:`_SLACK`, it is sorted by :func:`finding_sort_key` and cut back, so
memory is bounded by :data:`MAX_HELD_FINDINGS` findings whatever the image, while
every finding is still counted. The report lists at most
:data:`MAX_QUALITY_FINDINGS` per list: first, for every rule, its first
:data:`MIN_LISTED_PER_RULE` findings in report order (so no rule starves another),
then the first remaining findings in report order until the cap.
"""

from __future__ import annotations

from typing import Final

from moanart.quality.config import QUALITY_RULES, QualityRule
from moanart.quality.report import OmittedByRule, QualityFinding, finding_sort_key

__all__ = [
    "HELD_PER_LIST",
    "MAX_HELD_FINDINGS",
    "MAX_QUALITY_FINDINGS",
    "MIN_LISTED_PER_RULE",
    "FindingList",
]

MAX_QUALITY_FINDINGS: Final = 4096
"""Findings listed per list of a report (active, suppressed)."""
MIN_LISTED_PER_RULE: Final = 64
"""Findings each rule keeps in a capped list before the rest of the cap is shared."""
_SLACK: Final = 1024
HELD_PER_LIST: Final = MAX_QUALITY_FINDINGS + _SLACK
"""Findings one rule holds at most in one list before cutting back to the cap."""
MAX_HELD_FINDINGS: Final = 2 * len(QUALITY_RULES) * HELD_PER_LIST
"""Upper bound of findings held at once by one evaluation (both lists, every rule)."""


class _Bucket:
    __slots__ = ("items", "total")

    def __init__(self) -> None:
        self.items: list[QualityFinding] = []
        self.total = 0

    def add(self, finding: QualityFinding) -> None:
        self.items.append(finding)
        self.total += 1
        if len(self.items) > HELD_PER_LIST:
            self.items = self.first()

    def first(self) -> list[QualityFinding]:
        """The first :data:`MAX_QUALITY_FINDINGS` findings in report order."""
        return sorted(self.items, key=finding_sort_key)[:MAX_QUALITY_FINDINGS]


class FindingList:
    """Findings of one list, counted per rule and held with bounded memory."""

    def __init__(self) -> None:
        self._buckets: dict[QualityRule, _Bucket] = {rule: _Bucket() for rule in QUALITY_RULES}

    def add(self, finding: QualityFinding) -> None:
        """Count ``finding`` and keep it while it may still be listed."""
        self._buckets[finding.rule_id].add(finding)

    def count_omitted(self, rule: QualityRule, count: int) -> None:
        """Count ``count`` findings of ``rule`` that were never built (already capped)."""
        self._buckets[rule].total += count

    def total(self, rules: tuple[QualityRule, ...] = QUALITY_RULES) -> int:
        """Findings counted for ``rules``, listed or not."""
        return sum(self._buckets[rule].total for rule in rules)

    def capped(self) -> tuple[tuple[QualityFinding, ...], OmittedByRule]:
        """Listed findings in report order and the omitted count of each rule."""
        kept = {rule: bucket.first() for rule, bucket in self._buckets.items()}
        guaranteed = [item for items in kept.values() for item in items[:MIN_LISTED_PER_RULE]]
        rest = sorted(
            (item for items in kept.values() for item in items[MIN_LISTED_PER_RULE:]),
            key=finding_sort_key,
        )
        listed = sorted(
            guaranteed + rest[: MAX_QUALITY_FINDINGS - len(guaranteed)], key=finding_sort_key
        )
        shown = dict.fromkeys(QUALITY_RULES, 0)
        for item in listed:
            shown[item.rule_id] += 1
        omitted = tuple(
            (rule, bucket.total - shown[rule])
            for rule, bucket in self._buckets.items()
            if bucket.total > shown[rule]
        )
        return tuple(listed), omitted
