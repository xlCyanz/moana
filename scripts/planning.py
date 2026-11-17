"""Validate the issue DAG and generate reviewable Markdown from the catalogs."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parents[1]
Text = Annotated[str, Field(min_length=1, pattern=r"\S")]
IssueId = Annotated[str, Field(pattern=r"^MOANA-\d{3}$")]
LegacyId = Annotated[str, Field(pattern=r"^MOA-\d{3}$")]
RequirementId = Annotated[str, Field(pattern=r"^R\d{3}$")]
Status = Literal["todo", "ready", "in_progress", "blocked", "review", "done"]


class StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class Issue(StrictModel):
    id: IssueId
    aliases: list[LegacyId]
    title: Text
    phase: Literal["P0", "P1", "P2", "P3", "P4", "P5"]
    status: Status
    priority: Literal["P0", "P1", "P2", "P3"]
    complexity: Literal["S", "M", "L", "XL"]
    modules: Annotated[list[Text], Field(min_length=1)]
    dependencies: list[IssueId]
    requirements: Annotated[list[RequirementId], Field(min_length=1)]
    context: Text
    objective: Text
    scope: Text
    out_of_scope: Text
    technical: Annotated[list[Text], Field(min_length=2)]
    proposed_implementation: Annotated[list[Text], Field(min_length=2)]
    acceptance: Annotated[list[Text], Field(min_length=2)]
    tests: Annotated[list[Text], Field(min_length=2)]
    deliverables: Annotated[list[Text], Field(min_length=2)]
    risks: Annotated[list[Text], Field(min_length=1)]
    blocking_reason: Text | None
    acceptance_evidence: dict[str, Text]
    test_evidence: dict[str, Text]
    evidence: list[Text]


class Requirement(StrictModel):
    id: RequirementId
    description: Text
    sections: Annotated[list[Annotated[int, Field(ge=1, le=25)]], Field(min_length=1)]
    verification: Text


class Catalog(StrictModel):
    schema_version: Literal[2]
    issues: Annotated[list[Issue], Field(min_length=1)]


class Requirements(StrictModel):
    schema_version: Literal[1]
    requirements: Annotated[list[Requirement], Field(min_length=1)]


def validate_graph(issues: list[Issue], requirements: list[Requirement]) -> list[str]:
    """Return a deterministic dependency-first order or reject inconsistent planning."""
    for label, identifiers in (
        ("issue", [item.id for item in issues]),
        ("requirement", [item.id for item in requirements]),
        ("alias", [alias for item in issues for alias in item.aliases]),
    ):
        duplicates = sorted(key for key, count in Counter(identifiers).items() if count > 1)
        if duplicates:
            raise ValueError(f"Duplicate {label} IDs: {duplicates}")
    by_id = {issue.id: issue for issue in issues}
    required = {requirement.id for requirement in requirements}
    covered: set[str] = set()
    for issue in issues:
        if len(issue.dependencies) != len(set(issue.dependencies)):
            raise ValueError(f"Duplicate dependencies: {issue.id}")
        if len(issue.requirements) != len(set(issue.requirements)):
            raise ValueError(f"Duplicate requirements: {issue.id}")
        unknown_deps = set(issue.dependencies) - by_id.keys()
        unknown_reqs = set(issue.requirements) - required
        if unknown_deps or unknown_reqs:
            raise ValueError(f"Unknown references in {issue.id}: {unknown_deps | unknown_reqs}")
        covered.update(issue.requirements)
    if uncovered := required - covered:
        raise ValueError(f"Uncovered requirements: {sorted(uncovered)}")
    ordered: list[str] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(identifier: str) -> None:
        if identifier in visiting:
            raise ValueError(f"Dependency cycle involving {identifier}")
        if identifier in visited:
            return
        visiting.add(identifier)
        for dependency in sorted(by_id[identifier].dependencies):
            visit(dependency)
        visiting.remove(identifier)
        visited.add(identifier)
        ordered.append(identifier)

    for identifier in sorted(by_id):
        visit(identifier)
    for issue in issues:
        for dependency in issue.dependencies:
            if by_id[dependency].phase > issue.phase:
                raise ValueError(f"Phase inversion: {issue.id} depends on {dependency}")
        if issue.status == "blocked" and not issue.blocking_reason:
            raise ValueError(f"Blocked issue without reason: {issue.id}")
        if issue.status != "blocked" and issue.blocking_reason:
            raise ValueError(f"Non-blocked issue with blocking reason: {issue.id}")
        if issue.status == "done" and not issue.evidence:
            raise ValueError(f"Done issue without evidence: {issue.id}")
        if issue.status in {"ready", "in_progress", "review", "done"} and any(
            by_id[dep].status != "done" for dep in issue.dependencies
        ):
            raise ValueError(f"{issue.status} issue with unfinished dependencies: {issue.id}")
        for prefix, criteria, evidence in (
            ("AC", issue.acceptance, issue.acceptance_evidence),
            ("T", issue.tests, issue.test_evidence),
        ):
            expected = {f"{prefix}{index + 1}" for index in range(len(criteria))}
            if set(evidence) - expected:
                raise ValueError(f"Unknown {prefix} evidence key: {issue.id}")
            if issue.status == "done" and set(evidence) != expected:
                raise ValueError(f"Incomplete {prefix} evidence for done issue: {issue.id}")
    return ordered


def load_catalog(root: Path = ROOT) -> tuple[list[Issue], list[Requirement]]:
    issues = Catalog.model_validate_json(
        (root / "docs/issues/catalog.json").read_text(encoding="utf-8")
    ).issues
    requirements = Requirements.model_validate_json(
        (root / "docs/requirements.json").read_text(encoding="utf-8")
    ).requirements
    validate_graph(issues, requirements)
    return issues, requirements


def bullets(items: list[str], *, checkbox: bool = False, checked: bool = False) -> str:
    prefix = "- "
    if checkbox:
        prefix = "- [x] " if checked else "- [ ] "
    return "\n".join(prefix + item for item in items)


def dependency_waves(issues: list[Issue], order: list[str]) -> list[list[str]]:
    """Compute theoretical dependency levels, independently of current status."""
    by_id = {issue.id: issue for issue in issues}
    levels: dict[str, int] = {}
    for identifier in order:
        levels[identifier] = 1 + max(
            (levels[dep] for dep in by_id[identifier].dependencies), default=-1
        )
    return [
        sorted(identifier for identifier in order if levels[identifier] == level)
        for level in range(max(levels.values(), default=-1) + 1)
    ]


def critical_path(issues: list[Issue], order: list[str]) -> list[str]:
    """Longest dependency chain by issue count, with lexical tie-breaking; not a schedule."""
    by_id = {issue.id: issue for issue in issues}
    paths: dict[str, list[str]] = {}
    for identifier in order:
        parents = [paths[dep] for dep in by_id[identifier].dependencies]
        best = min(parents, key=lambda path: (-len(path), path)) if parents else []
        paths[identifier] = [*best, identifier]
    return min(paths.values(), key=lambda path: (-len(path), path)) if paths else []


def issue_document(issue: Issue, note: str) -> str:
    dependencies = ", ".join(f"[{dep}]({dep}.md)" for dep in issue.dependencies) or "Ninguna"
    text = f"# {issue.id} — {issue.title}\n\n{note}## Metadata\n\n"
    text += (
        bullets(
            [
                f"ID: {issue.id}",
                f"Aliases históricos: {', '.join(issue.aliases) or 'Ninguno'}",
                f"Phase: {issue.phase}",
                f"Priority: {issue.priority}",
                f"Status: {issue.status}",
                f"Complexity: {issue.complexity} (relativa, no estimación de tiempo)",
                f"Dependencies: {dependencies}",
                f"Related modules: {', '.join(issue.modules)}",
                f"Requirements: {', '.join(issue.requirements)} ([trazabilidad](traceability.md))",
                f"Bloqueo: {issue.blocking_reason or 'Ninguno'}",
            ]
        )
        + "\n\n"
    )
    for title, body in (
        ("Context", issue.context),
        ("Objective", issue.objective),
        ("Scope", issue.scope),
        ("Out of scope", issue.out_of_scope),
        ("Technical requirements", bullets(issue.technical)),
        ("Proposed implementation", bullets(issue.proposed_implementation)),
        (
            "Acceptance criteria",
            bullets(
                [f"AC{index + 1}: {criterion}" for index, criterion in enumerate(issue.acceptance)],
                checkbox=True,
                checked=issue.status == "done",
            ),
        ),
        (
            "Required tests",
            bullets(
                [f"T{index + 1}: {test}" for index, test in enumerate(issue.tests)],
                checkbox=True,
                checked=issue.status == "done",
            ),
        ),
        ("Expected deliverables", bullets(issue.deliverables)),
        (
            "Definition of Done",
            "Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC "
            "y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. "
            "Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.",
        ),
        ("Risks and notes", bullets(issue.risks)),
        (
            "Evidence",
            bullets(
                [
                    *issue.evidence,
                    *(f"{key}: {value}" for key, value in issue.acceptance_evidence.items()),
                    *(f"{key}: {value}" for key, value in issue.test_evidence.items()),
                ]
            )
            or "Pendiente de implementación.",
        ),
    ):
        text += f"## {title}\n\n{body}\n\n"
    return text.rstrip() + "\n"


def generated_documents(issues: list[Issue], requirements: list[Requirement]) -> dict[str, str]:
    order = validate_graph(issues, requirements)
    result: dict[str, str] = {}
    note = "> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.\n\n"
    for issue in issues:
        result[f"docs/issues/{issue.id}.md"] = issue_document(issue, note)
        for alias in issue.aliases:
            result[f"docs/issues/{alias}.md"] = (
                f"# {alias} — Alias histórico\n\n{note}"
                f"Este identificador corresponde a [{issue.id} — {issue.title}]({issue.id}.md). "
                "No es un issue adicional. El catálogo conserva la identidad y el historial; "
                "usar el identificador canónico en trabajo nuevo.\n"
            )
    phases = Counter(issue.phase for issue in issues)
    priorities: Counter[str] = Counter(issue.priority for issue in issues)
    states = Counter(issue.status for issue in issues)
    result["docs/issues/README.md"] = (
        f"# Backlog de Moana\n\n{note}{len(issues)} issues únicos; "
        "los aliases MOA-xxx conservan enlaces previos y no incrementan el total. "
        "Los IDs no son números de issues GitHub.\n\n"
        "Prioridades: P0 fundamento/bloqueante; P1 funcionalidad central; P2 avanzada; "
        "P3 mejora opcional. No se inventan mejoras opcionales sólo para llenar P3.\n\n"
        "[Roadmap](roadmap.md) · [Dependencias](dependency-map.md) · "
        "[Trazabilidad](traceability.md) · [Ciclo de vida](../guides/issue-lifecycle.md).\n\n"
        f"Estados: {dict(sorted(states.items()))}.\n\n"
        "| Issue | Resultado | Fase | Prioridad | Estado | Dependencias directas |\n"
        "| --- | --- | --- | --- | --- | --- |\n"
        + "\n".join(
            f"| [{i.id}]({i.id}.md) | {i.title} | {i.phase} | {i.priority} | {i.status} | "
            f"{', '.join(i.dependencies) or '—'} |"
            for i in issues
        )
        + "\n"
    )
    edges = [f'  {i.id.replace("-", "_")}["{i.id}"]' for i in issues]
    edges += [
        f"  {dep.replace('-', '_')} --> {i.id.replace('-', '_')}"
        for i in issues
        for dep in i.dependencies
    ]
    dependents = {
        issue.id: sorted(i.id for i in issues if issue.id in i.dependencies) for issue in issues
    }
    dependency_map = (
        f"# Dependencias entre issues\n\n{note}"
        "A → B significa que B requiere A completado. El checker rechaza ciclos, "
        "referencias desconocidas, inversiones de fase y estados activos "
        "con dependencias pendientes.\n\n"
        "```mermaid\nflowchart TD\n" + "\n".join(edges) + "\n```\n\n"
        "## Bloqueantes y dependientes\n\n"
        "| Issue | Bloqueado por | Desbloquea directamente |\n| --- | --- | --- |\n"
        + "\n".join(
            f"| [{i.id}]({i.id}.md) | {', '.join(i.dependencies) or '—'} | "
            f"{', '.join(dependents[i.id]) or '—'} |"
            for i in issues
        )
        + "\n\n## Ruta crítica estructural\n\n"
        + " → ".join(critical_path(issues, order))
        + "\n\n"
        "Es la cadena más larga por número de issues, con desempate lexicográfico. "
        "Sin duraciones estimadas no representa una ruta crítica de calendario.\n\n"
        "## Oleadas potencialmente paralelizables\n\n"
        "Son niveles del DAG, no permisos de ejecución ni estados ready. En una oleada, "
        "cada dependencia debe estar done y deben asignarse archivos distintos "
        "antes de delegar.\n\n"
    )
    for index, wave in enumerate(dependency_waves(issues, order)):
        dependency_map += f"- Nivel {index}: {', '.join(wave)}\n"
    dependency_map += "\n## Orden recomendado válido\n\n" + " → ".join(order) + "\n"
    result["docs/issues/dependency-map.md"] = dependency_map
    trace_rows = []
    for requirement in requirements:
        owners = [i for i in issues if requirement.id in i.requirements]
        links = ", ".join(f"[{i.id}]({i.id}.md)" for i in owners)
        sections = ", ".join(str(section) for section in requirement.sections)
        trace_rows.append(
            f"| {requirement.id} | {requirement.description} | {sections} | {links} | "
            f"{requirement.verification} |"
        )
    result["docs/issues/traceability.md"] = (
        f"# Matriz de trazabilidad\n\n{note}"
        f"{len(requirements)} requisitos con cobertura de planificación. "
        "Esto no implica implementación: comprobar estado y evidencia por criterio "
        "en cada issue.\n\n"
        "| Requisito | Descripción | MOANA.md § | Issues | Verificación exigida |\n"
        "| --- | --- | --- | --- | --- |\n" + "\n".join(trace_rows) + "\n"
    )
    gates = {
        "P0": ("Inicialización", "Gate de infraestructura, skills y backlog válido; sin motor."),
        "P1": ("Contratos y core", "Modelos estrictos, límites y fixtures enteras exactas."),
        "P2": ("Imagen estática", "Render 128 x 128, PNG roundtrip y determinismo en matriz."),
        "P3": ("Arte y edición", "Técnicas editables y batches atómicos con historial."),
        "P4": ("Persistencia y animación", "Proyecto reversible, atlas y timeline decodificado."),
        "P5": ("Evaluación y release", "Corpus revisado, seguridad, benchmarks y wheel limpio."),
    }
    roadmap = (
        f"# Roadmap\n\n{note}Se conservan las seis fases de MOANA.md para respetar "
        "las dependencias del contrato existente. Las ocho áreas temáticas de la solicitud "
        "se distribuyen entre estas fases; no se crean carpetas vacías ni se pospone schema "
        "hasta después del renderer.\n\n"
        f"Total: {len(issues)} issues; fases: {dict(sorted(phases.items()))}.\n\n"
        "Prioridades: "
        + ", ".join(f"{p}={priorities[p]}" for p in ("P0", "P1", "P2", "P3"))
        + ". Complejidad S/M/L/XL es relativa, sin promesas de calendario.\n\n"
    )
    for phase, (name, gate) in gates.items():
        selected = [issue for issue in issues if issue.phase == phase]
        completed = sum(issue.status == "done" for issue in selected)
        roadmap += f"## {phase} — {name}\n\nPuerta de salida: {gate}\n\n"
        roadmap += f"Estado: {completed}/{len(selected)} issues completados.\n\n"
        roadmap += (
            bullets([f"[{i.id}]({i.id}.md) — {i.title} ({i.status})" for i in selected]) + "\n\n"
        )
    ready = sorted((i for i in issues if i.status == "ready"), key=lambda i: (i.priority, i.id))
    roadmap += "## Siguiente paso\n\n"
    roadmap += (
        f"Implementar [{ready[0].id}]({ready[0].id}.md): {ready[0].title}.\n"
        if ready
        else "No hay issues ready. Revisar bloqueos y dependencias antes de iniciar.\n"
    )
    result["docs/issues/roadmap.md"] = roadmap
    for old, target in (
        ("ROADMAP.md", "roadmap.md"),
        ("DEPENDENCIES.md", "dependency-map.md"),
        ("TRACEABILITY.md", "traceability.md"),
    ):
        result[f"docs/{old}"] = (
            f"# Enlace de compatibilidad\n\n{note}"
            f"El documento vigente está en [docs/issues/{target}](issues/{target}). "
            "Se conserva esta ruta para enlaces anteriores.\n"
        )
    return result


def check_generated(root: Path, documents: dict[str, str]) -> list[str]:
    errors: list[str] = []
    expected_issues = {
        path for path in documents if path.startswith(("docs/issues/MOA-", "docs/issues/MOANA-"))
    }
    existing = {path.relative_to(root).as_posix() for path in (root / "docs/issues").glob("MO*.md")}
    errors.extend(f"Orphan issue file: {path}" for path in sorted(existing - expected_issues))
    for path, content in documents.items():
        target = root / path
        if not target.is_file() or target.read_text(encoding="utf-8") != content:
            errors.append(f"Stale or missing generated file: {path}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    issues, requirements = load_catalog()
    documents = generated_documents(issues, requirements)
    if args.check:
        errors = check_generated(ROOT, documents)
        for error in errors:
            print(error)
        return int(bool(errors))
    for path, content in documents.items():
        target = ROOT / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    print(f"Generated {len(documents)} documents for {len(issues)} issues")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
