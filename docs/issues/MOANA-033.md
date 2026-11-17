# MOANA-033 — Documentar flujos IA y previews editables

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-033
- Aliases históricos: MOA-033
- Phase: P5
- Priority: P1
- Status: blocked
- Complexity: M (relativa, no estimación de tiempo)
- Dependencies: [MOANA-012](MOANA-012.md), [MOANA-018](MOANA-018.md), [MOANA-020](MOANA-020.md), [MOANA-026](MOANA-026.md)
- Related modules: docs, api
- Requirements: R014, R034, R038 ([trazabilidad](traceability.md))
- Bloqueo: Dependencias pendientes: MOANA-012, MOANA-018, MOANA-020, MOANA-026

## Context

Las sesiones futuras no conservarán el contexto de esta conversación.

## Objective

Ofrecer un tutorial ejecutable del flujo crear/mostrar/editar con el motor real.

## Scope

Completar tutorial JSON/Python/CLI y flujo de agente desde brief hasta preview y modificación por ID usando capacidades reales.

## Out of scope

No GUI, servicio alojado, credenciales ni envío de mensajes a terceros.

## Technical requirements

- Ejemplos ejecutables con schema vigente, paths relativos autorizados y PNG 1×/4×
- Actualizar skills y capabilities tras implementar; sin proveedor IA obligatorio

## Proposed implementation

- Escribir ejemplos sobre API/CLI implementados y validar schema vigente
- Ejecutar tutorial desde wheel limpio y actualizar skills/capabilities

## Acceptance criteria

- [ ] AC1: Un usuario reproduce creación, inspección y recolor con los comandos documentados
- [ ] AC2: El agente conserva fuente/revisión y presenta limitaciones sin prometer generación visual inexistente

## Required tests

- [ ] T1: Ejecutar snippets/tutorial en entorno wheel limpio
- [ ] T2: Validar ejemplos JSON contra schema y comprobar sólo región prevista cambia salvo dependencias declaradas

## Expected deliverables

- Guía de flujos IA para crear, inspeccionar y editar documentos por IDs.
- Ejemplos ejecutables de preview/cambio localizado y recuperación de errores.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- No documentar una API de diseño como importable antes de completar sus dependencias.

## Guía para agentes de IA

**Estado para agentes:** No empezar: estado `blocked`. Esperar a que [MOANA-012](MOANA-012.md), [MOANA-018](MOANA-018.md), [MOANA-020](MOANA-020.md), [MOANA-026](MOANA-026.md) estén `done` y el catálogo marque este issue `ready`.

### 1. Preparación

- Rama: `feat/MOANA-033-documentar-flujos-ia` creada desde `develop` actualizado: `git switch develop && git pull --ff-only && git switch -c feat/MOANA-033-documentar-flujos-ia`.
- Verificar en `docs/issues/catalog.json` que este issue está `ready` y que sus dependencias ([MOANA-012](MOANA-012.md), [MOANA-018](MOANA-018.md), [MOANA-020](MOANA-020.md), [MOANA-026](MOANA-026.md)) están `done`.
- Entorno: `uv sync --locked` (sin uv global: `sh scripts/bootstrap.sh` y después `sh scripts/uv.sh` en lugar de `uv`).
- Al empezar, cambiar `status` a `in_progress` en el catálogo y regenerar con `uv run python scripts/planning.py`.

### 2. Lectura obligatoria (en orden)

1. `CLAUDE.md` (Claude Code) o `AGENTS.md` (Codex) y [flujo de sesión](../guides/agent-workflow.md).
2. MOANA.md: §1 Visión y objetivos; §3 Arquitectura modular; §13 API pública de Python; §15 Edición no destructiva; §25 Definition of Done. Estas secciones son el contrato normativo; ante duda, prevalecen sobre este issue.
3. [Contratos de módulos](../architecture/module-contracts.md) para: `docs`, `api`.
4. Estándares: [architecture](../../docs/standards/architecture.md), [python](../../docs/standards/python.md), [testing](../../docs/standards/testing.md).
5. Issues de dependencia ([MOANA-012](MOANA-012.md), [MOANA-018](MOANA-018.md), [MOANA-020](MOANA-020.md), [MOANA-026](MOANA-026.md)): leer su sección Evidence para conocer las APIs ya entregadas; no reimplementarlas.
6. ADR en `docs/architecture/` que mencionen los módulos afectados.

### 3. Requisitos de MOANA.md cubiertos

| ID | Requisito | Secciones | Verificación exigida |
| --- | --- | --- | --- |
| R014 | API Python y CLI públicas | §13 | Wheel limpio y contratos de errores/resultados |
| R034 | Codex, roles y flujos de agentes | §3, §13, §25 | Auditoría de capacidades y configuración local válida |
| R038 | Preview y modificación específica por IA | §1, §13, §15 | Tutorial render-preview-edit con IDs preservados |

### 4. Skills y subagentes

| Host | Skills a cargar | Revisión especializada |
| --- | --- | --- |
| Claude Code | `moana-issue-planning`, `moana-python`, `moana-architecture`, `moana-code-review` | `moana-documentation`, `moana-python-engineer`, `moana-architect` (sólo lectura; el agente principal integra) |
| Codex | `$moana-issue-planning`, `$moana-python`, `$moana-architecture`, `$moana-code-review` | `moana_documentation`, `moana_python_engineer`, `moana_architect` |

### 5. Archivos

- Código o documentos a crear/modificar: `docs/`, `src/moana/api/`.
- Pruebas: `tests/test_repository_tools.py`, `tests/unit/api/`.
- No crear módulos ni carpetas sin comportamiento real. No tocar otros módulos salvo exportaciones imprescindibles, justificadas en el PR.

### 6. Plan de pruebas

- T1: Ejecutar snippets/tutorial en entorno wheel limpio
- T2: Validar ejemplos JSON contra schema y comprobar sólo región prevista cambia salvo dependencias declaradas
- Oráculos independientes (cálculo a mano o fórmula de MOANA.md); nunca copiar la salida de la implementación como expected.
- Incluir casos negativos con el error de dominio esperado y casos borde (vacío, mínimo, máximo, fuera de rango).

### 7. Procedimiento

1. Escribir las pruebas de los criterios AC y T antes o junto con la implementación.
2. Implementar sólo **Scope**; respetar **Out of scope** y las dependencias permitidas de MOANA.md §3.
3. Validación de módulo: `uv run pytest tests/test_repository_tools.py tests/unit/api/ -q` y `uv run mypy src/`.
4. Validación completa: `uv run python scripts/validate.py` y `uv run python scripts/check_wheel.py`.
5. Revisión: subagentes listados y skill `moana-code-review`; corregir hallazgos críticos y altos.
6. Si hay salida raster: mostrar el PNG a 1x y ampliado por vecino más cercano; si cambia un golden, presentar expected/actual/diff y justificar.

### 8. Cierre

1. En `docs/issues/catalog.json`, para este issue: `status` → `review` (o `done` tras aprobación); completar `acceptance_evidence` (AC1, AC2), `test_evidence` (T1, T2) y `evidence` con rutas concretas de tests y archivos.
2. Issues que desbloquea ([MOANA-035](MOANA-035.md)): si todas sus dependencias quedan `done`, pasarlos a `ready` con `blocking_reason: null`.
3. Ejecutar `uv run python scripts/planning.py` y `uv run python -m scripts.check_repository`.
4. Abrir PR hacia `develop` enlazando este issue de GitHub (`Closes #<número>`), con comandos ejecutados y evidencia por AC/T. El CI completo corre al integrar `develop` en `main`.
5. Commit y push sólo con autorización del usuario. No declarar CI remoto ni aprobación artística humana sin evidencia.

### 9. Prohibido en este issue

- Implementar alcance de otros issues, incluidos los que desbloquea ([MOANA-035](MOANA-035.md)).
- Actualizar goldens automáticamente, desactivar checks, editar `uv.lock` a mano o añadir dependencias sin motivo técnico registrado.
- `eval`/`exec`/`pickle`, red o estado global mutable en el núcleo; lecturas de texto sin `encoding="utf-8"`.

## Evidence

Pendiente de implementación.
