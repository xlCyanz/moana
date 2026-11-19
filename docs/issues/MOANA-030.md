# MOANA-030 — Ejercitar amenazas y entradas adversarias

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-030
- Aliases históricos: MOA-030
- Phase: P5
- Priority: P0
- Status: review
- Complexity: L (relativa, no estimación de tiempo)
- Dependencies: [MOANA-003](MOANA-003.md), [MOANA-020](MOANA-020.md), [MOANA-021](MOANA-021.md), [MOANA-022](MOANA-022.md)
- Related modules: tests.security
- Requirements: R026, R027 ([trazabilidad](traceability.md))
- Bloqueo: Ninguno

## Context

Los límites nominales pueden saltarse con combinaciones maliciosas.

## Objective

Demostrar rechazo previo a buffers/IO para las fronteras del threat model.

## Scope

Implementar suite de seguridad y propiedades de rechazo para JSON, proyectos, assets, referencias y edición.

## Out of scope

No pentest de servicios externos ni garantía de aislamiento in-process para llamadas nativas bloqueadas.

## Technical requirements

- Generadores acotados Hypothesis y corpus malicioso versionado sin payload ejecutable
- Verificar no reserva/IO previo al rechazo, preservación de destino y errores sin secretos

## Proposed implementation

- Construir corpus adversario acotado y generadores de propiedades
- Instrumentar allocation/IO y límites del proceso de tests

## Acceptance criteria

- [ ] AC1: Todas las fronteras del threat model tienen caso reproducible y mitigación ejercitada
- [ ] AC2: Solicitudes hostiles fallan bajo límites de tiempo/memoria de test y no dejan salida parcial

## Required tests

- [ ] T1: Duplicados JSON, nesting, ciclos, NaN, tamaños enormes y ZIP traversal/bomb
- [ ] T2: Monkeypatch de asignación/IO, mutación parcial de batch, decode enorme y fallo de checksum

## Expected deliverables

- Suite adversaria de documentos, assets, rutas y presupuestos del motor.
- Casos que verifican rechazo antes de asignación/efectos y resumen de amenazas cubiertas.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- Las pruebas hostiles deben ser acotadas y nunca desactivar protecciones de Pillow.

## Guía para agentes de IA

**Estado para agentes:** En revisión: sólo correcciones de la revisión; no añadir alcance.

### 1. Preparación

- Rama: `feat/MOANA-030-ejercitar-amenazas-entradas` creada desde `develop` actualizado: `git switch develop && git pull --ff-only && git switch -c feat/MOANA-030-ejercitar-amenazas-entradas`.
- Verificar en `docs/issues/catalog.json` que este issue está `ready` y que sus dependencias ([MOANA-003](MOANA-003.md), [MOANA-020](MOANA-020.md), [MOANA-021](MOANA-021.md), [MOANA-022](MOANA-022.md)) están `done`.
- Entorno: `uv sync --locked` (sin uv global: `sh scripts/bootstrap.sh` y después `sh scripts/uv.sh` en lugar de `uv`).
- Al empezar, cambiar `status` a `in_progress` en el catálogo y regenerar con `uv run python scripts/planning.py`.

### 2. Lectura obligatoria (en orden)

1. `CLAUDE.md` (Claude Code) o `AGENTS.md` (Codex) y [flujo de sesión](../guides/agent-workflow.md).
2. MOANA.md: §3 Arquitectura modular; §20 Seguridad y validación; §21 Testing y regresiones visuales; §25 Definition of Done. Estas secciones son el contrato normativo; ante duda, prevalecen sobre este issue.
3. [Contratos de módulos](../architecture/module-contracts.md) para: `tests.security`.
4. Estándares: [testing](../../docs/standards/testing.md), [security](../../docs/standards/security.md).
5. Issues de dependencia ([MOANA-003](MOANA-003.md), [MOANA-020](MOANA-020.md), [MOANA-021](MOANA-021.md), [MOANA-022](MOANA-022.md)): leer su sección Evidence para conocer las APIs ya entregadas; no reimplementarlas.
6. ADR en `docs/architecture/` que mencionen los módulos afectados.

### 3. Requisitos de MOANA.md cubiertos

| ID | Requisito | Secciones | Verificación exigida |
| --- | --- | --- | --- |
| R026 | Validación y seguridad de datos | §20 | Entradas adversarias rechazadas antes de reservar/IO |
| R027 | Testing y regresión visual | §21 | Unit/property/integration y diffs exactos |

### 4. Skills y subagentes

| Host | Skills a cargar | Revisión especializada |
| --- | --- | --- |
| Claude Code | `moana-testing`, `moana-code-review` | `moana-qa-engineer` (sólo lectura; el agente principal integra) |
| Codex | `$moana-testing`, `$moana-code-review` | `moana_qa_engineer` |

### 5. Archivos

- Código o documentos a crear/modificar: `tests/security/`.
- Pruebas: `tests/security/`.
- No crear módulos ni carpetas sin comportamiento real. No tocar otros módulos salvo exportaciones imprescindibles, justificadas en el PR.

### 6. Plan de pruebas

- T1: Duplicados JSON, nesting, ciclos, NaN, tamaños enormes y ZIP traversal/bomb
- T2: Monkeypatch de asignación/IO, mutación parcial de batch, decode enorme y fallo de checksum
- Oráculos independientes (cálculo a mano o fórmula de MOANA.md); nunca copiar la salida de la implementación como expected.
- Incluir casos negativos con el error de dominio esperado y casos borde (vacío, mínimo, máximo, fuera de rango).

### 7. Procedimiento

1. Escribir las pruebas de los criterios AC y T antes o junto con la implementación.
2. Implementar sólo **Scope**; respetar **Out of scope** y las dependencias permitidas de MOANA.md §3.
3. Validación de módulo: `uv run pytest tests/security/ -q` y `uv run mypy src/`.
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

- Suite adversaria tests/security/ sin cambios en src/: guards.py (trampas forbid_allocation/forbid_writes/forbid_effects sobre NumPy zeros/empty/full/ones/*_like/frombuffer/array/asarray/ascontiguousarray/arange/repeat/pad/concatenate/stack/tile/broadcast_to y Pillow new/open/frombytes/frombuffer/fromarray, y sobre os.open/open/replace/rename/mkdir/unlink…; TripwireHit deriva de pytest Failed para que ni un except Exception la oculte ni Hypothesis pierda el ejemplo mínimo; measure/assert_bounded, tree_state, peak_bytes relativo y compatible con tracemalloc activo, assert_clean_error), corpus.py (57 HostileCase generados en memoria, sin binarios ni payload ejecutable, con marcador SECRET que nunca debe aparecer en un error) y coverage.py (mapa frontera → mitigación → tests).
- Cobertura de las 10 fronteras de docs/architecture/SECURITY_MODEL.md (nueva frontera spritesheet → frames): JSON → modelo, modelo → plan, resolución → render, plan → raster, asset → Pillow, ZIP → filesystem, export/proyecto → disco, batch → documento, spritesheet → frames e instalación/CI (uv.lock con sha256 y workflows con token de sólo lectura y acciones fijadas por SHA, análisis estático sin red). test_threat_coverage.py falla si una frontera de la tabla no tiene tests o un test citado no existe.
- AC2: cada rechazo del corpus y de los tests paramétricos de presupuesto, archivo y persistencia se mide con un tope de 2 s y 32 MiB de memoria trazada (máximos medidos 99 ms y 8,01 MiB); propiedades Hypothesis con derandomize=True y deadline explícito; la memoria nativa de Pillow/AggDraw la garantizan las trampas, no los picos. Límites conocidos documentados en tests/security/README.md (bytearray, .copy()/.astype(), os.chmod/utime/ftruncate sin trampa; el saver decide «existe» en el commit para evitar carreras).
- Revisiones de agente QA y Python aplicadas (cotas AC2, peak_bytes con traza previa, TripwireHit visible para Hypothesis, oráculos con reason y pointer, trampas ampliadas, casos de spritesheet, APNG e ICC, helpers deduplicados). Gate local macOS: scripts/validate.py 3499 passed con src/moana al 100 %, pytest tests/security 202 passed (también con PYTHONTRACEMALLOC=1), check_wheel OK, mypy --platform win32 OK, pre-commit OK; matriz pendiente en main (las ramas de rutas Windows sólo corren allí).
- AC1: tests/security/test_threat_coverage.py::test_ac1_every_threat_boundary_has_tests y ::test_ac1_every_mapped_test_exists_and_is_documented (10 fronteras); tests/security/test_corpus.py::test_ac1_t1_corpus_case_is_rejected_before_buffers_and_io (57 casos con trampas de asignación y E/S armadas); tests/security/test_supply_chain.py::test_ac1_every_locked_artifact_is_pinned_by_sha256 y ::test_ac1_ci_has_a_read_only_token_pinned_actions_and_no_secrets; tests/security/test_errors.py::test_ac1_*.
- AC2: tests/security/test_corpus.py::test_ac1_t1_corpus_case_is_rejected_before_buffers_and_io (assert_bounded: < 2 s y < 32 MiB por caso); tests/security/test_budgets.py::test_t2_export_over_budget_writes_nothing_and_allocates_nothing y ::test_t2_hostile_canvas_is_rejected_within_bounded_memory; tests/security/test_archives.py (todos vía _load_hostile acotado); tests/security/test_persistence.py::test_t2_existing_destination_is_never_replaced_implicitly y ::test_t2_property_injected_io_failure_keeps_the_previous_output (árbol byte a byte idéntico, sin temporales); tests/security/test_guards.py::test_peak_bytes_is_relative_and_keeps_an_outer_trace_running.
- T1: tests/security/test_documents.py::test_t1_property_duplicate_member_is_located_wherever_planted, ::test_t1_property_nesting_beyond_32_is_rejected_before_parsing, ::test_t1_property_mask_reference_cycles_never_reach_the_renderer, ::test_t1_mask_reference_chain_beyond_depth_16_is_rejected, ::test_t1_property_nan_and_infinity_are_rejected_anywhere; tests/security/test_archives.py::test_t1_property_traversal_names_are_refused_before_extraction, ::test_t1_declared_ratio_bomb_is_refused_before_decompression, ::test_t1_expanded_total_is_budgeted_before_any_entry_is_decompressed; tests/security/test_budgets.py::test_t1_*; casos zip-*, json-* y sheet-* del corpus.
- T2: tests/security/test_guards.py::test_t2_allocation_tripwire_fires_on_numpy_and_pillow y ::test_t2_tripwire_is_not_swallowed_by_except_exception (controles positivos); tests/security/test_persistence.py::test_t2_property_injected_io_failure_keeps_the_previous_output (fallo inyectado en cada os.write/os.fsync); tests/security/test_editing.py::test_t2_property_failing_command_anywhere_mutates_nothing; tests/security/test_assets_integrity.py::test_t2_bomb_headers_are_rejected_before_pillow, ::test_t2_checksum_failure_of_any_stored_file_loads_nothing, ::test_t2_tampered_spritesheet_atlas_fails_its_digests.
