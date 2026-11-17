# MOANA-009 — Implementar capas, grupos y composición

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-009
- Aliases históricos: MOA-009
- Phase: P2
- Priority: P1
- Status: done
- Complexity: L (relativa, no estimación de tiempo)
- Dependencies: [MOANA-002](MOANA-002.md), [MOANA-004](MOANA-004.md), [MOANA-005](MOANA-005.md), [MOANA-006](MOANA-006.md), [MOANA-008](MOANA-008.md)
- Related modules: layers
- Requirements: R011 ([trazabilidad](traceability.md))
- Bloqueo: Ninguno

## Context

La composición define la relación entre colores, visibilidad y grupos aislados.

## Objective

Componer capas ordenadas usando una sola fórmula entera source-over.

## Scope

Crear árbol ordenado de capas/grupos, visibilidad, bloqueo y composición normal source-over entera.

## Out of scope

No multiply/screen ni máscaras semánticas todavía.

## Technical requirements

- Orden abajo-arriba; buffer aislado por grupo y opacidad aplicada una vez
- Fórmula de redondeo §11, normalización alpha cero y límite de profundidad

## Proposed implementation

- Crear árbol de capas/grupos con ownership de buffer
- Componer hijos y aplicar opacidad del grupo una sola vez

## Acceptance criteria

- [x] AC1: Composición de fixture semitransparente coincide con cálculo entero independiente
- [x] AC2: Cambiar orden/visibilidad produce diferencia prevista; grupos no aplican opacidad por hijo

## Required tests

- [x] T1: Casos alpha 0/1/127/255 y normalización RGB en transparente
- [x] T2: Grupos anidados, profundidad límite, capa invisible y strict que rechaza opacidad intermedia

## Expected deliverables

- Árbol de capas/grupos y composición RGBA con opacidad de grupo aplicada una vez.
- Fixtures de orden, visibilidad, alfa parcial y aislamiento de grupos.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- La opacidad por hijo cambia la imagen; el bloqueo afecta edición, no render.

## Guía para agentes de IA

**Estado para agentes:** Completado; usar sólo como referencia del contrato entregado.

### 1. Preparación

- Rama: `feat/MOANA-009-implementar-capas-grupos` creada desde `develop` actualizado: `git switch develop && git pull --ff-only && git switch -c feat/MOANA-009-implementar-capas-grupos`.
- Verificar en `docs/issues/catalog.json` que este issue está `ready` y que sus dependencias ([MOANA-002](MOANA-002.md), [MOANA-004](MOANA-004.md), [MOANA-005](MOANA-005.md), [MOANA-006](MOANA-006.md), [MOANA-008](MOANA-008.md)) están `done`.
- Entorno: `uv sync --locked` (sin uv global: `sh scripts/bootstrap.sh` y después `sh scripts/uv.sh` en lugar de `uv`).
- Al empezar, cambiar `status` a `in_progress` en el catálogo y regenerar con `uv run python scripts/planning.py`.

### 2. Lectura obligatoria (en orden)

1. `CLAUDE.md` (Claude Code) o `AGENTS.md` (Codex) y [flujo de sesión](../guides/agent-workflow.md).
2. MOANA.md: §3 Arquitectura modular; §11 Capas, máscaras y regiones; §25 Definition of Done. Estas secciones son el contrato normativo; ante duda, prevalecen sobre este issue.
3. [Contratos de módulos](../architecture/module-contracts.md) para: `layers`.
4. Estándares: [python](../../docs/standards/python.md), [architecture](../../docs/standards/architecture.md), [testing](../../docs/standards/testing.md).
5. Issues de dependencia ([MOANA-002](MOANA-002.md), [MOANA-004](MOANA-004.md), [MOANA-005](MOANA-005.md), [MOANA-006](MOANA-006.md), [MOANA-008](MOANA-008.md)): leer su sección Evidence para conocer las APIs ya entregadas; no reimplementarlas.
6. ADR en `docs/architecture/` que mencionen los módulos afectados.

### 3. Requisitos de MOANA.md cubiertos

| ID | Requisito | Secciones | Verificación exigida |
| --- | --- | --- | --- |
| R011 | Capas, grupos y composición | §11 | Source-over entero y orden/opacidad de grupos |

### 4. Skills y subagentes

| Host | Skills a cargar | Revisión especializada |
| --- | --- | --- |
| Claude Code | `moana-graphics`, `moana-code-review` | `moana-graphics-engineer`, `moana-architect` (sólo lectura; el agente principal integra) |
| Codex | `$moana-graphics`, `$moana-code-review` | `moana_graphics_engineer`, `moana_architect` |

### 5. Archivos

- Código o documentos a crear/modificar: `src/moana/layers/`.
- Pruebas: `tests/unit/layers/`.
- No crear módulos ni carpetas sin comportamiento real. No tocar otros módulos salvo exportaciones imprescindibles, justificadas en el PR.

### 6. Plan de pruebas

- T1: Casos alpha 0/1/127/255 y normalización RGB en transparente
- T2: Grupos anidados, profundidad límite, capa invisible y strict que rechaza opacidad intermedia
- Oráculos independientes (cálculo a mano o fórmula de MOANA.md); nunca copiar la salida de la implementación como expected.
- Incluir casos negativos con el error de dominio esperado y casos borde (vacío, mínimo, máximo, fuera de rango).

### 7. Procedimiento

1. Escribir las pruebas de los criterios AC y T antes o junto con la implementación.
2. Implementar sólo **Scope**; respetar **Out of scope** y las dependencias permitidas de MOANA.md §3.
3. Validación de módulo: `uv run pytest tests/unit/layers/ -q` y `uv run mypy src/`.
4. Validación completa: `uv run python scripts/validate.py` y `uv run python scripts/check_wheel.py`.
5. Revisión: subagentes listados y skill `moana-code-review`; corregir hallazgos críticos y altos.
6. Si hay salida raster: mostrar el PNG a 1x y ampliado por vecino más cercano; si cambia un golden, presentar expected/actual/diff y justificar.

### 8. Cierre

1. En `docs/issues/catalog.json`, para este issue: `status` → `review` (o `done` tras aprobación); completar `acceptance_evidence` (AC1, AC2), `test_evidence` (T1, T2) y `evidence` con rutas concretas de tests y archivos.
2. Issues que desbloquea ([MOANA-010](MOANA-010.md), [MOANA-013](MOANA-013.md)): si todas sus dependencias quedan `done`, pasarlos a `ready` con `blocking_reason: null`.
3. Ejecutar `uv run python scripts/planning.py` y `uv run python -m scripts.check_repository`.
4. Abrir PR hacia `develop` enlazando este issue de GitHub (`Closes #<número>`), con comandos ejecutados y evidencia por AC/T. El CI completo corre al integrar `develop` en `main`.
5. Commit y push sólo con autorización del usuario. No declarar CI remoto ni aprobación artística humana sin evidencia.

### 9. Prohibido en este issue

- Implementar alcance de otros issues, incluidos los que desbloquea ([MOANA-010](MOANA-010.md), [MOANA-013](MOANA-013.md)).
- Actualizar goldens automáticamente, desactivar checks, editar `uv.lock` a mano o añadir dependencias sin motivo técnico registrado.
- `eval`/`exec`/`pickle`, red o estado global mutable en el núcleo; lecturas de texto sin `encoding="utf-8"`.

## Evidence

- src/moana/layers/nodes.py: árbol inmutable Fill/Layer/Group/LayerTree con validación de ID, nombre UTF-8 (≤4096 bytes), booleanos, opacidad 0..255, blend sólo normal, IDs únicos, ≤128 capas y grupos, profundidad ≤16 (MAX_GROUP_DEPTH en core.limits), máscaras dentro del lienzo y perfil strict (partial_opacity, partial_alpha).
- src/moana/layers/composite.py: kernel source-over entero literal de MOANA.md §11 en uint32 con round_half_up y normalización de alfa 0; grupos en buffer aislado con opacidad aplicada una vez; nodos ocultos sin coste; locked sin efecto; composition_cost puro y comprobación de presupuesto (geometría, frame_pixels, layers, operations, pixel_visits, buffer_bytes) antes de reservar; temporales por bloques de min(4096, A//4) píxeles; deadline por nodo y fill.
- ADR-017 (docs/architecture/decisions/ADR-017-layers-composition.md); contratos de módulos, overview, índice de arquitectura, README, guía de desarrollo, AGENTS.md y CLAUDE.md actualizados; probe de check_wheel ampliado.
- Gate: scripts/validate.py y scripts/check_wheel.py verdes.
- Revisión: moana-graphics-engineer y moana-python-engineer; corregidos límites de geometría, grupos en el límite de 128, temporales acotados por bloques para respetar budget-v1, deadline por fill, nombre de módulo, UTF-8 estricto, profile en el contexto de errores y pruebas de varios bloques, 1×1 y cota de temporales.
- Aprobado por el propietario el 2026-11-17 tras revisión; PR #47 hacia develop.
- AC1: tests/unit/layers/test_layers_compose.py::test_ac1_semitransparent_fixture_matches_hand_computation (161,80,90,255 calculado a mano) y ::test_ac1_random_trees_match_the_scalar_oracle (Hypothesis, oráculo escalar independiente con grupos).
- AC2: tests/unit/layers/test_layers_compose.py::test_ac2_order_decides_which_colour_is_on_top, ::test_ac2_hiding_a_layer_removes_exactly_its_pixels y ::test_ac2_group_opacity_is_applied_once_to_the_group_result (contraejemplo por hijo).
- T1: tests/unit/layers/test_layers_compose.py::test_t1_alpha_cases_match_hand_values (alfa 0/1/127/255) y ::test_t1_transparent_result_is_normalised_to_zero.
- T2: tests/unit/layers/test_layers_compose.py::test_t2_nested_groups_compose_like_the_oracle, ::test_t2_maximum_depth_composes_and_one_more_is_rejected, ::test_t2_hidden_group_skips_its_subtree_and_costs_nothing, ::test_t2_locked_does_not_change_the_render, ::test_t2_budget_is_checked_before_any_buffer, ::test_t2_other_budgets_are_enforced; tests/unit/layers/test_layers_nodes.py::test_t2_strict_rejects_intermediate_opacity y ::test_t2_depth_limit_counts_nested_groups.
