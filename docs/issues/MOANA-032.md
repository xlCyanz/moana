# MOANA-032 — Optimizar caché y render incremental acotados

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-032
- Aliases históricos: MOA-032
- Phase: P5
- Priority: P2
- Status: review
- Complexity: L (relativa, no estimación de tiempo)
- Dependencies: [MOANA-018](MOANA-018.md), [MOANA-031](MOANA-031.md)
- Related modules: render
- Requirements: R029, R028, R015 ([trazabilidad](traceability.md))
- Bloqueo: Ninguno

## Context

La optimización debe conservar semántica, presupuesto e inmutabilidad.

## Objective

Reducir trabajo sólo donde exista beneficio medido sin cambiar RGBA.

## Scope

Agregar caché LRU por bytes y dirty regions únicamente donde el benchmark demuestre beneficio.

## Out of scope

No paralelismo ni optimizaciones sin mejora medible; justificar si el benchmark no aconseja caché.

## Technical requirements

- Clave incluye documento/dependencias, renderer/backend/lock y frame
- Nunca filtrar buffers mutables; invalidar dependencias transitivas y limitar temporales

## Proposed implementation

- Elegir caché/dirty regions después del benchmark y documentar decisión
- Probar invalidación transitiva, LRU por bytes y equivalencia on/off

## Acceptance criteria

- [ ] AC1: Caché on/off produce RGBA y reportes idénticos
- [ ] AC2: Una edición cambia todos sus consumidores y la caché no supera el límite configurado

## Required tests

- [ ] T1: Comparar render completo/incremental para cambios de paleta, máscara, grupo y orden
- [ ] T2: Evicción LRU, versiones distintas, mutación externa impedida y benchmark antes/después

## Expected deliverables

- Caché e invalidación incremental acotadas por snapshot, parámetros y recursos.
- Comparaciones cold/warm y caché on/off con igualdad RGBA y mediciones de coste.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- Si no hay beneficio, documentar decisión de no introducir caché y su evidencia.

## Guía para agentes de IA

**Estado para agentes:** En revisión: sólo correcciones de la revisión; no añadir alcance.

### 1. Preparación

- Rama: `feat/MOANA-032-optimizar-cache-render` creada desde `develop` actualizado: `git switch develop && git pull --ff-only && git switch -c feat/MOANA-032-optimizar-cache-render`.
- Verificar en `docs/issues/catalog.json` que este issue está `ready` y que sus dependencias ([MOANA-018](MOANA-018.md), [MOANA-031](MOANA-031.md)) están `done`.
- Entorno: `uv sync --locked` (sin uv global: `sh scripts/bootstrap.sh` y después `sh scripts/uv.sh` en lugar de `uv`).
- Al empezar, cambiar `status` a `in_progress` en el catálogo y regenerar con `uv run python scripts/planning.py`.

### 2. Lectura obligatoria (en orden)

1. `CLAUDE.md` (Claude Code) o `AGENTS.md` (Codex) y [flujo de sesión](../guides/agent-workflow.md).
2. MOANA.md: §3 Arquitectura modular; §14 Renderizado y determinismo; §22 Rendimiento y optimización; §25 Definition of Done. Estas secciones son el contrato normativo; ante duda, prevalecen sobre este issue.
3. [Contratos de módulos](../architecture/module-contracts.md) para: `render`.
4. Estándares: [python](../../docs/standards/python.md), [architecture](../../docs/standards/architecture.md), [testing](../../docs/standards/testing.md).
5. Issues de dependencia ([MOANA-018](MOANA-018.md), [MOANA-031](MOANA-031.md)): leer su sección Evidence para conocer las APIs ya entregadas; no reimplementarlas.
6. ADR en `docs/architecture/` que mencionen los módulos afectados.

### 3. Requisitos de MOANA.md cubiertos

| ID | Requisito | Secciones | Verificación exigida |
| --- | --- | --- | --- |
| R029 | Caché e incrementalidad | §22 | Equivalencia caché on/off y límites LRU |
| R028 | Rendimiento y recursos medidos | §22 | Benchmark reproducible y memoria acotada |
| R015 | Renderizado determinista | §14 | Digests RGBA en procesos/OS y semillas distintas |

### 4. Skills y subagentes

| Host | Skills a cargar | Revisión especializada |
| --- | --- | --- |
| Claude Code | `moana-graphics`, `moana-architecture`, `moana-code-review` | `moana-graphics-engineer`, `moana-architect` (sólo lectura; el agente principal integra) |
| Codex | `$moana-graphics`, `$moana-architecture`, `$moana-code-review` | `moana_graphics_engineer`, `moana_architect` |

### 5. Archivos

- Código o documentos a crear/modificar: `src/moana/render/`.
- Pruebas: `tests/unit/render/`.
- No crear módulos ni carpetas sin comportamiento real. No tocar otros módulos salvo exportaciones imprescindibles, justificadas en el PR.

### 6. Plan de pruebas

- T1: Comparar render completo/incremental para cambios de paleta, máscara, grupo y orden
- T2: Evicción LRU, versiones distintas, mutación externa impedida y benchmark antes/después
- Oráculos independientes (cálculo a mano o fórmula de MOANA.md); nunca copiar la salida de la implementación como expected.
- Incluir casos negativos con el error de dominio esperado y casos borde (vacío, mínimo, máximo, fuera de rango).

### 7. Procedimiento

1. Escribir las pruebas de los criterios AC y T antes o junto con la implementación.
2. Implementar sólo **Scope**; respetar **Out of scope** y las dependencias permitidas de MOANA.md §3.
3. Validación de módulo: `uv run pytest tests/unit/render/ -q` y `uv run mypy src/`.
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

- Medición previa (ADR-038, macOS arm64): render estático de 32 capas/500 rects ≈ 29–30 ms (relleno ≈ 17 ms, composición ≈ 7 ms); animación de 16 frames ≈ 857 ms, de los que ≈ 360 ms son la doble evaluación de cada frame (admisión y render), y la mitad de cada evaluación es editing.index_nodes reconstruido por comando (fuera de alcance, seguimiento propuesto).
- Decisión: caché opcional y desactivada por defecto de buffers de capa terminados `moana.render.RenderCache(max_bytes)` (1 B–256 MiB, LRU por bytes, entrada = longitud + 256 B, entradas mayores que el límite rechazadas, CacheStats). Parámetro `cache=None` en render, render_admitted, render_sequence, animation.render_animation y render_frame; protocolo `moana.layers.LayerBuffers` en compose. Ganancias medidas: re-render tras editar un rect −41 %, apply_edit + render −35 %, animación −12 %; coste en frío +5 % (motivo para dejarla desactivada). Rechazadas con números: retener frames evaluados (rompe el streaming acotado de ADR-032), dirty rects (domina la composición), caché por operación o prefijo compuesto.
- Clave privada versionada `moana-layer-cache/1`: SHA-256 del JSON canónico de versiones de renderer/backend/estimador/RNG, NumPy y AggDraw/Pillow si hay paths, lienzo, perfil y semilla, la capa sin name/locked/visible/opacity, el cierre transitivo de máscaras y el RGBA resuelto de cada color y rampa referenciados (bandas y segmentos incluidos); opacidad, visibilidad y orden no invalidan. Entradas `bytes` copiadas al insertar, vistas de sólo lectura en los aciertos; plan_budget, el chequeo de composición y el deadline corren antes de cualquier acierto. Sin fachada ni CLI; no thread-safe (documentado).
- Revisiones de agente: gráficos (3364 renders cacheados con mutaciones encadenadas sobre los 17 ejemplos y animaciones, 0 divergencias) y arquitectura (sin imports prohibidos ni ciclos) aprobadas; correcciones aplicadas (clave privada, test de grupos a nivel de layers, memo del cierre de máscaras con clave idéntica, errores separados). Documentación: ADR-038, MOANA.md 0.1.26-draft (§14, §22), module-contracts, ADR-017/018/032 ampliados. Benchmark por defecto sin cambios (static 29,78 → 29,93 ms; animación 852,2 → 850,8 ms; compare ok). Gate local macOS: scripts/validate.py 3661 passed con src/moana al 100 %, check_wheel OK, mypy --platform win32 OK, pre-commit OK; matriz pendiente en main.
- AC1: tests/unit/render/test_render_cache.py::test_ac1_cold_and_warm_renders_equal_the_uncached_render y ::test_t1_incremental_render_equals_full_render (igualdad completa de RenderResult: RGBA, digest, advertencias y procedencia).
- AC2: tests/unit/render/test_render_cache.py::test_ac2_an_edit_changes_the_key_of_every_consumer_and_only_them, ::test_ac2_a_mask_edit_repaints_both_consumers_and_reuses_the_rest, ::test_ac2_a_cache_smaller_than_the_document_stays_bounded_and_exact, ::test_ac2_memoised_keys_equal_the_written_out_recipe, ::test_t2_property_lru_model_and_limit_after_every_insert (límite comprobado tras cada inserción).
- T1: tests/unit/render/test_render_cache.py::test_t1_incremental_render_equals_full_render[palette_ramp_colour|palette_shared_colour|mask_leaf_geometry|mask_combination_operands|layer_visibility|layer_opacity|layer_mask_reference|layer_order|operation_parameter|operation_colour_reference|operation_geometry|seed], ::test_t1_groups_with_opacity_and_nesting_reuse_layer_buffers_exactly (grupos a nivel de layers: el documento 1.0 no tiene grupos), ::test_t1_animation_frames_cached_equal_uncached.
- T2: tests/unit/render/test_render_cache.py::test_t2_lru_evicts_the_least_recently_used_entry_first, ::test_t2_property_lru_model_and_limit_after_every_insert, ::test_t2_another_version_never_reuses_an_entry, ::test_t2_mutating_the_inserted_buffer_does_not_change_the_entry, ::test_t2_budgets_are_enforced_before_any_hit; benchmark antes/después con caché desactivada en ADR-038 (compare ok).
