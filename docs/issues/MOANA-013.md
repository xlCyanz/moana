# MOANA-013 — Añadir máscaras y regiones semánticas

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-013
- Aliases históricos: MOA-013
- Phase: P3
- Priority: P1
- Status: review
- Complexity: L (relativa, no estimación de tiempo)
- Dependencies: [MOANA-009](MOANA-009.md), [MOANA-010](MOANA-010.md)
- Related modules: layers, schema
- Requirements: R012 ([trazabilidad](traceability.md))
- Bloqueo: Ninguno

## Context

La edición por región necesita identidad semántica independiente del PNG.

## Objective

Resolver máscaras DAG y regiones estables para clipping y targeting.

## Scope

Implementar nodos de máscaras binarias y union/intersect/subtract/xor; asociar regiones semánticas a IDs y geometría.

## Out of scope

No inferencia automática de regiones desde un PNG.

## Technical requirements

- Resolver referencias en DAG sin depender del color raster de capas
- Máscaras en coordenadas de canvas; bbox y caché potencial dependen de los nodos fuente

## Proposed implementation

- Definir modelos de máscaras/regiones y booleanas con coordenadas de canvas
- Resolver dependencias antes de render y aplicar clipping al destino

## Acceptance criteria

- [ ] AC1: Una operación enmascarada no modifica píxeles fuera de su máscara
- [ ] AC2: Regiones permiten resolver ojo izquierdo por ID; ciclos y referencias rotas se rechazan antes de render

## Required tests

- [ ] T1: Álgebra de conjuntos en fixtures 1/8/128 píxeles y máscaras vacías
- [ ] T2: Ciclos directos/indirectos, máscara fuera del canvas y grupos transformados

## Expected deliverables

- Modelos y resolución de máscaras/regiones semánticas por IDs estables.
- Fixtures de referencias, ciclos, clipping y selección de una región editable.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- Un grupo transformado requiere semántica clara de máscara en canvas frente a geometría local.

## Guía para agentes de IA

**Estado para agentes:** En revisión: sólo correcciones de la revisión; no añadir alcance.

### 1. Preparación

- Rama: `feat/MOANA-013-anadir-mascaras-regiones` creada desde `develop` actualizado: `git switch develop && git pull --ff-only && git switch -c feat/MOANA-013-anadir-mascaras-regiones`.
- Verificar en `docs/issues/catalog.json` que este issue está `ready` y que sus dependencias ([MOANA-009](MOANA-009.md), [MOANA-010](MOANA-010.md)) están `done`.
- Entorno: `uv sync --locked` (sin uv global: `sh scripts/bootstrap.sh` y después `sh scripts/uv.sh` en lugar de `uv`).
- Al empezar, cambiar `status` a `in_progress` en el catálogo y regenerar con `uv run python scripts/planning.py`.

### 2. Lectura obligatoria (en orden)

1. `CLAUDE.md` (Claude Code) o `AGENTS.md` (Codex) y [flujo de sesión](../guides/agent-workflow.md).
2. MOANA.md: §3 Arquitectura modular; §11 Capas, máscaras y regiones; §25 Definition of Done. Estas secciones son el contrato normativo; ante duda, prevalecen sobre este issue.
3. [Contratos de módulos](../architecture/module-contracts.md) para: `layers`, `schema`.
4. Estándares: [python](../../docs/standards/python.md), [architecture](../../docs/standards/architecture.md), [testing](../../docs/standards/testing.md), [security](../../docs/standards/security.md).
5. Issues de dependencia ([MOANA-009](MOANA-009.md), [MOANA-010](MOANA-010.md)): leer su sección Evidence para conocer las APIs ya entregadas; no reimplementarlas.
6. ADR en `docs/architecture/` que mencionen los módulos afectados.

### 3. Requisitos de MOANA.md cubiertos

| ID | Requisito | Secciones | Verificación exigida |
| --- | --- | --- | --- |
| R012 | Máscaras y regiones semánticas | §11 | DAG, álgebra de máscaras y targeting por ID |

### 4. Skills y subagentes

| Host | Skills a cargar | Revisión especializada |
| --- | --- | --- |
| Claude Code | `moana-graphics`, `moana-python`, `moana-architecture`, `moana-code-review` | `moana-graphics-engineer`, `moana-architect`, `moana-python-engineer` (sólo lectura; el agente principal integra) |
| Codex | `$moana-graphics`, `$moana-python`, `$moana-architecture`, `$moana-code-review` | `moana_graphics_engineer`, `moana_architect`, `moana_python_engineer` |

### 5. Archivos

- Código o documentos a crear/modificar: `src/moana/layers/`, `src/moana/schema/`.
- Pruebas: `tests/unit/layers/`, `tests/unit/schema/`.
- No crear módulos ni carpetas sin comportamiento real. No tocar otros módulos salvo exportaciones imprescindibles, justificadas en el PR.

### 6. Plan de pruebas

- T1: Álgebra de conjuntos en fixtures 1/8/128 píxeles y máscaras vacías
- T2: Ciclos directos/indirectos, máscara fuera del canvas y grupos transformados
- Oráculos independientes (cálculo a mano o fórmula de MOANA.md); nunca copiar la salida de la implementación como expected.
- Incluir casos negativos con el error de dominio esperado y casos borde (vacío, mínimo, máximo, fuera de rango).

### 7. Procedimiento

1. Escribir las pruebas de los criterios AC y T antes o junto con la implementación.
2. Implementar sólo **Scope**; respetar **Out of scope** y las dependencias permitidas de MOANA.md §3.
3. Validación de módulo: `uv run pytest tests/unit/layers/ tests/unit/schema/ -q` y `uv run mypy src/`.
4. Validación completa: `uv run python scripts/validate.py` y `uv run python scripts/check_wheel.py`.
5. Revisión: subagentes listados y skill `moana-code-review`; corregir hallazgos críticos y altos.
6. Si hay salida raster: mostrar el PNG a 1x y ampliado por vecino más cercano; si cambia un golden, presentar expected/actual/diff y justificar.

### 8. Cierre

1. En `docs/issues/catalog.json`, para este issue: `status` → `review` (o `done` tras aprobación); completar `acceptance_evidence` (AC1, AC2), `test_evidence` (T1, T2) y `evidence` con rutas concretas de tests y archivos.
2. Issues que desbloquea ([MOANA-014](MOANA-014.md), [MOANA-015](MOANA-015.md), [MOANA-016](MOANA-016.md), [MOANA-018](MOANA-018.md)): si todas sus dependencias quedan `done`, pasarlos a `ready` con `blocking_reason: null`.
3. Ejecutar `uv run python scripts/planning.py` y `uv run python -m scripts.check_repository`.
4. Abrir PR hacia `develop` enlazando este issue de GitHub (`Closes #<número>`), con comandos ejecutados y evidencia por AC/T. El CI completo corre al integrar `develop` en `main`.
5. Commit y push sólo con autorización del usuario. No declarar CI remoto ni aprobación artística humana sin evidencia.

### 9. Prohibido en este issue

- Implementar alcance de otros issues, incluidos los que desbloquea ([MOANA-014](MOANA-014.md), [MOANA-015](MOANA-015.md), [MOANA-016](MOANA-016.md), [MOANA-018](MOANA-018.md)).
- Actualizar goldens automáticamente, desactivar checks, editar `uv.lock` a mano o añadir dependencias sin motivo técnico registrado.
- `eval`/`exec`/`pickle`, red o estado global mutable en el núcleo; lecturas de texto sin `encoding="utf-8"`.

## Evidence

- src/moana/geometry/algebra.py: álgebra de máscaras (union, intersect, subtract como pliegue por la izquierda, xor) con MaskBuilder y combined_box; resultados recortados al lienzo; Mask inmutable sin NumPy en contratos públicos.
- src/moana/schema/: masks (hojas rect/ellipse/polygon y combinaciones por ID) y regions (operaciones agrupadas con mask_id) en el documento 1.0, Layer.mask_id; references.py resuelve el DAG con Tarjan iterativo, rechaza ciclos (mask_cycle) y referencias rotas antes de render, y protege documentos sin validar con ReferenceError en vez de bucles o KeyError; resolve_region y mask_dependencies públicos; JSON Schema regenerado.
- src/moana/layers/: MaskShape/MaskCombination (igualdad por identidad) y Layer.mask; la capa se recorta a su máscara antes de la opacidad (aplicada una vez); los nodos de caja vacía no evalúan operandos.
- src/moana/render/budget.py: budget-v3 con coste de máscaras por referencia expandida y suelo de 1 visita por nodo evaluado, idéntico al compositor; un DAG ancho y profundo de hojas llenas se rechaza con BudgetExceeded antes del raster y uno de hojas vacías cuesta el suelo y termina en milisegundos (32×8 ≈ 3,5e10 referencias: 0,011 s).
- src/moana/core/coordinates.py: combined_box puro compartido por geometry.algebra y render.budget; límites MAX_MASKS, MAX_MASK_OPERANDS, MAX_MASK_DEPTH y MAX_REGIONS en core.limits.
- moana.api: resolve_region reexportado; inspect_document informa masks, regions y mask_id por capa; capabilities con mask_types y planned_mask_types [path].
- ADR-022 (docs/architecture/decisions/ADR-022-masks-regions.md), con notas de cabecera en ADR-011, ADR-017, ADR-018 y ADR-020; MOANA.md 0.1.9-draft (§11, §12, §13, §16, §20): schema 1.0 ampliado como excepción previa a la primera publicación, después toda ampliación sube el minor; ejemplo examples/specs/masked-eyes.moana.json; contratos de módulos, índice de ADR, overview, README, guía de desarrollo, AGENTS.md y CLAUDE.md actualizados.
- Trazabilidad: R012 cubierto. La hoja path queda prevista para MOANA-007.
- Gate: scripts/validate.py (1223 passed, src/moana al 100 % de líneas y ramas) y scripts/check_wheel.py verdes; mypy también con --platform win32; generate_schema --check al día. Sin ejecución en Windows real (matriz pendiente en main).
- Revisión: moana-graphics-engineer (cambios requeridos, aplicados: coste exponencial de DAG con hojas vacías, trabajo no contado en _clear_outside, oráculo de caja independiente) y moana-architect (cambios requeridos, aplicados: el mismo riesgo exponencial, excepción de versión del schema documentada frente a §16, ciclos en documentos sin validar, aritmética de cajas extraída a core, MaskNode homónimos aclarados, MaskCombination con eq=False, regla de grupos transformados como norma futura).
- AC1: tests/unit/layers/test_layers_masks.py::test_ac1_masked_layer_changes_no_pixel_outside_its_mask, ::test_ac1_layer_opacity_is_applied_once_inside_the_mask, ::test_ac1_random_masks_match_the_scalar_oracle, ::test_each_operator_clips_the_layer_to_its_set; tests/unit/render/test_render_masks.py::test_ac1_masked_operation_changes_no_pixel_outside_its_mask, ::test_ac1_mask_reaching_outside_the_canvas_is_clipped y ::test_example_renders_to_the_hand_computed_face.
- AC2: tests/unit/schema/test_schema_masks.py::test_ac2_left_eye_resolves_by_id, ::test_ac2_region_resolution_does_not_depend_on_array_order, ::test_ac2_unknown_region_or_mask_is_a_reference_error, ::test_unvalidated_cycles_and_broken_references_fail_fast; tests/unit/api/test_api_masks.py::test_ac2_resolve_region_through_the_facade y ::test_inspect_of_an_unvalidated_cycle_fails_fast; tests/unit/render/test_render_masks.py::test_ac2_cycles_and_broken_references_fail_before_any_raster.
- T1: tests/unit/geometry/test_geometry_algebra.py::test_fixtures_have_the_documented_sizes (1/8/128 píxeles), ::test_t1_binary_operators_match_set_oracle, ::test_t1_hand_results_on_the_fixtures, ::test_t1_associative_and_commutative_operators, ::test_t1_subtract_is_left_fold_and_not_commutative, ::test_t1_empty_mask_identities, ::test_t1_results_are_clipped_to_the_canvas y ::test_t1_property_matches_python_sets (caja esperada calculada desde los conjuntos).
- T2: tests/unit/schema/test_schema_masks.py::test_t2_direct_cycle_is_rejected, ::test_t2_indirect_cycle_marks_every_edge_of_the_loop, ::test_t2_missing_references_point_to_the_member, ::test_t2_mask_depth_limit, ::test_t2_mask_outside_the_canvas_is_valid, ::test_shared_operands_are_not_cycles; tests/unit/layers/test_layers_masks.py::test_t2_mask_fully_outside_the_canvas_hides_the_layer, ::test_t2_transformed_group_content_is_clipped_by_a_canvas_mask, ::test_t2_group_opacity_applies_once_over_masked_children, ::test_wide_deep_dag_of_full_masks_is_rejected_before_composing; tests/unit/render/test_render_masks.py::test_t2_mask_fully_outside_the_canvas_draws_nothing, ::test_wide_deep_dag_of_empty_masks_costs_the_floor y ::test_wide_deep_dag_of_full_masks_is_rejected_before_raster.
