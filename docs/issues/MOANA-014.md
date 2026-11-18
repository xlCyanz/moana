# MOANA-014 — Crear contornos y análisis de clusters

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-014
- Aliases históricos: MOA-014
- Phase: P3
- Priority: P1
- Status: review
- Complexity: L (relativa, no estimación de tiempo)
- Dependencies: [MOANA-013](MOANA-013.md), [MOANA-005](MOANA-005.md)
- Related modules: techniques, quality
- Requirements: R006, R025 ([trazabilidad](traceability.md))
- Bloqueo: Ninguno

## Context

Los contornos y clusters deben admitir excepciones artísticas locales.

## Objective

Generar outlines editables y diagnósticos de componentes sin limpieza automática.

## Scope

Implementar morfología binaria para outlines y análisis conectado de clusters con salida editable y diagnósticos.

## Out of scope

No clasificar intención artística como error matemático ni borrar detalles automáticamente.

## Technical requirements

- Vecindad Chebyshev para contornos y conectividad 4/8 explícita para clusters
- Advertencias por singleton y escalones con supresión por región; no limpieza destructiva automática

## Proposed implementation

- Implementar dilatación/erosión acotada y análisis 4/8 conectado
- Representar resultado como operaciones y advertencias con bbox/región

## Acceptance criteria

- [ ] AC1: Contornos internos/externos respetan ancho, huecos y clipping
- [ ] AC2: Un brillo aislado puede conservarse mediante excepción; el análisis no cambia el documento

## Required tests

- [ ] T1: Máscaras con huecos, contactos de esquina, diagonal y borde de canvas
- [ ] T2: Componentes conocidos, outline de ancho 1/2 y operación editable que reproduce la máscara

## Expected deliverables

- Operaciones de contorno y análisis de clusters con conectividad explícita.
- Máscaras de referencia para bordes/huecos/diagonales y ejemplos ampliados.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- No eliminar ojos o partículas por ser singletons; las métricas no inferirán intención.

## Guía para agentes de IA

**Estado para agentes:** En revisión: sólo correcciones de la revisión; no añadir alcance.

### 1. Preparación

- Rama: `feat/MOANA-014-crear-contornos-analisis` creada desde `develop` actualizado: `git switch develop && git pull --ff-only && git switch -c feat/MOANA-014-crear-contornos-analisis`.
- Verificar en `docs/issues/catalog.json` que este issue está `ready` y que sus dependencias ([MOANA-013](MOANA-013.md), [MOANA-005](MOANA-005.md)) están `done`.
- Entorno: `uv sync --locked` (sin uv global: `sh scripts/bootstrap.sh` y después `sh scripts/uv.sh` en lugar de `uv`).
- Al empezar, cambiar `status` a `in_progress` en el catálogo y regenerar con `uv run python scripts/planning.py`.

### 2. Lectura obligatoria (en orden)

1. `CLAUDE.md` (Claude Code) o `AGENTS.md` (Codex) y [flujo de sesión](../guides/agent-workflow.md).
2. MOANA.md: §3 Arquitectura modular; §8 Siluetas, contornos y pixel clusters; §19 Control de calidad gráfico; §25 Definition of Done. Estas secciones son el contrato normativo; ante duda, prevalecen sobre este issue.
3. [Contratos de módulos](../architecture/module-contracts.md) para: `techniques`, `quality`.
4. Estándares: [python](../../docs/standards/python.md), [architecture](../../docs/standards/architecture.md), [testing](../../docs/standards/testing.md), [pixel-art](../../docs/standards/pixel-art.md).
5. Issues de dependencia ([MOANA-013](MOANA-013.md), [MOANA-005](MOANA-005.md)): leer su sección Evidence para conocer las APIs ya entregadas; no reimplementarlas.
6. ADR en `docs/architecture/` que mencionen los módulos afectados.

### 3. Requisitos de MOANA.md cubiertos

| ID | Requisito | Secciones | Verificación exigida |
| --- | --- | --- | --- |
| R006 | Siluetas, contornos y clusters | §8 | Morfología y componentes conocidos |
| R025 | Evaluación gráfica y diagnósticos | §19 | Hard/soft checks, bbox y supresiones |

### 4. Skills y subagentes

| Host | Skills a cargar | Revisión especializada |
| --- | --- | --- |
| Claude Code | `moana-graphics`, `moana-pixel-art`, `moana-testing`, `moana-code-review` | `moana-graphics-engineer`, `moana-pixel-artist`, `moana-qa-engineer` (sólo lectura; el agente principal integra) |
| Codex | `$moana-graphics`, `$moana-pixel-art`, `$moana-testing`, `$moana-code-review` | `moana_graphics_engineer`, `moana_pixel_artist`, `moana_qa_engineer` |

### 5. Archivos

- Código o documentos a crear/modificar: `src/moana/techniques/`, `src/moana/quality/`.
- Pruebas: `tests/unit/techniques/`, `tests/unit/quality/`.
- No crear módulos ni carpetas sin comportamiento real. No tocar otros módulos salvo exportaciones imprescindibles, justificadas en el PR.

### 6. Plan de pruebas

- T1: Máscaras con huecos, contactos de esquina, diagonal y borde de canvas
- T2: Componentes conocidos, outline de ancho 1/2 y operación editable que reproduce la máscara
- Oráculos independientes (cálculo a mano o fórmula de MOANA.md); nunca copiar la salida de la implementación como expected.
- Incluir casos negativos con el error de dominio esperado y casos borde (vacío, mínimo, máximo, fuera de rango).

### 7. Procedimiento

1. Escribir las pruebas de los criterios AC y T antes o junto con la implementación.
2. Implementar sólo **Scope**; respetar **Out of scope** y las dependencias permitidas de MOANA.md §3.
3. Validación de módulo: `uv run pytest tests/unit/techniques/ tests/unit/quality/ -q` y `uv run mypy src/`.
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

- Operación editable outline en schema 1.0 ({id, type, mask_id, width 1..16, side outer|inner, color}) bajo la excepción previa a la primera publicación (ADR-022/023/025); fila de miembros colors=(color,), masks=(mask_id,), sin geometría: set_color la recolorea, translate/set_geometry dan not_geometric; probado también con History (undo/redo).
- Morfología Chebyshev (moana.geometry.dilate/erode, core.morphology.morphology_bytes) con sumas prefijas int32 acumuladas en el sitio, radio 1–16 (MAX_MORPHOLOGY_RADIUS), clipping antes de reservar, sin wraparound y exterior transparente; outline_mask: outer = dilate−máscara, inner = máscara−erode; pico medido ≤ 0,997 de morphology_bytes en cajas 1×1…2048² y radios 1/3/16.
- Render: cada outline es un fill diferido sobre outline_box; budget-v6 = budget-v5 + término de outline (visitas(M)+16·P; bytes(M)+área(Bm)+morphology_bytes+2·área(X)); idéntico a v5 sin outline.
- Análisis de clusters en techniques (Python puro, sin NumPy directo): runs por fila + union-find en buffers array, conectividad 4/8, avisos singleton e irregular_steps, tope MAX_CLUSTER_RUNS=262144 (cluster_runs) y memoria acotada por cluster_bytes (CLUSTER_RUN_BYTES=512); excepciones por región (ClusterException, máx. MAX_CLUSTER_EXCEPTIONS=64) resueltas con MaskCover (una consulta vectorizada por hallazgo); deadline comprobado en cada etapa; el documento nunca cambia.
- moana.render.render_with_regions valida una vez, resuelve regiones antes de rasterizar y admite la solicitud entera (render + regiones + cover + análisis) contra un único presupuesto; moana.api.analyze_clusters valida la configuración antes de renderizar; sin comando CLI (ADR-027).
- Limitaciones documentadas en ADR-027: esquinas gruesas Chebyshev en contornos anchos (§8), irregular_steps casi no se dispara sobre contornos cerrados ni arcos que pasan de runs a columnas y da falsos positivos en curvas de duplicación 1,1,2,4 (suprimibles por región); peor caso medido 1,1 s sin excepciones y 1,9 s con 64 en un tablero 512².
- Ejemplo examples/specs/outlined-slime.moana.json: contorno exterior ink, contorno interior slime_dark recortado al lado en sombra (capa body_shade) y dos glints singleton conservados por la excepción eye_glints (0 avisos con ella, 2 sin ella); revisión artística de agente (no aprobación humana).
- ADR-027 (docs/architecture/decisions/ADR-027-outlines-clusters.md) con notas de cabecera en ADR-011, ADR-015, ADR-018, ADR-020, ADR-022 y ADR-025; MOANA.md 0.1.15-draft (§8, §12, §13, §19, §20); contratos de módulos, índice de ADR, overview, README, AGENTS.md y CLAUDE.md actualizados; JSON Schema regenerado; sin módulo quality (MOANA-026).
- Gate sobre develop 74dae10 (MOANA-019 incluido): scripts/validate.py (1932 passed, src/moana al 100 % de líneas y ramas) y scripts/check_wheel.py verdes; mypy también con --platform win32; generate_schema --check al día. Evidencia de plataforma: local macOS; matriz pendiente en main.
- Revisión: moana-graphics-engineer (cambios requeridos, aplicados: morphology_bytes como cota real con cumsum en el sitio y término de búferes de iteración, test de pico en 42 cajas/radios), moana-architect (cambios requeridos, aplicados: deadline y cota en la supresión, presupuesto por solicitud, rebase sobre MOANA-019, comentarios y contratos), moana-qa-engineer (cambios requeridos, aplicados: MaskCover y MAX_CLUSTER_EXCEPTIONS, memoria de clusters acotada, casos límite exactos, test de escalera corregido, severity Literal) y moana-pixel-artist (cambios requeridos, aplicados: sombreado según la luz y sheen separado del ojo).
- AC1: tests/unit/techniques/test_techniques_outline.py::test_ac1_outer_width_1_rings_the_square_and_fills_its_hole, ::test_ac1_inner_width_1_follows_the_border_and_the_hole, ::test_ac1_width_2_doubles_the_ring_on_both_sides, ::test_ac1_inner_width_2_around_a_single_pixel_hole, ::test_ac1_clipping_at_the_canvas_corner y ::test_outline_matches_the_set_oracle (Hypothesis contra oráculo de conjuntos); tests/unit/render/test_render_outline.py::test_ac1_document_outline_at_the_canvas_edge; tests/unit/geometry/test_geometry_morphology.py::test_width_16_matches_the_set_oracle_on_explicit_masks.
- AC2: tests/unit/api/test_api_clusters.py::test_ac2_without_exception_the_glint_warns, ::test_ac2_region_exception_keeps_the_glint_without_warning (canonical_json, snapshot_digest y normalize_document idénticos) y ::test_example_outlined_slime_keeps_its_glints_by_exception; tests/unit/techniques/test_techniques_clusters.py::test_ac2_region_exception_suppresses_and_keeps_the_finding_visible y ::test_many_exceptions_cost_one_cover_query_per_finding.
- T1: tests/unit/techniques/test_techniques_outline.py::test_t1_full_canvas_has_no_outer_outline_and_an_edge_inner_one, ::test_t1_corner_contact_fills_the_notches y ::test_t1_diagonal_line; tests/unit/techniques/test_techniques_clusters.py::test_t1_corner_contact_is_two_clusters_with_4_and_one_with_8, ::test_t1_hole_does_not_split_a_ring_and_the_hole_colour_is_its_own_cluster y ::test_t1_canvas_edges_never_wrap; tests/unit/geometry/test_geometry_morphology.py::test_a_hole_shrinks_under_dilation_and_grows_under_erosion, ::test_corner_contact_and_diagonal, ::test_dilation_clips_to_the_canvas_without_wraparound, ::test_erosion_treats_the_off_canvas_exterior_as_transparent y ::test_operators_match_the_set_oracle.
- T2: tests/unit/techniques/test_techniques_clusters.py::test_t2_known_components_with_counts_boxes_and_areas, ::test_components_match_breadth_first_search (Hypothesis contra BFS), ::test_run_limit_is_exact_at_a_512_checkerboard, ::test_peak_memory_stays_within_cluster_bytes y ::test_deadline_is_checked_in_every_stage; tests/unit/render/test_render_outline.py::test_t2_outer_width_1_paints_exactly_the_ring_and_the_hole, ::test_t2_inner_width_2_over_a_body_keeps_the_rest_of_the_body, ::test_editing_recolours_the_outline_but_cannot_move_it, ::test_history_recolours_an_outline_and_undo_redo_restore_the_pixels y ::test_outline_fill_peak_stays_within_its_cost; tests/unit/techniques/test_techniques_outline.py::test_t2_outline_is_disjoint_from_or_inside_the_mask; tests/unit/geometry/test_geometry_morphology.py::test_peak_memory_stays_within_morphology_bytes; tests/unit/api/test_api_clusters.py::test_settings_fail_before_validation_and_rendering, ::test_unknown_region_fails_before_rendering, ::test_one_budget_covers_render_regions_cover_and_analysis y ::test_deadline_reaches_the_regions_and_the_analysis; tests/unit/render/test_render_regions.py y tests/unit/geometry/test_geometry_cover.py.
