"""Bounds of reading and writing one project (MOANA.md sections 16 and 20, ADR-029)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

from moana.core.coordinates import require_int
from moana.core.limits import (
    MAX_ARCHIVE_BYTES,
    MAX_ARCHIVE_ENTRIES,
    MAX_ARCHIVE_EXPANDED_BYTES,
    MAX_ARCHIVE_RATIO,
    MAX_ASSET_BYTES,
    MAX_ASSET_PIXELS,
    MAX_PROJECT_ASSETS,
    MAX_PROJECT_MANIFEST_BYTES,
    MAX_PROJECT_MANIFEST_DEPTH,
    MAX_PROJECT_MANIFEST_NODES,
)
from moana.editing import DEFAULT_HISTORY_LIMITS, HistoryLimits
from moana.schema import DEFAULT_PARSE_LIMITS, ParseLimits

__all__ = ["DEFAULT_PROJECT_LIMITS", "ProjectLimits"]


@dataclass(frozen=True, slots=True)
class ProjectLimits:
    """Bounds of one load or save; a host may lower them, never raise them.

    ``parse`` bounds the embedded document, every snapshot and every batch;
    ``history`` the rebuilt history. Asset bounds apply to the declared assets of the
    manifest; archive bounds to a ``.moana`` ZIP, checked from its central directory
    before any entry is decompressed.
    """

    max_manifest_bytes: int = MAX_PROJECT_MANIFEST_BYTES
    max_manifest_depth: int = MAX_PROJECT_MANIFEST_DEPTH
    max_manifest_nodes: int = MAX_PROJECT_MANIFEST_NODES
    max_assets: int = MAX_PROJECT_ASSETS
    max_asset_bytes: int = MAX_ASSET_BYTES
    max_asset_pixels: int = MAX_ASSET_PIXELS
    max_archive_entries: int = MAX_ARCHIVE_ENTRIES
    max_archive_bytes: int = MAX_ARCHIVE_BYTES
    max_archive_expanded_bytes: int = MAX_ARCHIVE_EXPANDED_BYTES
    max_archive_ratio: int = MAX_ARCHIVE_RATIO
    parse: ParseLimits = field(default=DEFAULT_PARSE_LIMITS)
    history: HistoryLimits = field(default=DEFAULT_HISTORY_LIMITS)

    def __post_init__(self) -> None:
        bounds = (
            ("max_manifest_bytes", 2, MAX_PROJECT_MANIFEST_BYTES),
            ("max_manifest_depth", 1, MAX_PROJECT_MANIFEST_DEPTH),
            ("max_manifest_nodes", 1, MAX_PROJECT_MANIFEST_NODES),
            ("max_assets", 0, MAX_PROJECT_ASSETS),
            ("max_asset_bytes", 1, MAX_ASSET_BYTES),
            ("max_asset_pixels", 1, MAX_ASSET_PIXELS),
            ("max_archive_entries", 1, MAX_ARCHIVE_ENTRIES),
            ("max_archive_bytes", 1, MAX_ARCHIVE_BYTES),
            ("max_archive_expanded_bytes", 1, MAX_ARCHIVE_EXPANDED_BYTES),
            ("max_archive_ratio", 1, MAX_ARCHIVE_RATIO),
        )
        for name, minimum, maximum in bounds:
            require_int(getattr(self, name), name, minimum=minimum, maximum=maximum)
        if not isinstance(self.parse, ParseLimits):
            raise TypeError("parse must be a ParseLimits value")
        if not isinstance(self.history, HistoryLimits):
            raise TypeError("history must be a HistoryLimits value")


DEFAULT_PROJECT_LIMITS: Final = ProjectLimits()
