"""Test-only document formats 0.8 and 0.9 and their migration registry (MOANA-021).

These versions were **never published**: schema 1.0 is the only Moana format that has
ever existed, and the production registry ``moana.schema.DOCUMENT_MIGRATIONS``
registers no migration. The formats exist only to exercise the migration engine
(ADR-031); every fixture carries a ``test_only_format`` member that the last step
requires and removes, so a real document can never be mistaken for one.

* 0.8 -> 0.9: ``canvas.size: [w, h]`` becomes ``canvas.width`` and ``canvas.height``.
* 0.9 -> 1.0: palette colours ``value`` become ``rgba``, layer ``ops`` become
  ``operations`` and the ``test_only_format`` marker is removed.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from moana.schema import SCHEMA_VERSION, Migration, MigrationRegistry

FIXTURES: Final = Path(__file__).resolve().parent
OLDEST: Final = FIXTURES / "test-only-0.8.moana.json"
PREVIOUS: Final = FIXTURES / "test-only-0.9.moana.json"
EXPECTED: Final = FIXTURES / "expected-1.0.moana.json"
MARKER: Final = "test_only_format"


def canvas_size_to_members(tree: dict[str, Any]) -> Mapping[str, object]:
    """0.8 -> 0.9: split ``canvas.size``."""
    canvas = tree["canvas"]
    width, height = canvas.pop("size")
    canvas["width"], canvas["height"] = width, height
    return tree


def rename_members(tree: dict[str, Any]) -> Mapping[str, object]:
    """0.9 -> 1.0: ``value`` -> ``rgba``, ``ops`` -> ``operations``; drop the marker."""
    del tree[MARKER]  # KeyError: not a test-only document
    for color in tree["palette"]["colors"]:
        color["rgba"] = color.pop("value")
    for layer in tree["layers"]:
        layer["operations"] = layer.pop("ops")
    return tree


STEP_08_09: Final = Migration(
    id="test-only-0-8-to-0-9", source="0.8", target="0.9", apply=canvas_size_to_members
)
STEP_09_10: Final = Migration(
    id="test-only-0-9-to-1-0", source="0.9", target=SCHEMA_VERSION, apply=rename_members
)
TEST_ONLY_MIGRATIONS: Final = MigrationRegistry(
    member="schema_version", current=SCHEMA_VERSION, migrations=(STEP_08_09, STEP_09_10)
)
"""Registry used only by tests; it knows 0.8, 0.9 and 1.0."""
