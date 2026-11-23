"""Explicit registry of format versions and migration steps (MOANART.md section 16, ADR-031).

A :class:`MigrationRegistry` names one versioned member (``schema_version`` of a
document, ``project_version`` of a project envelope), its current version and the
registered :class:`Migration` steps. It is immutable and checked on construction:
every step goes from an older to a newer version no later than the current one, each
source version and step ID is registered once, and every chain reaches the current
version in at most ``MAX_MIGRATION_STEPS`` steps. The versions a registry *knows*
are the current one and the sources of its steps; nothing else is tolerated.

:data:`DOCUMENT_MIGRATIONS` is the production registry of documents. Schema 1.0 is
the only version ever defined (nothing has been published), so it registers **no**
migration: MoanArt claims no compatibility with a format that never existed. Tests
build their own registries with formats marked as test-only.

Version classes (``UnsupportedVersion``, pointer at the versioned member):

* ``migration_required``: an older version with a registered chain; readers never
  migrate implicitly, the caller migrates explicitly (:mod:`moanart.schema.migrations`
  in memory, ``moanart.project.migrate_project`` on disk);
* ``unsupported_version`` with ``relation`` ``future`` (newer than the current
  version), ``past`` (older, with no registered migration) or ``unknown`` (not a
  ``MAJOR.MINOR`` version). The untrusted version string is never echoed.

Versions of the package (``moanart.__version__``), of the renderer
(``RENDERER_VERSION``) and of the cost estimator are not format versions: they
never select a migration.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Final

from moanart.core.errors import UnsupportedVersion
from moanart.core.ids import is_id
from moanart.core.limits import MAX_MIGRATION_STEPS
from moanart.schema.capabilities import SCHEMA_VERSION

__all__ = [
    "DOCUMENT_MIGRATIONS",
    "Migration",
    "MigrationRegistry",
    "MigrationStep",
    "parse_version",
]

type MigrationStep = Callable[[dict[str, object]], Mapping[str, object]]
"""One pure step: receives a private bounded copy and returns the migrated tree."""

_VERSION: Final = re.compile(r"(0|[1-9][0-9]{0,3})\.(0|[1-9][0-9]{0,3})")


def parse_version(text: object) -> tuple[int, int] | None:
    """``(major, minor)`` of a ``MAJOR.MINOR`` version string, ``None`` otherwise."""
    if not isinstance(text, str):
        return None
    match = _VERSION.fullmatch(text)
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2))


def _version(text: str, what: str) -> tuple[int, int]:
    parsed = parse_version(text)
    if parsed is None:
        raise ValueError(f"{what} must be a MAJOR.MINOR version")
    return parsed


@dataclass(frozen=True, slots=True)
class Migration:
    """One registered step from ``source`` to ``target`` (both ``MAJOR.MINOR``).

    ``apply`` must be pure and deterministic: it receives a private copy of the tree
    (already bounded by the parse limits) and returns the migrated tree; the engine
    sets the versioned member to ``target`` afterwards.
    """

    id: str
    source: str
    target: str
    apply: MigrationStep

    def __post_init__(self) -> None:
        if not is_id(self.id):
            raise ValueError("migration id must match the ID grammar")
        if _version(self.source, "source") >= _version(self.target, "target"):
            raise ValueError("a migration must go to a newer version")
        if not callable(self.apply):
            raise TypeError("apply must be callable")


@dataclass(frozen=True, slots=True)
class MigrationRegistry:
    """Immutable set of versions and steps of one versioned member."""

    member: str
    current: str
    migrations: tuple[Migration, ...] = ()

    def __post_init__(self) -> None:
        if self.member not in ("schema_version", "project_version"):
            raise ValueError("member must be schema_version or project_version")
        current = _version(self.current, "current")
        if not isinstance(self.migrations, tuple) or not all(
            isinstance(step, Migration) for step in self.migrations
        ):
            raise TypeError("migrations must be a tuple of Migration values")
        sources = [step.source for step in self.migrations]
        identifiers = [step.id for step in self.migrations]
        if len(set(sources)) != len(sources) or len(set(identifiers)) != len(identifiers):
            raise ValueError("each source version and migration id is registered once")
        for step in self.migrations:
            if _version(step.target, "target") > current:
                raise ValueError("a migration cannot target a version after the current one")
            self.path(step.source)  # every chain reaches the current version

    @property
    def versions(self) -> frozenset[str]:
        """Every known version: the current one and the source of each step."""
        return frozenset({self.current, *(step.source for step in self.migrations)})

    def _step(self, version: str) -> Migration | None:
        return next((step for step in self.migrations if step.source == version), None)

    def path(self, version: str) -> tuple[Migration, ...]:
        """The registered steps from ``version`` to the current version, in order.

        ``()`` for the current version; ``UnsupportedVersion`` for any other version
        without a registered chain.
        """
        steps: list[Migration] = []
        while version != self.current:
            step = self._step(version)
            if step is None or len(steps) == MAX_MIGRATION_STEPS:
                if steps:
                    raise ValueError("a migration chain does not reach the current version")
                raise self._unsupported(version)
            steps.append(step)
            version = step.target
        return tuple(steps)

    def _unsupported(self, version: str) -> UnsupportedVersion:
        parsed = parse_version(version)
        if parsed is None:
            relation = "unknown"
        elif parsed > _version(self.current, "current"):
            relation = "future"
        else:
            relation = "past"
        return UnsupportedVersion(
            f"{self.member} is not supported by this reader",
            json_pointer=f"/{self.member}",
            context={
                "field": self.member,
                "reason": "unsupported_version",
                "relation": relation,
                "supported": (self.current,),
            },
        )

    def check(self, tree: Mapping[str, object]) -> None:
        """Accept the current version; reject every other string version.

        A non-string or absent member is left to the structural validation. A version
        with a registered chain is ``migration_required``: readers never migrate.
        """
        version = tree.get(self.member)
        if not isinstance(version, str) or version == self.current:
            return
        steps = self.path(version)
        raise UnsupportedVersion(
            f"{self.member} needs an explicit migration",
            json_pointer=f"/{self.member}",
            context={
                "field": self.member,
                "reason": "migration_required",
                "supported": (self.current,),
                "target": self.current,
                "migrations": tuple(step.id for step in steps),
            },
        )


DOCUMENT_MIGRATIONS: Final = MigrationRegistry(member="schema_version", current=SCHEMA_VERSION)
"""Production registry of documents: only schema 1.0 exists, so no migration."""
