# MOANA-015 — Añadir bandas de sombreado e iluminación

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-015
- Aliases históricos: MOA-015
- Phase: P3
- Priority: P1
- Status: review
- Complexity: M (relativa, no estimación de tiempo)
- Dependencies: [MOANA-005](MOANA-005.md), [MOANA-013](MOANA-013.md)
- Related modules: techniques, palette
- Requirements: R008 ([trazabilidad](traceability.md))
- Bloqueo: Ninguno

## Context

La iluminación estilizada depende de rampas y máscaras authored.

## Objective

Seleccionar tonos de forma explícita y consistente al editar sombras.

## Scope

Agregar luces discretas, máscaras de bandas y selección de índices de rampa para volúmenes estilizados.

## Out of scope

No sombreado 3D físico ni multiplicación RGB que cree colores ocultos.

## Technical requirements

- Prioridad por orden de bandas y clamp de pasos a la rampa
- Sin normales inferidas: luz recibe regiones/mapas authored; selective outline consume la misma información

## Proposed implementation

- Registrar luz discreta y bandas ordenadas
- Resolver rampas, prioridad de solapamiento y clamp sin inventar normales

## Acceptance criteria

- [ ] AC1: Solapamientos toman la última banda y todos los colores pertenecen a la rampa
- [ ] AC2: Modificar una máscara de sombra conserva geometría/IDs y da un diff localizado documentado

## Required tests

- [ ] T1: Bandas vacías, solapamientos, clamp y cambios de orientación
- [ ] T2: Fixtures manuales con rampa de 3/5 tonos y píxeles de frontera

## Expected deliverables

- Operaciones de bandas y sombreado que conservan rampas y máscaras editables.
- Fixtures de orientación, número de tonos, clipping y evaluación visual de iluminación.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- La estética de una rampa puede contradecir luminancia monótona; emitir advertencia configurable.

## Guía para agentes de IA

**Estado para agentes:** En revisión: sólo correcciones de la revisión; no añadir alcance.

### 1. Preparación

- Rama: `feat/MOANA-015-anadir-bandas-sombreado` creada desde `develop` actualizado: `git switch develop && git pull --ff-only && git switch -c feat/MOANA-015-anadir-bandas-sombreado`.
- Verificar en `docs/issues/catalog.json` que este issue está `ready` y que sus dependencias ([MOANA-005](MOANA-005.md), [MOANA-013](MOANA-013.md)) están `done`.
- Entorno: `uv sync --locked` (sin uv global: `sh scripts/bootstrap.sh` y después `sh scripts/uv.sh` en lugar de `uv`).
- Al empezar, cambiar `status` a `in_progress` en el catálogo y regenerar con `uv run python scripts/planning.py`.

### 2. Lectura obligatoria (en orden)

1. `CLAUDE.md` (Claude Code) o `AGENTS.md` (Codex) y [flujo de sesión](../guides/agent-workflow.md).
2. MOANA.md: §3 Arquitectura modular; §9 Paletas, color e iluminación; §10 Sombreado, dithering y materiales; §25 Definition of Done. Estas secciones son el contrato normativo; ante duda, prevalecen sobre este issue.
3. [Contratos de módulos](../architecture/module-contracts.md) para: `techniques`, `palette`.
4. Estándares: [python](../../docs/standards/python.md), [architecture](../../docs/standards/architecture.md), [testing](../../docs/standards/testing.md), [pixel-art](../../docs/standards/pixel-art.md).
5. Issues de dependencia ([MOANA-005](MOANA-005.md), [MOANA-013](MOANA-013.md)): leer su sección Evidence para conocer las APIs ya entregadas; no reimplementarlas.
6. ADR en `docs/architecture/` que mencionen los módulos afectados.

### 3. Requisitos de MOANA.md cubiertos

| ID | Requisito | Secciones | Verificación exigida |
| --- | --- | --- | --- |
| R008 | Iluminación y sombreado por bandas | §9, §10 | Fixtures de rampas y prioridades de máscaras |

### 4. Skills y subagentes

| Host | Skills a cargar | Revisión especializada |
| --- | --- | --- |
| Claude Code | `moana-graphics`, `moana-pixel-art`, `moana-python`, `moana-code-review` | `moana-graphics-engineer`, `moana-pixel-artist`, `moana-python-engineer` (sólo lectura; el agente principal integra) |
| Codex | `$moana-graphics`, `$moana-pixel-art`, `$moana-python`, `$moana-code-review` | `moana_graphics_engineer`, `moana_pixel_artist`, `moana_python_engineer` |

### 5. Archivos

- Código o documentos a crear/modificar: `src/moana/techniques/`, `src/moana/palette/`.
- Pruebas: `tests/unit/techniques/`, `tests/unit/palette/`.
- No crear módulos ni carpetas sin comportamiento real. No tocar otros módulos salvo exportaciones imprescindibles, justificadas en el PR.

### 6. Plan de pruebas

- T1: Bandas vacías, solapamientos, clamp y cambios de orientación
- T2: Fixtures manuales con rampa de 3/5 tonos y píxeles de frontera
- Oráculos independientes (cálculo a mano o fórmula de MOANA.md); nunca copiar la salida de la implementación como expected.
- Incluir casos negativos con el error de dominio esperado y casos borde (vacío, mínimo, máximo, fuera de rango).

### 7. Procedimiento

1. Escribir las pruebas de los criterios AC y T antes o junto con la implementación.
2. Implementar sólo **Scope**; respetar **Out of scope** y las dependencias permitidas de MOANA.md §3.
3. Validación de módulo: `uv run pytest tests/unit/techniques/ tests/unit/palette/ -q` y `uv run mypy src/`.
4. Validación completa: `uv run python scripts/validate.py` y `uv run python scripts/check_wheel.py`.
5. Revisión: subagentes listados y skill `moana-code-review`; corregir hallazgos críticos y altos.
6. Si hay salida raster: mostrar el PNG a 1x y ampliado por vecino más cercano; si cambia un golden, presentar expected/actual/diff y justificar.

### 8. Cierre

1. En `docs/issues/catalog.json`, para este issue: `status` → `review` (o `done` tras aprobación); completar `acceptance_evidence` (AC1, AC2), `test_evidence` (T1, T2) y `evidence` con rutas concretas de tests y archivos.
2. Issues que desbloquea ([MOANA-017](MOANA-017.md), [MOANA-026](MOANA-026.md)): si todas sus dependencias quedan `done`, pasarlos a `ready` con `blocking_reason: null`.
3. Ejecutar `uv run python scripts/planning.py` y `uv run python -m scripts.check_repository`.
4. Abrir PR hacia `develop` enlazando este issue de GitHub (`Closes #<número>`), con comandos ejecutados y evidencia por AC/T. El CI completo corre al integrar `develop` en `main`.
5. Commit y push sólo con autorización del usuario. No declarar CI remoto ni aprobación artística humana sin evidencia.

### 9. Prohibido en este issue

- Implementar alcance de otros issues, incluidos los que desbloquea ([MOANA-017](MOANA-017.md), [MOANA-026](MOANA-026.md)).
- Actualizar goldens automáticamente, desactivar checks, editar `uv.lock` a mano o añadir dependencias sin motivo técnico registrado.
- `eval`/`exec`/`pickle`, red o estado global mutable en el núcleo; lecturas de texto sin `encoding="utf-8"`.

## Evidence

- Operación shade en schema 1.0 (excepción previa a la primera publicación, ADR-022/023/025/027): {id, type, ramp, ramp_order monotonic|stylized, light {direction 8+front, height 0–3, intensity, ambient}, bands 1–64 × {id, mask_id, facing, offset}}; referencia unknown_ramp; IDs de banda globales en el DAG de máscaras; JSON Schema regenerado; moana.schema.document_ids expone todos los IDs del documento (incluidas bandas).
- Sin normales inferidas: cada banda trae su facing authored; exposure entera −6..6, band_level = round_half_away(intensity·exp/6), índice = clamp(ambient + level + offset) a la rampa (moana.core.shading, moana.techniques.shading: ShadeLight, exposure, band_level, ramp_index, band_index, last_wins, resolve_bands). Ningún color se calcula: sólo se elige un paso de la rampa.
- Render: un fill diferido por banda con máscara = banda − bandas posteriores que la tocan (shade_later); partes disjuntas, gana la última banda listada, ningún paso translúcido se mezcla con otra banda; budget-v7 idéntico a v6 sin shade, con SHADE_FIXED_BYTES=8192 y SHADE_FOLD_BYTES=24576 (3 operandos × NPY_BUFSIZE) medidos con tracemalloc en 360 configuraciones.
- Advertencia configurable del riesgo del issue: ramp_order monotonic emite Palette.ramp_warnings en …/ramp; stylized sólo suprime la luminancia no creciente.
- Edición: NodeMembers gana columnas ramps e items (filas anidadas limitadas a masks por test); las bandas son items con ID global: insert_operation valida sus IDs (duplicate_id/reused_id con puntero de banda), borrar un shade o su capa retira esos IDs y los incluye en affected_ids; las máscaras de banda se editan por su ID (AC2). Parámetros de banda/luz sin comando propio (seguimiento en ADR-028 §6). OperationSummary.color puede ser null.
- Ejemplo examples/specs/shaded-orb.moana.json: orbe con rampa de 5 tonos, luz nw, bandas de cuerpo, sombra (clamp −1→0), lado iluminado, terminadores ne/sw, rebote y brillo; sin advertencias y 0 singletons (analyze_clusters en el test); revisión artística de agente, no aprobación humana.
- Contorno selectivo de §8 pendiente: ADR-028 lo asigna a MOANA-017, con nota técnica en el catálogo.
- ADR-028 (docs/architecture/decisions/ADR-028-band-shading.md) con notas de cabecera en ADR-011, 014, 018, 020, 022, 024, 025 y 027; MOANA.md 0.1.16-draft (§9, §10, §12, §13, §15, §17, §20); contratos de módulos, índice de ADR, overview, README, AGENTS.md y CLAUDE.md actualizados. El issue toca también schema, render, editing y api (justificado en ADR-028).
- Gate sobre 6793f4b: scripts/validate.py (2098 passed, src/moana al 100 % de líneas y ramas) y scripts/check_wheel.py verdes; mypy también con --platform win32; generate_schema --check al día. Evidencia de plataforma: local macOS; matriz pendiente en main.
- Revisión: moana-architect (cambios requeridos, aplicados: IDs de banda en reused_id/affected_ids, document_ids público, filas anidadas acotadas, selective outline asignado, docstrings), moana-graphics-engineer (cambios requeridos, aplicados: cota por fill general con SHADE_FOLD_BYTES de 3 operandos y test por banda en cajas desplazadas, fixture 1×1), moana-qa-engineer (aprobado con menores, aplicados: cifra de cobertura, propiedad AC1 de documento, bordes de schema, rampa de 1 tono, field en ramp_warnings) y moana-pixel-artist (cambios requeridos, aplicados: terminadores ne/sw y rebote limitado al cuadrante se, 0 singletons).
- AC1: tests/unit/techniques/test_techniques_shading.py::test_ac1_overlap_goes_to_the_last_listed_band y ::test_ac1_visible_parts_are_disjoint_and_cover_the_union; tests/unit/render/test_render_shade.py::test_ac1_overlap_takes_the_last_band_and_only_ramp_colours, ::test_ac1_every_pixel_takes_the_ramp_step_of_the_last_band_containing_it (Hypothesis contra oráculo de conjuntos), ::test_ac1_exact_pixels_on_a_one_pixel_canvas y ::test_ac1_translucent_ramp_steps_never_blend_two_bands.
- AC2: tests/unit/editing/test_editing_shade.py::test_ac2_moving_the_shadow_mask_keeps_ids_and_changes_one_column (diff documentado: columna x=4, 8 píxeles; también en ADR-028 §6) y ::test_ac2_any_shadow_edit_only_changes_pixels_of_the_old_or_new_mask (diferencia simétrica); ::test_removing_a_shade_retires_its_band_ids, ::test_an_inserted_band_id_must_be_new y ::test_removing_a_layer_reports_the_band_ids_of_its_shades.
- T1: tests/unit/techniques/test_techniques_shading.py::test_t1_turning_the_light_swaps_the_lit_and_the_shadowed_band, ::test_t1_rotating_light_and_facings_together_changes_nothing, ::test_t1_opposite_facings_get_opposite_levels_within_intensity, ::test_t1_steps_are_clamped_to_the_ramp, ::test_t1_offsets_beyond_the_ramp_are_clamped y ::test_t1_empty_bands_and_fully_covered_bands; tests/unit/render/test_render_shade.py::test_t1_listing_order_decides_the_overlap, ::test_t1_turning_the_light_swaps_the_tones_without_touching_the_masks, ::test_t1_offsets_are_clamped_to_the_ramp y ::test_t1_empty_bands_paint_nothing.
- T2: tests/unit/techniques/test_techniques_shading.py::test_t2_five_tone_ramp_under_an_east_light y ::test_t2_three_tone_ramp_under_a_front_light; tests/unit/render/test_render_shade.py::test_t2_five_tone_fixture_with_boundary_pixels, ::test_t2_three_tone_fixture_under_a_front_light y ::test_every_band_fill_peak_stays_within_its_cost; tests/unit/schema/test_schema_shade.py (payload, negativos, 64 bandas, unknown_ramp).
