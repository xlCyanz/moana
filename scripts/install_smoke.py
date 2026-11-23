"""Migration and corpus smoke run against an *installed* MoanArt (MOANA-035 T1).

``scripts/check_wheel.py`` runs this file with the interpreter of a clean virtual
environment in isolated mode (``python -I``), once for the wheel and once for the
sdist, so it imports only the standard library and the installed ``moanart``:

``migrations WORK DOCUMENT``
    Copies the current ``DOCUMENT`` into ``WORK`` as a smoke-only legacy 0.9 file
    (an extra ``smoke_only_format`` member that the single step removes; never a
    published format) and migrates it with :func:`moanart.schema.migrate_document` and
    :func:`moanart.project.migrate_project` into a new project. The legacy source must
    keep its exact bytes, the migrated project must render exactly like the current
    document and keep the original in its migration record; the production registry
    must treat the current document as already migrated and write nothing.
``corpus FOLDER``
    Renders every example of a copy of ``examples/corpus`` and compares the pinned
    render and frame digests of its record; the hard checks must pass.

Exit code 0 on success; any failed expectation raises ``AssertionError`` explicitly
(never a bare ``assert``, so ``python -O`` cannot skip a check).
"""

from __future__ import annotations

import copy
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from moanart.api import evaluate_quality, load_document, render
from moanart.project import load_project, migrate_project
from moanart.schema import (
    SCHEMA_VERSION,
    Migration,
    MigrationRegistry,
    migrate_document,
    snapshot_digest,
)

LEGACY_VERSION: Final = "0.9"
MARKER: Final = "smoke_only_format"
STEP_ID: Final = "smoke-only-0-9-to-1-0"


def drop_marker(tree: dict[str, Any]) -> Mapping[str, object]:
    """0.9 -> 1.0 of the smoke-only format: remove the marker (KeyError otherwise)."""
    del tree[MARKER]
    return tree


def require(condition: bool, message: str) -> None:
    """Raise ``AssertionError(message)`` unless ``condition`` holds."""
    if not condition:
        raise AssertionError(message)


SMOKE_MIGRATIONS: Final = MigrationRegistry(
    member="schema_version",
    current=SCHEMA_VERSION,
    migrations=(
        Migration(id=STEP_ID, source=LEGACY_VERSION, target=SCHEMA_VERSION, apply=drop_marker),
    ),
)
"""Registry used only by this smoke; the production registry knows 1.0 only."""


def legacy_tree(current: Mapping[str, Any]) -> dict[str, Any]:
    tree = copy.deepcopy(dict(current))
    tree["schema_version"] = LEGACY_VERSION
    tree[MARKER] = True
    return tree


def check_migrations(work: Path, document: Path) -> str:
    """Migrate a legacy copy of ``document`` in memory and on disk; return a summary."""
    current = json.loads(document.read_text(encoding="utf-8"))
    expected = load_document(document)
    expected_digest = render(expected).digest

    legacy = legacy_tree(current)
    untouched = copy.deepcopy(legacy)
    migrated = migrate_document(legacy, registry=SMOKE_MIGRATIONS)
    require(legacy == untouched, "migrate_document modified its source")
    require(
        (migrated.source_version, migrated.target_version) == (LEGACY_VERSION, "1.0"),
        "unexpected migrated versions",
    )
    require(migrated.steps == (STEP_ID,), "unexpected migration steps")
    require(
        snapshot_digest(migrated.document) == snapshot_digest(expected),
        "migrated document differs from the current one",
    )
    require(migrate_document(current).steps == (), "a current document was migrated")

    source = work / "legacy" / "legacy sprite.moanart.json"
    source.parent.mkdir(parents=True)
    source.write_text(json.dumps(legacy, indent=2), encoding="utf-8")
    original = source.read_bytes()
    destination = work / "migrated project"
    report = migrate_project(source, destination, registry=SMOKE_MIGRATIONS)
    require(
        report.steps == (STEP_ID,) and report.save is not None,
        "migrate_project did not apply the step",
    )
    require(source.read_bytes() == original, "migrate_project modified its source")
    project = load_project(destination)
    require(
        render(project.document).digest == expected_digest, "migrated project renders differently"
    )
    (backup,) = project.migrations
    require(
        backup.data == original and backup.record.source_version == LEGACY_VERSION,
        "original not preserved in the migration record",
    )

    unchanged = work / "current project"
    production = migrate_project(document, unchanged)
    require(
        production.steps == () and production.save is None,
        "production registry migrated a current document",
    )
    require(not unchanged.exists(), "a current document must not be migrated")
    return f"{LEGACY_VERSION} -> {SCHEMA_VERSION} via {STEP_ID}; original preserved"


def check_corpus(folder: Path) -> int:
    """Render every example of a corpus copy against its record; return the count."""
    examples = sorted(path for path in folder.iterdir() if path.is_dir())
    require(bool(examples), f"no corpus examples under {folder}")
    for example in examples:
        record = json.loads((example / f"{example.name}.corpus.json").read_text(encoding="utf-8"))
        document = load_document(example / f"{example.name}.moanart.json")
        pinned = record["render"]
        require(render(document).digest == pinned["digest"], example.name)
        animation_id = record.get("animation_id")
        report = evaluate_quality(
            document, animation_id=animation_id if isinstance(animation_id, str) else None
        )
        require(report.passed_hard_checks, example.name)
        if pinned["frame_digests"] is not None:
            frames = {item.frame_id: item.digest for item in report.frame_metrics}
            require(frames == pinned["frame_digests"], example.name)
    return len(examples)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments[:1] == ["migrations"] and len(arguments) == 3:
        print("Installed migrations OK:", check_migrations(Path(arguments[1]), Path(arguments[2])))
        return 0
    if arguments[:1] == ["corpus"] and len(arguments) == 2:
        count = check_corpus(Path(arguments[1]))
        print(f"Installed corpus OK: {count} examples match their pinned digests")
        return 0
    print("usage: install_smoke.py migrations WORK DOCUMENT | corpus FOLDER", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
