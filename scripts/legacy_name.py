"""Keep the pre-rename name out of the repository and of the built artifacts (ADR-041).

The project was renamed from its 0.1.0rc1 name to MoanArt (MOANA-037). Any path or
text that still matches :data:`LEGACY_NAME` (case-insensitive, ``MoanArt`` itself
excluded) is an error unless it is an issue ID or the remote repository, or it falls
under one of the audited :data:`EXCEPTIONS`. ``python -m scripts.legacy_name`` checks
the files Git knows (tracked and untracked, ignored ones excluded) and
:mod:`scripts.check_wheel` applies the same rules to every member of the wheel and
the sdist.
"""

from __future__ import annotations

import fnmatch
import json
import re
import subprocess
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

LEGACY_NAME = re.compile(r"moana(?!rt)", re.IGNORECASE)
"""The old name in any case, never the start of ``moanart``/``MoanArt``."""

ALWAYS_ALLOWED = re.compile(
    # Issue IDs: MOANA-037 (MOANA_037 in test names), the placeholders MOANA-xxx and
    # MOANA-…, the pattern MOANA-\d{3} and the bare prefix "MOANA-" of a path literal.
    r"MOANA[-_]\d{3}(?!\d)|MOANA-(?:xxx|XXX)\b|MOANA-…|MOANA-\\d\{3\}|MOANA-(?=\")"
    r"|(?:github\.com/)?xlCyanz/moana(?![\w-])"  # the remote repository is not renamed
)
"""Occurrences that are not the product name: issue IDs and the remote repository."""

LEGACY_IDENTIFIERS = (
    r"(?:project\.moana\.json|moana-project|moana-spritesheet|moana-rubric/1"
    r"|\.moana\.json|\.moana)(?![\w/.-])"
)
"""The 0.1.0rc1 identifiers that the migrations read and their tests build."""


@dataclass(frozen=True, slots=True)
class Exception_:
    """Files (``fnmatch`` patterns) where ``allowed`` occurrences are expected, and why."""

    patterns: tuple[str, ...]
    reason: str
    allowed: str | None = None  # a regex of the allowed occurrences; None allows any
    metadata_only: bool = False  # JSON documents: only their ``metadata`` is exempt


EXCEPTIONS: tuple[Exception_, ...] = (
    Exception_(
        ("tests/fixtures/rename/rc1/*",),
        "artefactos reales escritos por 0.1.0rc1 (oráculo de las migraciones): "
        "ruta y bytes congelados",
    ),
    Exception_(
        ("docs/FILE_INVENTORY.md",),
        "el inventario enumera las rutas de esos artefactos de 0.1.0rc1",
        r"tests/fixtures/rename/rc1/[^)\s|]*",
    ),
    Exception_(
        ("CHANGELOG.md",),
        "historial de versiones publicadas y nota de ruptura de 0.1.0rc2",
    ),
    Exception_(
        (
            "docs/architecture/ADR-00[2-4]-*.md",
            "docs/architecture/decisions/ADR-0[0-3][0-9]-*.md",
            "docs/architecture/decisions/ADR-040-*.md",
        ),
        "ADR aceptados antes del renombrado: no se reescriben (ADR-041 los amplía)",
    ),
    Exception_(
        ("docs/architecture/decisions/ADR-041-*.md",),
        "el ADR del renombrado: tabla nombre antiguo -> nuevo",
    ),
    Exception_(
        ("docs/issues/MOANA-037.md",),
        "el issue del renombrado (generado de su entrada del catálogo)",
    ),
    Exception_(
        ("examples/*.moanart.json", "examples/**/*.moanart.json", "tests/fixtures/**/*.json"),
        "metadatos de documentos con snapshot_digest fijado: cambiarlos cambiaría el digest",
        r"unknown to moana",  # the description of the test-only formats of MOANA-021
        metadata_only=True,
    ),
    Exception_(
        ("examples/tiles/meadow.layout.json",),
        "procedencia que la escena derivada copia en sus metadatos (digest fijado)",
        r"operaciones de Moana",
    ),
    Exception_(
        (
            "src/moanart/project/manifest.py",
            "src/moanart/project/migrate.py",
            "src/moanart/export/spritesheet.py",
            "src/moanart/quality/rubric.py",
            "tests/unit/project/test_project_rename.py",
            "tests/unit/export/test_export_spritesheet.py",
            "tests/unit/quality/test_quality_rubric.py",
        ),
        "tablas de migración: los identificadores de 0.1.0rc1 que sólo leen las migraciones",
        LEGACY_IDENTIFIERS,
    ),
    Exception_(
        ("scripts/github_sync.py",),
        "etiqueta remota de GitHub del backlog, que no se renombra (recurso remoto)",
        r'"moana"|backlog de Moana',
    ),
    Exception_(
        ("scripts/legacy_name.py", "tests/test_legacy_name.py"),
        "este comprobador y sus pruebas",
    ),
)

CATALOG = "docs/issues/catalog.json"
RENAME_ISSUE = "MOANA-037"


def _exception(path: str) -> Exception_ | None:
    for exception in EXCEPTIONS:
        if any(fnmatch.fnmatchcase(path, pattern) for pattern in exception.patterns):
            return exception
    return None


def _stray(text: str, allowed: str | None) -> list[str]:
    """Occurrences of the old name in ``text`` that no rule allows, with their line."""
    masked = ALWAYS_ALLOWED.sub(lambda match: "_" * len(match.group(0)), text)
    if allowed is not None:
        masked = re.sub(allowed, lambda match: "_" * len(match.group(0)), masked)
    lines = text.split("\n")  # the same line breaks as the count below
    found = []
    for match in LEGACY_NAME.finditer(masked):
        line = text.count("\n", 0, match.start()) + 1
        found.append(f"{line}: {lines[line - 1].strip()[:120]}")
    return found


def _catalog_text(data: bytes) -> str:
    """The catalog without the entry of the rename issue, which names the old name."""
    catalog = json.loads(data)
    catalog["issues"] = [item for item in catalog["issues"] if item["id"] != RENAME_ISSUE]
    return json.dumps(catalog, indent=2, ensure_ascii=False)


def _without_metadata(text: str) -> str:
    """A document without its ``metadata`` object (title, author, provenance).

    Re-serialised with two-space indentation: reported lines refer to that text.
    """
    try:
        tree = json.loads(text)
    except ValueError:
        return text
    if isinstance(tree, dict):
        tree.pop("metadata", None)
    return json.dumps(tree, indent=2, ensure_ascii=False)


def legacy_name_errors(files: Mapping[str, bytes]) -> list[str]:
    """One error per path or text occurrence of the old name outside the exceptions.

    ``files`` maps POSIX paths relative to the repository root to their bytes. Files
    that are not UTF-8 (PNG images, the rc1 ZIP fixture) are checked by path only:
    their compressed or binary contents are not searched. The lines of the catalog
    and of exempt documents refer to their re-serialised JSON (``indent=2``).
    """
    errors: list[str] = []
    for path, data in sorted(files.items()):
        exception = _exception(path)
        if exception is not None and exception.allowed is None:
            continue  # whole file exempt, path included
        if _stray(path, exception.allowed if exception else None):
            errors.append(f"{path}: the path uses the old name")
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if path == CATALOG:
            text = _catalog_text(data)
        elif exception is not None and exception.metadata_only:
            text = _without_metadata(text)
        for occurrence in _stray(text, exception.allowed if exception else None):
            errors.append(f"{path}:{occurrence}")
    return errors


def repository_files(root: Path = ROOT) -> dict[str, bytes]:
    """Tracked and untracked (not ignored) files of the checkout, by relative path."""
    listed = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        check=True,
        capture_output=True,
    ).stdout.decode("utf-8")
    paths: Iterable[str] = sorted({path for path in listed.split("\0") if path})
    return {path: (root / path).read_bytes() for path in paths if (root / path).is_file()}


def main() -> int:
    errors = legacy_name_errors(repository_files())
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        print(f"{len(errors)} occurrences of the old name (ADR-041)", file=sys.stderr)
        return 1
    print("Legacy name OK: only audited exceptions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
