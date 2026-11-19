# MOANA-035 — Preparar release y comprobar Definition of Done

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-035
- Aliases históricos: MOA-035
- Phase: P5
- Priority: P1
- Status: blocked
- Complexity: L (relativa, no estimación de tiempo)
- Dependencies: [MOANA-007](MOANA-007.md), [MOANA-021](MOANA-021.md), [MOANA-023](MOANA-023.md), [MOANA-024](MOANA-024.md), [MOANA-025](MOANA-025.md), [MOANA-027](MOANA-027.md), [MOANA-029](MOANA-029.md), [MOANA-030](MOANA-030.md), [MOANA-032](MOANA-032.md), [MOANA-033](MOANA-033.md), [MOANA-034](MOANA-034.md)
- Related modules: release, docs
- Requirements: R031, R039, R036 ([trazabilidad](traceability.md))
- Bloqueo: Dependencias pendientes: MOANA-025, MOANA-027, MOANA-030, MOANA-032, MOANA-033, MOANA-034

## Context

Una release necesita evidencias de alcance, compatibilidad y licencia además de un wheel.

## Objective

Preparar un candidato instalable con DoD y pendientes explícitos.

## Scope

Preparar release candidate con wheel/sdist, changelog, matriz de compatibilidad, evidencia de QA y decisión de licencia.

## Out of scope

No publicar en PyPI/GitHub ni declarar CI remoto verde sin ejecutarlo y sin autorización de publicación.

## Technical requirements

- Auditar todos los requisitos y evidencias sin confundir cobertura de planning con implementación
- Versiones paquete/schema/renderer, migraciones y capacidades documentadas; publicación separada

## Proposed implementation

- Auditar requisitos/evidencias y generar matriz de capacidades
- Probar wheel/sdist, tutorial, migraciones y dejar publicación como acción autorizada separada

## Acceptance criteria

- [ ] AC1: Wheel y sdist se instalan limpios y tutorial/corpus funcionan sin checkout
- [ ] AC2: DoD completa, licencia decidida por propietario y limitaciones/artistic review pendientes explícitas antes de publicar

## Required tests

- [ ] T1: Instalación desde ambos artefactos, smoke CLI y migraciones en entorno limpio
- [ ] T2: Revisión final de traceability, CI remoto real, corpus, seguridad y benchmark archivados

## Expected deliverables

- Checklist de release con decisión de licencia, compatibilidad y documentación pública.
- Wheel/sdist auditados, instalación limpia y evidencia de todos los gates de entrega.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- No declarar CI remoto de cambios locales ni licencia decidida sin evidencia del propietario.

## Guía para agentes de IA

**Estado para agentes:** No empezar: estado `blocked`. Esperar a que [MOANA-007](MOANA-007.md), [MOANA-021](MOANA-021.md), [MOANA-023](MOANA-023.md), [MOANA-024](MOANA-024.md), [MOANA-025](MOANA-025.md), [MOANA-027](MOANA-027.md), [MOANA-029](MOANA-029.md), [MOANA-030](MOANA-030.md), [MOANA-032](MOANA-032.md), [MOANA-033](MOANA-033.md), [MOANA-034](MOANA-034.md) estén `done` y el catálogo marque este issue `ready`.

### 1. Preparación

- Rama: `feat/MOANA-035-preparar-release-comprobar` creada desde `develop` actualizado: `git switch develop && git pull --ff-only && git switch -c feat/MOANA-035-preparar-release-comprobar`.
- Verificar en `docs/issues/catalog.json` que este issue está `ready` y que sus dependencias ([MOANA-007](MOANA-007.md), [MOANA-021](MOANA-021.md), [MOANA-023](MOANA-023.md), [MOANA-024](MOANA-024.md), [MOANA-025](MOANA-025.md), [MOANA-027](MOANA-027.md), [MOANA-029](MOANA-029.md), [MOANA-030](MOANA-030.md), [MOANA-032](MOANA-032.md), [MOANA-033](MOANA-033.md), [MOANA-034](MOANA-034.md)) están `done`.
- Entorno: `uv sync --locked` (sin uv global: `sh scripts/bootstrap.sh` y después `sh scripts/uv.sh` en lugar de `uv`).
- Al empezar, cambiar `status` a `in_progress` en el catálogo y regenerar con `uv run python scripts/planning.py`.

### 2. Lectura obligatoria (en orden)

1. `CLAUDE.md` (Claude Code) o `AGENTS.md` (Codex) y [flujo de sesión](../guides/agent-workflow.md).
2. MOANA.md: §3 Arquitectura modular; §4 Stack tecnológico; §23 Roadmap por fases; §24 Criterios de aceptación; §25 Definition of Done. Estas secciones son el contrato normativo; ante duda, prevalecen sobre este issue.
3. [Contratos de módulos](../architecture/module-contracts.md) para: `release`, `docs`.
4. Estándares: [python](../../docs/standards/python.md), [security](../../docs/standards/security.md), [architecture](../../docs/standards/architecture.md).
5. Issues de dependencia ([MOANA-007](MOANA-007.md), [MOANA-021](MOANA-021.md), [MOANA-023](MOANA-023.md), [MOANA-024](MOANA-024.md), [MOANA-025](MOANA-025.md), [MOANA-027](MOANA-027.md), [MOANA-029](MOANA-029.md), [MOANA-030](MOANA-030.md), [MOANA-032](MOANA-032.md), [MOANA-033](MOANA-033.md), [MOANA-034](MOANA-034.md)): leer su sección Evidence para conocer las APIs ya entregadas; no reimplementarlas.
6. ADR en `docs/architecture/` que mencionen los módulos afectados.

### 3. Requisitos de MOANA.md cubiertos

| ID | Requisito | Secciones | Verificación exigida |
| --- | --- | --- | --- |
| R031 | Paquete instalable y artefactos | §4, §25 | Build y smoke de wheel/sdist aislados |
| R039 | Criterios de aceptación y Definition of Done | §24, §25 | Evidencias por issue y gate de release |
| R036 | Issues, roadmap, dependencias y trazabilidad | §23, §24 | Checker DAG, cobertura y documentos sincronizados |

### 4. Skills y subagentes

| Host | Skills a cargar | Revisión especializada |
| --- | --- | --- |
| Claude Code | `moana-code-review`, `moana-testing`, `moana-issue-planning` | `moana-qa-engineer`, `moana-documentation` (sólo lectura; el agente principal integra) |
| Codex | `$moana-code-review`, `$moana-testing`, `$moana-issue-planning` | `moana_qa_engineer`, `moana_documentation` |

### 5. Archivos

- Código o documentos a crear/modificar: `pyproject.toml`, `CHANGELOG.md`, `README.md`, `docs/`.
- Pruebas: `scripts/check_wheel.py`, `tests/test_repository_tools.py`.
- No crear módulos ni carpetas sin comportamiento real. No tocar otros módulos salvo exportaciones imprescindibles, justificadas en el PR.

### 6. Plan de pruebas

- T1: Instalación desde ambos artefactos, smoke CLI y migraciones en entorno limpio
- T2: Revisión final de traceability, CI remoto real, corpus, seguridad y benchmark archivados
- Oráculos independientes (cálculo a mano o fórmula de MOANA.md); nunca copiar la salida de la implementación como expected.
- Incluir casos negativos con el error de dominio esperado y casos borde (vacío, mínimo, máximo, fuera de rango).

### 7. Procedimiento

1. Escribir las pruebas de los criterios AC y T antes o junto con la implementación.
2. Implementar sólo **Scope**; respetar **Out of scope** y las dependencias permitidas de MOANA.md §3.
3. Validación de módulo: `uv run pytest scripts/check_wheel.py tests/test_repository_tools.py -q` y `uv run mypy src/`.
4. Validación completa: `uv run python scripts/validate.py` y `uv run python scripts/check_wheel.py`.
5. Revisión: subagentes listados y skill `moana-code-review`; corregir hallazgos críticos y altos.
6. Si hay salida raster: mostrar el PNG a 1x y ampliado por vecino más cercano; si cambia un golden, presentar expected/actual/diff y justificar.

### 8. Cierre

1. En `docs/issues/catalog.json`, para este issue: `status` → `review` (o `done` tras aprobación); completar `acceptance_evidence` (AC1, AC2), `test_evidence` (T1, T2) y `evidence` con rutas concretas de tests y archivos.
2. Issues que desbloquea (ninguno): si todas sus dependencias quedan `done`, pasarlos a `ready` con `blocking_reason: null`.
3. Ejecutar `uv run python scripts/planning.py` y `uv run python -m scripts.check_repository`.
4. Abrir PR hacia `develop` enlazando este issue de GitHub (`Closes #<número>`), con comandos ejecutados y evidencia por AC/T. El CI completo corre al integrar `develop` en `main`.
5. Commit y push sólo con autorización del usuario. No declarar CI remoto ni aprobación artística humana sin evidencia.

### 9. Prohibido en este issue

- Implementar alcance de otros issues, incluidos los que desbloquea (ninguno).
- Actualizar goldens automáticamente, desactivar checks, editar `uv.lock` a mano o añadir dependencias sin motivo técnico registrado.
- `eval`/`exec`/`pickle`, red o estado global mutable en el núcleo; lecturas de texto sin `encoding="utf-8"`.

## Evidence

Pendiente de implementación.
