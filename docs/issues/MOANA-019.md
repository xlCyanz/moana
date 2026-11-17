# MOANA-019 — Añadir undo/redo e historial inmutable

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-019
- Aliases históricos: MOA-019
- Phase: P3
- Priority: P1
- Status: blocked
- Complexity: L (relativa, no estimación de tiempo)
- Dependencies: [MOANA-018](MOANA-018.md)
- Related modules: editing
- Requirements: R017 ([trazabilidad](traceability.md))
- Bloqueo: Dependencias pendientes: MOANA-018

## Context

Undo/redo debe recuperar el documento y sus píxeles, no aproximarlos.

## Objective

Mantener snapshots persistentes y ramas sin pérdida silenciosa de estados.

## Scope

Crear snapshots con digest, comandos canónicos y cursor de historial; permitir undo/redo y nueva rama después de undo.

## Out of scope

No persistir todavía un contenedor de proyecto ni fusionar ramas automáticamente.

## Technical requirements

- No reconstruir estados con operaciones inversas aproximadas
- Limitar memoria/historial y separar selección de revisión de la edición que crea nueva revisión
- Identidad del snapshot por digest; número revision local a cada rama, nunca usado como clave global.

## Proposed implementation

- Indexar snapshots por digest y guardar padre/batch con cursor separado
- Implementar navegación y nueva rama con presupuesto explícito

## Acceptance criteria

- [ ] AC1: Undo y redo recuperan documento y RGBA exactos
- [ ] AC2: Editar después de undo invalida sólo redo activo sin eliminar estados ya persistidos

## Required tests

- [ ] T1: Secuencias de 1/10/100 ediciones y navegación a límites
- [ ] T2: Fallo de batch no agrega snapshot; ramas, revisiones y budget de historial

## Expected deliverables

- Historial inmutable con undo/redo y relación entre snapshots mediante digest.
- Fixtures de ramificación, invalidez de redo y restauración exacta del documento.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- No usar el número de revisión como identidad global del historial.

## Guía para agentes de IA

**Estado para agentes:** No empezar: estado `blocked`. Esperar a que [MOANA-018](MOANA-018.md) estén `done` y el catálogo marque este issue `ready`.

### 1. Preparación

- Rama: `feat/MOANA-019-anadir-undo-redo` creada desde `develop` actualizado: `git switch develop && git pull --ff-only && git switch -c feat/MOANA-019-anadir-undo-redo`.
- Verificar en `docs/issues/catalog.json` que este issue está `ready` y que sus dependencias ([MOANA-018](MOANA-018.md)) están `done`.
- Entorno: `uv sync --locked` (sin uv global: `sh scripts/bootstrap.sh` y después `sh scripts/uv.sh` en lugar de `uv`).
- Al empezar, cambiar `status` a `in_progress` en el catálogo y regenerar con `uv run python scripts/planning.py`.

### 2. Lectura obligatoria (en orden)

1. `CLAUDE.md` (Claude Code) o `AGENTS.md` (Codex) y [flujo de sesión](../guides/agent-workflow.md).
2. MOANA.md: §3 Arquitectura modular; §15 Edición no destructiva; §25 Definition of Done. Estas secciones son el contrato normativo; ante duda, prevalecen sobre este issue.
3. [Contratos de módulos](../architecture/module-contracts.md) para: `editing`.
4. Estándares: [python](../../docs/standards/python.md), [architecture](../../docs/standards/architecture.md), [testing](../../docs/standards/testing.md).
5. Issues de dependencia ([MOANA-018](MOANA-018.md)): leer su sección Evidence para conocer las APIs ya entregadas; no reimplementarlas.
6. ADR en `docs/architecture/` que mencionen los módulos afectados.

### 3. Requisitos de MOANA.md cubiertos

| ID | Requisito | Secciones | Verificación exigida |
| --- | --- | --- | --- |
| R017 | Historial y undo/redo | §15 | Snapshots y ramas con igualdad exacta |

### 4. Skills y subagentes

| Host | Skills a cargar | Revisión especializada |
| --- | --- | --- |
| Claude Code | `moana-python`, `moana-architecture`, `moana-code-review` | `moana-python-engineer`, `moana-architect` (sólo lectura; el agente principal integra) |
| Codex | `$moana-python`, `$moana-architecture`, `$moana-code-review` | `moana_python_engineer`, `moana_architect` |

### 5. Archivos

- Código o documentos a crear/modificar: `src/moana/editing/`.
- Pruebas: `tests/unit/editing/`.
- No crear módulos ni carpetas sin comportamiento real. No tocar otros módulos salvo exportaciones imprescindibles, justificadas en el PR.

### 6. Plan de pruebas

- T1: Secuencias de 1/10/100 ediciones y navegación a límites
- T2: Fallo de batch no agrega snapshot; ramas, revisiones y budget de historial
- Oráculos independientes (cálculo a mano o fórmula de MOANA.md); nunca copiar la salida de la implementación como expected.
- Incluir casos negativos con el error de dominio esperado y casos borde (vacío, mínimo, máximo, fuera de rango).

### 7. Procedimiento

1. Escribir las pruebas de los criterios AC y T antes o junto con la implementación.
2. Implementar sólo **Scope**; respetar **Out of scope** y las dependencias permitidas de MOANA.md §3.
3. Validación de módulo: `uv run pytest tests/unit/editing/ -q` y `uv run mypy src/`.
4. Validación completa: `uv run python scripts/validate.py` y `uv run python scripts/check_wheel.py`.
5. Revisión: subagentes listados y skill `moana-code-review`; corregir hallazgos críticos y altos.
6. Si hay salida raster: mostrar el PNG a 1x y ampliado por vecino más cercano; si cambia un golden, presentar expected/actual/diff y justificar.

### 8. Cierre

1. En `docs/issues/catalog.json`, para este issue: `status` → `review` (o `done` tras aprobación); completar `acceptance_evidence` (AC1, AC2), `test_evidence` (T1, T2) y `evidence` con rutas concretas de tests y archivos.
2. Issues que desbloquea ([MOANA-020](MOANA-020.md), [MOANA-022](MOANA-022.md)): si todas sus dependencias quedan `done`, pasarlos a `ready` con `blocking_reason: null`.
3. Ejecutar `uv run python scripts/planning.py` y `uv run python -m scripts.check_repository`.
4. Abrir PR hacia `develop` enlazando este issue de GitHub (`Closes #<número>`), con comandos ejecutados y evidencia por AC/T. El CI completo corre al integrar `develop` en `main`.
5. Commit y push sólo con autorización del usuario. No declarar CI remoto ni aprobación artística humana sin evidencia.

### 9. Prohibido en este issue

- Implementar alcance de otros issues, incluidos los que desbloquea ([MOANA-020](MOANA-020.md), [MOANA-022](MOANA-022.md)).
- Actualizar goldens automáticamente, desactivar checks, editar `uv.lock` a mano o añadir dependencias sin motivo técnico registrado.
- `eval`/`exec`/`pickle`, red o estado global mutable en el núcleo; lecturas de texto sin `encoding="utf-8"`.

## Evidence

Pendiente de implementación.
