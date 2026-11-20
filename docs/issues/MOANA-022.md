# MOANA-022 — Implementar timeline y evaluación de frames

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-022
- Aliases históricos: MOA-022
- Phase: P4
- Priority: P1
- Status: done
- Complexity: L (relativa, no estimación de tiempo)
- Dependencies: [MOANA-018](MOANA-018.md), [MOANA-019](MOANA-019.md), [MOANA-010](MOANA-010.md)
- Related modules: animation, schema
- Requirements: R020 ([trazabilidad](traceability.md))
- Bloqueo: Ninguno

## Context

Evaluar frames incrementalmente introduce dependencia del orden y deriva temporal.

## Objective

Evaluar cada frame contra la misma base con tiempos/pivotes verificables.

## Scope

Crear animaciones con duración, loops, pivote común y overrides evaluados siempre contra la base.

## Out of scope

No tweening implícito, rigging ni interpolación aprendida.

## Technical requirements

- Validar IDs y presupuestos acumulados antes de export; frames no heredan cambios del anterior
- Estabilidad de semilla por defecto y variación temporal sólo explícita

## Proposed implementation

- Definir timeline y overrides limitados sin revision persistente
- Presupuestar todos los frames y evaluar cada uno independientemente

## Acceptance criteria

- [x] AC1: Cambiar el orden de evaluación de frames no cambia ninguno de sus resultados
- [x] AC2: Duraciones y pivotes se preservan y un override inválido impide el render parcial de la solicitud

## Required tests

- [x] T1: Frame único, 256 frames, límite de duración/área y loops
- [x] T2: Overrides de geometría/color/visibilidad y textura estable entre frames

## Expected deliverables

- Timeline con evaluación de frames/overrides y reglas de duración/composición.
- Fixtures de límites temporales, estabilidad de IDs y determinismo por frame.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- Un bucle infinito de playback no autoriza un render infinito; exportar secuencia finita.

## Guía para agentes de IA

**Estado para agentes:** Completado; usar sólo como referencia del contrato entregado.

### 1. Preparación

- Rama: `feat/MOANA-022-implementar-timeline-evaluacion` creada desde `develop` actualizado: `git switch develop && git pull --ff-only && git switch -c feat/MOANA-022-implementar-timeline-evaluacion`.
- Verificar en `docs/issues/catalog.json` que este issue está `ready` y que sus dependencias ([MOANA-018](MOANA-018.md), [MOANA-019](MOANA-019.md), [MOANA-010](MOANA-010.md)) están `done`.
- Entorno: `uv sync --locked` (sin uv global: `sh scripts/bootstrap.sh` y después `sh scripts/uv.sh` en lugar de `uv`).
- Al empezar, cambiar `status` a `in_progress` en el catálogo y regenerar con `uv run python scripts/planning.py`.

### 2. Lectura obligatoria (en orden)

1. `CLAUDE.md` (Claude Code) o `AGENTS.md` (Codex) y [flujo de sesión](../guides/agent-workflow.md).
2. MOANA.md: §3 Arquitectura modular; §17 Animaciones y spritesheets; §25 Definition of Done. Estas secciones son el contrato normativo; ante duda, prevalecen sobre este issue.
3. [Contratos de módulos](../architecture/module-contracts.md) para: `animation`, `schema`.
4. Estándares: [python](../../docs/standards/python.md), [architecture](../../docs/standards/architecture.md), [testing](../../docs/standards/testing.md), [pixel-art](../../docs/standards/pixel-art.md), [security](../../docs/standards/security.md).
5. Issues de dependencia ([MOANA-018](MOANA-018.md), [MOANA-019](MOANA-019.md), [MOANA-010](MOANA-010.md)): leer su sección Evidence para conocer las APIs ya entregadas; no reimplementarlas.
6. ADR en `docs/architecture/` que mencionen los módulos afectados.

### 3. Requisitos de MOANA.md cubiertos

| ID | Requisito | Secciones | Verificación exigida |
| --- | --- | --- | --- |
| R020 | Animaciones, duraciones y pivotes | §17 | Evaluación independiente y continuidad temporal |

### 4. Skills y subagentes

| Host | Skills a cargar | Revisión especializada |
| --- | --- | --- |
| Claude Code | `moana-graphics`, `moana-pixel-art`, `moana-python`, `moana-architecture`, `moana-code-review` | `moana-graphics-engineer`, `moana-pixel-artist`, `moana-python-engineer`, `moana-architect` (sólo lectura; el agente principal integra) |
| Codex | `$moana-graphics`, `$moana-pixel-art`, `$moana-python`, `$moana-architecture`, `$moana-code-review` | `moana_graphics_engineer`, `moana_pixel_artist`, `moana_python_engineer`, `moana_architect` |

### 5. Archivos

- Código o documentos a crear/modificar: `src/moana/animation/`, `src/moana/schema/`.
- Pruebas: `tests/unit/animation/`, `tests/unit/schema/`.
- No crear módulos ni carpetas sin comportamiento real. No tocar otros módulos salvo exportaciones imprescindibles, justificadas en el PR.

### 6. Plan de pruebas

- T1: Frame único, 256 frames, límite de duración/área y loops
- T2: Overrides de geometría/color/visibilidad y textura estable entre frames
- Oráculos independientes (cálculo a mano o fórmula de MOANA.md); nunca copiar la salida de la implementación como expected.
- Incluir casos negativos con el error de dominio esperado y casos borde (vacío, mínimo, máximo, fuera de rango).

### 7. Procedimiento

1. Escribir las pruebas de los criterios AC y T antes o junto con la implementación.
2. Implementar sólo **Scope**; respetar **Out of scope** y las dependencias permitidas de MOANA.md §3.
3. Validación de módulo: `uv run pytest tests/unit/animation/ tests/unit/schema/ -q` y `uv run mypy src/`.
4. Validación completa: `uv run python scripts/validate.py` y `uv run python scripts/check_wheel.py`.
5. Revisión: subagentes listados y skill `moana-code-review`; corregir hallazgos críticos y altos.
6. Si hay salida raster: mostrar el PNG a 1x y ampliado por vecino más cercano; si cambia un golden, presentar expected/actual/diff y justificar.

### 8. Cierre

1. En `docs/issues/catalog.json`, para este issue: `status` → `review` (o `done` tras aprobación); completar `acceptance_evidence` (AC1, AC2), `test_evidence` (T1, T2) y `evidence` con rutas concretas de tests y archivos.
2. Issues que desbloquea ([MOANA-023](MOANA-023.md), [MOANA-024](MOANA-024.md), [MOANA-025](MOANA-025.md), [MOANA-026](MOANA-026.md), [MOANA-027](MOANA-027.md), [MOANA-030](MOANA-030.md), [MOANA-031](MOANA-031.md), [MOANA-036](MOANA-036.md)): si todas sus dependencias quedan `done`, pasarlos a `ready` con `blocking_reason: null`.
3. Ejecutar `uv run python scripts/planning.py` y `uv run python -m scripts.check_repository`.
4. Abrir PR hacia `develop` enlazando este issue de GitHub (`Closes #<número>`), con comandos ejecutados y evidencia por AC/T. El CI completo corre al integrar `develop` en `main`.
5. Commit y push sólo con autorización del usuario. No declarar CI remoto ni aprobación artística humana sin evidencia.

### 9. Prohibido en este issue

- Implementar alcance de otros issues, incluidos los que desbloquea ([MOANA-023](MOANA-023.md), [MOANA-024](MOANA-024.md), [MOANA-025](MOANA-025.md), [MOANA-026](MOANA-026.md), [MOANA-027](MOANA-027.md), [MOANA-030](MOANA-030.md), [MOANA-031](MOANA-031.md), [MOANA-036](MOANA-036.md)).
- Actualizar goldens automáticamente, desactivar checks, editar `uv.lock` a mano o añadir dependencias sin motivo técnico registrado.
- `eval`/`exec`/`pickle`, red o estado global mutable en el núcleo; lecturas de texto sin `encoding="utf-8"`.

## Evidence

- Colección `animations` soportada en schema 1.0 (excepción previa a la publicación, ADR-032; DOCUMENT_MIGRATIONS de ADR-031 sigue sin pasos): Animation {id, loop_count 0–65535, pivot entero dentro del lienzo con bordes, frames 1–256}, Frame {id, duration_ms 1–60000, overrides ≤1024}; IDs de animación y frame globales; overrides set_visibility/translate/set_color con la forma exacta del comando de edición; límites nuevos en moana.core.limits (MAX_ANIMATIONS=64, MAX_ANIMATION_FRAMES=256, MAX_FRAME_DURATION_MS, MAX_FRAME_OVERRIDES, MAX_LOOP_COUNT).
- Cada frame se evalúa siempre contra la base (nunca contra el anterior) con moana.editing.apply_commands, que sólo acepta los tres overrides (TypeError para el resto), aplica las reglas del editor (locked_layer, not_geometric, out_of_range, invalid_result) y no crea revisión; un frame sin overrides es la base estática; semilla, revisión e IDs de la base.
- Render en streaming con presupuesto acumulado: moana.render.plan_frame/admit_sequence/render_admitted/render_sequence; pasada 1 evalúa TODOS los frames (un override inválido en cualquiera impide render parcial) y guarda sólo CostEstimate; admisión de Σ visitas, Σ píxeles de frame y pico + RGBA retenido + RESULT_OVERHEAD_BYTES antes del primer buffer; pasada 2 reevalúa y renderiza frame a frame. render no importa editing.
- Peor caso medido (256 frames × 2000 operaciones): RSS 693 MB → 129 MiB, pico tracemalloc 266,7 MiB → 68,7 MiB; render_frame 3,2 s y 54 MiB. Deadline comprobado antes de cada validación y frame; el coste de CPU de validar no entra en pixel_visits (documentado en ADR-032 con la recomendación de pasar Deadline).
- El editor conoce las animaciones: remove de un destino animado o de un color usado por set_color es live_reference; un ID nuevo que choque con animación o frame es duplicate_id; persistencia (directorio, .moana, .moana.json), migrate_project e History funcionan con documentos animados.
- moana.animation: evaluate_frame, evaluate_animation, render_animation, render_frame con duración, inicio y pivote por frame; loop_count es sólo dato (cada frame se renderiza una vez). moana.api.render(frame_id=…) renderiza un frame (§13); moana.render.render(frame_id) sigue dibujando sólo la base (frame_not_evaluated). Sin CLI, GIF ni spritesheet.
- Limitación documentada: mover un sprite texturizado (material/dither) en un frame desliza la textura respecto del sprite porque no hay override de origin en el MVP (ADR-032 §4, MOANA.md §17; seguimiento: override acotado de origin).
- Ejemplo examples/specs/bouncing-slime.moana.json (16×16, rest/rise/apex/fall 150/100/120/100 ms, pivote [8,16]) con squash/stretch por capas alternadas con set_visibility, espaciado físico y sombra que se encoge con la altura, según la revisión de pixel-art; revisión artística humana PENDIENTE.
- Revisiones de agente: arquitectura, gráficos, python/QA y pixel-art con correcciones aplicadas. Gate local macOS: scripts/validate.py 2732 passed con src/moana al 100 %, check_wheel OK, mypy --platform win32 OK, JSON Schema al día, pre-commit OK; matriz pendiente en main.
- Aprobado por el propietario el 2026-11-17 tras revisión; PR #62 hacia develop.
- AC1: tests/unit/animation/test_animation_frames.py::test_ac1_any_evaluation_order_gives_the_same_bytes_per_frame, ::test_ac1_frames_never_inherit_the_previous_frame, ::test_ac1_one_frame_alone_equals_the_same_frame_in_a_sequence, ::test_ac1_evaluating_does_not_touch_the_base
- AC2: tests/unit/animation/test_animation_frames.py::test_ac2_durations_pivots_and_offsets_are_preserved, ::test_ac2_provenance_names_the_frame_and_keeps_the_revision, ::test_ac2_an_invalid_override_in_any_frame_renders_nothing, ::test_ac2_an_override_whose_result_is_invalid_renders_nothing, ::test_ac2_budget_of_the_whole_request_is_checked_before_any_frame; tests/unit/render/test_render_sequence.py::test_ac2_a_frame_over_budget_alone_names_its_index_and_renders_nothing
- T1: tests/unit/animation/test_animation_frames.py::test_t1_single_frame_animation, ::test_t1_256_frames_render_each_frame_once, ::test_t1_256_frames_at_exactly_16777216_accumulated_pixels, ::test_t1_accumulated_frame_pixels_limit_is_inclusive, ::test_t1_default_budget_rejects_a_sequence_over_16777216_frame_pixels, ::test_t1_loop_count_never_multiplies_the_render, ::test_t1_deadline_is_checked_before_every_validation_and_frame, ::test_t1_a_short_deadline_fails_near_its_limit; tests/unit/animation/test_animation_memory.py::test_t1_render_frame_holds_one_frame_document, ::test_t1_selected_frames_do_not_keep_the_unrequested_ones, ::test_t1_rendering_every_frame_stays_within_the_admitted_bytes; tests/unit/schema/test_schema_animations.py::test_t1_frame_count_is_one_to_256, ::test_t1_duration_is_a_whole_millisecond_count_1_to_60000, ::test_t1_longest_timeline_is_bounded, ::test_t1_loop_count_zero_is_infinite_playback, ::test_t1_pivot_lies_on_the_canvas_edges_included, ::test_t1_animation_and_override_counts_are_bounded; tests/unit/render/test_render_sequence.py::test_t1_accumulated_totals_are_checked_against_one_budget, ::test_t1_plan_frame_estimates_without_rendering, ::test_t1_render_admitted_renders_only_the_admitted_document
- T2: tests/unit/animation/test_animation_frames.py::test_t2_each_override_changes_only_its_target, ::test_t2_evaluated_frames_are_static_documents_with_stable_ids, ::test_t2_dither_phase_is_anchored_and_stable_between_frames, ::test_t2_material_texture_is_identical_in_every_frame, ::test_t2_moving_a_textured_sprite_slides_its_texture, ::test_t2_a_frame_without_overrides_does_not_call_the_editor; tests/unit/editing/test_editing_commands.py::test_t2_only_override_commands_are_accepted; tests/unit/editing/test_editing_animations.py::test_t2_removing_an_animated_node_or_colour_is_a_live_reference, ::test_t2_new_ids_cannot_reuse_animation_or_frame_ids; tests/unit/project/test_project_animations.py::test_t2_an_animated_document_survives_every_format, ::test_t2_history_edits_an_animated_document; tests/unit/schema/test_schema_animations.py::test_t2_override_references_must_exist, ::test_t2_animation_and_frame_ids_are_global
