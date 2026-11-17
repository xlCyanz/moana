# Moana — instrucciones para Claude Code

Moana es un motor Python determinista de Pixel Art (128 × 128 de referencia) controlable por agentes. **Estado: P0 completado; `moana.core` (MOANA-001) implementado; sin render.** El siguiente issue `ready` está en el [roadmap](docs/issues/roadmap.md).

Las reglas operativas comunes a todos los agentes viven en `AGENTS.md` y se importan aquí; no se duplican:

@AGENTS.md

## Específico de Claude Code

- Fuente de verdad del producto: [MOANA.md](MOANA.md). Léelo por secciones según el issue; no conviertas ejemplos de diseño en APIs.
- Arquitectura y fronteras: [overview](docs/architecture/overview.md), [contratos de módulos](docs/architecture/module-contracts.md), ADR en `docs/architecture/`.
- Flujo de sesión obligatorio: [agent-workflow](docs/guides/agent-workflow.md). Inventario y límites de la configuración: [CLAUDE_CODE.md](docs/CLAUDE_CODE.md).
- Reglas por ruta en `.claude/rules/` (se cargan al tocar archivos coincidentes). Estándares completos en `docs/standards/`.
- Skills: `.claude/skills/moana-*` son envoltorios descubribles de las fuentes canónicas en `.agents/skills/`. Edita la fuente canónica; el checker exige que nombre y descripción coincidan.
- Subagentes en `.claude/agents/`: `moana-architect`, `moana-python-engineer`, `moana-graphics-engineer`, `moana-pixel-artist`, `moana-qa-engineer`, `moana-documentation`. Sólo los de documentación editan; el resto revisa e informa. El agente principal integra y ejecuta el gate.
- Hooks (`.claude/settings.json`): tras editar `.py` se ejecuta Ruff sobre ese archivo; antes de Bash se bloquean force push, reset duro, `--no-verify` y borrados recursivos fuera de artefactos; no se edita `uv.lock` ni `.env`.

## Niveles de validación

| Nivel | Cuándo | Comando |
| --- | --- | --- |
| Rápida | Automática tras cada edición `.py` | hook Ruff del archivo |
| Módulo | Al terminar una unidad | `uv run pytest tests/unit -q` o el archivo afectado; `uv run mypy src/` |
| Completa | Antes de declarar un issue en review/done | `uv run python scripts/validate.py` y `uv run python scripts/check_wheel.py` |
| Pre-commit | Al hacer commit (si se pidió) | `uv run pre-commit run --all-files` |

Sin uv global: `sh scripts/uv.sh` en lugar de `uv`. No ejecutes la suite completa tras cada cambio pequeño.

## Definition of Done (resumen)

Criterios AC y pruebas T del issue con evidencia por ID, gate completo verde, docs/trazabilidad/catálogo regenerados (`uv run python scripts/planning.py`), diff revisado, estado del issue actualizado en `docs/issues/catalog.json`. Detalle: MOANA.md §25 y [ciclo de vida](docs/guides/issue-lifecycle.md). No hagas commit, push ni cambios remotos sin autorización explícita.
