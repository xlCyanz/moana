"""Evaluation configuration of a quality report (MOANA.md section 19, ADR-036).

The configuration is a frozen value owned by the caller, never part of the document:
which rules run, their thresholds, the regions evaluated on their own (with optional
per-region thresholds), the regions that must contain every opaque pixel and the
suppressions of artistic warnings. Every collection is canonicalised on
construction (sorted, duplicates rejected), so two configurations that list the same
items in another order are equal, have the same :attr:`QualityConfig.digest` and
produce byte-identical reports.

Hard rules (``severity`` ``error``) are mathematical conformance and can never be
suppressed. Soft rules (``severity`` ``warning``) are heuristics with thresholds;
they never reject anything. Thresholds are integers: ratios are *per mille*
(``floor(1000 · part / whole)``), so no float decides a finding.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Final, Literal, get_args

from moana.core.coordinates import require_int
from moana.core.errors import ValidationError
from moana.core.ids import check_id
from moana.core.limits import MAX_CLUSTER_EXCEPTIONS, MAX_COLORS_RGBA
from moana.techniques import CONNECTIVITIES, Connectivity

__all__ = [
    "DEFAULT_MAX_CHANGED_PERMILLE",
    "DEFAULT_MAX_COLORS",
    "DEFAULT_MAX_LISTED_SINGLETONS",
    "DEFAULT_MAX_SINGLETON_PERMILLE",
    "DEFAULT_MIN_NOISE_SINGLETONS",
    "DEFAULT_RULES",
    "HARD_RULES",
    "MAX_QUALITY_REGIONS",
    "QUALITY_RULES",
    "RULE_SET_VERSION",
    "RULE_SEVERITY",
    "SOFT_RULES",
    "QualityConfig",
    "QualityRule",
    "RegionSettings",
    "Severity",
    "Suppression",
]

QualityRule = Literal[
    "canvas_dimensions",
    "alpha_normalized",
    "palette_strict",
    "outside_mask",
    "singleton",
    "irregular_steps",
    "color_excess",
    "noise",
    "temporal_change",
    "temporal_flicker",
]
QUALITY_RULES: Final[tuple[QualityRule, ...]] = get_args(QualityRule)
"""Every rule of :data:`RULE_SET_VERSION`, hard rules first; the report order."""
Severity = Literal["error", "warning"]
HARD_RULES: Final[tuple[QualityRule, ...]] = QUALITY_RULES[:4]
SOFT_RULES: Final[tuple[QualityRule, ...]] = QUALITY_RULES[4:]
_ERROR: Final[Severity] = "error"
_WARNING: Final[Severity] = "warning"
RULE_SEVERITY: Final[Mapping[QualityRule, Severity]] = MappingProxyType(
    {rule: (_ERROR if rule in HARD_RULES else _WARNING) for rule in QUALITY_RULES}
)
RULE_SET_VERSION: Final = "quality-v1"
"""Identity of the rules, their definitions and their explanations (ADR-036)."""

DEFAULT_RULES: Final[tuple[QualityRule, ...]] = tuple(
    rule for rule in QUALITY_RULES if rule != "temporal_change"
)
"""Rules that run by default: every rule but ``temporal_change`` (a pose change is
usually intended; enable it explicitly)."""
DEFAULT_MAX_COLORS: Final = 32
DEFAULT_MAX_LISTED_SINGLETONS: Final = 16
DEFAULT_MAX_SINGLETON_PERMILLE: Final = 50
DEFAULT_MIN_NOISE_SINGLETONS: Final = 8
DEFAULT_MAX_CHANGED_PERMILLE: Final = 900
MAX_QUALITY_REGIONS: Final = MAX_CLUSTER_EXCEPTIONS
"""Distinct regions one configuration may name (each is read once as a mask)."""
_PERMILLE: Final = 1000
_MAX_COUNT_SETTING: Final = 1 << 30


def _invalid(field_name: str, message: str, reason: str) -> ValidationError:
    return ValidationError(message, context={"field": field_name, "reason": reason})


def _items(value: object, field_name: str) -> tuple[object, ...]:
    if isinstance(value, str | bytes) or not isinstance(value, Iterable):
        raise TypeError(f"{field_name} must be a sequence")
    return tuple(value)


def _rule(value: object, field_name: str) -> QualityRule:
    for rule in QUALITY_RULES:
        if type(value) is str and value == rule:
            return rule
    raise _invalid(field_name, "unknown quality rule", "unknown_rule")


def _optional(value: int | None, name: str, minimum: int, maximum: int) -> None:
    if value is not None:
        require_int(value, name, minimum=minimum, maximum=maximum)


@dataclass(frozen=True, slots=True)
class Suppression:
    """Silence the warnings of ``rule_id`` whose pixels lie entirely in ``region_id``.

    Only soft rules can be suppressed (``ValidationError``, ``not_suppressible``).
    A suppression never hides a finding that has a pixel outside its region.
    """

    rule_id: QualityRule
    region_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "rule_id", _rule(self.rule_id, "rule_id"))
        check_id(self.region_id, "region_id")
        if self.rule_id in HARD_RULES:
            raise _invalid("rule_id", "hard rules cannot be suppressed", "not_suppressible")

    def to_mapping(self) -> dict[str, object]:
        """``{"region_id", "rule_id"}``."""
        return {"region_id": self.region_id, "rule_id": self.rule_id}


@dataclass(frozen=True, slots=True)
class RegionSettings:
    """Evaluate ``region_id`` on its own: region metrics, ``color_excess`` and ``noise``.

    The region's analysis sees only the pixels of its mask (the rest is treated as
    transparent). ``None`` thresholds take the global value of the configuration;
    ``max_singleton_permille`` is the ``noise`` threshold over the region's opaque
    pixels.
    """

    region_id: str
    max_colors: int | None = None
    max_singleton_permille: int | None = None

    def __post_init__(self) -> None:
        check_id(self.region_id, "region_id")
        _optional(self.max_colors, "max_colors", 1, MAX_COLORS_RGBA)
        _optional(self.max_singleton_permille, "max_singleton_permille", 0, _PERMILLE)

    def to_mapping(self) -> dict[str, object]:
        """Region ID and its threshold overrides (``None`` when inherited)."""
        return {
            "max_colors": self.max_colors,
            "max_singleton_permille": self.max_singleton_permille,
            "region_id": self.region_id,
        }


def _rules(value: object) -> tuple[QualityRule, ...]:
    chosen = [_rule(item, "rules") for item in _items(value, "rules")]
    if len(dict.fromkeys(chosen)) != len(chosen):
        raise _invalid("rules", "repeated quality rule", "duplicate_reference")
    return tuple(rule for rule in QUALITY_RULES if rule in chosen)


def _containment(value: object) -> tuple[str, ...]:
    regions = [check_id(item, "containment") for item in _items(value, "containment")]
    if len(dict.fromkeys(regions)) != len(regions):
        raise _invalid("containment", "repeated region", "duplicate_reference")
    return tuple(sorted(regions))


def _region_settings(value: object) -> tuple[RegionSettings, ...]:
    settings = _items(value, "regions")
    if not all(isinstance(item, RegionSettings) for item in settings):
        raise TypeError("regions must hold RegionSettings values")
    ordered = sorted(
        (item for item in settings if isinstance(item, RegionSettings)),
        key=lambda item: item.region_id,
    )
    if len({item.region_id: None for item in ordered}) != len(ordered):
        raise _invalid("regions", "repeated region", "duplicate_reference")
    return tuple(ordered)


def _suppressions(value: object) -> tuple[Suppression, ...]:
    items = _items(value, "suppressions")
    if not all(isinstance(item, Suppression) for item in items):
        raise TypeError("suppressions must hold Suppression values")
    ordered = sorted(
        (item for item in items if isinstance(item, Suppression)),
        key=lambda item: (item.region_id, QUALITY_RULES.index(item.rule_id)),
    )
    if len(dict.fromkeys(ordered)) != len(ordered):
        raise _invalid("suppressions", "repeated suppression", "duplicate_reference")
    return tuple(ordered)


@dataclass(frozen=True, slots=True)
class QualityConfig:
    """Rules, thresholds, regions and suppressions of one evaluation (canonical value).

    * ``rules``: the rules that run (default :data:`DEFAULT_RULES`: all but
      ``temporal_change``);
    * ``connectivity``: ``4`` (default, section 8) or ``8`` for the silhouette
      ``components`` metric;
    * ``cluster_connectivity``: ``8`` (default) or ``4`` for the artistic cluster
      rules (``singleton``, ``irregular_steps``, ``noise``) and the ``clusters`` and
      ``singletons`` metrics: a diagonal pixel line is one cluster, not a run of
      singletons, and ``irregular_steps`` only exists with ``8``;
    * ``max_colors``: ``color_excess`` warns above this many distinct colours;
    * ``max_listed_singletons``: up to this many active singletons are listed one
      per pixel; above it, one ``singleton`` finding per colour;
    * ``min_noise_singletons`` and ``max_singleton_permille``: ``noise`` warns when
      an image has at least that many singletons and more than this many singletons
      per thousand opaque pixels;
    * ``max_changed_permille``: ``temporal_change`` warns when more than this many
      per thousand of the pixels opaque in either of two consecutive frames change;
    * ``containment``: regions whose union must hold every opaque pixel
      (``outside_mask``, a hard rule); empty disables the rule;
    * ``regions``: :class:`RegionSettings`, regions evaluated on their own;
    * ``suppressions``: :class:`Suppression` values for soft rules.

    At most :data:`MAX_QUALITY_REGIONS` distinct regions may be named overall
    (``too_many_regions``).
    """

    rules: tuple[QualityRule, ...] = DEFAULT_RULES
    connectivity: Connectivity = 4
    cluster_connectivity: Connectivity = 8
    max_colors: int = DEFAULT_MAX_COLORS
    max_listed_singletons: int = DEFAULT_MAX_LISTED_SINGLETONS
    min_noise_singletons: int = DEFAULT_MIN_NOISE_SINGLETONS
    max_singleton_permille: int = DEFAULT_MAX_SINGLETON_PERMILLE
    max_changed_permille: int = DEFAULT_MAX_CHANGED_PERMILLE
    containment: tuple[str, ...] = ()
    regions: tuple[RegionSettings, ...] = ()
    suppressions: tuple[Suppression, ...] = field(default=())

    def __post_init__(self) -> None:
        object.__setattr__(self, "rules", _rules(self.rules))
        for name in ("connectivity", "cluster_connectivity"):
            value = getattr(self, name)
            if type(value) is not int or value not in CONNECTIVITIES:
                raise _invalid(name, "connectivity must be 4 or 8", "unsupported")
        require_int(self.max_colors, "max_colors", minimum=1, maximum=MAX_COLORS_RGBA)
        require_int(
            self.max_listed_singletons,
            "max_listed_singletons",
            minimum=0,
            maximum=_MAX_COUNT_SETTING,
        )
        require_int(
            self.min_noise_singletons, "min_noise_singletons", minimum=1, maximum=_MAX_COUNT_SETTING
        )
        require_int(
            self.max_singleton_permille, "max_singleton_permille", minimum=0, maximum=_PERMILLE
        )
        require_int(self.max_changed_permille, "max_changed_permille", minimum=0, maximum=_PERMILLE)
        object.__setattr__(self, "containment", _containment(self.containment))
        object.__setattr__(self, "regions", _region_settings(self.regions))
        object.__setattr__(self, "suppressions", _suppressions(self.suppressions))
        if len(self.region_ids) > MAX_QUALITY_REGIONS:
            raise _invalid("regions", "too many regions in one evaluation", "too_many_regions")

    @property
    def region_ids(self) -> tuple[str, ...]:
        """Every region the configuration names, sorted and without repeats."""
        named = [
            *self.containment,
            *(item.region_id for item in self.regions),
            *(item.region_id for item in self.suppressions),
        ]
        return tuple(sorted(dict.fromkeys(named)))

    def enabled(self, rule: QualityRule) -> bool:
        """Whether ``rule`` runs."""
        return rule in self.rules

    def to_mapping(self) -> dict[str, object]:
        """Canonical JSON-compatible form (sorted keys and items)."""
        return {
            "cluster_connectivity": self.cluster_connectivity,
            "connectivity": self.connectivity,
            "containment": list(self.containment),
            "max_changed_permille": self.max_changed_permille,
            "max_colors": self.max_colors,
            "max_listed_singletons": self.max_listed_singletons,
            "max_singleton_permille": self.max_singleton_permille,
            "min_noise_singletons": self.min_noise_singletons,
            "regions": [item.to_mapping() for item in self.regions],
            "rule_set": RULE_SET_VERSION,
            "rules": list(self.rules),
            "suppressions": [item.to_mapping() for item in self.suppressions],
        }

    @property
    def digest(self) -> str:
        """``sha256:`` of the canonical JSON of :meth:`to_mapping`."""
        text = json.dumps(self.to_mapping(), sort_keys=True, separators=(",", ":"))
        return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
