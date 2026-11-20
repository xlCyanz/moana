"""Release candidate tables generated from the code and the catalogs (MOANA-035).

``docs/RELEASE.md`` is written by hand except for the block between
:data:`BEGIN` and :data:`END`, which this script renders from what is real now:

* versions read from the code (package, schema, project, renderer, estimator, quality
  rules, vector backend) and the production migration registries;
* the compatibility matrix from ``pyproject.toml`` and the CI matrix of
  ``.github/workflows/ci.yml``;
* the capability matrix from :func:`moana.api.capabilities` (implemented and planned
  stay apart; codec *availability* is a runtime fact of each install, so only the
  formats and their optional status are listed);
* the requirement audit from ``docs/requirements.json`` and the issue statuses of
  ``docs/issues/catalog.json``. A requirement counts as delivered only when every
  issue that covers it is ``done``; covering it in planning is not delivering it.

Subcommands: ``report`` prints the block, ``write`` replaces it in ``docs/RELEASE.md``
and ``check`` fails (exit code 1) when the document is stale.
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final

import yaml

ROOT: Final = Path(__file__).resolve().parents[1]
RELEASE_DOC: Final = ROOT / "docs" / "RELEASE.md"
BEGIN: Final = "<!-- release:begin (generado por scripts/release.py write; no editar) -->"
END: Final = "<!-- release:end -->"

OPTIONAL_CODECS: Final = frozenset({"apng", "webp"})
"""Export formats whose availability depends on the Pillow build (MOANA-025)."""

_CI_NOTE: Final = (
    "matriz de CI remota verde (9 trabajos + determinismo) en `3857617`, run 44777404728; "
    "falta observarla sobre el commit candidato"
)
PENDING_NOTES: Final[dict[str, str]] = {
    "R005": "revisión artística humana del corpus pendiente (ningún ejemplo es profesional)",
    "R015": _CI_NOTE,
    "R035": _CI_NOTE,
    "R037": "revisión artística humana de tiles y escena pendiente",
}
"""Known gaps that the issue status alone does not show; they are listed, never hidden."""


def _cell(value: object) -> str:
    return str(value).replace("|", "\\|")


def _table(header: Sequence[str], rows: Sequence[Sequence[object]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join("---" for _ in header) + " |"]
    lines.extend("| " + " | ".join(_cell(item) for item in row) + " |" for row in rows)
    return lines


def _code(values: Sequence[str]) -> str:
    return ", ".join(f"`{value}`" for value in values) if values else "—"


def version_rows() -> list[tuple[str, str, str]]:
    """Name, value and source of every version a release candidate declares."""
    import moana
    from moana.geometry.paths import TESTED_AGGDRAW_VERSIONS
    from moana.project import PROJECT_MIGRATIONS
    from moana.project.manifest import PROJECT_VERSION
    from moana.quality.config import RULE_SET_VERSION
    from moana.render.budget import ESTIMATOR_VERSION
    from moana.render.result import RENDERER_VERSION
    from moana.schema import DOCUMENT_MIGRATIONS
    from moana.schema.capabilities import SCHEMA_VERSION

    def registry(versions: frozenset[str], steps: int) -> str:
        return f"{_code(sorted(versions))}; {steps} migraciones registradas"

    return [
        ("Paquete", f"`{moana.__version__}`", "`moana.__version__`"),
        ("Schema de documento", f"`{SCHEMA_VERSION}`", "`moana.schema.capabilities`"),
        ("Formato de proyecto", f"`{PROJECT_VERSION}`", "`moana.project.manifest`"),
        ("Renderer", f"`{RENDERER_VERSION}`", "`moana.render.result`"),
        ("Estimador de presupuesto", f"`{ESTIMATOR_VERSION}`", "`moana.render.budget`"),
        ("Reglas de calidad", f"`{RULE_SET_VERSION}`", "`moana.quality.config`"),
        (
            "Backend vectorial",
            f"`aggdraw-v1` (AggDraw ensayado: {_code(TESTED_AGGDRAW_VERSIONS)})",
            "`moana.geometry.paths`",
        ),
        (
            "Migraciones de documento",
            registry(DOCUMENT_MIGRATIONS.versions, len(DOCUMENT_MIGRATIONS.migrations)),
            "`moana.schema.DOCUMENT_MIGRATIONS`",
        ),
        (
            "Migraciones de proyecto",
            registry(PROJECT_MIGRATIONS.versions, len(PROJECT_MIGRATIONS.migrations)),
            "`moana.project.PROJECT_MIGRATIONS`",
        ),
    ]


def ci_matrix(root: Path = ROOT) -> dict[str, list[str]]:
    """``python`` and ``os`` lists of the ``verify`` job matrix of the CI workflow.

    Any other shape is a ``ValueError`` naming what is missing, so a workflow change
    that moves the matrix fails with a message instead of a ``KeyError``.
    """
    workflow = yaml.load(
        (root / ".github/workflows/ci.yml").read_text(encoding="utf-8"), Loader=yaml.BaseLoader
    )
    node: Any = workflow
    for key in ("jobs", "verify", "strategy", "matrix"):
        if not isinstance(node, dict) or key not in node:
            raise ValueError(f".github/workflows/ci.yml: no jobs.verify.strategy.matrix ({key!r})")
        node = node[key]
    matrix: dict[str, list[str]] = {}
    for key in ("python", "os"):
        values = node.get(key)
        if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
            raise ValueError(f".github/workflows/ci.yml: matrix {key!r} must be a list of strings")
        matrix[key] = values
    return matrix


def compatibility_rows(root: Path = ROOT) -> list[tuple[str, str, str]]:
    """Declared Python, systems and runtime dependency ranges, with their source."""
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    prefix = "Programming Language :: Python :: 3."
    pythons = [
        item.removeprefix("Programming Language :: Python :: ")
        for item in project["classifiers"]
        if item.startswith(prefix)
    ]
    matrix = ci_matrix(root)
    rows = [
        (
            "Python",
            f"`{project['requires-python']}`; clasificadores {_code(pythons)}",
            "`pyproject.toml`",
        ),
        ("Matriz CI: Python", _code(matrix["python"]), "`.github/workflows/ci.yml`"),
        ("Matriz CI: sistemas", _code(matrix["os"]), "`.github/workflows/ci.yml`"),
    ]
    rows.extend(
        ("Dependencia de ejecución", f"`{requirement}`", "`pyproject.toml`")
        for requirement in project["dependencies"]
    )
    rows.append(
        (
            "Licencia",
            f"`{project['license']}` ({_code(project['license-files'])})",
            "`pyproject.toml`",
        )
    )
    return rows


def capability_rows() -> list[tuple[str, str, str]]:
    """Implemented and planned surface of the installed engine, side by side."""
    from moana.api import capabilities

    found = capabilities()
    codecs = [
        f"`{codec.format}`" + (" (opcional)" if codec.format in OPTIONAL_CODECS else "")
        for codec in found.export_codecs
    ]
    backends = [f"`{backend.name}`" for backend in found.backends]
    return [
        ("Versiones de schema", _code(found.schema_versions), "—"),
        ("Perfiles de color", _code(found.profiles), "—"),
        ("Operaciones", _code(found.operations), _code(found.planned_operations)),
        ("Máscaras", _code(found.mask_types), _code(found.planned_mask_types)),
        ("Colecciones", _code(found.collections), _code(found.planned_collections)),
        ("Modos de fusión", _code(found.blend_modes), _code(found.planned_blend_modes)),
        ("Campos de capa", "—", _code(found.planned_layer_fields)),
        ("Funciones de `moana.api`", _code(found.functions), _code(found.planned_functions)),
        ("Comandos de edición", _code(found.edit_commands), "—"),
        ("Exportación desde el CLI", _code(found.export_formats), "—"),
        ("Exportación desde Python", ", ".join(codecs), "—"),
        ("Backends vectoriales", ", ".join(backends), "—"),
    ]


def requirement_rows(root: Path = ROOT) -> list[tuple[str, str, str, str, str]]:
    """Requirement, description, covering issues, delivery status and explicit gaps."""
    requirements = json.loads((root / "docs/requirements.json").read_text(encoding="utf-8"))
    issues: list[dict[str, Any]] = json.loads(
        (root / "docs/issues/catalog.json").read_text(encoding="utf-8")
    )["issues"]
    rows: list[tuple[str, str, str, str, str]] = []
    for requirement in requirements["requirements"]:
        identifier = requirement["id"]
        covering = [issue for issue in issues if identifier in issue["requirements"]]
        done = sum(issue["status"] == "done" for issue in covering)
        if covering and done == len(covering):
            status = "implementado"
        elif done:
            status = "parcial"
        else:
            status = "pendiente"
        if identifier in PENDING_NOTES and status == "implementado":
            status = "implementado con pendientes"
        listed = ", ".join(f"{issue['id']} ({issue['status']})" for issue in covering)
        rows.append(
            (
                identifier,
                requirement["description"],
                listed or "—",
                status,
                PENDING_NOTES.get(identifier, "—"),
            )
        )
    return rows


def report(root: Path = ROOT) -> str:
    """The generated block, markers included, ending with a newline."""
    requirements = requirement_rows(root)
    counts = {
        status: sum(row[3] == status for row in requirements)
        for status in ("implementado", "implementado con pendientes", "parcial", "pendiente")
    }
    summary = "; ".join(f"{status}: {count}" for status, count in counts.items())
    lines = [BEGIN, "", "### Versiones", ""]
    lines += _table(("Elemento", "Versión", "Fuente"), version_rows())
    lines += ["", "### Compatibilidad declarada", ""]
    lines += _table(("Elemento", "Valor", "Fuente"), compatibility_rows(root))
    lines += ["", "### Capacidades (`moana.api.capabilities()`)", ""]
    lines += _table(("Superficie", "Implementado", "Previsto (no ejecutable)"), capability_rows())
    lines += ["", f"### Auditoría de requisitos ({len(requirements)}; {summary})", ""]
    lines += _table(("ID", "Requisito", "Issues (estado)", "Entrega", "Pendiente"), requirements)
    lines += ["", END]
    return "\n".join(lines) + "\n"


def _split(text: str) -> tuple[str, str, str]:
    start, end = text.find(BEGIN), text.find(END)
    if start < 0 or end < start or text.count(BEGIN) != 1 or text.count(END) != 1:
        raise ValueError(f"{RELEASE_DOC.name} must contain one generated block")
    return text[:start], text[start : end + len(END) + 1], text[end + len(END) + 1 :]


def check(document: Path = RELEASE_DOC, root: Path = ROOT) -> list[str]:
    """Errors when the generated block of ``document`` differs from :func:`report`."""
    try:
        _, block, _ = _split(document.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return [str(error)]
    if block != report(root):
        return [f"{document.name} is stale: run `uv run python scripts/release.py write`"]
    return []


def write(document: Path = RELEASE_DOC, root: Path = ROOT) -> None:
    before, _, after = _split(document.read_text(encoding="utf-8"))
    document.write_text(before + report(root) + after, encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("report", "write", "check"))
    arguments = parser.parse_args(argv)
    if arguments.command == "report":
        sys.stdout.write(report())
        return 0
    if arguments.command == "write":
        write()
        print(f"wrote {RELEASE_DOC.relative_to(ROOT).as_posix()}")
        return 0
    errors = check()
    for error in errors:
        print(error, file=sys.stderr)
    if not errors:
        print("Release tables OK")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
