# MOANA-025 — Añadir APNG y WebP lossless opcionales

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-025
- Aliases históricos: MOA-025
- Phase: P4
- Priority: P2
- Status: done
- Complexity: M (relativa, no estimación de tiempo)
- Dependencies: [MOANA-022](MOANA-022.md), [MOANA-011](MOANA-011.md)
- Related modules: export
- Requirements: R024 ([trazabilidad](traceability.md))
- Bloqueo: Ninguno

## Context

APNG/WebP dependen de capacidades del build y no justifican fallbacks ocultos.

## Objective

Exponer formatos adicionales sólo con codecs y roundtrip comprobados.

## Scope

Agregar exportadores adicionales sólo cuando el build de Pillow soporte los codecs, con capabilities públicas.

## Out of scope

No WebP lossy por defecto ni dependencia obligatoria de encoders ausentes.

## Technical requirements

- Detectar capacidad en runtime sin sustituir formatos; preservación de alfa/tiempos
- Opciones lossless explícitas y manifest con versiones de codec

## Proposed implementation

- Detectar capacidades y registrar opciones lossless
- Probar formatos disponibles y rechazar ausentes antes de crear destino

## Acceptance criteria

- [x] AC1: Cada codec disponible pasa roundtrip RGBA y timeline
- [x] AC2: Codec ausente produce UnsupportedOperation claro sin archivo con extensión engañosa

## Required tests

- [x] T1: Pruebas condicionadas a capacidades con skip explicado y reporte del build
- [x] T2: Mock de codec ausente y casos multi-frame, alfa parcial y duración

## Expected deliverables

- Adaptadores APNG/WebP lossless con detección de capacidades del codec.
- Roundtrips de timeline y errores verificables cuando una capacidad no está disponible.

## Definition of Done

Cumplir [MOANART.md §25](../../MOANART.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- Un skip de codec no equivale a soporte probado; publicar capability matrix.

## Guía para agentes de IA

**Estado para agentes:** Completado; usar sólo como referencia del contrato entregado.

### 1. Preparación

- Rama: `feat/MOANA-025-anadir-apng-webp` creada desde `develop` actualizado: `git switch develop && git pull --ff-only && git switch -c feat/MOANA-025-anadir-apng-webp`.
- Verificar en `docs/issues/catalog.json` que este issue está `ready` y que sus dependencias ([MOANA-022](MOANA-022.md), [MOANA-011](MOANA-011.md)) están `done`.
- Entorno: `uv sync --locked` (sin uv global: `sh scripts/bootstrap.sh` y después `sh scripts/uv.sh` en lugar de `uv`).
- Al empezar, cambiar `status` a `in_progress` en el catálogo y regenerar con `uv run python scripts/planning.py`.

### 2. Lectura obligatoria (en orden)

1. `CLAUDE.md` (Claude Code) o `AGENTS.md` (Codex) y [flujo de sesión](../guides/agent-workflow.md).
2. MOANART.md: §3 Arquitectura modular; §18 Exportación PNG, GIF y formatos adicionales; §25 Definition of Done. Estas secciones son el contrato normativo; ante duda, prevalecen sobre este issue.
3. [Contratos de módulos](../architecture/module-contracts.md) para: `export`.
4. Estándares: [python](../../docs/standards/python.md), [architecture](../../docs/standards/architecture.md), [testing](../../docs/standards/testing.md).
5. Issues de dependencia ([MOANA-022](MOANA-022.md), [MOANA-011](MOANA-011.md)): leer su sección Evidence para conocer las APIs ya entregadas; no reimplementarlas.
6. ADR en `docs/architecture/` que mencionen los módulos afectados.

### 3. Requisitos de MOANART.md cubiertos

| ID | Requisito | Secciones | Verificación exigida |
| --- | --- | --- | --- |
| R024 | Formatos adicionales | §18 | APNG/WebP lossless según codec disponible |

### 4. Skills y subagentes

| Host | Skills a cargar | Revisión especializada |
| --- | --- | --- |
| Claude Code | `moanart-graphics`, `moanart-python`, `moanart-code-review` | `moanart-graphics-engineer`, `moanart-python-engineer` (sólo lectura; el agente principal integra) |
| Codex | `$moanart-graphics`, `$moanart-python`, `$moanart-code-review` | `moanart_graphics_engineer`, `moanart_python_engineer` |

### 5. Archivos

- Código o documentos a crear/modificar: `src/moanart/export/`.
- Pruebas: `tests/unit/export/`.
- No crear módulos ni carpetas sin comportamiento real. No tocar otros módulos salvo exportaciones imprescindibles, justificadas en el PR.

### 6. Plan de pruebas

- T1: Pruebas condicionadas a capacidades con skip explicado y reporte del build
- T2: Mock de codec ausente y casos multi-frame, alfa parcial y duración
- Oráculos independientes (cálculo a mano o fórmula de MOANART.md); nunca copiar la salida de la implementación como expected.
- Incluir casos negativos con el error de dominio esperado y casos borde (vacío, mínimo, máximo, fuera de rango).

### 7. Procedimiento

1. Escribir las pruebas de los criterios AC y T antes o junto con la implementación.
2. Implementar sólo **Scope**; respetar **Out of scope** y las dependencias permitidas de MOANART.md §3.
3. Validación de módulo: `uv run pytest tests/unit/export/ -q` y `uv run mypy src/`.
4. Validación completa: `uv run python scripts/validate.py` y `uv run python scripts/check_wheel.py`.
5. Revisión: subagentes listados y skill `moanart-code-review`; corregir hallazgos críticos y altos.
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

- moanart.export.codecs: export_capabilities()/codec_status() comprueban en tiempo de ejecución, sin caché ni estado global, cada formato (png, gif, apng, webp): codec presente (PIL.features) y roundtrip mínimo en memoria con alfa parcial, varios frames y bucle; reason missing o roundtrip_failed (cualquier excepción de la sonda se informa, nunca rompe). La matriz de este build (macOS, Pillow 13.0.0, zlib 1.3.1.zlib-ng, libwebp 1.6.0: los cuatro disponibles) consta en ADR-035; moanart.api.capabilities y `moanart capabilities` publican export_codecs (export_formats se conserva).
- moanart.export.animated (ADR-035): encode_apng/export_apng y encode_webp/export_webp sólo lossless (sin opción lossy) sobre el protocolo SpriteFrame; el codec se exige (UnsupportedOperation codec_unavailable con formato, codec y versión de Pillow) antes de leer frames y de crear temporal o destino, sin sustituir formato. APNG usa extensión .png y media type image/apng; WebP .webp.
- APNG con contenedor escrito por MoanArt (IHDR RGBA8, acTL, fcTL por frame completo con dispose NONE y blend SOURCE, retardos ms/1000 exactos, IDAT/fdAT con un único contador de secuencia; Pillow sólo comprime); WebP lossless con opciones fijas (method 4, exact) compartidas con la sonda; frames iguales fusionados por libwebp verificados como timeline equivalente y una sola imagen distinta guardada como VP8L fija (detección por chunks RIFF) con AnimationWarning still_image y stored_durations_ms/stored_loop_count None.
- loop_count = reproducciones totales (0 infinito), escrito tal cual en num_plays de APNG y ANIM de WebP; verificación decodificando con Pillow (frames normalizados, milisegundos exactos, bucle) antes del commit atómico; bytes idénticos con las mismas versiones de codec, que el informe registra.
- Presupuesto antes de leer píxeles con buffer_bytes = C + F·A + O·n·A calibrado con RSS real en subprocesos (APNG 0/48/12; WebP 24 MiB/64/32, porque tracemalloc no ve la memoria nativa de libwebp); test de RSS en subproceso. Helpers compartidos con GIF en moanart.export._frames (bytes de GIF idénticos tras el refactor, comprobado por la revisión de gráficos).
- Documentación: ADR-035, MOANART.md 0.1.23-draft (§13 export_codecs, §18), module-contracts, sección «APNG y WebP» en docs/standards/pixel-art.md.
- Revisiones de agente: gráficos (APNG contrastado con ffprobe/ffmpeg y WebP con webpinfo/dwebp; presupuesto WebP corregido) y python (sondas robustas, avisos estructurados, detección RIFF y errores sin eco) con cambios aplicados. Gate local macOS: scripts/validate.py verde con src/moanart al 100 %, check_wheel OK, mypy --platform win32 OK, pre-commit OK; matriz pendiente en main (RSS no medido en Linux ni Windows).
- Aprobado por el propietario el 2026-11-17 tras revisión; PR #65 hacia develop.
- AC1: tests/unit/export/test_export_animated.py::test_multi_frame_partial_alpha_and_durations_roundtrip_exactly[apng|webp], ::test_decoded_timeline_equals_the_target (hypothesis), ::test_apng_container_is_full_frame_with_exact_delays, ::test_webp_stores_exact_milliseconds_and_the_loop, ::test_loop_count_is_total_plays; tests/integration/test_animated_export.py::test_bouncing_slime_decodes_to_the_rendered_timeline[apng|webp].
- AC2: tests/unit/export/test_export_animated.py::test_an_absent_codec_is_unsupported_and_writes_nothing[apng|webp] (directorio sin cambios y frames sin leer), ::test_a_failing_probe_is_unsupported_too; tests/unit/export/test_export_codecs.py::test_a_missing_webp_module_is_reported_and_refused.
- T1: tests/unit/export/test_export_codecs.py::test_capability_matrix_reports_every_format_of_this_build (matriz contra PIL.features, impresa); marcas needs_apng/needs_webp con el informe del build como motivo de skip (ningún skip en este equipo); ::test_a_probe_that_raises_anything_is_a_failed_roundtrip.
- T2: tests/unit/export/test_export_animated.py::test_an_absent_codec_is_unsupported_and_writes_nothing (codec ausente simulado), ::test_multi_frame_partial_alpha_and_durations_roundtrip_exactly (alfa (255,0,0,128) y (1,2,3,1); 1, 33, 1001, 59999 y 60000 ms), ::test_apng_keeps_duplicated_frames, ::test_webp_merged_duplicates_keep_an_equivalent_timeline, ::test_equal_webp_frames_collapse_to_a_still_image_with_a_warning, ::test_webp_reports_the_timeline_the_file_stores; tests/integration/test_animated_export.py::test_webp_budget_covers_the_measured_process_memory.
