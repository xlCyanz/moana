# MOANA-031 — Medir rendimiento y memoria de referencia

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-031
- Aliases históricos: MOA-031
- Phase: P5
- Priority: P1
- Status: done
- Complexity: M (relativa, no estimación de tiempo)
- Dependencies: [MOANA-010](MOANA-010.md), [MOANA-022](MOANA-022.md), [MOANA-027](MOANA-027.md)
- Related modules: benchmarks
- Requirements: R028 ([trazabilidad](traceability.md))
- Bloqueo: Ninguno

## Context

No hay objetivos de rendimiento verificados antes de medir corpus real.

## Objective

Publicar latencia/memoria reproducibles y contexto de hardware.

## Scope

Crear benchmark repetible del corpus de §22 y registrar hardware, versiones, warmups, mediana, p95 y memoria.

## Out of scope

No optimización GPU/JIT/paralela antes de disponer de mediciones.

## Technical requirements

- Separar render de I/O, 5 warmups y 30 muestras; buffers y proceso identificados
- Objetivos informativos hasta runner estable; no esconder regresión con tolerancia arbitraria

## Proposed implementation

- Separar render de I/O y medir warmups/muestras de §22
- Registrar mediana/p95/pico y comparar la misma carga sin caché engañosa

## Acceptance criteria

- [x] AC1: Reporte reproducible indica si 100 ms/2 s/256 MiB se cumplen y en qué máquina
- [x] AC2: Casos adversos respetan presupuestos aunque incumplan objetivo de latencia

## Required tests

- [x] T1: Benchmark estático 32 capas/500 rects y animación 16 frames
- [x] T2: Comprobar contadores, ausencia de trabajo eliminado por caché y comparabilidad de versiones

## Expected deliverables

- Benchmarks reproducibles con warmups, muestras, mediana/p95 y memoria.
- Corpus y reporte de entorno/lock, diferenciando coste de render e I/O.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- No usar fluctuaciones de runners compartidos como gate rígido sin estabilizar entorno.

## Guía para agentes de IA

**Estado para agentes:** Completado; usar sólo como referencia del contrato entregado.

### 1. Preparación

- Rama: `feat/MOANA-031-medir-rendimiento-memoria` creada desde `develop` actualizado: `git switch develop && git pull --ff-only && git switch -c feat/MOANA-031-medir-rendimiento-memoria`.
- Verificar en `docs/issues/catalog.json` que este issue está `ready` y que sus dependencias ([MOANA-010](MOANA-010.md), [MOANA-022](MOANA-022.md), [MOANA-027](MOANA-027.md)) están `done`.
- Entorno: `uv sync --locked` (sin uv global: `sh scripts/bootstrap.sh` y después `sh scripts/uv.sh` en lugar de `uv`).
- Al empezar, cambiar `status` a `in_progress` en el catálogo y regenerar con `uv run python scripts/planning.py`.

### 2. Lectura obligatoria (en orden)

1. `CLAUDE.md` (Claude Code) o `AGENTS.md` (Codex) y [flujo de sesión](../guides/agent-workflow.md).
2. MOANA.md: §3 Arquitectura modular; §22 Rendimiento y optimización; §25 Definition of Done. Estas secciones son el contrato normativo; ante duda, prevalecen sobre este issue.
3. [Contratos de módulos](../architecture/module-contracts.md) para: `benchmarks`.
4. Estándares: [testing](../../docs/standards/testing.md).
5. Issues de dependencia ([MOANA-010](MOANA-010.md), [MOANA-022](MOANA-022.md), [MOANA-027](MOANA-027.md)): leer su sección Evidence para conocer las APIs ya entregadas; no reimplementarlas.
6. ADR en `docs/architecture/` que mencionen los módulos afectados.

### 3. Requisitos de MOANA.md cubiertos

| ID | Requisito | Secciones | Verificación exigida |
| --- | --- | --- | --- |
| R028 | Rendimiento y recursos medidos | §22 | Benchmark reproducible y memoria acotada |

### 4. Skills y subagentes

| Host | Skills a cargar | Revisión especializada |
| --- | --- | --- |
| Claude Code | `moana-testing`, `moana-code-review` | `moana-qa-engineer`, `moana-python-engineer` (sólo lectura; el agente principal integra) |
| Codex | `$moana-testing`, `$moana-code-review` | `moana_qa_engineer`, `moana_python_engineer` |

### 5. Archivos

- Código o documentos a crear/modificar: `tests/benchmarks/`.
- Pruebas: `tests/benchmarks/`.
- No crear módulos ni carpetas sin comportamiento real. No tocar otros módulos salvo exportaciones imprescindibles, justificadas en el PR.

### 6. Plan de pruebas

- T1: Benchmark estático 32 capas/500 rects y animación 16 frames
- T2: Comprobar contadores, ausencia de trabajo eliminado por caché y comparabilidad de versiones
- Oráculos independientes (cálculo a mano o fórmula de MOANA.md); nunca copiar la salida de la implementación como expected.
- Incluir casos negativos con el error de dominio esperado y casos borde (vacío, mínimo, máximo, fuera de rango).

### 7. Procedimiento

1. Escribir las pruebas de los criterios AC y T antes o junto con la implementación.
2. Implementar sólo **Scope**; respetar **Out of scope** y las dependencias permitidas de MOANA.md §3.
3. Validación de módulo: `uv run pytest tests/benchmarks/ -q` y `uv run mypy src/`.
4. Validación completa: `uv run python scripts/validate.py` y `uv run python scripts/check_wheel.py`.
5. Revisión: subagentes listados y skill `moana-code-review`; corregir hallazgos críticos y altos.
6. Si hay salida raster: mostrar el PNG a 1x y ampliado por vecino más cercano; si cambia un golden, presentar expected/actual/diff y justificar.

### 8. Cierre

1. En `docs/issues/catalog.json`, para este issue: `status` → `review` (o `done` tras aprobación); completar `acceptance_evidence` (AC1, AC2), `test_evidence` (T1, T2) y `evidence` con rutas concretas de tests y archivos.
2. Issues que desbloquea ([MOANA-032](MOANA-032.md)): si todas sus dependencias quedan `done`, pasarlos a `ready` con `blocking_reason: null`.
3. Ejecutar `uv run python scripts/planning.py` y `uv run python -m scripts.check_repository`.
4. Abrir PR hacia `develop` enlazando este issue de GitHub (`Closes #<número>`), con comandos ejecutados y evidencia por AC/T. El CI completo corre al integrar `develop` en `main`.
5. Commit y push sólo con autorización del usuario. No declarar CI remoto ni aprobación artística humana sin evidencia.

### 9. Prohibido en este issue

- Implementar alcance de otros issues, incluidos los que desbloquea ([MOANA-032](MOANA-032.md)).
- Actualizar goldens automáticamente, desactivar checks, editar `uv.lock` a mano o añadir dependencias sin motivo técnico registrado.
- `eval`/`exec`/`pickle`, red o estado global mutable en el núcleo; lecturas de texto sin `encoding="utf-8"`.

## Evidence

- Benchmark informativo de MOANA.md §22 en tests/benchmarks/ sin cambios en src/: corpus programático (static 128×128 strict con 32 capas y 500 rects; animation con 16 frames de igual complejidad, 32 translate + 8 set_color distintos por frame; además los 5 ejemplos de examples/corpus), runner `uv run python -m tests.benchmarks run` con un subproceso nuevo por caso (PYTHONHASHSEED=0, stdin cerrado, timeout proporcional), 5 warmups y 30 muestras, fases parse / render en memoria / render_frame / encode_png / write_png separadas, mediana, p95 por rango más cercano, mín, máx y media; pico RSS por proceso (ru_maxrss en macOS, VmHWM en Linux, null con motivo en Windows) y pico tracemalloc etiquetado como sólo Python.
- Informe canónico `moana-benchmark/1` (JSON con claves ordenadas y resumen Markdown regenerable desde el JSON): CPU, núcleos, arquitectura, SO, Python, numpy/Pillow/aggdraw/pydantic, sha256 de uv.lock, commit y dirty, renderer/backend/estimator y digest del corpus; objetivos 100 ms / 2 s / 256 MiB con met true/false/null y nota de que son informativos; sin hostname, usuario, rutas absolutas ni marca de tiempo (write_report rechaza un informe con fugas). `compare` rechaza informes no comparables (formato, corpus, renderer, backend, estimator, warmups, muestras, casos, fases o informe mal formado) y marca `investigate` si la mediana o el pico RSS suben más de un 20 % (comparación exacta sin división); no es un gate.
- Línea base tests/benchmarks/results/macos-arm64-py312.{json,md} (Apple M4, macOS, CPython 3.12.16; commit 33ee89e con dirty=true porque se midió antes del commit): static 30,11 ms mediana / 30,95 ms p95; secuencia de 16 frames 853,44 ms / 869,82 ms (29,81 ms por frame); pico de proceso 66,8 MiB. Los tres objetivos se cumplen. Hallazgo para MOANA-032 sin optimizar: ~45 % del tiempo de la secuencia es evaluación de frames, no raster.
- Revisiones de agente QA y Python aplicadas (falso positivo de privacidad con el usuario `runner` de GitHub, timeouts, detector de rutas en cualquier posición, comparación exacta y estricta, VmHWM en Linux, Markdown regenerable, tracemalloc relativo). Gate local macOS: scripts/validate.py 3600 passed con src/moana al 100 %, tests/benchmarks 101 passed (también con USER=runner y PYTHONTRACEMALLOC=1), check_wheel OK, mypy --platform win32 OK, pre-commit OK; matriz pendiente en main. Los tests del gate nunca comprueban latencia.
- Aprobado por el propietario el 2026-11-17 tras revisión; PR #70 hacia develop.
- AC1: tests/benchmarks/results/macos-arm64-py312.json y .md (objetivos cumplidos y máquina registrada); tests/benchmarks/test_benchmark_runner.py::test_t1_smoke_report_is_well_formed, ::test_t1_targets_are_stated_with_true_false_or_null, ::test_committed_baseline_summary_regenerates_from_its_json, ::test_privacy_vocabulary_is_not_a_leak, ::test_privacy_findings_detect_leaks_in_the_environment, ::test_write_report_refuses_a_leaking_report.
- AC2: tests/benchmarks/test_benchmark_budgets.py::test_ac2_oversized_static_is_rejected_on_pixel_visits, ::test_ac2_operation_budget_rejects_the_benchmark_corpus, ::test_ac2_cumulative_animation_budget_is_checked_before_any_frame, ::test_ac2_a_request_within_budget_is_not_reported_as_rejected (rechazo con BUDGET_EXCEEDED, 0 llamadas al rasterizador y pico tracemalloc muy por debajo de un buffer RGBA).
- T1: tests/benchmarks/test_benchmark_corpus.py::test_t1_static_case_has_32_layers_and_500_rects, ::test_t1_animation_has_16_frames_of_equal_complexity (oráculos contados sobre el JSON); tests/benchmarks/test_benchmark_runner.py::test_t1_smoke_report_is_well_formed y ::test_t1_animation_reports_the_sequence_and_every_frame.
- T2: tests/benchmarks/test_benchmark_runner.py::test_t2_counters_are_equal_non_zero_and_match_the_json, ::test_t2_every_sample_matches_an_independent_reference, ::test_t2_a_changed_rect_is_drawn_again_with_the_same_work, ::test_t2_the_engine_has_no_memoisation, ::test_stats_against_hand_computed_values; tests/benchmarks/test_benchmark_compare.py::test_t2_a_rise_over_20_percent_is_flagged, ::test_t2_the_20_percent_boundary_is_exact, ::test_t2_non_comparable_reports_are_refused, ::test_t2_malformed_reports_are_refused.
