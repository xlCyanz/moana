# MOANA-036 — Índice incremental de nodos en la edición por batches

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-036
- Aliases históricos: Ninguno
- Phase: P5
- Priority: P2
- Status: review
- Complexity: M (relativa, no estimación de tiempo)
- Dependencies: [MOANA-018](MOANA-018.md), [MOANA-022](MOANA-022.md), [MOANA-031](MOANA-031.md)
- Related modules: editing, animation
- Requirements: R028 ([trazabilidad](traceability.md))
- Bloqueo: Ninguno

## Context

El benchmark de MOANA-031 y la medición de MOANA-032 (ADR-038) mostraron que `editing.index_nodes` se reconstruye para cada comando (src/moana/editing/apply.py) y supone cerca de la mitad de `apply_commands`; la animación evalúa cada frame dos veces (admisión y render), así que domina su coste. El test lineal de ADR-039 fija hoy una reconstrucción por comando.

## Objective

Eliminar la reconstrucción del índice por comando conservando exactamente la semántica de la edición atómica.

## Scope

Sustituir la reconstrucción de `editing.index_nodes` por comando dentro de `apply_commands` por un índice de trabajo mantenido de forma incremental durante el batch (altas, bajas, renombres y movimientos), con resultados, errores y atomicidad idénticos.

## Out of scope

No cambiar el formato de batch, la semántica de comandos, los códigos de error ni el render; sin paralelismo ni caché entre batches o documentos.

## Technical requirements

- El índice incremental debe ser observablemente equivalente a `index_nodes` tras cada comando, incluida la regla de que la primera declaración gana ante IDs duplicados
- Mantener el rechazo atómico, los punteros JSON de error y el orden de `affected_ids`; coste por comando independiente del número de nodos salvo en los comandos que recorren subárboles

## Proposed implementation

- Introducir un índice de trabajo privado en `_Work` actualizado por cada comando que añade, elimina, renombra o mueve nodos, con verificación opcional contra `index_nodes` en tests
- Actualizar el test de linealidad de ADR-039 al nuevo recuento y medir con `python -m tests.benchmarks run|compare` antes y después

## Acceptance criteria

- [ ] AC1: Batches y timelines producen documentos, revisiones, snapshots, errores y RGBA idénticos antes y después del cambio
- [ ] AC2: El coste de `apply_commands` deja de crecer como comandos × nodos y la animación de 16 frames del benchmark mejora de forma medida

## Required tests

- [ ] T1: Propiedad: tras cada comando de batches aleatorios deterministas el índice incremental coincide con `index_nodes` recalculado, incluidos fallos a mitad de batch
- [ ] T2: Recuento de operaciones (sin reloj) que fije índices O(1) por comando y benchmark antes/después de MOANA.md §22 con `compare`

## Expected deliverables

- Índice incremental privado en `moana.editing` con equivalencia probada frente a la reconstrucción completa.
- Benchmark antes/después archivado y decisión registrada (ADR nuevo o ampliación) si cambia un contrato de rendimiento.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- Un índice desincronizado podría resolver IDs obsoletos: la prueba de propiedad debe cubrir cada comando que modifica la estructura, también en fallos y rollback.

## Guía para agentes de IA

**Estado para agentes:** En revisión: sólo correcciones de la revisión; no añadir alcance.

### 1. Preparación

- Rama: `feat/MOANA-036-indice-incremental-nodos` creada desde `develop` actualizado: `git switch develop && git pull --ff-only && git switch -c feat/MOANA-036-indice-incremental-nodos`.
- Verificar en `docs/issues/catalog.json` que este issue está `ready` y que sus dependencias ([MOANA-018](MOANA-018.md), [MOANA-022](MOANA-022.md), [MOANA-031](MOANA-031.md)) están `done`.
- Entorno: `uv sync --locked` (sin uv global: `sh scripts/bootstrap.sh` y después `sh scripts/uv.sh` en lugar de `uv`).
- Al empezar, cambiar `status` a `in_progress` en el catálogo y regenerar con `uv run python scripts/planning.py`.

### 2. Lectura obligatoria (en orden)

1. `CLAUDE.md` (Claude Code) o `AGENTS.md` (Codex) y [flujo de sesión](../guides/agent-workflow.md).
2. MOANA.md: §3 Arquitectura modular; §22 Rendimiento y optimización; §25 Definition of Done. Estas secciones son el contrato normativo; ante duda, prevalecen sobre este issue.
3. [Contratos de módulos](../architecture/module-contracts.md) para: `editing`, `animation`.
4. Estándares: [python](../../docs/standards/python.md), [architecture](../../docs/standards/architecture.md), [testing](../../docs/standards/testing.md), [pixel-art](../../docs/standards/pixel-art.md).
5. Issues de dependencia ([MOANA-018](MOANA-018.md), [MOANA-022](MOANA-022.md), [MOANA-031](MOANA-031.md)): leer su sección Evidence para conocer las APIs ya entregadas; no reimplementarlas.
6. ADR en `docs/architecture/` que mencionen los módulos afectados.

### 3. Requisitos de MOANA.md cubiertos

| ID | Requisito | Secciones | Verificación exigida |
| --- | --- | --- | --- |
| R028 | Rendimiento y recursos medidos | §22 | Benchmark reproducible y memoria acotada |

### 4. Skills y subagentes

| Host | Skills a cargar | Revisión especializada |
| --- | --- | --- |
| Claude Code | `moana-python`, `moana-architecture`, `moana-graphics`, `moana-pixel-art`, `moana-code-review` | `moana-python-engineer`, `moana-architect`, `moana-graphics-engineer`, `moana-pixel-artist` (sólo lectura; el agente principal integra) |
| Codex | `$moana-python`, `$moana-architecture`, `$moana-graphics`, `$moana-pixel-art`, `$moana-code-review` | `moana_python_engineer`, `moana_architect`, `moana_graphics_engineer`, `moana_pixel_artist` |

### 5. Archivos

- Código o documentos a crear/modificar: `src/moana/editing/`, `src/moana/animation/`.
- Pruebas: `tests/unit/editing/`, `tests/unit/animation/`.
- No crear módulos ni carpetas sin comportamiento real. No tocar otros módulos salvo exportaciones imprescindibles, justificadas en el PR.

### 6. Plan de pruebas

- T1: Propiedad: tras cada comando de batches aleatorios deterministas el índice incremental coincide con `index_nodes` recalculado, incluidos fallos a mitad de batch
- T2: Recuento de operaciones (sin reloj) que fije índices O(1) por comando y benchmark antes/después de MOANA.md §22 con `compare`
- Oráculos independientes (cálculo a mano o fórmula de MOANA.md); nunca copiar la salida de la implementación como expected.
- Incluir casos negativos con el error de dominio esperado y casos borde (vacío, mínimo, máximo, fuera de rango).

### 7. Procedimiento

1. Escribir las pruebas de los criterios AC y T antes o junto con la implementación.
2. Implementar sólo **Scope**; respetar **Out of scope** y las dependencias permitidas de MOANA.md §3.
3. Validación de módulo: `uv run pytest tests/unit/editing/ tests/unit/animation/ -q` y `uv run mypy src/`.
4. Validación completa: `uv run python scripts/validate.py` y `uv run python scripts/check_wheel.py`.
5. Revisión: subagentes listados y skill `moana-code-review`; corregir hallazgos críticos y altos.
6. Si hay salida raster: mostrar el PNG a 1x y ampliado por vecino más cercano; si cambia un golden, presentar expected/actual/diff y justificar.

### 8. Cierre

1. En `docs/issues/catalog.json`, para este issue: `status` → `review` (o `done` tras aprobación); completar `acceptance_evidence` (AC1, AC2), `test_evidence` (T1, T2) y `evidence` con rutas concretas de tests y archivos.
2. Issues que desbloquea (ninguno): si todas sus dependencias quedan `done`, pasarlos a `ready` con `blocking_reason: null`.
3. Ejecutar `uv run python scripts/planning.py` y `uv run python -m scripts.check_repository`.
4. Abrir PR hacia `develop` enlazando este issue de GitHub (`Closes #<número>`), con comandos ejecutados y evidencia por AC/T. El CI completo corre al integrar `develop` en `main`.
5. Commit y push sólo con autorización del usuario. No declarar CI remoto ni aprobación artística humana sin evidencia.

### 9. Prohibido en este issue

- Implementar alcance de otros issues, incluidos los que desbloquea (ninguno).
- Actualizar goldens automáticamente, desactivar checks, editar `uv.lock` a mano o añadir dependencias sin motivo técnico registrado.
- `eval`/`exec`/`pickle`, red o estado global mutable en el núcleo; lecturas de texto sin `encoding="utf-8"`.

## Evidence

- Índice privado moana.editing._tree.WorkingIndex dentro de _Work: se construye una vez por batch en la primera consulta (perezoso, para conservar invalid_source en el puntero del primer comando) y cada comando estructural lo actualiza: insert_operation (operación y sus bandas/segmentos), remove (destino, operaciones e items retirados), set_geometry/set_parameters (objetos reemplazados, sin cambio de IDs), reorder (sin cambio con IDs únicos); set_color/translate/set_visibility/replace_palette_color mutan en el sitio. is_color sustituye la reconstrucción de la paleta por comando. Con IDs duplicados (origen sin validar) cada cambio estructural reconstruye entero y la primera declaración sigue ganando. Rollback atómico sin trabajo extra: el índice muere con _Work. Un índice desincronizado falla como AssertionError interno, nunca como invalid_source. index_nodes se conserva como referencia.
- Benchmark MOANA.md §22 (macOS arm64, 5 warmups + 30 muestras; antes sobre eb0d177 limpio, después sin otra carga; compare ok en todas las filas): animación de 16 frames 874,9 → 658,8 ms (−24,7 %), corpus adventurer-walk 72,6 → 46,4 ms (−36,2 %), render estático 30,6 → 29,9 ms (ruido), tracemalloc idéntico. La línea base versionada de tests/benchmarks/results no se regenera aquí (se mide sobre un commit integrado limpio en un cambio aparte).
- ADR-040 (decisión, pruebas, mediciones, costes que siguen: Node.position O(hermanos), live_references de remove O(nodos), reconstrucción con IDs duplicados); ADR-024 y ADR-039 «Ampliado por ADR-040»; module-contracts (coste de apply_batch). RELEASE.md: el run 44783751159 del candidato terminó verde 9/9 más determinismo.
- Revisiones de agente Python y arquitectura aprobadas sin hallazgos medios ni altos; correcciones bajas aplicadas. Gate local macOS: scripts/validate.py 3851 passed con src/moana al 100 %, check_wheel OK, mypy --platform win32 OK, release.py check OK, pre-commit OK; matriz pendiente en main.
- AC1: tests/unit/editing/test_editing_index.py::test_ac1_example_batches_match_the_rebuilding_editor (todos los examples/**/*.edit.json, incluido el digest de render), ::test_ac1_timelines_match_the_rebuilding_editor (bouncing-slime, adventurer-walk y animación del benchmark: documentos evaluados, RGBA y digest de cada frame) y ::test_ac1_failing_override_reports_the_same_error, contra RebuildingIndex (el algoritmo anterior conservado sólo en el test).
- AC2: tests/unit/editing/test_editing_apply.py::test_worst_case_translate_batch_stays_linear (256 y 1024 comandos: una construcción del índice por batch, nodos indexados = objetos con id contados aparte, una consulta por comando, cero revalidaciones de nodo y una del documento) y benchmark antes/después de ADR-040 (animación −24,7 %).
- T1: tests/unit/editing/test_editing_index.py::test_t1_index_matches_a_fresh_rebuild_after_every_command (Hypothesis derandomize, 1000 ejemplos sobre specs, corpus, tiles y tutorial; tras cada comando, éxito o fallo, el índice = index_nodes recalculado y el resultado o error completo = RebuildingIndex), ::test_t1_every_structural_command_keeps_the_index_exact, ::test_t1_structural_cases_name_existing_targets, ::test_t1_duplicate_ids_keep_first_declaration_wins, ::test_t1_duplicate_ids_are_seen_by_palette_membership, ::test_t1_the_index_is_built_lazily_once, ::test_t1_a_desynchronised_removal_is_not_a_key_error.
- T2: tests/unit/editing/test_editing_apply.py::test_worst_case_translate_batch_stays_linear (recuento de operaciones sin reloj en dos tamaños) y python -m tests.benchmarks run|compare antes/después (ADR-040).
