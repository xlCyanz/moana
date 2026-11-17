"""Validate the issue DAG and generate reviewable Markdown from the catalogs."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parents[1]
Text = Annotated[str, Field(min_length=1)]
IssueId = Annotated[str, Field(pattern=r"^MOA-\d{3}$")]
RequirementId = Annotated[str, Field(pattern=r"^R\d{3}$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class Issue(StrictModel):
    id: IssueId
    title: Text
    phase: Literal["P0", "P1", "P2", "P3", "P4", "P5"]
    status: Literal["planned", "in_progress", "done"]
    priority: Literal["P0", "P1", "P2"]
    dependencies: list[IssueId]
    requirements: Annotated[list[RequirementId], Field(min_length=1)]
    scope: Text
    out_of_scope: Text
    technical: Annotated[list[Text], Field(min_length=2)]
    acceptance: Annotated[list[Text], Field(min_length=2)]
    tests: Annotated[list[Text], Field(min_length=2)]
    evidence: list[Text]


class Requirement(StrictModel):
    id: RequirementId
    description: Text
    sections: Annotated[list[Annotated[int, Field(ge=1, le=25)]], Field(min_length=1)]
    verification: Text


class Catalog(StrictModel):
    schema_version: Literal[1]
    issues: Annotated[list[Issue], Field(min_length=1)]


class Requirements(StrictModel):
    schema_version: Literal[1]
    requirements: Annotated[list[Requirement], Field(min_length=1)]


def validate_graph(issues: list[Issue], requirements: list[Requirement]) -> list[str]:
    """Return a deterministic dependency-first order or reject inconsistent planning."""
    for label, identifiers in (
        ("issue", [item.id for item in issues]),
        ("requirement", [item.id for item in requirements]),
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
        if issue.status == "done":
            if not issue.evidence:
                raise ValueError(f"Done issue without evidence: {issue.id}")
            if any(by_id[dep].status != "done" for dep in issue.dependencies):
                raise ValueError(f"Done issue with unfinished dependencies: {issue.id}")
    return ordered


def load_catalog(root: Path = ROOT) -> tuple[list[Issue], list[Requirement]]:
    issues = Catalog.model_validate_json((root / "docs/issues/catalog.json").read_text()).issues
    requirements = Requirements.model_validate_json(
        (root / "docs/requirements.json").read_text()
    ).requirements
    validate_graph(issues, requirements)
    return issues, requirements


def bullets(items: list[str], *, checkbox: bool = False, checked: bool = False) -> str:
    prefix = "- "
    if checkbox:
        prefix = "- [x] " if checked else "- [ ] "
    return "\n".join(prefix + item for item in items)


def generated_documents(issues: list[Issue], requirements: list[Requirement]) -> dict[str, str]:
    order = validate_graph(issues, requirements)
    result: dict[str, str] = {}
    note = "> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.\n\n"
    for issue in issues:
        deps = ", ".join(f"[{dep}]({dep}.md)" for dep in issue.dependencies) or "Ninguna"
        result[f"docs/issues/{issue.id}.md"] = (
            f"# {issue.id} — {issue.title}\n\n{note}"
            f"Fase: **{issue.phase}** · Estado: **{issue.status}** · "
            f"Prioridad: **{issue.priority}**\n\n"
            f"Dependencias: {deps}.\n\nRequisitos: {', '.join(issue.requirements)} "
            "([matriz](../TRACEABILITY.md)). Contrato: [MOANA.md](../../MOANA.md).\n\n"
            f"## Alcance\n\n{issue.scope}\n\n## Fuera de alcance\n\n{issue.out_of_scope}\n\n"
            f"## Requisitos técnicos\n\n{bullets(issue.technical)}\n\n"
            "## Criterios de aceptación\n\n"
            f"{bullets(issue.acceptance, checkbox=True, checked=issue.status == 'done')}\n\n"
            f"## Pruebas necesarias\n\n{bullets(issue.tests)}\n\n"
            "## Cierre\n\nCumplir la Definition of Done de MOANA.md §25, adjuntar evidencia "
            "y actualizar el catálogo. No cerrar sólo por disponer de código.\n\n"
            "## Evidencia registrada\n\n"
            f"{bullets(issue.evidence) or 'Pendiente de implementación.'}\n"
        )
    rows = [
        f"| [{i.id}]({i.id}.md) | {i.title} | {i.phase} | {i.status} | "
        f"{', '.join(i.dependencies) or '—'} |"
        for i in issues
    ]
    result["docs/issues/README.md"] = (
        f"# Backlog de Moana\n\n{note}{len(issues)} issues locales; "
        "sus IDs no implican publicación en GitHub. Prioridad P0 = contrato/crítico, "
        "P1 = entrega principal, P2 = extensión.\n\n"
        "| Issue | Resultado | Fase | Estado | Dependencias directas |\n"
        "| --- | --- | --- | --- | --- |\n" + "\n".join(rows) + "\n"
    )
    edges = [f'  {i.id.replace("-", "_")}["{i.id}"]' for i in issues]
    edges += [
        f"  {dep.replace('-', '_')} --> {i.id.replace('-', '_')}"
        for i in issues
        for dep in i.dependencies
    ]
    result["docs/DEPENDENCIES.md"] = (
        f"# Dependencias entre issues\n\n{note}"
        "Una flecha A → B significa que B requiere A completado. "
        "El checker rechaza ciclos, referencias desconocidas e inversiones de fase.\n\n"
        "```mermaid\nflowchart TD\n" + "\n".join(edges) + "\n```\n\n"
        "## Orden topológico válido\n\n" + " → ".join(order) + "\n\n"
        "El orden no obliga a ejecutar secuencialmente issues independientes. "
        "El siguiente issue listo se obtiene de dependencias completadas, no del número menor.\n"
    )
    trace_rows = []
    for requirement in requirements:
        owners = [i for i in issues if requirement.id in i.requirements]
        links = ", ".join(f"[{i.id}](issues/{i.id}.md)" for i in owners)
        sections = ", ".join(str(section) for section in requirement.sections)
        trace_rows.append(
            f"| {requirement.id} | {requirement.description} | {sections} | {links} | "
            f"{requirement.verification} |"
        )
    result["docs/TRACEABILITY.md"] = (
        f"# Matriz de trazabilidad\n\n{note}"
        f"{len(requirements)} requisitos con cobertura de planificación. "
        "Cobertura no significa implementación; consultar estado y evidencia de cada issue.\n\n"
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
    roadmap = f"# Roadmap\n\n{note}Sin fechas estimadas; gates basados en evidencia.\n\n"
    for phase, (name, gate) in gates.items():
        selected = [issue for issue in issues if issue.phase == phase]
        completed = sum(issue.status == "done" for issue in selected)
        roadmap += f"## {phase} — {name}\n\nPuerta de salida: {gate}\n\n"
        roadmap += f"Estado: {completed}/{len(selected)} issues completados.\n\n"
        roadmap += bullets([f"[{i.id}](issues/{i.id}.md) — {i.title}" for i in selected]) + "\n\n"
    roadmap += (
        "## Siguiente paso\n\nImplementar MOA-001; continuar con MOA-002 y los fundamentos "
        "según el [DAG](DEPENDENCIES.md). La asignación de fases no sustituye las dependencias.\n"
    )
    result["docs/ROADMAP.md"] = roadmap
    return result


def check_generated(root: Path, documents: dict[str, str]) -> list[str]:
    errors: list[str] = []
    expected_issues = {path for path in documents if path.startswith("docs/issues/MOA-")}
    existing = {
        path.relative_to(root).as_posix() for path in (root / "docs/issues").glob("MOA-*.md")
    }
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
