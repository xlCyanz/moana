# MOANA-024 — Exportar GIF con política de pérdidas

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-024
- Aliases históricos: MOA-024
- Phase: P4
- Priority: P1
- Status: review
- Complexity: L (relativa, no estimación de tiempo)
- Dependencies: [MOANA-022](MOANA-022.md), [MOANA-005](MOANA-005.md), [MOANA-011](MOANA-011.md)
- Related modules: export, animation
- Requirements: R023 ([trazabilidad](traceability.md))
- Bloqueo: Ninguno

## Context

GIF no representa alfa parcial, colores arbitrarios ni todos los tiempos.

## Objective

Exportar una timeline equivalente con pérdidas explícitas y controladas.

## Scope

Implementar GIF con paleta compartida, transparencia, disposal y duración efectiva declarada.

## Out of scope

No cuantización silenciosa ni equiparar GIF al maestro RGBA.

## Technical requirements

- <=256 índices, reserva de transparencia y rechazo de alfa intermedio sin background explícito
- Duración múltiplo de 10 ms o redondeo solicitado; comprobar timeline tras decode

## Proposed implementation

- Preparar paleta compartida/reserva transparente y política de duración
- Codificar frames/disposal y reconstruir timeline decodificada

## Acceptance criteria

- [ ] AC1: Frames decodificados/composited y tiempos son equivalentes al objetivo bajo las opciones elegidas
- [ ] AC2: Colores o tiempos no representables generan error o informe de pérdida explícitamente aceptada

## Required tests

- [ ] T1: Paleta llena, 255 colores más transparente, alpha intermedio y disposal
- [ ] T2: Frames duplicados fusionados, loop, duraciones cortas y decode acumulado en Pillow

## Expected deliverables

- Exportador GIF con política explícita de pérdidas, paleta y duración efectiva.
- Pruebas de timeline decodificado, transparencia, límites y rechazos sin pérdida autorizada.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- Los encoders pueden fusionar frames idénticos; comparar tiempo/imagen, no sólo count.

## Guía para agentes de IA

**Estado para agentes:** En revisión: sólo correcciones de la revisión; no añadir alcance.

### 1. Preparación

- Rama: `feat/MOANA-024-exportar-gif-politica` creada desde `develop` actualizado: `git switch develop && git pull --ff-only && git switch -c feat/MOANA-024-exportar-gif-politica`.
- Verificar en `docs/issues/catalog.json` que este issue está `ready` y que sus dependencias ([MOANA-022](MOANA-022.md), [MOANA-005](MOANA-005.md), [MOANA-011](MOANA-011.md)) están `done`.
- Entorno: `uv sync --locked` (sin uv global: `sh scripts/bootstrap.sh` y después `sh scripts/uv.sh` en lugar de `uv`).
- Al empezar, cambiar `status` a `in_progress` en el catálogo y regenerar con `uv run python scripts/planning.py`.

### 2. Lectura obligatoria (en orden)

1. `CLAUDE.md` (Claude Code) o `AGENTS.md` (Codex) y [flujo de sesión](../guides/agent-workflow.md).
2. MOANA.md: §3 Arquitectura modular; §18 Exportación PNG, GIF y formatos adicionales; §25 Definition of Done. Estas secciones son el contrato normativo; ante duda, prevalecen sobre este issue.
3. [Contratos de módulos](../architecture/module-contracts.md) para: `export`, `animation`.
4. Estándares: [python](../../docs/standards/python.md), [architecture](../../docs/standards/architecture.md), [testing](../../docs/standards/testing.md), [pixel-art](../../docs/standards/pixel-art.md).
5. Issues de dependencia ([MOANA-022](MOANA-022.md), [MOANA-005](MOANA-005.md), [MOANA-011](MOANA-011.md)): leer su sección Evidence para conocer las APIs ya entregadas; no reimplementarlas.
6. ADR en `docs/architecture/` que mencionen los módulos afectados.

### 3. Requisitos de MOANA.md cubiertos

| ID | Requisito | Secciones | Verificación exigida |
| --- | --- | --- | --- |
| R023 | Exportación GIF | §18 | Timeline/disposal y pérdidas explícitas |

### 4. Skills y subagentes

| Host | Skills a cargar | Revisión especializada |
| --- | --- | --- |
| Claude Code | `moana-graphics`, `moana-python`, `moana-pixel-art`, `moana-code-review` | `moana-graphics-engineer`, `moana-python-engineer`, `moana-pixel-artist` (sólo lectura; el agente principal integra) |
| Codex | `$moana-graphics`, `$moana-python`, `$moana-pixel-art`, `$moana-code-review` | `moana_graphics_engineer`, `moana_python_engineer`, `moana_pixel_artist` |

### 5. Archivos

- Código o documentos a crear/modificar: `src/moana/export/`, `src/moana/animation/`.
- Pruebas: `tests/unit/export/`, `tests/unit/animation/`.
- No crear módulos ni carpetas sin comportamiento real. No tocar otros módulos salvo exportaciones imprescindibles, justificadas en el PR.

### 6. Plan de pruebas

- T1: Paleta llena, 255 colores más transparente, alpha intermedio y disposal
- T2: Frames duplicados fusionados, loop, duraciones cortas y decode acumulado en Pillow
- Oráculos independientes (cálculo a mano o fórmula de MOANA.md); nunca copiar la salida de la implementación como expected.
- Incluir casos negativos con el error de dominio esperado y casos borde (vacío, mínimo, máximo, fuera de rango).

### 7. Procedimiento

1. Escribir las pruebas de los criterios AC y T antes o junto con la implementación.
2. Implementar sólo **Scope**; respetar **Out of scope** y las dependencias permitidas de MOANA.md §3.
3. Validación de módulo: `uv run pytest tests/unit/export/ tests/unit/animation/ -q` y `uv run mypy src/`.
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

- moana.export.gif (ADR-034): encode_gif/export_gif sobre el protocolo SpriteFrame (moana.animation.FrameRender lo cumple; el pivote se ignora). Paleta compartida ≤ 256 sin cuantizar: derivada (transparente en el índice 0 si hace falta y opacos ordenados por (r, g, b)) o Palette declarada (orden declarado; transparente añadido si falta); 256 opacos + transparencia es too_many_colors.
- Alfa: 0 → índice transparente, 255 opaco; alfa intermedio es partial_alpha salvo background opaco explícito, aplanado con (c·a + b·(255 − a) + 127) // 255 y pérdida alpha_flattened. Duraciones: exact (por defecto) rechaza no múltiplos de 10 ms; round = max(10, 10·⌊(d + 5)/10⌋) con pérdida duration_rounded; aviso estructurado GifWarning short_delay por frame < 20 ms.
- Disposal background (2) por defecto con frames completos; none (1) rechaza frames que mostrarían el anterior, también en la costura del bucle (disposal_reveals_previous). loop_count en Moana = reproducciones totales (0 infinito): NETSCAPE 0, N−1 o ausente para N = 1 (MOANA.md §17).
- Contenedor GIF89a escrito por Moana (tabla global única, índice de fondo = transparente, sin fusionar frames, sin recortes); Pillow sólo comprime LZW cada plano de índices y su salida se analiza estrictamente (encoder_layout). Verificación decodificando con Pillow: timelines equivalentes tras fusionar frames iguales consecutivos (timeline_mismatch) y bucle (loop_mismatch); bytes idénticos para la misma entrada.
- Presupuesto antes de leer píxeles: frames ≤ 256 (len), Σ píxeles de frame, lado, área y buffer_bytes = 48·A + 4·n·A (pico RSS medido por la revisión de gráficos por debajo del presupuesto); escritura atómica sin sobrescribir por defecto. Comprobación de frames compartida con spritesheet en moana.export._frames.
- Documentación: ADR-034, MOANA.md 0.1.22-draft (§17 bucle, §18 GIF), module-contracts, sección «GIF animado» en docs/standards/pixel-art.md (duraciones, alfa, paleta, escala previa, disposal). Test determinista para el tramo de selective_outline tapado por un tramo posterior (render/pipeline.py:277).
- Revisiones de agente: gráficos (aprobado; contenedor contrastado con ffmpeg y giftext), python (aprobado con observaciones aplicadas) y pixel-art (aprobado con menores aplicados); revisión artística humana PENDIENTE. Gate local macOS: scripts/validate.py verde con src/moana al 100 %, check_wheel OK, mypy --platform win32 OK, pre-commit OK; matriz pendiente en main.
- AC1: tests/integration/test_gif_animation.py::test_bouncing_slime_gif_decodes_to_the_rendered_timeline (frames decodificados = RGBA renderizado, 150/100/120/100 ms, bucle infinito, bytes idénticos); tests/unit/export/test_export_gif.py::test_accumulated_decode_equals_every_target_frame, ::test_decoded_timeline_equals_the_target y ::test_none_disposal_timeline_equals_the_target (hypothesis).
- AC2: tests/unit/export/test_export_gif.py::test_losses_need_explicit_acceptance, ::test_colours_beyond_the_table_are_never_quantised, ::test_partial_alpha_is_rejected_without_background, ::test_short_durations_and_rounding_policy, ::test_flatten_background_is_reported_for_reproduction.
- T1: tests/unit/export/test_export_gif.py::test_full_palette_of_256_opaque_colours, ::test_255_opaque_colours_plus_transparency, ::test_256_opaque_colours_plus_transparency_is_rejected, ::test_partial_alpha_is_flattened_exactly_with_background (valores a mano), ::test_background_disposal_never_shows_an_older_frame_through_a_hole, ::test_none_disposal_rejects_frames_that_reveal_the_previous_one, ::test_none_disposal_checks_the_loop_seam, ::test_a_file_whose_disposal_shows_older_frames_never_verifies.
- T2: tests/unit/export/test_export_gif.py::test_duplicated_frames_keep_an_equivalent_timeline, ::test_verification_accepts_a_decoder_that_merges_duplicates, ::test_equivalent_timeline_merges_equal_neighbours, ::test_loop_count_roundtrips (0, 1, 2, 7, 65535 con bytes NETSCAPE a mano), ::test_loop_mismatch_is_an_error, ::test_short_durations_and_rounding_policy, ::test_accumulated_decode_equals_every_target_frame, ::test_rejected_large_gif_allocates_almost_nothing, ::test_admitted_gif_stays_within_its_traced_estimate.
