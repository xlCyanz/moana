# MOANA-023 — Exportar spritesheets y manifest reversible

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-023
- Aliases históricos: MOA-023
- Phase: P4
- Priority: P1
- Status: done
- Complexity: M (relativa, no estimación de tiempo)
- Dependencies: [MOANA-022](MOANA-022.md), [MOANA-011](MOANA-011.md)
- Related modules: export, animation
- Requirements: R021 ([trazabilidad](traceability.md))
- Bloqueo: Ninguno

## Context

Un atlas sin manifest íntegro pierde pivotes, duración o tamaño fuente.

## Objective

Exportar un grid reversible que reconstruya exactamente sus frames.

## Scope

Crear atlas grid con margen/padding, manifiesto de frames, pivotes y tiempos; reconstrucción comprobable.

## Out of scope

No packing heurístico compacto hasta tener contrato de desempate independiente.

## Technical requirements

- Orden de frames estable, sin rotación/trim implícito y dimensiones presupuestadas
- Manifest versionado con rect, source_size, trim_offset, duration y digest

## Proposed implementation

- Calcular layout desde columnas/margen/padding y presupuesto
- Serializar manifest versionado y verificar recortes contra originales

## Acceptance criteria

- [x] AC1: Recortar atlas por manifest reconstruye RGBA exacto de cada frame
- [x] AC2: Export idéntico con misma configuración y ningún frame solapa padding o sale del sheet

## Required tests

- [x] T1: Columnas 1/N, último renglón incompleto, margen/padding y canvas no cuadrado
- [x] T2: Atlas excesivo, manifest corrupto y roundtrip recortes/tiempos

## Expected deliverables

- Exportador de spritesheets y manifiesto reversible con pivotes/duraciones.
- Reconstrucción exacta de frames desde atlas y pruebas de packing/límites.

## Definition of Done

Cumplir [MOANART.md §25](../../MOANART.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- Confundir rect xywh con bbox semiabierta causa offsets; especificar ambos claramente.

## Guía para agentes de IA

**Estado para agentes:** Completado; usar sólo como referencia del contrato entregado.

### 1. Preparación

- Rama: `feat/MOANA-023-exportar-spritesheets-manifest` creada desde `develop` actualizado: `git switch develop && git pull --ff-only && git switch -c feat/MOANA-023-exportar-spritesheets-manifest`.
- Verificar en `docs/issues/catalog.json` que este issue está `ready` y que sus dependencias ([MOANA-022](MOANA-022.md), [MOANA-011](MOANA-011.md)) están `done`.
- Entorno: `uv sync --locked` (sin uv global: `sh scripts/bootstrap.sh` y después `sh scripts/uv.sh` en lugar de `uv`).
- Al empezar, cambiar `status` a `in_progress` en el catálogo y regenerar con `uv run python scripts/planning.py`.

### 2. Lectura obligatoria (en orden)

1. `CLAUDE.md` (Claude Code) o `AGENTS.md` (Codex) y [flujo de sesión](../guides/agent-workflow.md).
2. MOANART.md: §3 Arquitectura modular; §17 Animaciones y spritesheets; §25 Definition of Done. Estas secciones son el contrato normativo; ante duda, prevalecen sobre este issue.
3. [Contratos de módulos](../architecture/module-contracts.md) para: `export`, `animation`.
4. Estándares: [python](../../docs/standards/python.md), [architecture](../../docs/standards/architecture.md), [testing](../../docs/standards/testing.md), [pixel-art](../../docs/standards/pixel-art.md).
5. Issues de dependencia ([MOANA-022](MOANA-022.md), [MOANA-011](MOANA-011.md)): leer su sección Evidence para conocer las APIs ya entregadas; no reimplementarlas.
6. ADR en `docs/architecture/` que mencionen los módulos afectados.

### 3. Requisitos de MOANART.md cubiertos

| ID | Requisito | Secciones | Verificación exigida |
| --- | --- | --- | --- |
| R021 | Spritesheets y manifest | §17 | Reconstrucción exacta de cada frame |

### 4. Skills y subagentes

| Host | Skills a cargar | Revisión especializada |
| --- | --- | --- |
| Claude Code | `moanart-graphics`, `moanart-python`, `moanart-pixel-art`, `moanart-code-review` | `moanart-graphics-engineer`, `moanart-python-engineer`, `moanart-pixel-artist` (sólo lectura; el agente principal integra) |
| Codex | `$moanart-graphics`, `$moanart-python`, `$moanart-pixel-art`, `$moanart-code-review` | `moanart_graphics_engineer`, `moanart_python_engineer`, `moanart_pixel_artist` |

### 5. Archivos

- Código o documentos a crear/modificar: `src/moanart/export/`, `src/moanart/animation/`.
- Pruebas: `tests/unit/export/`, `tests/unit/animation/`.
- No crear módulos ni carpetas sin comportamiento real. No tocar otros módulos salvo exportaciones imprescindibles, justificadas en el PR.

### 6. Plan de pruebas

- T1: Columnas 1/N, último renglón incompleto, margen/padding y canvas no cuadrado
- T2: Atlas excesivo, manifest corrupto y roundtrip recortes/tiempos
- Oráculos independientes (cálculo a mano o fórmula de MOANART.md); nunca copiar la salida de la implementación como expected.
- Incluir casos negativos con el error de dominio esperado y casos borde (vacío, mínimo, máximo, fuera de rango).

### 7. Procedimiento

1. Escribir las pruebas de los criterios AC y T antes o junto con la implementación.
2. Implementar sólo **Scope**; respetar **Out of scope** y las dependencias permitidas de MOANART.md §3.
3. Validación de módulo: `uv run pytest tests/unit/export/ tests/unit/animation/ -q` y `uv run mypy src/`.
4. Validación completa: `uv run python scripts/validate.py` y `uv run python scripts/check_wheel.py`.
5. Revisión: subagentes listados y skill `moanart-code-review`; corregir hallazgos críticos y altos.
6. Si hay salida raster: mostrar el PNG a 1x y ampliado por vecino más cercano; si cambia un golden, presentar expected/actual/diff y justificar.

### 8. Cierre

1. En `docs/issues/catalog.json`, para este issue: `status` → `review` (o `done` tras aprobación); completar `acceptance_evidence` (AC1, AC2), `test_evidence` (T1, T2) y `evidence` con rutas concretas de tests y archivos.
2. Issues que desbloquea ([MOANA-034](MOANA-034.md), [MOANA-035](MOANA-035.md)): si todas sus dependencias quedan `done`, pasarlos a `ready` con `blocking_reason: null`.
3. Ejecutar `uv run python scripts/planning.py` y `uv run python -m scripts.check_repository`.
4. Abrir PR hacia `develop` enlazando este issue de GitHub (`Closes #<número>`), con comandos ejecutados y evidencia por AC/T. El CI completo corre al integrar `develop` en `main`.
5. Commit y push sólo con autorización del usuario. No declarar CI remoto ni aprobación artística humana sin evidencia.

### 9. Prohibido en este issue

- Implementar alcance de otros issues, incluidos los que desbloquea ([MOANA-034](MOANA-034.md), [MOANA-035](MOANA-035.md)).
- Actualizar goldens automáticamente, desactivar checks, editar `uv.lock` a mano o añadir dependencias sin motivo técnico registrado.
- `eval`/`exec`/`pickle`, red o estado global mutable en el núcleo; lecturas de texto sin `encoding="utf-8"`.

## Evidence

- moanart.export.spritesheet (ADR-033): grid uniforme en orden de frames con columns 1–256 (columns > n es too_many_columns, sin clamp), margin y padding 0–2048; frame i en x = margin + (i % columns)·(w + padding), y = margin + (i // columns)·(h + padding); rect [x,y,w,h] ≡ caja semiabierta [x,y,x+w,y+h); huecos (0,0,0,0); sin trim ni rotación; todos los frames del mismo tamaño (size_mismatch).
- Frames por el protocolo SpriteFrame (frame_id, duration_ms, pivot, result: RasterFrame), que moanart.animation.FrameRender cumple sin que export importe animation (test de arquitectura); SheetFrame/FramePixels para recortes reexportables; bloque opcional animation {id, loop_count} vía SheetAnimation.
- Presupuesto antes de reservar el atlas: frames ≤ 256 (comprobado con len antes de leer frames), Σ píxeles de frame ≤ max_frame_pixels, lado y área de la hoja, buffer_bytes = 32·área; frames no normalizados rechazados antes del atlas.
- Manifiesto JSON canónico versionado (format moanart-spritesheet, version 1) con image {name, media_type, width, height, digest visual, sha256 de procedencia}, layout, frames {frame_id, rect, duration_ms, pivot, source_size, trim_offset [0,0], digest}; parser estricto (tamaño ≤ 1 MiB antes de decodificar, versión antes que miembros → UnsupportedVersion, bool/float nunca enteros, claves duplicadas, NaN, anidamiento, rects iguales a su celda) con ValidationError reason + json_pointer sin rutas ni eco de claves.
- Escritura en dos archivos con commit_bytes: todo codificado y verificado en memoria, overwrite=False comprueba ambos destinos antes de escribir, atlas primero y manifiesto al final (un fallo del manifiesto informa committed sin borrar el atlas). Recorte: IHDR/IEND y presupuesto len(png) + 12·A antes de decodificar, digest del atlas, not_normalized y dirty_gap independientes de los digests, digest por frame; load_spritesheet abre con O_NONBLOCK y exige archivo regular (un FIFO nunca bloquea).
- Guía para motores en ADR-033 y MOANART.md §17: filtrado nearest sin mipmaps, padding ≥ 1 (≥ 2 con mipmaps) si hay filtrado, padding no es extrusión; pivote en píxeles enteros del frame fuente con conversión (px/w, 1 − py/h) para motores Y-up; semántica de trim_offset fijada. MOANART.md 0.1.21-draft.
- Cubiertas con tests las líneas que MOANA-022 dejó sin cubrir (animation/frames.py:185, render/sequence.py:189 y 237).
- Revisiones de agente: gráficos (aprobado), python (cambios aplicados: nombres no UTF-8/C1, FIFO, versión antes de miembros, reutilización de destination_path/is_normalized, consistencia de errores) y pixel-art (guía de motores, bloque animation); revisión artística humana PENDIENTE. Gate local macOS: scripts/validate.py verde con src/moanart al 100 %, check_wheel OK, mypy --platform win32 OK, pre-commit OK; matriz pendiente en main.
- Aprobado por el propietario el 2026-11-17 tras revisión; PR #63 hacia develop.
- AC1: tests/unit/export/test_export_spritesheet.py::test_slice_rebuilds_frames_and_reexports_identically, ::test_translucent_pixels_survive_the_roundtrip, ::test_rects_are_disjoint_inside_and_roundtrip (hypothesis); tests/integration/test_spritesheet_animation.py::test_bouncing_slime_sheet_rebuilds_every_frame (RGBA, digests, duraciones, pivotes y animation con columnas/margen/padding (1,0,0), (2,1,1), (4,2,3)).
- AC2: tests/unit/export/test_export_spritesheet.py::test_export_is_byte_identical_across_directories, ::test_rects_are_disjoint_inside_and_roundtrip (rects disjuntos, dentro del margen, separados ≥ padding, huecos transparentes), ::test_atlas_pixels_are_checked_independently_of_digests (dirty_gap, not_normalized), ::test_corrupt_manifest_is_located (rect_mismatch, rect_out_of_sheet).
- T1: tests/unit/export/test_export_spritesheet.py::test_layout_matches_hand_computed_grid y ::test_atlas_pixels_are_placed_by_hand_and_gaps_are_transparent (oráculos a mano: una columna, una fila, último renglón incompleto, sólo margen, sólo padding, frame único; frames 3×2 y 2×3 no cuadrados), ::test_manifest_records_every_frame_value, ::test_invalid_layout_options.
- T2: tests/unit/export/test_export_spritesheet.py::test_excessive_sheet_is_rejected_before_the_atlas_exists, ::test_rejected_large_sheet_allocates_almost_nothing (tracemalloc), ::test_too_many_frames_is_rejected_before_reading_any_frame, ::test_slicing_checks_its_budget_before_decoding, ::test_corrupt_manifest_is_located, ::test_unreadable_manifest_bytes, ::test_manifest_size_version_and_type, ::test_digest_mismatches_are_located, ::test_bad_atlas_images, ::test_load_never_blocks_on_a_fifo, ::test_animation_block_roundtrips_and_is_optional, ::test_slice_rebuilds_frames_and_reexports_identically (recortes y tiempos).
