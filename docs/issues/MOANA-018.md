# MOANA-018 — Implementar batches de edición atómica

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-018
- Aliases históricos: MOA-018
- Phase: P3
- Priority: P0
- Status: blocked
- Complexity: L (relativa, no estimación de tiempo)
- Dependencies: [MOANA-002](MOANA-002.md), [MOANA-010](MOANA-010.md), [MOANA-012](MOANA-012.md), [MOANA-013](MOANA-013.md)
- Related modules: editing, api
- Requirements: R016, R038 ([trazabilidad](traceability.md))
- Bloqueo: Dependencias pendientes: MOANA-002, MOANA-010, MOANA-012, MOANA-013

## Context

Un cambio local necesita ser atómico y comprobar la revisión exacta de origen.

## Objective

Crear documentos nuevos mediante batches tipados con conflictos verificables.

## Scope

Crear moana/editing con comandos de §15, targeting por ID y revisión optimista; integrar apply_edit en fachada.

## Out of scope

No protocolo JSON Patch arbitrario ni colaboración en tiempo real.

## Technical requirements

- Validar lote completo y escena final; sin cambios parciales ni mutación del documento fuente
- Rechazar revisión vieja, capa bloqueada, borrado referenciado e IDs mutados; incrementar revisión una vez
- Exigir base_revision y base_snapshot (digest del documento) en cada batch; rechazar mismatches incluso con revisión numérica igual.

## Proposed implementation

- Resolver targets y locks, aplicar batch a una copia y validar el resultado completo
- Aceptar una sola nueva revisión y reportar IDs/dependencias/bbox afectados

## Acceptance criteria

- [ ] AC1: Recolor de body_fill modifica únicamente su referencia y la revisión preservando toda otra estructura
- [ ] AC2: Un segundo comando inválido revierte también el primero; se devuelve EditConflict para base vieja

## Required tests

- [ ] T1: Cada comando con caso válido/negativo, reorder al principio y dependencias vivas
- [ ] T2: Comparar documento original byte a byte, render antes/después y batch sin cambio visual
- [ ] T3: Dos ramas con revision=1 y contenidos distintos rechazan el batch de la otra rama mediante base_snapshot.

## Expected deliverables

- Modelos de batch y aplicación transaccional que verifica revisión y snapshot base.
- Pruebas de rollback, preservación de IDs y conflicto entre ramas con igual revisión.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- Tras undo pueden existir revisiones numéricas iguales en ramas distintas; verificar también identidad del snapshot.

## Guía para agentes de IA

**Estado para agentes:** No empezar: estado `blocked`. Esperar a que [MOANA-002](MOANA-002.md), [MOANA-010](MOANA-010.md), [MOANA-012](MOANA-012.md), [MOANA-013](MOANA-013.md) estén `done` y el catálogo marque este issue `ready`.

### 1. Preparación

- Rama: `feat/MOANA-018-implementar-batches-edicion` creada desde `develop` actualizado: `git switch develop && git pull --ff-only && git switch -c feat/MOANA-018-implementar-batches-edicion`.
- Verificar en `docs/issues/catalog.json` que este issue está `ready` y que sus dependencias ([MOANA-002](MOANA-002.md), [MOANA-010](MOANA-010.md), [MOANA-012](MOANA-012.md), [MOANA-013](MOANA-013.md)) están `done`.
- Entorno: `uv sync --locked` (sin uv global: `sh scripts/bootstrap.sh` y después `sh scripts/uv.sh` en lugar de `uv`).
- Al empezar, cambiar `status` a `in_progress` en el catálogo y regenerar con `uv run python scripts/planning.py`.

### 2. Lectura obligatoria (en orden)

1. `CLAUDE.md` (Claude Code) o `AGENTS.md` (Codex) y [flujo de sesión](../guides/agent-workflow.md).
2. MOANA.md: §1 Visión y objetivos; §3 Arquitectura modular; §13 API pública de Python; §15 Edición no destructiva; §25 Definition of Done. Estas secciones son el contrato normativo; ante duda, prevalecen sobre este issue.
3. [Contratos de módulos](../architecture/module-contracts.md) para: `editing`, `api`.
4. Estándares: [python](../../docs/standards/python.md), [architecture](../../docs/standards/architecture.md), [testing](../../docs/standards/testing.md).
5. Issues de dependencia ([MOANA-002](MOANA-002.md), [MOANA-010](MOANA-010.md), [MOANA-012](MOANA-012.md), [MOANA-013](MOANA-013.md)): leer su sección Evidence para conocer las APIs ya entregadas; no reimplementarlas.
6. ADR en `docs/architecture/` que mencionen los módulos afectados.

### 3. Requisitos de MOANA.md cubiertos

| ID | Requisito | Secciones | Verificación exigida |
| --- | --- | --- | --- |
| R016 | Edición no destructiva atómica | §15 | Batch reversible, revisión obsoleta y diff local |
| R038 | Preview y modificación específica por IA | §1, §13, §15 | Tutorial render-preview-edit con IDs preservados |

### 4. Skills y subagentes

| Host | Skills a cargar | Revisión especializada |
| --- | --- | --- |
| Claude Code | `moana-python`, `moana-architecture`, `moana-code-review` | `moana-python-engineer`, `moana-architect` (sólo lectura; el agente principal integra) |
| Codex | `$moana-python`, `$moana-architecture`, `$moana-code-review` | `moana_python_engineer`, `moana_architect` |

### 5. Archivos

- Código o documentos a crear/modificar: `src/moana/editing/`, `src/moana/api/`.
- Pruebas: `tests/unit/editing/`, `tests/unit/api/`.
- No crear módulos ni carpetas sin comportamiento real. No tocar otros módulos salvo exportaciones imprescindibles, justificadas en el PR.

### 6. Plan de pruebas

- T1: Cada comando con caso válido/negativo, reorder al principio y dependencias vivas
- T2: Comparar documento original byte a byte, render antes/después y batch sin cambio visual
- T3: Dos ramas con revision=1 y contenidos distintos rechazan el batch de la otra rama mediante base_snapshot.
- Oráculos independientes (cálculo a mano o fórmula de MOANA.md); nunca copiar la salida de la implementación como expected.
- Incluir casos negativos con el error de dominio esperado y casos borde (vacío, mínimo, máximo, fuera de rango).

### 7. Procedimiento

1. Escribir las pruebas de los criterios AC y T antes o junto con la implementación.
2. Implementar sólo **Scope**; respetar **Out of scope** y las dependencias permitidas de MOANA.md §3.
3. Validación de módulo: `uv run pytest tests/unit/editing/ tests/unit/api/ -q` y `uv run mypy src/`.
4. Validación completa: `uv run python scripts/validate.py` y `uv run python scripts/check_wheel.py`.
5. Revisión: subagentes listados y skill `moana-code-review`; corregir hallazgos críticos y altos.
6. Si hay salida raster: mostrar el PNG a 1x y ampliado por vecino más cercano; si cambia un golden, presentar expected/actual/diff y justificar.

### 8. Cierre

1. En `docs/issues/catalog.json`, para este issue: `status` → `review` (o `done` tras aprobación); completar `acceptance_evidence` (AC1, AC2), `test_evidence` (T1, T2, T3) y `evidence` con rutas concretas de tests y archivos.
2. Issues que desbloquea ([MOANA-019](MOANA-019.md), [MOANA-020](MOANA-020.md), [MOANA-022](MOANA-022.md), [MOANA-032](MOANA-032.md), [MOANA-033](MOANA-033.md)): si todas sus dependencias quedan `done`, pasarlos a `ready` con `blocking_reason: null`.
3. Ejecutar `uv run python scripts/planning.py` y `uv run python -m scripts.check_repository`.
4. Abrir PR hacia `develop` enlazando este issue de GitHub (`Closes #<número>`), con comandos ejecutados y evidencia por AC/T. El CI completo corre al integrar `develop` en `main`.
5. Commit y push sólo con autorización del usuario. No declarar CI remoto ni aprobación artística humana sin evidencia.

### 9. Prohibido en este issue

- Implementar alcance de otros issues, incluidos los que desbloquea ([MOANA-019](MOANA-019.md), [MOANA-020](MOANA-020.md), [MOANA-022](MOANA-022.md), [MOANA-032](MOANA-032.md), [MOANA-033](MOANA-033.md)).
- Actualizar goldens automáticamente, desactivar checks, editar `uv.lock` a mano o añadir dependencias sin motivo técnico registrado.
- `eval`/`exec`/`pickle`, red o estado global mutable en el núcleo; lecturas de texto sin `encoding="utf-8"`.

## Evidence

Pendiente de implementación.
