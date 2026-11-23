"""Render the per-issue execution guide that lets an AI agent work an issue unaided.

The guide is derived only from the catalogs, MOANART.md headings and fixed module
conventions, so it stays reproducible and is regenerated with the rest of the backlog.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from string import Template
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from scripts.planning import Issue, Requirement

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE: Final = Template(
    (Path(__file__).parent / "templates/agent_guide.md").read_text(encoding="utf-8")
)


@dataclass(frozen=True)
class ModuleGuide:
    """Where a module lives and which skills/agents/standards support it."""

    paths: tuple[str, ...]
    tests: tuple[str, ...]
    skills: tuple[str, ...]
    agents: tuple[str, ...]
    standards: tuple[str, ...]


PY: Final = "docs/standards/python.md"
ARCH: Final = "docs/standards/architecture.md"
TEST: Final = "docs/standards/testing.md"
ART: Final = "docs/standards/pixel-art.md"
SEC: Final = "docs/standards/security.md"


def _source(module: str, *skills: str, agents: tuple[str, ...], extra: str = "") -> ModuleGuide:
    standards = tuple(dict.fromkeys((PY, ARCH, TEST, *([extra] if extra else []))))
    return ModuleGuide(
        paths=(f"src/moanart/{module}/",),
        tests=(f"tests/unit/{module}/",),
        skills=skills,
        agents=agents,
        standards=standards,
    )


MODULES: Final[Mapping[str, ModuleGuide]] = {
    "core": _source(
        "core", "moanart-python", "moanart-graphics", agents=("python-engineer", "architect")
    ),
    "schema": _source(
        "schema",
        "moanart-python",
        "moanart-architecture",
        agents=("python-engineer", "architect"),
        extra=SEC,
    ),
    "palette": _source(
        "palette",
        "moanart-python",
        "moanart-pixel-art",
        agents=("python-engineer", "pixel-artist"),
        extra=ART,
    ),
    "geometry": _source(
        "geometry", "moanart-graphics", agents=("graphics-engineer", "python-engineer")
    ),
    "layers": _source("layers", "moanart-graphics", agents=("graphics-engineer", "architect")),
    "techniques": _source(
        "techniques",
        "moanart-graphics",
        "moanart-pixel-art",
        agents=("graphics-engineer", "pixel-artist"),
        extra=ART,
    ),
    "render": _source(
        "render",
        "moanart-graphics",
        "moanart-architecture",
        agents=("graphics-engineer", "architect"),
    ),
    "editing": _source(
        "editing", "moanart-python", "moanart-architecture", agents=("python-engineer", "architect")
    ),
    "project": _source(
        "project", "moanart-python", agents=("python-engineer", "architect"), extra=SEC
    ),
    "animation": _source(
        "animation",
        "moanart-graphics",
        "moanart-pixel-art",
        agents=("graphics-engineer", "pixel-artist"),
        extra=ART,
    ),
    "export": _source(
        "export",
        "moanart-graphics",
        "moanart-python",
        agents=("graphics-engineer", "python-engineer"),
    ),
    "quality": _source(
        "quality",
        "moanart-pixel-art",
        "moanart-testing",
        agents=("pixel-artist", "qa-engineer"),
        extra=ART,
    ),
    "api": _source(
        "api", "moanart-python", "moanart-architecture", agents=("python-engineer", "architect")
    ),
    "cli": _source("cli", "moanart-python", agents=("python-engineer", "architect"), extra=SEC),
    "tests.visual": ModuleGuide(
        ("tests/visual/",), ("tests/visual/",), ("moanart-testing",), ("qa-engineer",), (TEST, ART)
    ),
    "tests.integration": ModuleGuide(
        ("tests/integration/",),
        ("tests/integration/",),
        ("moanart-testing",),
        ("qa-engineer",),
        (TEST,),
    ),
    "tests.security": ModuleGuide(
        ("tests/security/",),
        ("tests/security/",),
        ("moanart-testing",),
        ("qa-engineer",),
        (TEST, SEC),
    ),
    "benchmarks": ModuleGuide(
        ("tests/benchmarks/",),
        ("tests/benchmarks/",),
        ("moanart-testing",),
        ("qa-engineer", "python-engineer"),
        (TEST,),
    ),
    "docs": ModuleGuide(
        ("docs/",),
        ("tests/test_repository_tools.py",),
        ("moanart-issue-planning",),
        ("documentation",),
        (ARCH,),
    ),
    "agents": ModuleGuide(
        ("docs/guides/", ".agents/skills/", ".claude/"),
        ("tests/test_repository_tools.py",),
        ("moanart-issue-planning",),
        ("documentation",),
        (ARCH,),
    ),
    "examples": ModuleGuide(
        ("examples/",),
        ("tests/integration/",),
        ("moanart-pixel-art",),
        ("pixel-artist", "documentation"),
        (ART,),
    ),
    "tooling": ModuleGuide(
        ("scripts/",),
        ("tests/",),
        ("moanart-python", "moanart-testing"),
        ("python-engineer",),
        (PY,),
    ),
    "ci": ModuleGuide(
        (".github/workflows/",),
        ("tests/test_repository_tools.py",),
        ("moanart-testing",),
        ("qa-engineer",),
        (TEST, SEC),
    ),
    "release": ModuleGuide(
        ("pyproject.toml", "CHANGELOG.md", "README.md"),
        ("scripts/check_wheel.py",),
        ("moanart-code-review", "moanart-testing"),
        ("qa-engineer", "documentation"),
        (PY, SEC),
    ),
}
STOPWORDS: Final = frozenset({"a", "al", "con", "de", "del", "e", "el", "en", "la", "las", "los"})
STOPWORDS_EXTRA: Final = frozenset({"o", "para", "por", "su", "un", "una", "y"})


@cache
def section_titles(root: Path = ROOT) -> dict[int, str]:
    """Map MOANART.md section numbers to their headings."""
    text = (root / "MOANART.md").read_text(encoding="utf-8")
    return {int(number): title for number, title in re.findall(r"^## (\d+)\. (.+)$", text, re.M)}


def branch_name(issue: Issue) -> str:
    """Return the conventional feature branch, e.g. feat/MOANA-001-definir-tipos-coordenadas."""
    ascii_title = unicodedata.normalize("NFKD", issue.title).encode("ascii", "ignore").decode()
    words = [
        word
        for word in re.findall(r"[a-z0-9]+", ascii_title.lower())
        if word not in STOPWORDS | STOPWORDS_EXTRA
    ]
    return f"feat/{issue.id}-{'-'.join(words[:3])}"


def module_guides(issue: Issue) -> list[ModuleGuide]:
    """Return the guides of the issue modules; unknown modules are a catalog error."""
    unknown = [module for module in issue.modules if module not in MODULES]
    if unknown:
        raise ValueError(f"Unknown module in {issue.id}: {unknown}")
    return [MODULES[module] for module in issue.modules]


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def agent_guide(
    issue: Issue,
    requirements: Mapping[str, Requirement],
    dependents: list[str],
) -> str:
    """Render the 'Guía para agentes de IA' Markdown section body."""
    guides = module_guides(issue)
    titles = section_titles()
    sections = sorted(
        {3, 25, *(number for rid in issue.requirements for number in requirements[rid].sections)}
    )
    skills = _unique(
        [skill for guide in guides for skill in guide.skills] + ["moanart-code-review"]
    )
    agents = _unique([agent for guide in guides for agent in guide.agents])
    standards = _unique([standard for guide in guides for standard in guide.standards])
    paths = _unique([path for guide in guides for path in guide.paths])
    tests = _unique([path for guide in guides for path in guide.tests])
    branch = branch_name(issue)
    dependency_links = ", ".join(f"[{dep}]({dep}.md)" for dep in issue.dependencies) or "ninguna"
    unlocks = ", ".join(f"[{dep}]({dep}.md)" for dep in dependents) or "ninguno"
    if issue.status == "done":
        state = "Completado; usar sólo como referencia del contrato entregado."
    elif issue.status == "ready":
        state = "Listo: todas las dependencias están `done`; puede empezarse."
    elif issue.status == "in_progress":
        state = "En curso: continuar en su rama sin ampliar el alcance."
    elif issue.status == "review":
        state = "En revisión: sólo correcciones de la revisión; no añadir alcance."
    else:
        state = (
            f"No empezar: estado `{issue.status}`. Esperar a que {dependency_links} "
            "estén `done` y el catálogo marque este issue `ready`."
        )
    reading = [
        "`CLAUDE.md` (Claude Code) o `AGENTS.md` (Codex) y "
        "[flujo de sesión](../guides/agent-workflow.md).",
        "MOANART.md: "
        + "; ".join(f"§{number} {titles.get(number, '')}".rstrip() for number in sections)
        + ". Estas secciones son el contrato normativo; ante duda, prevalecen sobre este issue.",
        "[Contratos de módulos](../architecture/module-contracts.md) para: "
        + ", ".join(f"`{module}`" for module in issue.modules)
        + ".",
        "Estándares: "
        + ", ".join(f"[{Path(path).stem}](../../{path})" for path in standards)
        + ".",
        f"Issues de dependencia ({dependency_links}): leer su sección Evidence para conocer "
        "las APIs ya entregadas; no reimplementarlas.",
        "ADR en `docs/architecture/` que mencionen los módulos afectados.",
    ]
    requirement_rows = "\n".join(
        f"| {rid} | {requirements[rid].description} | "
        f"{', '.join(f'§{s}' for s in requirements[rid].sections)} | "
        f"{requirements[rid].verification} |"
        for rid in issue.requirements
    )
    test_rows = "\n".join(f"- T{index + 1}: {test}" for index, test in enumerate(issue.tests))
    values = {
        "state": state,
        "branch": branch,
        "dependencies": dependency_links,
        "reading": "\n".join(f"{index + 1}. {item}" for index, item in enumerate(reading)),
        "requirements": requirement_rows,
        "skills_claude": ", ".join(f"`{skill}`" for skill in skills),
        "skills_codex": ", ".join(f"`${skill}`" for skill in skills),
        "agents_claude": ", ".join(f"`moanart-{agent}`" for agent in agents),
        "agents_codex": ", ".join(f"`moanart_{agent.replace('-', '_')}`" for agent in agents),
        "paths": ", ".join(f"`{path}`" for path in paths),
        "tests": ", ".join(f"`{path}`" for path in tests),
        "test_plan": test_rows,
        "test_args": " ".join(tests),
        "ac_keys": ", ".join(f"AC{index + 1}" for index in range(len(issue.acceptance))),
        "t_keys": ", ".join(f"T{index + 1}" for index in range(len(issue.tests))),
        "unlocks": unlocks,
    }
    return TEMPLATE.substitute(values).rstrip()
