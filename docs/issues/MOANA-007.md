# MOANA-007 — Añadir adaptador de paths AggDraw

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-007
- Aliases históricos: MOA-007
- Phase: P3
- Priority: P2
- Status: review
- Complexity: M (relativa, no estimación de tiempo)
- Dependencies: [MOANA-006](MOANA-006.md), [MOANA-010](MOANA-010.md), [MOANA-028](MOANA-028.md)
- Related modules: geometry, render
- Requirements: R004, R015 ([trazabilidad](traceability.md))
- Bloqueo: Ninguno

## Context

Curvas complementarias requieren backend explícito sin diluir el contrato entero.

## Objective

Añadir paths con cobertura binaria y garantía de compatibilidad limitada.

## Scope

Agregar path M/L/Q/C/Z con punto fijo, versión de backend y binarización de cobertura; mantener separado el perfil entero.

## Out of scope

No fuentes, SVG completo ni rasterización vectorial genérica.

## Technical requirements

- Umbral >=128 a resolución nativa; comandos limitados y sin SVG externo
- Registrar aggdraw-v1 y versiones en provenance; exponer capacidad real y estimación de trabajo

## Proposed implementation

- Definir el payload de comandos fijo 1/256 en schema junto al adaptador
- Validar segmentos, rasterizar con AggDraw y aplicar threshold/documentar provenance

## Acceptance criteria

- [ ] AC1: Paths cerrados producen únicamente máscara binaria y no introducen colores por AA
- [ ] AC2: Entradas desconocidas o excesivas fallan antes del adaptador; ausencia de capacidad da error explícito

## Required tests

- [ ] T1: Fixtures de curvas pequeñas, joins, cierres y curvas fuera de lienzo
- [ ] T2: Repetición con entorno fijado y comparación backend por plataforma sin prometer equivalencia al raster entero

## Expected deliverables

- Adaptador AggDraw para paths con política explícita de muestreo y cuantización.
- Fixtures de curvas y uniones; evaluación RGBA y de errores del adaptador.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- No asumir que AggDraw comparte píxeles entre versiones o plataformas no ensayadas.

## Guía para agentes de IA

**Estado para agentes:** En revisión: sólo correcciones de la revisión; no añadir alcance.

### 1. Preparación

- Rama: `feat/MOANA-007-anadir-adaptador-paths` creada desde `develop` actualizado: `git switch develop && git pull --ff-only && git switch -c feat/MOANA-007-anadir-adaptador-paths`.
- Verificar en `docs/issues/catalog.json` que este issue está `ready` y que sus dependencias ([MOANA-006](MOANA-006.md), [MOANA-010](MOANA-010.md), [MOANA-028](MOANA-028.md)) están `done`.
- Entorno: `uv sync --locked` (sin uv global: `sh scripts/bootstrap.sh` y después `sh scripts/uv.sh` en lugar de `uv`).
- Al empezar, cambiar `status` a `in_progress` en el catálogo y regenerar con `uv run python scripts/planning.py`.

### 2. Lectura obligatoria (en orden)

1. `CLAUDE.md` (Claude Code) o `AGENTS.md` (Codex) y [flujo de sesión](../guides/agent-workflow.md).
2. MOANA.md: §3 Arquitectura modular; §4 Stack tecnológico; §6 Geometría y primitivas; §14 Renderizado y determinismo; §25 Definition of Done. Estas secciones son el contrato normativo; ante duda, prevalecen sobre este issue.
3. [Contratos de módulos](../architecture/module-contracts.md) para: `geometry`, `render`.
4. Estándares: [python](../../docs/standards/python.md), [architecture](../../docs/standards/architecture.md), [testing](../../docs/standards/testing.md).
5. Issues de dependencia ([MOANA-006](MOANA-006.md), [MOANA-010](MOANA-010.md), [MOANA-028](MOANA-028.md)): leer su sección Evidence para conocer las APIs ya entregadas; no reimplementarlas.
6. ADR en `docs/architecture/` que mencionen los módulos afectados.

### 3. Requisitos de MOANA.md cubiertos

| ID | Requisito | Secciones | Verificación exigida |
| --- | --- | --- | --- |
| R004 | Geometría complementaria AggDraw | §4, §6 | Fixtures de paths y capabilities por backend |
| R015 | Renderizado determinista | §14 | Digests RGBA en procesos/OS y semillas distintas |

### 4. Skills y subagentes

| Host | Skills a cargar | Revisión especializada |
| --- | --- | --- |
| Claude Code | `moana-graphics`, `moana-architecture`, `moana-code-review` | `moana-graphics-engineer`, `moana-python-engineer`, `moana-architect` (sólo lectura; el agente principal integra) |
| Codex | `$moana-graphics`, `$moana-architecture`, `$moana-code-review` | `moana_graphics_engineer`, `moana_python_engineer`, `moana_architect` |

### 5. Archivos

- Código o documentos a crear/modificar: `src/moana/geometry/`, `src/moana/render/`.
- Pruebas: `tests/unit/geometry/`, `tests/unit/render/`.
- No crear módulos ni carpetas sin comportamiento real. No tocar otros módulos salvo exportaciones imprescindibles, justificadas en el PR.

### 6. Plan de pruebas

- T1: Fixtures de curvas pequeñas, joins, cierres y curvas fuera de lienzo
- T2: Repetición con entorno fijado y comparación backend por plataforma sin prometer equivalencia al raster entero
- Oráculos independientes (cálculo a mano o fórmula de MOANA.md); nunca copiar la salida de la implementación como expected.
- Incluir casos negativos con el error de dominio esperado y casos borde (vacío, mínimo, máximo, fuera de rango).

### 7. Procedimiento

1. Escribir las pruebas de los criterios AC y T antes o junto con la implementación.
2. Implementar sólo **Scope**; respetar **Out of scope** y las dependencias permitidas de MOANA.md §3.
3. Validación de módulo: `uv run pytest tests/unit/geometry/ tests/unit/render/ -q` y `uv run mypy src/`.
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

- src/moana/core/vector_path.py: gramática M/L/Q/C/Z en punto fijo 1/256 (2–4096 comandos, |v| ≤ 2^28, empieza por M, sin subpaths vacíos, sólo M tras Z), aplanado entero de Bernstein con tolerancia 1/16 px y 1–64 segmentos por curva (≤ 65 536 segmentos), FixedPath/PathCommand autovalidados, fórmulas compartidas de buffer, celdas y memoria; stdlib puro reutilizado por schema, render.budget y geometry.
- src/moana/geometry/paths.py: adaptador AggDraw con import perezoso y superficie tipada; regla nonzero con acumulación por winding, cierre implícito, cobertura ≥128 a escala nativa cortada a la caja de los puntos de control y buffer recortado al lienzo antes de reservar; devuelve una Mask binaria sin objetos AggDraw/Pillow; backend ausente, roto, incompatible o con versión fuera de TESTED_AGGDRAW_VERSIONS (1.4.1) → UNSUPPORTED_OPERATION backend_unavailable con un único constructor; fallos del backend → error de dominio.
- src/moana/schema/: operación path y hoja de máscara path (backend aggdraw-v1) en el documento 1.0 como ampliación previa a la publicación; errores de gramática con puntero al comando; cada modelo parsea sus comandos una vez; capabilities().backends y path como capacidad de ejecución (prevista si el backend no está disponible, sin desaparecer).
- src/moana/render/: budget-v4 (idéntico a budget-v3 sin paths; por path, visitas, celdas acotadas por MAX_PATH_CELLS = 2 097 152, límite del motor que host_override no sube porque AGG descarta celdas por encima de 4 194 304, y 128 KiB de memoria nativa de AGG); provenance vector_backend/vector_backend_versions en todos los renders; comprobación del backend antes del presupuesto.
- Garantía limitada (ADR-023 §4): un píxel cuyo cuadrado queda dentro de un único subpath simple pertenece a la máscara; el engorde de ~1/4 px de AGG, los picos en ángulos agudos y la acumulación por winding quedan caracterizados con los contraejemplos A–D, sin equivalencia prometida con el raster entero ni entre plataformas no ensayadas.
- ADR-023 (docs/architecture/decisions/ADR-023-aggdraw-paths.md) con notas de cabecera en ADR-005, ADR-011, ADR-015, ADR-018, ADR-020 y ADR-022; MOANA.md 0.1.10-draft (§6, §12, §13, §14, §20); ejemplo examples/specs/path-sail.moana.json; contratos de módulos, índice de ADR, overview, README, guía de desarrollo, AGENTS.md y CLAUDE.md actualizados.
- Trazabilidad: R004 cubierto; R015 cubierto para aggdraw-v1 sólo en procesos locales (matriz pendiente en main).
- Gate: scripts/validate.py (1414 passed, src/moana al 100 % de líneas y ramas) y scripts/check_wheel.py verdes; mypy también con --platform win32; generate_schema --check al día. Sin ejecución en Linux ni Windows reales.
- Revisión: moana-graphics-engineer (cambios requeridos, aplicados: garantías de ADR-023 §4 corregidas con contraejemplos, corte no local por caja, memoria nativa de AGG en el presupuesto, oráculo independiente del error de cuerda), moana-architect (cambios requeridos, aplicados: contrato de provenance y de capacidad de ejecución, path_cells informado en inspect, evidencia T2 parcial, constante de backend probada) y moana-python-engineer (cambios requeridos, aplicados: parseo único por modelo, FixedPath autovalidado, punteros por comando, constructor único de backend_unavailable, carga robusta de aggdraw, versión de Pillow por metadatos, timeouts en subprocess).
- AC1: tests/unit/geometry/test_geometry_paths.py::test_ac1_paths_give_binary_masks_inside_their_box, ::test_integer_rectangles_equal_the_integer_rect_mask, ::test_polygon_paths_agree_with_the_integer_polygon_where_guaranteed, ::test_curves_stay_within_the_hull_of_their_control_points, ::test_fill_rule_is_nonzero_winding, ::test_the_box_cut_is_not_local, ::test_result_is_a_moana_mask_without_backend_objects; tests/unit/render/test_render_paths.py::test_ac1_render_has_only_palette_colours_inside_the_path_boxes y ::test_ac1_rgba_profile_keeps_binary_coverage; tests/unit/api/test_api_paths.py::test_example_with_paths_loads_inspects_and_renders.
- AC2: tests/unit/core/test_core_vector_path.py::test_invalid_commands_raise_located_validation_errors, ::test_fixed_paths_validate_themselves; tests/unit/schema/test_schema_paths.py::test_invalid_path_payloads_are_located_validation_errors y ::test_order_errors_carry_the_command_index; tests/unit/render/test_render_paths.py::test_ac2_unvalidated_models_fail_validation_before_the_adapter, ::test_ac2_missing_backend_fails_before_budget_and_raster, ::test_ac2_untested_version_names_the_version_and_the_mask_leaf y ::test_renderer_and_adapter_report_the_same_backend_error; tests/unit/geometry/test_geometry_paths.py::test_missing_backend_is_an_explicit_unsupported_operation, ::test_a_backend_without_the_used_api_is_incompatible; tests/unit/api/test_api_paths.py::test_capabilities_move_path_to_planned_without_the_backend y ::test_cli_render_without_backend_is_unsupported_operation.
- T1: tests/unit/geometry/test_geometry_paths.py::test_convex_and_join_fixtures_lie_between_the_geometric_oracles, ::test_explicit_and_implicit_close_fill_the_same_pixels, ::test_partly_off_canvas_paths_are_clipped_without_wraparound, ::test_degenerate_paths_of_zero_area_draw_nothing, ::test_far_away_coordinates_cost_nothing_and_still_clip, ::test_case_a_one_pixel_wall_between_two_holes_is_out, ::test_case_b_winding_minus_one_strip_through_a_shared_vertex_is_out, ::test_case_c_stacked_slivers_let_in_a_pixel_far_from_the_outline, ::test_case_d_four_stacked_eighth_pixel_strips_fill_two_rows; tests/unit/core/test_core_vector_path.py::test_chosen_steps_bound_the_chord_error; tests/unit/render/test_render_paths.py::test_budget_v4_hand_oracle_for_a_square_path, ::test_plan_budget_admission_means_render_succeeds_with_paths y ::test_path_cells_over_the_engine_limit_are_rejected_by_the_plan.
- T2: tests/integration/test_path_determinism.py::test_t2_fresh_processes_with_any_hash_seed_agree (procesos nuevos con PYTHONHASHSEED 0/1/4242/aleatorio y dos serializaciones) y ::test_t2_integer_rectangles_agree_with_the_integer_backend_on_any_platform; tests/unit/geometry/test_geometry_paths.py::test_repeated_rasterisation_is_identical. Entre plataformas: local macOS; matriz pendiente en main, sin equivalencia prometida con el raster entero.
