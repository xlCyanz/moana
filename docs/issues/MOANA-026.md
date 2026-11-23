# MOANA-026 — Crear informes de calidad gráfica

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-026
- Aliases históricos: MOA-026
- Phase: P5
- Priority: P1
- Status: done
- Complexity: L (relativa, no estimación de tiempo)
- Dependencies: [MOANA-014](MOANA-014.md), [MOANA-015](MOANA-015.md), [MOANA-022](MOANA-022.md)
- Related modules: quality
- Requirements: R025, R005 ([trazabilidad](traceability.md))
- Bloqueo: Ninguno

## Context

Heurísticas artísticas y errores de contrato tienen distinta severidad.

## Objective

Producir informes reproducibles y accionables sin modificar el sprite.

## Scope

Crear moanart/quality para hard checks, heurísticas configurables, métricas y diagnósticos por región.

## Out of scope

No puntaje automático que garantice calidad profesional ni revisión humana ficticia.

## Technical requirements

- Informe ordenado con rule_id, severidad, bbox, explicación y evidencia; no modifica render
- Separar conformidad matemática de advertencias artísticas y permitir supresiones localizadas

## Proposed implementation

- Implementar hard checks primero y métricas sobre fixtures sintéticas
- Añadir heurísticas/supresiones y orden estable por regla/región/posición

## Acceptance criteria

- [x] AC1: Un color fuera de paleta strict se detecta como fallo y un singleton como advertencia
- [x] AC2: Informe se reproduce idéntico y supresión de un ojo no oculta errores de otra región

## Required tests

- [x] T1: Corpus sintético con defectos conocidos y versiones corregidas
- [x] T2: Tests de no mutación, orden estable, regiones superpuestas y estabilidad temporal

## Expected deliverables

- Reporte estructurado de calidad con hard checks y warnings identificables.
- Fixtures positivas/negativas por regla y separación entre métricas y juicio artístico.

## Definition of Done

Cumplir [MOANART.md §25](../../MOANART.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- Un score no debe presentarse como garantía profesional ni como aprobación humana.

## Guía para agentes de IA

**Estado para agentes:** Completado; usar sólo como referencia del contrato entregado.

### 1. Preparación

- Rama: `feat/MOANA-026-crear-informes-calidad` creada desde `develop` actualizado: `git switch develop && git pull --ff-only && git switch -c feat/MOANA-026-crear-informes-calidad`.
- Verificar en `docs/issues/catalog.json` que este issue está `ready` y que sus dependencias ([MOANA-014](MOANA-014.md), [MOANA-015](MOANA-015.md), [MOANA-022](MOANA-022.md)) están `done`.
- Entorno: `uv sync --locked` (sin uv global: `sh scripts/bootstrap.sh` y después `sh scripts/uv.sh` en lugar de `uv`).
- Al empezar, cambiar `status` a `in_progress` en el catálogo y regenerar con `uv run python scripts/planning.py`.

### 2. Lectura obligatoria (en orden)

1. `CLAUDE.md` (Claude Code) o `AGENTS.md` (Codex) y [flujo de sesión](../guides/agent-workflow.md).
2. MOANART.md: §3 Arquitectura modular; §7 Técnicas profesionales de Pixel Art; §19 Control de calidad gráfico; §25 Definition of Done. Estas secciones son el contrato normativo; ante duda, prevalecen sobre este issue.
3. [Contratos de módulos](../architecture/module-contracts.md) para: `quality`.
4. Estándares: [python](../../docs/standards/python.md), [architecture](../../docs/standards/architecture.md), [testing](../../docs/standards/testing.md), [pixel-art](../../docs/standards/pixel-art.md).
5. Issues de dependencia ([MOANA-014](MOANA-014.md), [MOANA-015](MOANA-015.md), [MOANA-022](MOANA-022.md)): leer su sección Evidence para conocer las APIs ya entregadas; no reimplementarlas.
6. ADR en `docs/architecture/` que mencionen los módulos afectados.

### 3. Requisitos de MOANART.md cubiertos

| ID | Requisito | Secciones | Verificación exigida |
| --- | --- | --- | --- |
| R025 | Evaluación gráfica y diagnósticos | §19 | Hard/soft checks, bbox y supresiones |
| R005 | Técnicas profesionales y calidad artística | §7, §19 | Corpus editable y rúbrica humana documentada |

### 4. Skills y subagentes

| Host | Skills a cargar | Revisión especializada |
| --- | --- | --- |
| Claude Code | `moanart-pixel-art`, `moanart-testing`, `moanart-code-review` | `moanart-pixel-artist`, `moanart-qa-engineer` (sólo lectura; el agente principal integra) |
| Codex | `$moanart-pixel-art`, `$moanart-testing`, `$moanart-code-review` | `moanart_pixel_artist`, `moanart_qa_engineer` |

### 5. Archivos

- Código o documentos a crear/modificar: `src/moanart/quality/`.
- Pruebas: `tests/unit/quality/`.
- No crear módulos ni carpetas sin comportamiento real. No tocar otros módulos salvo exportaciones imprescindibles, justificadas en el PR.

### 6. Plan de pruebas

- T1: Corpus sintético con defectos conocidos y versiones corregidas
- T2: Tests de no mutación, orden estable, regiones superpuestas y estabilidad temporal
- Oráculos independientes (cálculo a mano o fórmula de MOANART.md); nunca copiar la salida de la implementación como expected.
- Incluir casos negativos con el error de dominio esperado y casos borde (vacío, mínimo, máximo, fuera de rango).

### 7. Procedimiento

1. Escribir las pruebas de los criterios AC y T antes o junto con la implementación.
2. Implementar sólo **Scope**; respetar **Out of scope** y las dependencias permitidas de MOANART.md §3.
3. Validación de módulo: `uv run pytest tests/unit/quality/ -q` y `uv run mypy src/`.
4. Validación completa: `uv run python scripts/validate.py` y `uv run python scripts/check_wheel.py`.
5. Revisión: subagentes listados y skill `moanart-code-review`; corregir hallazgos críticos y altos.
6. Si hay salida raster: mostrar el PNG a 1x y ampliado por vecino más cercano; si cambia un golden, presentar expected/actual/diff y justificar.

### 8. Cierre

1. En `docs/issues/catalog.json`, para este issue: `status` → `review` (o `done` tras aprobación); completar `acceptance_evidence` (AC1, AC2), `test_evidence` (T1, T2) y `evidence` con rutas concretas de tests y archivos.
2. Issues que desbloquea ([MOANA-027](MOANA-027.md), [MOANA-033](MOANA-033.md)): si todas sus dependencias quedan `done`, pasarlos a `ready` con `blocking_reason: null`.
3. Ejecutar `uv run python scripts/planning.py` y `uv run python -m scripts.check_repository`.
4. Abrir PR hacia `develop` enlazando este issue de GitHub (`Closes #<número>`), con comandos ejecutados y evidencia por AC/T. El CI completo corre al integrar `develop` en `main`.
5. Commit y push sólo con autorización del usuario. No declarar CI remoto ni aprobación artística humana sin evidencia.

### 9. Prohibido en este issue

- Implementar alcance de otros issues, incluidos los que desbloquea ([MOANA-027](MOANA-027.md), [MOANA-033](MOANA-033.md)).
- Actualizar goldens automáticamente, desactivar checks, editar `uv.lock` a mano o añadir dependencias sin motivo técnico registrado.
- `eval`/`exec`/`pickle`, red o estado global mutable en el núcleo; lecturas de texto sin `encoding="utf-8"`.

## Evidence

- Nuevo paquete moanart.quality (ADR-036; §3 ampliado: depende de core, palette, geometry y techniques; ningún módulo de dominio lo importa): evaluate_quality(image, *, canvas, palette, config, regions, frames, loop, limits, deadline) lee píxeles ya renderizados por protocolo (RasterImage, TimelineFrame), nunca renderiza ni modifica entradas, y devuelve QualityReport canónico con rule set quality-v1, digests, métricas, hallazgos y aviso fijo de que no es puntuación, garantía profesional ni revisión humana.
- Hard checks (error, nunca suprimibles: not_suppressible): canvas_dimensions, alpha_normalized, palette_strict (un hallazgo por valor fuera de paleta strict) y outside_mask (regiones de contención). Advertencias configurables por regla y por región: singleton (agrupados por color por encima de 16), irregular_steps (vía moanart.techniques.analyze_clusters con cluster_connectivity 8 por defecto; la silueta usa 4), color_excess (> 32), noise (≥ 8 singletons y > 50 ‰ del área opaca), temporal_flicker (incluida la costura del bucle) y temporal_change opcional (> 900 ‰ de la unión opaca). Umbrales enteros por mil con floor.
- Métricas sin juicio: colores distintos, área opaca, componentes, clusters, singletons, ‰ de singletons, bbox y por frame digest, píxeles cambiados y ‰. Orden estable regla → región → frame → y, x; configuración canónica (el orden de entrada no cambia los bytes); supresión Suppression(rule_id, region_id) sólo si todos los píxeles del hallazgo están en la región; regiones superpuestas evaluadas por separado.
- Presupuesto: quality_cost admitido antes de crear arrays (frames ≤ 256, ≤ 64 regiones, hallazgos acotados por regla con tope listado de 4096, mínimo garantizado de 64 por regla y recuentos omitidos por regla; frames de tamaño distinto al lienzo no se leen); deadline por fila, región y frame; picos tracemalloc medidos bajo la estimación en imágenes de alta entropía.
- Fachada moanart.api.evaluate_quality(document, *, config, animation_id, limits, deadline): animación desconocida rechazada antes de renderizar; render base, máscaras de región, frames de animación y quality_cost admitidos contra un único presupuesto; sin CLI (MOANA-033).
- Los 12 ejemplos pasan todos los hard checks (también cada frame de bouncing-slime); advertencias registradas en ADR-036 con procedimiento de revisión y digest SHA-256 del informe canónico de cada ejemplo fijado en el test de integración. Documentación: MOANART.md 0.1.24-draft (§3, §13, §19), module-contracts, ADR-036.
- Revisiones de agente: arquitectura, QA y pixel-art con cambios aplicados (conectividad de clusters, agrupación, ruido relativo al área, temporal_change opcional, presupuesto único, memoria acotada); revisión artística humana PENDIENTE. Gate local macOS: scripts/validate.py verde con src/moanart al 100 %, check_wheel OK, mypy --platform win32 OK, pre-commit OK; matriz pendiente en main.
- Aprobado por el propietario el 2026-11-17 tras revisión; PR #66 hacia develop.
- AC1: tests/unit/quality/test_quality_rules.py::test_ac1_off_palette_is_an_error_and_a_singleton_a_warning y los casos off_palette/singleton de ::test_t1_defect_reports_the_expected_finding.
- AC2: tests/unit/quality/test_quality_report.py::test_ac2_suppressing_one_eye_hides_only_that_eye, ::test_ac2_errors_in_a_suppressed_region_stay_active, ::test_suppression_never_hides_a_finding_with_pixels_outside_its_region, ::test_ac2_report_is_identical_across_runs; tests/unit/api/test_api_quality.py::test_ac2_report_is_identical_across_processes_and_hash_seeds (PYTHONHASHSEED 0 y 1234).
- T1: tests/unit/quality/test_quality_rules.py::test_t1_defect_reports_the_expected_finding y ::test_t1_corrected_version_has_no_finding_of_that_rule sobre el corpus sintético tests/fixtures/quality.py (defectos contados a mano y versiones corregidas), ::test_metrics_match_independent_counts (búsqueda independiente), ::test_singletons_are_grouped_per_colour_above_the_listing_limit.
- T2: tests/unit/quality/test_quality_report.py::test_t2_inputs_are_not_modified, ::test_t2_report_bytes_do_not_depend_on_configuration_order, ::test_findings_follow_rule_region_frame_y_x, ::test_t2_overlapping_regions_each_count_the_shared_pixel, ::test_t2_shared_pixel_is_suppressed_by_the_first_region_in_canonical_order, ::test_cap_keeps_every_rule_before_filling_in_report_order, ::test_measured_memory_of_a_high_entropy_image_stays_within_the_estimate; tests/unit/quality/test_quality_rules.py::test_loop_compares_the_seam_from_the_last_frame_to_the_first; tests/unit/api/test_api_quality.py::test_t2_temporal_stability_of_the_bouncing_slime, ::test_quality_never_modifies_the_document, ::test_whole_request_is_admitted_against_one_budget; tests/integration/test_quality_examples.py::test_example_report_matches_its_pinned_digest.
