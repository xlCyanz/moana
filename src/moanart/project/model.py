"""In-memory project: a document, its assets, an optional history (ADR-029) and the
records of the explicit migrations that produced it, with their originals (ADR-031)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from moanart.core.errors import BudgetExceeded, ValidationError
from moanart.core.limits import MAX_ASSET_PIXELS, MAX_PROJECT_ASSETS, MAX_PROJECT_MIGRATIONS
from moanart.editing import History
from moanart.project.assets import Asset
from moanart.project.manifest import MigrationRecord
from moanart.schema import Document, document_ids, snapshot_digest

__all__ = ["MigrationBackup", "Project", "check_asset_ids"]


def _invalid(message: str, reason: str, **extra: int) -> ValidationError:
    return ValidationError(message, context={"field": "assets", "reason": reason, **extra})


def check_asset_ids(document: Document, asset_ids: tuple[str, ...]) -> None:
    """Asset IDs are unique and never collide with an ID of the document.

    The document's namespace is ``moanart.schema.document_ids``: it includes the IDs
    of items such as the bands of a ``shade`` operation (ADR-028).
    """
    declared = document_ids(document)
    seen: set[str] = set()
    for index, asset_id in enumerate(asset_ids):
        if asset_id in seen:
            raise _invalid("an asset ID is declared twice", "duplicate_asset_id", index=index)
        if asset_id in declared:
            raise _invalid(
                "an asset ID is already used by the document", "id_collision", index=index
            )
        seen.add(asset_id)


def _budget(resource: str, limit: int, estimated: int) -> BudgetExceeded:
    return BudgetExceeded(
        "the project exceeds its contract budget",
        context={"resource": resource, "limit": limit, "estimated": estimated},
    )


@dataclass(frozen=True, slots=True)
class MigrationBackup:
    """A migration record and the exact bytes of the original it preserves.

    ``data`` must match ``record.byte_length`` and ``record.sha256``
    (``checksum_mismatch``); it is stored at ``record.path``
    (``migrations/<sha256>.json``) and never parsed again: it is an opaque copy.
    """

    record: MigrationRecord
    data: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.record, MigrationRecord):
            raise TypeError("record must be a MigrationRecord")
        if not isinstance(self.data, bytes):
            raise TypeError("data must be bytes")
        if (
            len(self.data) != self.record.byte_length
            or hashlib.sha256(self.data).hexdigest() != self.record.sha256
        ):
            raise ValidationError(
                "a migration original does not match its checksum",
                context={"field": "migrations", "reason": "checksum_mismatch"},
            )

    @property
    def path(self) -> str:
        """Immutable path of the preserved original inside the project."""
        return self.record.path


@dataclass(frozen=True, slots=True)
class Project:
    """A validated document, its PNG assets (in declared order) and an optional history.

    When ``history`` is given, its cursor must be ``document`` (same snapshot digest):
    the saved manifest embeds the cursor's document and the history is rebuilt around
    it. Asset IDs are unique and distinct from every document ID; more than
    ``MAX_PROJECT_ASSETS`` assets or ``MAX_ASSET_PIXELS`` decoded pixels in total is
    ``BudgetExceeded`` (``project_assets``, ``asset_pixels``), as when loading.
    ``migrations`` lists, oldest first, the explicit migrations that produced the
    project with their preserved originals (ADR-031); more than
    ``MAX_PROJECT_MIGRATIONS`` is ``BudgetExceeded`` (``project_migrations``) and the
    same original twice is ``duplicate_migration``.
    """

    document: Document
    assets: tuple[Asset, ...] = ()
    history: History | None = None
    migrations: tuple[MigrationBackup, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.document, Document):
            raise TypeError("document must be a moanart.schema.Document")
        if not isinstance(self.assets, tuple) or not all(
            isinstance(asset, Asset) for asset in self.assets
        ):
            raise TypeError("assets must be a tuple of Asset values")
        if self.history is not None and not isinstance(self.history, History):
            raise TypeError("history must be a History or None")
        if not isinstance(self.migrations, tuple) or not all(
            isinstance(backup, MigrationBackup) for backup in self.migrations
        ):
            raise TypeError("migrations must be a tuple of MigrationBackup values")
        if len(self.migrations) > MAX_PROJECT_MIGRATIONS:
            raise _budget("project_migrations", MAX_PROJECT_MIGRATIONS, len(self.migrations))
        hashes = [backup.record.sha256 for backup in self.migrations]
        if len(set(hashes)) != len(hashes):
            raise ValidationError(
                "a migration original is preserved twice",
                context={"field": "migrations", "reason": "duplicate_migration"},
            )
        if len(self.assets) > MAX_PROJECT_ASSETS:
            raise _budget("project_assets", MAX_PROJECT_ASSETS, len(self.assets))
        pixels = sum(asset.pixels for asset in self.assets)
        if pixels > MAX_ASSET_PIXELS:
            raise _budget("asset_pixels", MAX_ASSET_PIXELS, pixels)
        check_asset_ids(self.document, tuple(asset.id for asset in self.assets))
        if self.history is not None and self.history.cursor != snapshot_digest(self.document):
            raise ValidationError(
                "the history cursor is not the project document",
                context={"field": "history", "reason": "cursor_mismatch"},
            )
