# MOANA-016 — Implementar dithering ordenado

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-016
- Aliases históricos: MOA-016
- Phase: P3
- Priority: P1
- Status: done
- Complexity: M (relativa, no estimación de tiempo)
- Dependencies: [MOANA-005](MOANA-005.md), [MOANA-013](MOANA-013.md)
- Related modules: techniques
- Requirements: R009 ([trazabilidad](traceability.md))
- Bloqueo: Ninguno

## Context

Un patrón mal anclado produce costuras y parpadeo.

## Objective

Aplicar Bayer exacto con coverage entera y fase estable.

## Scope

Añadir patrones Bayer 2×2/4×4 con coverage entera, anclaje explícito y clipping por máscara.

## Out of scope

No error diffusion ni dithering automático global.

## Technical requirements

- Tablas y módulo matemático fijados en §10; dos IDs de color
- El patrón se ancla al canvas y conserva fase entre tiles y frames salvo instrucción explícita

## Proposed implementation

- Implementar tablas normativas y módulo matemático
- Aplicar la selección A/B sobre máscara y origen compartido

## Acceptance criteria

- [x] AC1: Coverage 0 produce sólo A y N² sólo B dentro de la máscara
- [x] AC2: Patrones con origen negativo y traducciones múltiplo del período coinciden exactamente

## Required tests

- [x] T1: Todos los thresholds, coberturas y posiciones del período
- [x] T2: Máscaras no rectangulares, costuras entre tiles y repetición temporal sin parpadeo

## Expected deliverables

- Dithering ordenado con patrón/anclaje documentado y máscara de aplicación.
- Fixtures exactas de patrones, transparencia y estabilidad ante recortes.

## Definition of Done

Cumplir [MOANART.md §25](../../MOANART.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- El módulo negativo y los overrides temporales deben tener tests propios.

## Guía para agentes de IA

**Estado para agentes:** Completado; usar sólo como referencia del contrato entregado.

### 1. Preparación

- Rama: `feat/MOANA-016-implementar-dithering-ordenado` creada desde `develop` actualizado: `git switch develop && git pull --ff-only && git switch -c feat/MOANA-016-implementar-dithering-ordenado`.
- Verificar en `docs/issues/catalog.json` que este issue está `ready` y que sus dependencias ([MOANA-005](MOANA-005.md), [MOANA-013](MOANA-013.md)) están `done`.
- Entorno: `uv sync --locked` (sin uv global: `sh scripts/bootstrap.sh` y después `sh scripts/uv.sh` en lugar de `uv`).
- Al empezar, cambiar `status` a `in_progress` en el catálogo y regenerar con `uv run python scripts/planning.py`.

### 2. Lectura obligatoria (en orden)

1. `CLAUDE.md` (Claude Code) o `AGENTS.md` (Codex) y [flujo de sesión](../guides/agent-workflow.md).
2. MOANART.md: §3 Arquitectura modular; §10 Sombreado, dithering y materiales; §25 Definition of Done. Estas secciones son el contrato normativo; ante duda, prevalecen sobre este issue.
3. [Contratos de módulos](../architecture/module-contracts.md) para: `techniques`.
4. Estándares: [python](../../docs/standards/python.md), [architecture](../../docs/standards/architecture.md), [testing](../../docs/standards/testing.md), [pixel-art](../../docs/standards/pixel-art.md).
5. Issues de dependencia ([MOANA-005](MOANA-005.md), [MOANA-013](MOANA-013.md)): leer su sección Evidence para conocer las APIs ya entregadas; no reimplementarlas.
6. ADR en `docs/architecture/` que mencionen los módulos afectados.

### 3. Requisitos de MOANART.md cubiertos

| ID | Requisito | Secciones | Verificación exigida |
| --- | --- | --- | --- |
| R009 | Dithering controlado | §10 | Patrones exactos, coverage y fase temporal |

### 4. Skills y subagentes

| Host | Skills a cargar | Revisión especializada |
| --- | --- | --- |
| Claude Code | `moanart-graphics`, `moanart-pixel-art`, `moanart-code-review` | `moanart-graphics-engineer`, `moanart-pixel-artist` (sólo lectura; el agente principal integra) |
| Codex | `$moanart-graphics`, `$moanart-pixel-art`, `$moanart-code-review` | `moanart_graphics_engineer`, `moanart_pixel_artist` |

### 5. Archivos

- Código o documentos a crear/modificar: `src/moanart/techniques/`.
- Pruebas: `tests/unit/techniques/`.
- No crear módulos ni carpetas sin comportamiento real. No tocar otros módulos salvo exportaciones imprescindibles, justificadas en el PR.

### 6. Plan de pruebas

- T1: Todos los thresholds, coberturas y posiciones del período
- T2: Máscaras no rectangulares, costuras entre tiles y repetición temporal sin parpadeo
- Oráculos independientes (cálculo a mano o fórmula de MOANART.md); nunca copiar la salida de la implementación como expected.
- Incluir casos negativos con el error de dominio esperado y casos borde (vacío, mínimo, máximo, fuera de rango).

### 7. Procedimiento

1. Escribir las pruebas de los criterios AC y T antes o junto con la implementación.
2. Implementar sólo **Scope**; respetar **Out of scope** y las dependencias permitidas de MOANART.md §3.
3. Validación de módulo: `uv run pytest tests/unit/techniques/ -q` y `uv run mypy src/`.
4. Validación completa: `uv run python scripts/validate.py` y `uv run python scripts/check_wheel.py`.
5. Revisión: subagentes listados y skill `moanart-code-review`; corregir hallazgos críticos y altos.
6. Si hay salida raster: mostrar el PNG a 1x y ampliado por vecino más cercano; si cambia un golden, presentar expected/actual/diff y justificar.

### 8. Cierre

1. En `docs/issues/catalog.json`, para este issue: `status` → `review` (o `done` tras aprobación); completar `acceptance_evidence` (AC1, AC2), `test_evidence` (T1, T2) y `evidence` con rutas concretas de tests y archivos.
2. Issues que desbloquea ([MOANA-017](MOANA-017.md), [MOANA-034](MOANA-034.md)): si todas sus dependencias quedan `done`, pasarlos a `ready` con `blocking_reason: null`.
3. Ejecutar `uv run python scripts/planning.py` y `uv run python -m scripts.check_repository`.
4. Abrir PR hacia `develop` enlazando este issue de GitHub (`Closes #<número>`), con comandos ejecutados y evidencia por AC/T. El CI completo corre al integrar `develop` en `main`.
5. Commit y push sólo con autorización del usuario. No declarar CI remoto ni aprobación artística humana sin evidencia.

### 9. Prohibido en este issue

- Implementar alcance de otros issues, incluidos los que desbloquea ([MOANA-017](MOANA-017.md), [MOANA-034](MOANA-034.md)).
- Actualizar goldens automáticamente, desactivar checks, editar `uv.lock` a mano o añadir dependencias sin motivo técnico registrado.
- `eval`/`exec`/`pickle`, red o estado global mutable en el núcleo; lecturas de texto sin `encoding="utf-8"`.

## Evidence

- src/moanart/techniques/dither.py: dithering ordenado Bayer 2×2/4×4 con las matrices normativas de §10; t = M[(y−oy) mod N][(x−ox) mod N] con módulo matemático; B si t < coverage, A en el resto; split_dither reparte exactamente la máscara en dos partes disjuntas; techniques sólo importa core y geometry.
- src/moanart/geometry/pattern.py: select_periodic genérico sobre la caja recortada de la máscara (sin reservar fuera de ella); src/moanart/core/dither.py: DITHER_SIZES y PATTERN_INDEX_BYTES compartidos.
- src/moanart/schema/: operación dither en schema 1.0 (size 2|4, coverage 0..size², origin, color_a, color_b, mask_id obligatorios) como ampliación previa a la primera publicación; referencias de color y máscara validadas antes del render; tabla de miembros por tipo OPERATION_MEMBERS/MASK_MEMBERS (NodeMembers: colores, máscaras, geometría) con prueba de exhaustividad.
- src/moanart/render/: cada dither son dos fills diferidos sobre la caja de su máscara (layers.evaluate_mask, una máscara construida a la vez); budget-v5 (idéntico a budget-v4 sin dither) con CostEstimate.fills/BudgetReport.fills y el recurso operations comparando fills (2 por dither).
- Ejemplo examples/specs/dither-dusk.moanart.json: bandas del cielo de 4 filas alineadas con el período 4×4 (coberturas 6/8/10, rampa night/dusk/ember/glow), duna a contraluz más oscura que el horizonte con núcleo sólido y transición 2×2 con origen [0,-1] que difiere visiblemente de [0,0]; revisado a 1× y 8× por agente (sin aprobación artística humana).
- ADR-025 (docs/architecture/decisions/ADR-025-ordered-dithering.md) con notas de cabecera en ADR-011, ADR-012, ADR-015, ADR-017, ADR-018, ADR-020 y ADR-022; MOANART.md 0.1.12-draft (§10, §12, §13, §20); contratos de módulos, índice de ADR, overview, README, guía de desarrollo, AGENTS.md y CLAUDE.md actualizados.
- Trazabilidad: R009 cubierto (dithering ordenado). Seguimientos documentados en ADR-025: coste por nodo de máscara (budget-v6) e inspect sólo con color A.
- Gate: scripts/validate.py (1548 passed, src/moanart al 100 % de líneas y ramas) y scripts/check_wheel.py verdes; mypy también con --platform win32; generate_schema --check al día. Determinismo entre procesos en macOS; matriz pendiente en main.
- Revisión: moanart-graphics-engineer (aprobado; riesgo heredado de coste por nodo documentado), moanart-architect (cambios requeridos, aplicados: fills separado de operations, nota en ADR-012, constantes en core, tabla de miembros para integrar MOANA-018) y moanart-pixel-artist (cambios requeridos, aplicados: contraste duna/horizonte, anclaje negativo visible, bandas alineadas al período, rampa con ember, núcleo de sombra sólido).
- Aprobado por el propietario el 2026-11-17 tras revisión; PR #54 hacia develop.
- AC1: tests/unit/techniques/test_techniques_dither.py::test_ac1_extreme_coverages_inside_non_rectangular_masks; tests/unit/render/test_render_dither.py::test_ac1_extreme_coverages_paint_only_a_or_only_b_inside_the_mask, ::test_dither_without_background_leaves_outside_transparent y ::test_transparent_colour_b_keeps_the_background.
- AC2: tests/unit/techniques/test_techniques_dither.py::test_ac2_negative_origin_and_period_translations_match y ::test_ac2_negative_origin_uses_the_floor_modulo; tests/unit/render/test_render_dither.py::test_ac2_origin_translations_by_the_period_give_identical_bytes; tests/integration/test_dither_determinism.py::test_example_dune_matches_hand_computed_pixels (origen [0,-1] distinto de [0,0]).
- T1: tests/unit/techniques/test_techniques_dither.py::test_matrices_are_the_normative_ones, ::test_t1_every_threshold_position_and_coverage y ::test_t1_every_coverage_on_a_full_canvas_period_counts; tests/unit/render/test_render_dither.py::test_t1_every_coverage_matches_the_literal_matrix; tests/integration/test_dither_determinism.py::test_example_sky_matches_the_hand_computed_bayer_bands.
- T2: tests/unit/techniques/test_techniques_dither.py::test_t2_non_rectangular_masks_split_exactly, ::test_t2_adjacent_tiles_with_a_shared_anchor_have_no_seam, ::test_t2_repeated_dithering_is_identical y ::test_property_parts_partition_the_mask_like_the_oracle; tests/unit/render/test_render_dither.py::test_t2_combined_non_rectangular_mask, ::test_t2_adjacent_tiles_with_a_shared_anchor_have_no_seam y ::test_t2_repeated_renders_never_flicker; tests/integration/test_dither_determinism.py::test_t2_fresh_processes_with_any_hash_seed_agree y ::test_t2_repeated_renders_in_one_process_agree.
