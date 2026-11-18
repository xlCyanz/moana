# MOANA-019 — Añadir undo/redo e historial inmutable

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-019
- Aliases históricos: MOA-019
- Phase: P3
- Priority: P1
- Status: review
- Complexity: L (relativa, no estimación de tiempo)
- Dependencies: [MOANA-018](MOANA-018.md)
- Related modules: editing
- Requirements: R017 ([trazabilidad](traceability.md))
- Bloqueo: Ninguno

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

**Estado para agentes:** En revisión: sólo correcciones de la revisión; no añadir alcance.

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

- src/moana/editing/history.py: History inmutable (frozen) con start, edit, undo, redo, checkout, snapshot, children_of, leaves, can_undo, can_redo, current y document; cada Snapshot guarda documento, digest, padre, batch canónico, affected_ids, revisión y tamaño en bytes de JSON canónico; las ramas se identifican por digest, nunca por número de revisión.
- Undo/redo mueven el cursor sin crear revisiones; editar tras undo crea una rama y sustituye sólo el redo activo de ese padre; las ramas antiguas siguen accesibles con checkout (sin revisión nueva); un batch fallido no añade nada ni mueve el cursor.
- Presupuesto: MAX_HISTORY_SNAPSHOTS=1024 y MAX_HISTORY_BYTES=32 MiB de JSON canónico, comprobados antes de añadir; es una medida determinista proporcional, no una cota de RAM (factor trazado ~10–17×, fijado por un test slow con tracemalloc, k=24). HistoryLimits sólo puede bajar los máximos.
- Convergencia: el mismo edit tras undo reutiliza el snapshot guardado (conserva el primer batch y affected_ids); un digest alcanzado desde otro padre da EditConflict (existing_snapshot, salida 4), reintentable con checkout; la alternativa queda anotada como riesgo de MOANA-020.
- El constructor de History valida y congela un historial hecho a mano (ValidationError reason invalid_history; BudgetExceeded sobre límites), base de la reconstrucción desde persistencia en MOANA-020; los métodos usan un constructor interno sin revalidación.
- ADR-026 (docs/architecture/decisions/ADR-026-edit-history.md) con nota de cabecera en ADR-024; MOANA.md 0.1.14-draft (§15); contratos de módulos, índice de ADR, overview, README, AGENTS.md y CLAUDE.md actualizados. Sin cambios en api, cli, schema ni capabilities: la persistencia y su exposición quedan para MOANA-020.
- Gate: scripts/validate.py (1750 passed, src/moana al 100 % de líneas y ramas) y scripts/check_wheel.py verdes; mypy también con --platform win32; generate_schema --check al día. Evidencia de plataforma: local macOS; matriz pendiente en main.
- Revisión: moana-architect (cambios requeridos, aplicados: presupuesto de bytes rebajado y documentado como medida no-RAM, existing_snapshot como EditConflict, constructor validado, hash coherente, parse_limits) y moana-qa-engineer/python (cambios requeridos, aplicados: test de memoria trazada, propiedades Hypothesis con checkout e invariantes de árbol, reutilización con otro batch, casos de límite exactos, equivalencia de canonical_batch).
- AC1: tests/unit/editing/test_editing_history.py::test_ac1_undo_and_redo_restore_document_and_rgba (documento y RGBA idénticos tras undo/redo) y ::test_ac1_oracles_are_consistent_with_the_fixture.
- AC2: tests/unit/editing/test_editing_history.py::test_ac2_edit_after_undo_replaces_only_the_active_redo y ::test_ac2_undo_of_an_old_branch_reactivates_its_redo; propiedades ::test_property_history_matches_a_list_and_cursor_model y ::test_property_history_with_checkouts_matches_a_path_tree.
- T1: tests/unit/editing/test_editing_history.py::test_t1_sequences_and_navigation_limits[1], [10] y [100]; ::test_t1_snapshot_records_parent_batch_revision_and_size.
- T2: tests/unit/editing/test_editing_history.py::test_t2_failed_batch_adds_nothing_and_keeps_the_cursor, ::test_t2_branches_with_the_same_revision_have_distinct_digests, ::test_t2_checkout_creates_no_revision, ::test_t2_checkout_of_an_unknown_digest_is_a_reference_error, ::test_t2_snapshot_budget_rejects_before_adding, ::test_t2_byte_budget_rejects_before_adding, ::test_t2_exact_byte_budget_accepts_and_one_byte_less_rejects, ::test_t2_a_single_snapshot_budget_rejects_every_edit, ::test_t2_traced_memory_is_proportional_to_total_bytes (slow), ::test_t2_same_edit_after_undo_reuses_the_stored_snapshot, ::test_t2_reuse_keeps_the_first_batch_and_affected_ids, ::test_t2_a_digest_reached_from_another_parent_is_rejected, ::test_t2_hand_built_history_is_validated, ::test_t2_hand_built_history_rejects_corruption (18 casos), ::test_t2_hand_built_history_types_and_budget, ::test_canonical_batch_uses_the_canonical_document_encoding, ::test_t2_history_limits_can_only_be_lowered, ::test_t2_defaults_and_argument_types y ::test_t2_history_values_are_frozen.
