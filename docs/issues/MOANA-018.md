# MOANA-018 — Implementar batches de edición atómica

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-018
- Aliases históricos: MOA-018
- Phase: P3
- Priority: P0
- Status: done
- Complexity: L (relativa, no estimación de tiempo)
- Dependencies: [MOANA-002](MOANA-002.md), [MOANA-010](MOANA-010.md), [MOANA-012](MOANA-012.md), [MOANA-013](MOANA-013.md)
- Related modules: editing, api
- Requirements: R016, R038 ([trazabilidad](traceability.md))
- Bloqueo: Ninguno

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

- [x] AC1: Recolor de body_fill modifica únicamente su referencia y la revisión preservando toda otra estructura
- [x] AC2: Un segundo comando inválido revierte también el primero; se devuelve EditConflict para base vieja

## Required tests

- [x] T1: Cada comando con caso válido/negativo, reorder al principio y dependencias vivas
- [x] T2: Comparar documento original byte a byte, render antes/después y batch sin cambio visual
- [x] T3: Dos ramas con revision=1 y contenidos distintos rechazan el batch de la otra rama mediante base_snapshot.

## Expected deliverables

- Modelos de batch y aplicación transaccional que verifica revisión y snapshot base.
- Pruebas de rollback, preservación de IDs y conflicto entre ramas con igual revisión.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- Tras undo pueden existir revisiones numéricas iguales en ramas distintas; verificar también identidad del snapshot.

## Guía para agentes de IA

**Estado para agentes:** Completado; usar sólo como referencia del contrato entregado.

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

- src/moana/editing/: batches atómicos con los ocho comandos de §15 (set_color, set_geometry, translate, set_visibility, replace_palette_color, insert_operation, remove, reorder) dirigidos por ID; EditBatch estricto (1–1024 comandos, MAX_EDIT_COMMANDS); los comandos se aplican sobre una copia normalizada y el resultado se revalida entero (DAG de máscaras, límites, perfil) antes de construir nada; el documento fuente nunca cambia.
- Revisión optimista: base_revision y base_snapshot identifican conjuntamente la base; una revisión distinta (stale_revision) o un snapshot distinto (snapshot_mismatch) dan EditConflict (EDIT_CONFLICT, salida 4); revision_overflow se comprueba antes de aplicar.
- Reglas por tipo leídas de la tabla moana.schema.OPERATION_MEMBERS/MASK_MEMBERS (ADR-025): remove rechaza referencias vivas (live_reference), set_color exige un único miembro de color (multiple_colors en dither), translate/set_geometry rechazan tipos sin geometría (not_geometric), insert valida todos los colores; un ID borrado no se reinserta en el mismo batch (reused_id); capas bloqueadas rechazadas salvo replace_palette_color, que no pertenece a ninguna capa.
- Fachada: moana.api.apply_edit, edit_document y load_edit_batch (lectura acotada del batch); comando moana edit DOC BATCH que imprime revisión, snapshot, IDs afectados y el documento sin escribir archivos; capabilities con edit_commands y sin funciones ni comandos previstos.
- affected_ids lista objetivos, insertados y eliminados; la caja de diferencia y las dependencias indirectas quedan para el manifiesto de historial de MOANA-020 (project), según §15 y ADR-024.
- ADR-024 (docs/architecture/decisions/ADR-024-atomic-edits.md) con notas de cabecera en ADR-011, ADR-020 y ADR-025; MOANA.md 0.1.13-draft (§13, §15); contratos de módulos, índice de ADR, overview, README, guía de desarrollo, AGENTS.md y CLAUDE.md actualizados; scripts/check_wheel.py ejecuta moana edit con el wheel instalado.
- Trazabilidad: R016 cubierto; R038 cubierto en edición (render, preview y edición desde API/CLI); la persistencia queda para MOANA-020. La evidencia de MOANA-012 que citaba el comando edit previsto queda sustituida por tests/unit/cli/test_cli_edit.py.
- Gate: scripts/validate.py (1698 passed, src/moana al 100 % de líneas y ramas) y scripts/check_wheel.py verdes; mypy también con --platform win32; generate_schema --check al día. Sin ejecución en Windows real (matriz pendiente en main).
- Revisión: moana-architect (cambios requeridos, aplicados: tabla de miembros por tipo compatible con dither, imports privados de schema listados y fijados, documentos de estado, capas bloqueadas y paleta, aplazamiento de bbox a MOANA-020), moana-python-engineer (aprobado; bajos aplicados: robustez con model_construct, tablas inmutables, dispatch tipado, mensajes de batch) y moana-qa-engineer (aprobado con cambios; aplicados: reinserción de IDs, coste de translate en paths, máscaras path/regiones, casos no-op y fuera de lienzo, rollback en la validación final, oráculo mínimo en Hypothesis, CLI sin escritura de archivos).
- Aprobado por el propietario el 2026-11-17 tras revisión; PR #55 hacia develop.
- AC1: tests/unit/editing/test_editing_apply.py::test_ac1_recolor_changes_only_its_reference_and_the_revision (diff campo a campo: sólo /revision y /layers/0/operations/0/color), ::test_ac1_ids_order_and_untouched_members_are_preserved y ::test_no_op_and_off_canvas_batches_still_bump_the_revision.
- AC2: tests/unit/editing/test_editing_apply.py::test_ac2_an_invalid_second_command_rolls_back_the_first, ::test_a_failure_in_the_final_validation_rolls_everything_back, ::test_property_failing_batch_is_all_or_nothing, ::test_ac2_stale_revision_is_an_edit_conflict, ::test_ac2_a_previous_revision_cannot_be_reused_after_an_edit y ::test_revision_overflow_is_rejected_before_any_command; tests/unit/cli/test_cli_edit.py (conflicto con salida 4).
- T1: tests/unit/editing/test_editing_apply.py: casos válidos y negativos de cada comando (test_t1_*), reorder al principio (test_t1_reorder_to_the_start_and_after_a_sibling), dependencias vivas (test_t1_remove_rejects_live_references, test_t1_reorder_keeps_references_alive), ::test_removed_id_cannot_be_reinserted_in_the_same_batch y ::test_property_matches_a_minimal_oracle; tests/unit/editing/test_editing_dither.py (remove con referencias vivas, multiple_colors, not_geometric, insert y reorder de dither); tests/unit/editing/test_editing_members.py::test_every_geometric_member_has_a_translate_shape.
- T2: tests/unit/editing/test_editing_apply.py::test_t2_source_document_is_byte_identical_after_success_and_failure, ::test_t2_render_before_and_after_a_recolor y ::test_t2_batch_without_visual_change_keeps_the_visual_digest; tests/unit/cli/test_cli_edit.py::test_edit_writes_no_files; tests/integration/test_cli_paths.py::test_cli_edit_in_a_fresh_process.
- T3: tests/unit/editing/test_editing_apply.py::test_t3_branches_with_the_same_revision_reject_each_other (dos ramas con revision=1 se rechazan mutuamente con snapshot_mismatch y cada batch se acepta en su rama).
