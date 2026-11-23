# MOANA-010 — Construir pipeline de render determinista

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-010
- Aliases históricos: MOA-010
- Phase: P2
- Priority: P0
- Status: done
- Complexity: L (relativa, no estimación de tiempo)
- Dependencies: [MOANA-002](MOANA-002.md), [MOANA-003](MOANA-003.md), [MOANA-006](MOANA-006.md), [MOANA-009](MOANA-009.md)
- Related modules: render
- Requirements: R015, R030 ([trazabilidad](traceability.md))
- Bloqueo: Ninguno

## Context

La reproducibilidad necesita orden explícito y normalización compartida.

## Objective

Producir RenderResult sin modificar documentos ni acceder a disco.

## Scope

Implementar moanart/render como orquestador validación-resolución-coste-raster-composición y RenderResult inmutable.

## Out of scope

No caché, concurrencia ni optimizaciones sin benchmark.

## Technical requirements

- Canonicalizar defaults/keys y digest dimensional RGBA según §14
- Registro explícito de operaciones; RNG por ID/coordenadas; sin reloj, hash() ni estado global

## Proposed implementation

- Resolver/costear el documento y construir plan estable
- Ejecutar operaciones y calcular digest dimensional/versiones/RNG por identidad

## Acceptance criteria

- [x] AC1: El mismo documento produce RGBA y digest idénticos en procesos nuevos
- [x] AC2: Añadir una operación no cambia la secuencia aleatoria de otra; render no modifica documento ni escribe archivos

## Required tests

- [x] T1: Variar PYTHONHASHSEED, orden de claves de objeto y repetir en subprocesos
- [x] T2: Entradas no soportadas, references inválidas, cancelación entre operaciones y límites previos al render

## Expected deliverables

- Pipeline documento→validación→presupuesto→render y RenderResult inmutable.
- Escenas de integración y manifiesto de decisiones/versiones para reproducción.

## Definition of Done

Cumplir [MOANART.md §25](../../MOANART.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- hash(), reloj o estado global rompen reproducibilidad aunque el primer test pase.

## Guía para agentes de IA

**Estado para agentes:** Completado; usar sólo como referencia del contrato entregado.

### 1. Preparación

- Rama: `feat/MOANA-010-construir-pipeline-render` creada desde `develop` actualizado: `git switch develop && git pull --ff-only && git switch -c feat/MOANA-010-construir-pipeline-render`.
- Verificar en `docs/issues/catalog.json` que este issue está `ready` y que sus dependencias ([MOANA-002](MOANA-002.md), [MOANA-003](MOANA-003.md), [MOANA-006](MOANA-006.md), [MOANA-009](MOANA-009.md)) están `done`.
- Entorno: `uv sync --locked` (sin uv global: `sh scripts/bootstrap.sh` y después `sh scripts/uv.sh` en lugar de `uv`).
- Al empezar, cambiar `status` a `in_progress` en el catálogo y regenerar con `uv run python scripts/planning.py`.

### 2. Lectura obligatoria (en orden)

1. `CLAUDE.md` (Claude Code) o `AGENTS.md` (Codex) y [flujo de sesión](../guides/agent-workflow.md).
2. MOANART.md: §3 Arquitectura modular; §14 Renderizado y determinismo; §25 Definition of Done. Estas secciones son el contrato normativo; ante duda, prevalecen sobre este issue.
3. [Contratos de módulos](../architecture/module-contracts.md) para: `render`.
4. Estándares: [python](../../docs/standards/python.md), [architecture](../../docs/standards/architecture.md), [testing](../../docs/standards/testing.md).
5. Issues de dependencia ([MOANA-002](MOANA-002.md), [MOANA-003](MOANA-003.md), [MOANA-006](MOANA-006.md), [MOANA-009](MOANA-009.md)): leer su sección Evidence para conocer las APIs ya entregadas; no reimplementarlas.
6. ADR en `docs/architecture/` que mencionen los módulos afectados.

### 3. Requisitos de MOANART.md cubiertos

| ID | Requisito | Secciones | Verificación exigida |
| --- | --- | --- | --- |
| R015 | Renderizado determinista | §14 | Digests RGBA en procesos/OS y semillas distintas |
| R030 | Arquitectura modular y documentación | §3 | Dependencias internas y ADR revisados |

### 4. Skills y subagentes

| Host | Skills a cargar | Revisión especializada |
| --- | --- | --- |
| Claude Code | `moanart-graphics`, `moanart-architecture`, `moanart-code-review` | `moanart-graphics-engineer`, `moanart-architect` (sólo lectura; el agente principal integra) |
| Codex | `$moanart-graphics`, `$moanart-architecture`, `$moanart-code-review` | `moanart_graphics_engineer`, `moanart_architect` |

### 5. Archivos

- Código o documentos a crear/modificar: `src/moanart/render/`.
- Pruebas: `tests/unit/render/`.
- No crear módulos ni carpetas sin comportamiento real. No tocar otros módulos salvo exportaciones imprescindibles, justificadas en el PR.

### 6. Plan de pruebas

- T1: Variar PYTHONHASHSEED, orden de claves de objeto y repetir en subprocesos
- T2: Entradas no soportadas, references inválidas, cancelación entre operaciones y límites previos al render
- Oráculos independientes (cálculo a mano o fórmula de MOANART.md); nunca copiar la salida de la implementación como expected.
- Incluir casos negativos con el error de dominio esperado y casos borde (vacío, mínimo, máximo, fuera de rango).

### 7. Procedimiento

1. Escribir las pruebas de los criterios AC y T antes o junto con la implementación.
2. Implementar sólo **Scope**; respetar **Out of scope** y las dependencias permitidas de MOANART.md §3.
3. Validación de módulo: `uv run pytest tests/unit/render/ -q` y `uv run mypy src/`.
4. Validación completa: `uv run python scripts/validate.py` y `uv run python scripts/check_wheel.py`.
5. Revisión: subagentes listados y skill `moanart-code-review`; corregir hallazgos críticos y altos.
6. Si hay salida raster: mostrar el PNG a 1x y ampliado por vecino más cercano; si cambia un golden, presentar expected/actual/diff y justificar.

### 8. Cierre

1. En `docs/issues/catalog.json`, para este issue: `status` → `review` (o `done` tras aprobación); completar `acceptance_evidence` (AC1, AC2), `test_evidence` (T1, T2) y `evidence` con rutas concretas de tests y archivos.
2. Issues que desbloquea ([MOANA-007](MOANA-007.md), [MOANA-011](MOANA-011.md), [MOANA-012](MOANA-012.md), [MOANA-013](MOANA-013.md), [MOANA-018](MOANA-018.md), [MOANA-022](MOANA-022.md), [MOANA-029](MOANA-029.md), [MOANA-031](MOANA-031.md)): si todas sus dependencias quedan `done`, pasarlos a `ready` con `blocking_reason: null`.
3. Ejecutar `uv run python scripts/planning.py` y `uv run python -m scripts.check_repository`.
4. Abrir PR hacia `develop` enlazando este issue de GitHub (`Closes #<número>`), con comandos ejecutados y evidencia por AC/T. El CI completo corre al integrar `develop` en `main`.
5. Commit y push sólo con autorización del usuario. No declarar CI remoto ni aprobación artística humana sin evidencia.

### 9. Prohibido en este issue

- Implementar alcance de otros issues, incluidos los que desbloquea ([MOANA-007](MOANA-007.md), [MOANA-011](MOANA-011.md), [MOANA-012](MOANA-012.md), [MOANA-013](MOANA-013.md), [MOANA-018](MOANA-018.md), [MOANA-022](MOANA-022.md), [MOANA-029](MOANA-029.md), [MOANA-031](MOANA-031.md)).
- Actualizar goldens automáticamente, desactivar checks, editar `uv.lock` a mano o añadir dependencias sin motivo técnico registrado.
- `eval`/`exec`/`pickle`, red o estado global mutable en el núcleo; lecturas de texto sin `encoding="utf-8"`.

## Evidence

- src/moanart/render/pipeline.py: render(document, *, frame_id, limits, deadline) ejecuta validación (revalida el árbol canónico) → frame (sólo None en schema 1.0) → registro explícito de rasterizadores (RENDERABLE_OPERATION_TYPES) → paleta resuelta → plan_budget → LayerTree con máscaras diferidas → compose; sin disco, caché, concurrencia, reloj ni hash().
- src/moanart/render/result.py: RenderResult inmutable (width, height, rgba bytes, digest §14 recalculado, warnings empty_bounds con puntero, renderer_version, provenance) y Provenance como manifiesto de reproducción (snapshot, seed, frame, render-v1, backend integer, budget-v2, RNG, moanart_version).
- src/moanart/layers: DeferredMask para construir una máscara a la vez dentro de compose; src/moanart/render/budget.py: estimador budget-v2 (raster + pasada de pintado sobre mask_box; bytes max(40A, 14A + 80·tile) + máscara).
- src/moanart/core/procedural.py: RNG por celda de §14 (SHA-256 del JSON canónico [seed, operation_id, x, y, channel, version], u = 8 bytes big-endian, u·n//2^64); src/moanart/core/digest.py: digest visual único para Canvas y RenderResult.
- ADR-018 (docs/architecture/decisions/ADR-018-render-pipeline.md); notas de cabecera en ADR-012, ADR-015 y ADR-017; MOANART.md 0.1.7-draft (§13 render disponible con deadline, §20 budget-v2); contratos de módulos, overview, README, guía de desarrollo, AGENTS.md y CLAUDE.md actualizados; probe de check_wheel ampliado.
- Gate: scripts/validate.py y scripts/check_wheel.py verdes; render, layers, core.procedural y core.digest al 100 % de líneas y ramas.
- Revisión: moanart-graphics-engineer y moanart-architect (cambios requeridos, aplicados): cota de bytes en lienzos de 1–3 píxeles, RNG movido a core, digest único, moanart_version, frame_id tras validar y sin puntero, aviso empty_bounds, RuntimeError para cajas diferidas incorrectas, bytes de máscara diferida en composition_cost, colisión de nombres budget-v2 resuelta y pruebas de 1×1, coordenadas negativas, documento vacío y propiedad plan ⇒ render.
- Aprobado por el propietario el 2026-11-17 tras revisión; PR #48 hacia develop.
- AC1: tests/integration/test_render_determinism.py::test_ac1_t1_fresh_processes_with_any_hash_seed_agree (subprocesos nuevos) y ::test_t1_repeated_renders_in_one_process_agree; digests recalculados a mano con hashlib en tests/unit/render/test_render_pipeline.py::test_semitransparent_scene_matches_hand_computation, ::test_every_primitive_in_a_strict_scene y ::test_minimal_example_document.
- AC2: tests/unit/core/test_core_procedural.py::test_ac2_an_operation_sequence_depends_only_on_its_own_identity; tests/unit/render/test_render_pipeline.py::test_ac2_adding_an_operation_only_changes_its_own_pixels, ::test_ac2_render_does_not_modify_the_document y ::test_ac2_render_writes_and_reads_no_file.
- T1: tests/integration/test_render_determinism.py::test_ac1_t1_fresh_processes_with_any_hash_seed_agree (PYTHONHASHSEED 0, 1, 4242 y random × tres codificaciones) y ::test_t1_key_order_and_whitespace_do_not_change_the_render (claves en orden inverso, espacios, sort_keys).
- T2: tests/unit/render/test_render_pipeline.py::test_t2_unsupported_arguments_are_type_errors, ::test_t2_only_documents_are_rendered, ::test_t2_unknown_frame_is_a_reference_error, ::test_t2_invalid_references_are_rejected_with_pointers, ::test_t2_operation_without_rasteriser_is_unsupported, ::test_t2_cancellation_between_operations, ::test_t2_expired_deadline_stops_before_any_raster, ::test_t2_budgets_are_checked_before_any_raster_or_buffer y ::test_plan_budget_admission_means_render_succeeds.
