# MOANA-006 — Rasterizar primitivas enteras y flood fill

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-006
- Aliases históricos: MOA-006
- Phase: P1
- Priority: P1
- Status: review
- Complexity: L (relativa, no estimación de tiempo)
- Dependencies: [MOANA-004](MOANA-004.md), [MOANA-005](MOANA-005.md)
- Related modules: geometry, layers
- Requirements: R003 ([trazabilidad](traceability.md))
- Bloqueo: Ninguno

## Context

Defaults de raster de bibliotecas producen diferencias de un píxel.

## Objective

Producir máscaras de primitivas que cumplan fixtures exactas del contrato.

## Scope

Implementar pixel, line, rect, ellipse, polygon y flood_fill en moana/geometry según reglas exactas de §6.

## Out of scope

No paths Bézier, AA ni trazos de grosor implícito.

## Technical requirements

- Máscaras binarias con empates y bordes normativos; no depender de defaults de ImageDraw
- Flood fill iterativo 4-conectado sobre snapshot de la capa y coste acotado; clipping consistente

## Proposed implementation

- Implementar primitivas en orden pixel/rect/line/ellipse/polygon con oráculos manuales
- Incorporar flood fill iterativo a partir de snapshot de capa recibido como entrada

## Acceptance criteria

- [ ] AC1: Invertir una línea produce la misma máscara y los extremos están incluidos
- [ ] AC2: Rectángulos, elipses y polígonos concuerdan con fixtures manuales; fill no atraviesa límites de color

## Required tests

- [ ] T1: Octantes de línea, degenerados, bordes semiabiertos y autointersecciones even-odd
- [ ] T2: Flood fill de un píxel/todo canvas, coincidencia de color, contención y rechazo por presupuesto
- [ ] T3: Bow-tie con área firmada cero pero interior even-odd no vacío; verificar máscara manual y no usar shoelace como descarte.

## Expected deliverables

- Rasterizadores enteros de primitivas y flood fill acotado.
- Máscaras manuales de bordes, degenerados, polígonos even-odd y relleno.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- Even-odd de autointersecciones no se puede descartar por área firmada cero.

## Guía para agentes de IA

**Estado para agentes:** En revisión: sólo correcciones de la revisión; no añadir alcance.

### 1. Preparación

- Rama: `feat/MOANA-006-rasterizar-primitivas-enteras` creada desde `develop` actualizado: `git switch develop && git pull --ff-only && git switch -c feat/MOANA-006-rasterizar-primitivas-enteras`.
- Verificar en `docs/issues/catalog.json` que este issue está `ready` y que sus dependencias ([MOANA-004](MOANA-004.md), [MOANA-005](MOANA-005.md)) están `done`.
- Entorno: `uv sync --locked` (sin uv global: `sh scripts/bootstrap.sh` y después `sh scripts/uv.sh` en lugar de `uv`).
- Al empezar, cambiar `status` a `in_progress` en el catálogo y regenerar con `uv run python scripts/planning.py`.

### 2. Lectura obligatoria (en orden)

1. `CLAUDE.md` (Claude Code) o `AGENTS.md` (Codex) y [flujo de sesión](../guides/agent-workflow.md).
2. MOANA.md: §3 Arquitectura modular; §6 Geometría y primitivas; §25 Definition of Done. Estas secciones son el contrato normativo; ante duda, prevalecen sobre este issue.
3. [Contratos de módulos](../architecture/module-contracts.md) para: `geometry`, `layers`.
4. Estándares: [python](../../docs/standards/python.md), [architecture](../../docs/standards/architecture.md), [testing](../../docs/standards/testing.md).
5. Issues de dependencia ([MOANA-004](MOANA-004.md), [MOANA-005](MOANA-005.md)): leer su sección Evidence para conocer las APIs ya entregadas; no reimplementarlas.
6. ADR en `docs/architecture/` que mencionen los módulos afectados.

### 3. Requisitos de MOANA.md cubiertos

| ID | Requisito | Secciones | Verificación exigida |
| --- | --- | --- | --- |
| R003 | Primitivas exactas, clipping y flood fill | §6 | Oráculos de píxel por primitiva y casos degenerados |

### 4. Skills y subagentes

| Host | Skills a cargar | Revisión especializada |
| --- | --- | --- |
| Claude Code | `moana-graphics`, `moana-code-review` | `moana-graphics-engineer`, `moana-python-engineer`, `moana-architect` (sólo lectura; el agente principal integra) |
| Codex | `$moana-graphics`, `$moana-code-review` | `moana_graphics_engineer`, `moana_python_engineer`, `moana_architect` |

### 5. Archivos

- Código o documentos a crear/modificar: `src/moana/geometry/`, `src/moana/layers/`.
- Pruebas: `tests/unit/geometry/`, `tests/unit/layers/`.
- No crear módulos ni carpetas sin comportamiento real. No tocar otros módulos salvo exportaciones imprescindibles, justificadas en el PR.

### 6. Plan de pruebas

- T1: Octantes de línea, degenerados, bordes semiabiertos y autointersecciones even-odd
- T2: Flood fill de un píxel/todo canvas, coincidencia de color, contención y rechazo por presupuesto
- T3: Bow-tie con área firmada cero pero interior even-odd no vacío; verificar máscara manual y no usar shoelace como descarte.
- Oráculos independientes (cálculo a mano o fórmula de MOANA.md); nunca copiar la salida de la implementación como expected.
- Incluir casos negativos con el error de dominio esperado y casos borde (vacío, mínimo, máximo, fuera de rango).

### 7. Procedimiento

1. Escribir las pruebas de los criterios AC y T antes o junto con la implementación.
2. Implementar sólo **Scope**; respetar **Out of scope** y las dependencias permitidas de MOANA.md §3.
3. Validación de módulo: `uv run pytest tests/unit/geometry/ tests/unit/layers/ -q` y `uv run mypy src/`.
4. Validación completa: `uv run python scripts/validate.py` y `uv run python scripts/check_wheel.py`.
5. Revisión: subagentes listados y skill `moana-code-review`; corregir hallazgos críticos y altos.
6. Si hay salida raster: mostrar el PNG a 1x y ampliado por vecino más cercano; si cambia un golden, presentar expected/actual/diff y justificar.

### 8. Cierre

1. En `docs/issues/catalog.json`, para este issue: `status` → `review` (o `done` tras aprobación); completar `acceptance_evidence` (AC1, AC2), `test_evidence` (T1, T2, T3) y `evidence` con rutas concretas de tests y archivos.
2. Issues que desbloquea ([MOANA-007](MOANA-007.md), [MOANA-008](MOANA-008.md), [MOANA-009](MOANA-009.md), [MOANA-010](MOANA-010.md)): si todas sus dependencias quedan `done`, pasarlos a `ready` con `blocking_reason: null`.
3. Ejecutar `uv run python scripts/planning.py` y `uv run python -m scripts.check_repository`.
4. Abrir PR hacia `develop` enlazando este issue de GitHub (`Closes #<número>`), con comandos ejecutados y evidencia por AC/T. El CI completo corre al integrar `develop` en `main`.
5. Commit y push sólo con autorización del usuario. No declarar CI remoto ni aprobación artística humana sin evidencia.

### 9. Prohibido en este issue

- Implementar alcance de otros issues, incluidos los que desbloquea ([MOANA-007](MOANA-007.md), [MOANA-008](MOANA-008.md), [MOANA-009](MOANA-009.md), [MOANA-010](MOANA-010.md)).
- Actualizar goldens automáticamente, desactivar checks, editar `uv.lock` a mano o añadir dependencias sin motivo técnico registrado.
- `eval`/`exec`/`pickle`, red o estado global mutable en el núcleo; lecturas de texto sin `encoding="utf-8"`.

## Evidence

- src/moana/geometry/{__init__,mask,primitives,fill}.py: Mask inmutable (igualdad por conjunto de píxeles; copy/deepcopy/pickle conservan bits de sólo lectura), rasterize_pixel/line/rect/ellipse/polygon según §6 (Bresenham con extremos ordenados, elipse por centros con isqrt exacto, polígono even-odd por centros con umbral entero, sin shoelace), recorte sin wraparound antes de reservar.
- flood_fill 4-conectado sobre snapshot Canvas con igualdad RGBA exacta, scanline iterativo sin recursión, BudgetExceeded (pixel_visits, buffer_bytes; A visitas, 8A bytes) antes de copiar; semilla fuera del lienzo → máscara vacía (pendiente de ratificar en MOANA.md cuando el esquema active flood_fill).
- ADR-015 (docs/architecture/decisions/ADR-015-raster-primitives.md); contratos de módulos, overview e índice de arquitectura actualizados; memoria de máscaras igual al término mask_bytes de budget-v1 (sin cambio de estimador).
- Gate: scripts/validate.py (601 pruebas) y scripts/check_wheel.py verdes; cobertura 100 % de líneas y ramas en moana.geometry.
- Revisión: moana-graphics-engineer (aprobado; fuerza bruta 20 000 líneas, 20 000 elipses, 4 000 polígonos y 1 500 rellenos sin discrepancias) y moana-architect; corregidos deepcopy/pickle escribibles, recuento de vértices antes de iterar, probe de wheel y documentación de identidad/hash de Mask.
- AC1: tests/unit/geometry/test_geometry_primitives.py::test_ac1_reversed_line_gives_identical_mask (8 octantes), ::test_line_properties y ::test_line_matches_literal_recurrence (Hypothesis, recurrencia literal independiente).
- AC2: tests/unit/geometry/test_geometry_primitives.py::test_rect_is_half_open, ::test_ellipse_5x3_by_pixel_centres, ::test_ellipse_4x4_circle, ::test_triangle_by_pixel_centres, ::test_ellipse_matches_literal_per_pixel_formula, ::test_polygon_matches_literal_even_odd_rule; tests/unit/geometry/test_geometry_fill.py::test_ac2_fill_does_not_cross_colour_boundaries.
- T1: tests/unit/geometry/test_geometry_primitives.py::test_line_octants_match_hand_oracle, ::test_degenerate_line_is_one_pixel, ::test_horizontal_vertical_and_diagonal_lines, ::test_line_tie_breaking_on_shallow_slope, ::test_line_partially_off_canvas_is_clipped_without_wraparound, ::test_rect_partially_off_canvas_and_negative, ::test_ellipse_partially_and_fully_off_canvas, ::test_polygon_off_canvas_and_negative_coordinates, ::test_one_by_one_canvas_cases, ::test_t1_self_intersection_leaves_even_odd_hole.
- T2: tests/unit/geometry/test_geometry_fill.py::test_fill_of_isolated_single_pixel, ::test_fill_of_uniform_canvas_covers_everything, ::test_colour_match_is_exact_per_channel, ::test_transparent_pixels_match_after_alpha_normalisation, ::test_fill_is_four_connected_not_diagonal, ::test_fill_matches_breadth_first_reference, ::test_budget_rejection_happens_before_any_copy, ::test_budget_admits_exact_limit, ::test_one_by_one_canvas_fill; tests/unit/geometry/test_geometry_memory.py.
- T3: tests/unit/geometry/test_geometry_primitives.py::test_t3_bow_tie_with_zero_signed_area_is_not_empty (área firmada 0, máscara manual de 8 píxeles).
