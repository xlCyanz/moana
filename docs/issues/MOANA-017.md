# MOANA-017 — Crear presets de materiales versionados

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-017
- Aliases históricos: MOA-017
- Phase: P3
- Priority: P1
- Status: done
- Complexity: L (relativa, no estimación de tiempo)
- Dependencies: [MOANA-014](MOANA-014.md), [MOANA-015](MOANA-015.md), [MOANA-016](MOANA-016.md)
- Related modules: techniques, schema
- Requirements: R010, R005 ([trazabilidad](traceability.md))
- Bloqueo: Ninguno

## Context

Un material repetible debe exponer parámetros y conservar paleta/IDs.

## Objective

Entregar cinco recetas de material editables con versión y procedencia.

## Scope

Crear presets editables de piel, tela, metal, madera y piedra definidos por rampas, bandas y patrones.

## Out of scope

No afirmar calidad profesional sólo por aprobar fixtures ni usar assets sin licencia.

## Technical requirements

- Semilla por operación/coordenada según §14; ningún shader ejecutable en JSON
- Parámetros con rango, fuente, versión y recetas reproducibles; registrar procedencia de ejemplos
- Contorno selectivo de MOANA.md §8 (pendiente desde MOANA-015, ADR-028): reutilizar ShadeLight/exposure/band_index de moana.techniques.shading para decidir qué tramos del outline se aclaran u oscurecen, sin una segunda regla de luz.

## Proposed implementation

- Definir presets como composición de bandas, ramps y patrones existentes
- Añadir controles de rango, semillas y ejemplos propios por material

## Acceptance criteria

- [x] AC1: Cada material puede editarse sin perder IDs ni introducir colores fuera del perfil
- [x] AC2: Misma semilla genera igual textura y una operación nueva no altera material existente

## Required tests

- [x] T1: Fixtures pequeñas por material con máscara y límites de densidad/escala
- [x] T2: Pruebas de estabilidad entre frames y revisión visual a 1×/4× documentada como humana o pendiente

## Expected deliverables

- Presets de materiales versionados con parámetros y semilla local explícitos.
- Ejemplos editables, fixtures de repetibilidad y límites de cada material.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- Una receta reproducible puede seguir siendo visualmente mala; separar evaluación humana.

## Guía para agentes de IA

**Estado para agentes:** Completado; usar sólo como referencia del contrato entregado.

### 1. Preparación

- Rama: `feat/MOANA-017-crear-presets-materiales` creada desde `develop` actualizado: `git switch develop && git pull --ff-only && git switch -c feat/MOANA-017-crear-presets-materiales`.
- Verificar en `docs/issues/catalog.json` que este issue está `ready` y que sus dependencias ([MOANA-014](MOANA-014.md), [MOANA-015](MOANA-015.md), [MOANA-016](MOANA-016.md)) están `done`.
- Entorno: `uv sync --locked` (sin uv global: `sh scripts/bootstrap.sh` y después `sh scripts/uv.sh` en lugar de `uv`).
- Al empezar, cambiar `status` a `in_progress` en el catálogo y regenerar con `uv run python scripts/planning.py`.

### 2. Lectura obligatoria (en orden)

1. `CLAUDE.md` (Claude Code) o `AGENTS.md` (Codex) y [flujo de sesión](../guides/agent-workflow.md).
2. MOANA.md: §3 Arquitectura modular; §7 Técnicas profesionales de Pixel Art; §10 Sombreado, dithering y materiales; §19 Control de calidad gráfico; §25 Definition of Done. Estas secciones son el contrato normativo; ante duda, prevalecen sobre este issue.
3. [Contratos de módulos](../architecture/module-contracts.md) para: `techniques`, `schema`.
4. Estándares: [python](../../docs/standards/python.md), [architecture](../../docs/standards/architecture.md), [testing](../../docs/standards/testing.md), [pixel-art](../../docs/standards/pixel-art.md), [security](../../docs/standards/security.md).
5. Issues de dependencia ([MOANA-014](MOANA-014.md), [MOANA-015](MOANA-015.md), [MOANA-016](MOANA-016.md)): leer su sección Evidence para conocer las APIs ya entregadas; no reimplementarlas.
6. ADR en `docs/architecture/` que mencionen los módulos afectados.

### 3. Requisitos de MOANA.md cubiertos

| ID | Requisito | Secciones | Verificación exigida |
| --- | --- | --- | --- |
| R010 | Materiales editables y reproducibles | §10 | Fixtures de cinco materiales y semillas |
| R005 | Técnicas profesionales y calidad artística | §7, §19 | Corpus editable y rúbrica humana documentada |

### 4. Skills y subagentes

| Host | Skills a cargar | Revisión especializada |
| --- | --- | --- |
| Claude Code | `moana-graphics`, `moana-pixel-art`, `moana-python`, `moana-architecture`, `moana-code-review` | `moana-graphics-engineer`, `moana-pixel-artist`, `moana-python-engineer`, `moana-architect` (sólo lectura; el agente principal integra) |
| Codex | `$moana-graphics`, `$moana-pixel-art`, `$moana-python`, `$moana-architecture`, `$moana-code-review` | `moana_graphics_engineer`, `moana_pixel_artist`, `moana_python_engineer`, `moana_architect` |

### 5. Archivos

- Código o documentos a crear/modificar: `src/moana/techniques/`, `src/moana/schema/`.
- Pruebas: `tests/unit/techniques/`, `tests/unit/schema/`.
- No crear módulos ni carpetas sin comportamiento real. No tocar otros módulos salvo exportaciones imprescindibles, justificadas en el PR.

### 6. Plan de pruebas

- T1: Fixtures pequeñas por material con máscara y límites de densidad/escala
- T2: Pruebas de estabilidad entre frames y revisión visual a 1×/4× documentada como humana o pendiente
- Oráculos independientes (cálculo a mano o fórmula de MOANA.md); nunca copiar la salida de la implementación como expected.
- Incluir casos negativos con el error de dominio esperado y casos borde (vacío, mínimo, máximo, fuera de rango).

### 7. Procedimiento

1. Escribir las pruebas de los criterios AC y T antes o junto con la implementación.
2. Implementar sólo **Scope**; respetar **Out of scope** y las dependencias permitidas de MOANA.md §3.
3. Validación de módulo: `uv run pytest tests/unit/techniques/ tests/unit/schema/ -q` y `uv run mypy src/`.
4. Validación completa: `uv run python scripts/validate.py` y `uv run python scripts/check_wheel.py`.
5. Revisión: subagentes listados y skill `moana-code-review`; corregir hallazgos críticos y altos.
6. Si hay salida raster: mostrar el PNG a 1x y ampliado por vecino más cercano; si cambia un golden, presentar expected/actual/diff y justificar.

### 8. Cierre

1. En `docs/issues/catalog.json`, para este issue: `status` → `review` (o `done` tras aprobación); completar `acceptance_evidence` (AC1, AC2), `test_evidence` (T1, T2) y `evidence` con rutas concretas de tests y archivos.
2. Issues que desbloquea ([MOANA-027](MOANA-027.md)): si todas sus dependencias quedan `done`, pasarlos a `ready` con `blocking_reason: null`.
3. Ejecutar `uv run python scripts/planning.py` y `uv run python -m scripts.check_repository`.
4. Abrir PR hacia `develop` enlazando este issue de GitHub (`Closes #<número>`), con comandos ejecutados y evidencia por AC/T. El CI completo corre al integrar `develop` en `main`.
5. Commit y push sólo con autorización del usuario. No declarar CI remoto ni aprobación artística humana sin evidencia.

### 9. Prohibido en este issue

- Implementar alcance de otros issues, incluidos los que desbloquea ([MOANA-027](MOANA-027.md)).
- Actualizar goldens automáticamente, desactivar checks, editar `uv.lock` a mano o añadir dependencias sin motivo técnico registrado.
- `eval`/`exec`/`pickle`, red o estado global mutable en el núcleo; lecturas de texto sin `encoding="utf-8"`.

## Evidence

- Tabla de presets versionados de sólo lectura moana.core.materials.MATERIAL_PRESETS (MappingProxyType de filas frozen por (name, version)): v1 skin (poros, max_density 4), cloth (tejido en cesta), metal (veta diagonal), wood (veta horizontal) y stone (moteado); procedencia propia y licencia de las recetas por decidir; MAX_MATERIAL_SCALE=8 es margen para versiones futuras (ninguna fila v1 supera 4).
- Textura por celdas determinista moana.techniques.materials: celdas scale×scale ancladas en origin con división entera hacia abajo (también negativos), puerta cell_choice(seed, op_id, cx, cy, 0, 64) < density con SHA-256 y enteros big-endian (cell_choices vectorizado igual byte a byte al escalar), paso ±1 de rampa con clamp; sin floats, hash() ni sets.
- Operación material en schema 1.0 (excepción previa a la publicación, ADR-030 §8, que también cubre el comando set_parameters del batch 1.0; DOCUMENT_MIGRATIONS de ADR-031 sigue sin pasos): bandas con ID global y la misma regla de luz de shade (band_index, ADR-028), sin segunda regla; colección raíz materials aceptada sólo vacía.
- Operación selective_outline: anillo de outline_mask como base y tramos authored con ramp[band_index]; partes disjuntas cuya unión es el anillo, cajas declaradas dentro de su máscara.
- Edición: columna parameters en NodeMembers (lista blanca por tipo; outline y dither vacías a propósito) y comando set_parameters revalidado; el error not_parameter apunta a /commands/i/parameters sin repetir la clave del usuario. Mover un sprite con textura exige translate de las máscaras y set_parameters de origin en el mismo batch.
- Presupuesto budget-v8: visitas y bytes por parte (banda + textura) medidos con tracemalloc en geometrías extremas (2048×1, 2048², orígenes ±2048, muchas bandas) sin superar la cota; documentos admitidos de mayor coste renderizan en <1 s.
- Cinco ejemplos editables examples/specs/material-{skin,cloth,metal,wood,stone}.moana.json con sombra plana tras la textura (0 contactos del paso más oscuro con la tinta) y contorno selectivo; singletons c4 tras la revisión: skin 2, cloth 2 (antes 334), metal 67 (diagonales continuas, 0 en c8), wood 0, stone 7.
- Revisiones de agente: gráficos aprobado; arquitectura, QA y pixel-art con correcciones aplicadas. Revisión artística humana a 1×/4×: PENDIENTE (registrada en metadata.provenance de los ejemplos y en ADR-030).
- Gate local macOS: scripts/validate.py 2614 passed con src/moana al 100 %, check_wheel OK, mypy --platform win32 OK, JSON Schema al día, pre-commit OK; matriz pendiente en main.
- Aprobado por el propietario el 2026-11-17 tras revisión; PR #61 hacia develop.
- AC1: tests/unit/editing/test_editing_material.py::test_ac1_tuning_a_material_keeps_ids_and_stays_in_the_palette, ::test_ac1_material_edits_are_undoable_in_the_history; tests/unit/render/test_render_material.py::test_ac1_every_pixel_is_the_ramp_step_of_its_last_band_plus_its_texel, ::test_ac1_the_light_and_facings_follow_the_shade_rule
- AC2: tests/unit/editing/test_editing_material.py::test_ac2_inserted_operation_keeps_existing_texture; tests/unit/render/test_render_material.py::test_ac2_same_seed_same_texture_and_another_operation_changes_nothing; tests/unit/techniques/test_techniques_materials.py::test_ac2_same_seed_same_texture_and_the_key_is_the_operation
- T1: tests/unit/techniques/test_techniques_materials.py::test_t1_cloth_full_density_is_a_basket_weave, ::test_t1_metal_full_density_is_a_diagonal_streak_every_fourth_cell, ::test_t1_wood_full_density_is_horizontal_grain_every_third_row, ::test_t1_zero_density_never_moves_a_pixel, ::test_t1_every_preset_matches_the_independent_hash_oracle, ::test_t1_limits_of_density_and_scale, ::test_t1_marked_fraction_follows_the_density, ::test_t1_a_cell_marked_at_one_density_stays_marked_above_it, ::test_t1_every_pixel_of_a_cell_shares_its_offset; tests/unit/render/test_render_material.py::test_t1_cloth_weave_moves_basket_pixels_one_step_down, ::test_t1_metal_streak_moves_diagonal_pixels_one_step_up, ::test_t1_wood_grain_with_scale_two_and_an_offset_origin, ::test_t1_clamp_keeps_texture_steps_inside_the_ramp, ::test_t1_one_pixel_canvas, ::test_t1_band_entirely_off_the_canvas_paints_nothing, ::test_t1_zero_density_is_plain_band_shading, ::test_t1_seeded_presets_match_the_independent_oracle; límites de densidad/escala en tests/unit/schema/test_schema_material.py
- T2: tests/unit/render/test_render_material.py::test_t2_a_frame_that_moves_mask_and_origin_together_moves_every_pixel, ::test_t2_recipe_golden_of_every_example, ::test_t2_recipe_golden_of_every_preset_row; tests/unit/techniques/test_techniques_materials.py::test_t2_texture_follows_its_origin; tests/integration/test_material_determinism.py::test_t2_fresh_processes_with_any_hash_seed_agree, ::test_t2_repeated_renders_in_one_process_agree, ::test_t2_the_texture_does_not_depend_on_the_order_of_json_keys; revisión visual a 1×/4×/8× por agentes (pixel-art); revisión humana PENDIENTE
