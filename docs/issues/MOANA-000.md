# MOANA-000 — Inicializar infraestructura y planificación

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-000
- Aliases históricos: MOA-000
- Phase: P0
- Priority: P0
- Status: done
- Complexity: L (relativa, no estimación de tiempo)
- Dependencies: Ninguna
- Related modules: tooling, docs, agents
- Requirements: R001, R030, R031, R032, R033, R034, R035, R036, R039 ([trazabilidad](traceability.md))
- Bloqueo: Ninguno

## Context

Un checkout vacío no ofrecía contrato ni herramientas de desarrollo.

## Objective

Conservar una base reproducible y ampliar su planificación sin crear motor.

## Scope

Crear especificación, paquete mínimo, entorno, skills, roles, CI y backlog completo; registrar evidencia de las capacidades realmente observadas.

## Out of scope

No implementar canvas, rasterizador, API gráfica ni publicar repositorio/paquete.

## Technical requirements

- Python >=3.12, src layout, uv.lock resuelto y entorno virtual real
- Ruff, mypy, pytest, build y validación de DAG/skills accesibles desde scripts/validate.py

## Proposed implementation

- Auditar archivos y capacidades existentes; resolver divergencias con ADR
- Generar documentación desde un catálogo validado y ejecutar comandos reales

## Acceptance criteria

- [x] AC1: Las 25 secciones normativas y todos los requisitos tienen trazabilidad sin ciclos
- [x] AC2: Import y wheel aislado funcionan; siete skills válidas, configuración local documentada y gate verde

## Required tests

- [x] T1: Ejecutar lint, formato, tipos, smoke de bibliotecas y comprobación del backlog
- [x] T2: Construir wheel/sdist, instalar wheel fuera de src y validar las siete skills con el validador disponible

## Expected deliverables

- Entorno uv, paquete mínimo tipado, gate y workflow CI verificables.
- AGENTS.md, siete skills, ocho roles, contratos, backlog generado y reporte de evidencia.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- Confundir configuración guardada con una capacidad activa; registrar evidencia por superficie.

## Guía para agentes de IA

**Estado para agentes:** Completado; usar sólo como referencia del contrato entregado.

### 1. Preparación

- Rama: `feat/MOANA-000-inicializar-infraestructura-planificacion` creada desde `develop` actualizado: `git switch develop && git pull --ff-only && git switch -c feat/MOANA-000-inicializar-infraestructura-planificacion`.
- Verificar en `docs/issues/catalog.json` que este issue está `ready` y que sus dependencias (ninguna) están `done`.
- Entorno: `uv sync --locked` (sin uv global: `sh scripts/bootstrap.sh` y después `sh scripts/uv.sh` en lugar de `uv`).
- Al empezar, cambiar `status` a `in_progress` en el catálogo y regenerar con `uv run python scripts/planning.py`.

### 2. Lectura obligatoria (en orden)

1. `CLAUDE.md` (Claude Code) o `AGENTS.md` (Codex) y [flujo de sesión](../guides/agent-workflow.md).
2. MOANA.md: §1 Visión y objetivos; §2 Alcance funcional y no funcional; §3 Arquitectura modular; §4 Stack tecnológico; §13 API pública de Python; §21 Testing y regresiones visuales; §23 Roadmap por fases; §24 Criterios de aceptación; §25 Definition of Done. Estas secciones son el contrato normativo; ante duda, prevalecen sobre este issue.
3. [Contratos de módulos](../architecture/module-contracts.md) para: `tooling`, `docs`, `agents`.
4. Estándares: [python](../../docs/standards/python.md), [architecture](../../docs/standards/architecture.md).
5. Issues de dependencia (ninguna): leer su sección Evidence para conocer las APIs ya entregadas; no reimplementarlas.
6. ADR en `docs/architecture/` que mencionen los módulos afectados.

### 3. Requisitos de MOANA.md cubiertos

| ID | Requisito | Secciones | Verificación exigida |
| --- | --- | --- | --- |
| R001 | Visión, alcance y especificación exhaustiva | §1, §2, §23, §24, §25 | Revisión de las 25 secciones y gate P0 |
| R030 | Arquitectura modular y documentación | §3 | Dependencias internas y ADR revisados |
| R031 | Paquete instalable y artefactos | §4, §25 | Build y smoke de wheel/sdist aislados |
| R032 | Entorno Python y herramientas de calidad | §4, §21 | uv locked, Ruff, mypy, pytest y dependencias nativas |
| R033 | Siete skills especializadas | §3, §25 | Frontmatter, UI metadata, referencias y validador de skills |
| R034 | Codex, roles y flujos de agentes | §3, §13, §25 | Auditoría de capacidades y configuración local válida |
| R035 | Hooks y automatización CI | §21, §25 | pre-commit y workflow en matriz sin publicación |
| R036 | Issues, roadmap, dependencias y trazabilidad | §23, §24 | Checker DAG, cobertura y documentos sincronizados |
| R039 | Criterios de aceptación y Definition of Done | §24, §25 | Evidencias por issue y gate de release |

### 4. Skills y subagentes

| Host | Skills a cargar | Revisión especializada |
| --- | --- | --- |
| Claude Code | `moana-python`, `moana-testing`, `moana-issue-planning`, `moana-code-review` | `moana-python-engineer`, `moana-documentation` (sólo lectura; el agente principal integra) |
| Codex | `$moana-python`, `$moana-testing`, `$moana-issue-planning`, `$moana-code-review` | `moana_python_engineer`, `moana_documentation` |

### 5. Archivos

- Código o documentos a crear/modificar: `scripts/`, `docs/`, `docs/guides/`, `.agents/skills/`, `.claude/`.
- Pruebas: `tests/`, `tests/test_repository_tools.py`.
- No crear módulos ni carpetas sin comportamiento real. No tocar otros módulos salvo exportaciones imprescindibles, justificadas en el PR.

### 6. Plan de pruebas

- T1: Ejecutar lint, formato, tipos, smoke de bibliotecas y comprobación del backlog
- T2: Construir wheel/sdist, instalar wheel fuera de src y validar las siete skills con el validador disponible
- Oráculos independientes (cálculo a mano o fórmula de MOANA.md); nunca copiar la salida de la implementación como expected.
- Incluir casos negativos con el error de dominio esperado y casos borde (vacío, mínimo, máximo, fuera de rango).

### 7. Procedimiento

1. Escribir las pruebas de los criterios AC y T antes o junto con la implementación.
2. Implementar sólo **Scope**; respetar **Out of scope** y las dependencias permitidas de MOANA.md §3.
3. Validación de módulo: `uv run pytest tests/ tests/test_repository_tools.py -q` y `uv run mypy src/`.
4. Validación completa: `uv run python scripts/validate.py` y `uv run python scripts/check_wheel.py`.
5. Revisión: subagentes listados y skill `moana-code-review`; corregir hallazgos críticos y altos.
6. Si hay salida raster: mostrar el PNG a 1x y ampliado por vecino más cercano; si cambia un golden, presentar expected/actual/diff y justificar.

### 8. Cierre

1. En `docs/issues/catalog.json`, para este issue: `status` → `review` (o `done` tras aprobación); completar `acceptance_evidence` (AC1, AC2), `test_evidence` (T1, T2) y `evidence` con rutas concretas de tests y archivos.
2. Issues que desbloquea ([MOANA-001](MOANA-001.md)): si todas sus dependencias quedan `done`, pasarlos a `ready` con `blocking_reason: null`.
3. Ejecutar `uv run python scripts/planning.py` y `uv run python -m scripts.check_repository`.
4. Abrir PR hacia `develop` enlazando este issue de GitHub (`Closes #<número>`), con comandos ejecutados y evidencia por AC/T. El CI completo corre al integrar `develop` en `main`.
5. Commit y push sólo con autorización del usuario. No declarar CI remoto ni aprobación artística humana sin evidencia.

### 9. Prohibido en este issue

- Implementar alcance de otros issues, incluidos los que desbloquea ([MOANA-001](MOANA-001.md)).
- Actualizar goldens automáticamente, desactivar checks, editar `uv.lock` a mano o añadir dependencias sin motivo técnico registrado.
- `eval`/`exec`/`pickle`, red o estado global mutable en el núcleo; lecturas de texto sin `encoding="utf-8"`.

## Evidence

- 2026-11-16: scripts/validate.py aprobó lock, Ruff, mypy, checker, 20 tests y build en macOS arm64 / Python 3.12.16.
- Wheel construido desde sdist e instalado fuera del checkout; metadata y py.typed verificados.
- Siete skills aprobadas por quick_validate.py; roles/config TOML verificados y ajustes aceptados por CLI Codex.
- pre-commit instalado y ejecutado sobre todos los archivos nuevos. Ver docs/INITIALIZATION_REPORT.md para límites y versiones.
- 2026-11-17: refinamiento validado localmente con 26 tests, gate completo, uv build, wheel aislado y siete skills descubiertas por Codex; docs/BOOTSTRAP_REPORT.md. Sin push de esta revisión.
- AC1: 2026-11-17: scripts.check_repository y planning.py --check validan 36 IDs canónicos, DAG acíclico, 40 requisitos y 25 secciones; docs/BOOTSTRAP_REPORT.md.
- AC2: 2026-11-17: validate.py aprobado; check_wheel.py verificó import/metadata/py.typed en venv aislado; skills/list devolvió siete skills habilitadas de scope repo sin errores.
- T1: 2026-11-17: Ruff, formato, mypy (10 archivos), checker y pytest (26 aprobados) en macOS arm64/Python 3.12.16; artifacts/validation.log.
- T2: 2026-11-17: uv build y build del gate generaron sdist/wheel; instalación aislada aprobada y quick_validate.py aprobó las siete skills.
