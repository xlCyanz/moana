# MOANA-011 — Exportar PNG y manifiesto de salida

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-011
- Aliases históricos: MOA-011
- Phase: P2
- Priority: P1
- Status: done
- Complexity: M (relativa, no estimación de tiempo)
- Dependencies: [MOANA-010](MOANA-010.md)
- Related modules: export
- Requirements: R022 ([trazabilidad](traceability.md))
- Bloqueo: Ninguno

## Context

Exportar no debe perder píxeles ni sobrescribir archivos por accidente.

## Objective

Escribir PNG maestro y manifiesto con roundtrip y atomicidad comprobados.

## Scope

Crear exportador PNG RGBA/indexado con escala entera y escritura atómica que no sobrescribe por defecto.

## Out of scope

No GIF ni publicar archivos en servicios externos.

## Technical requirements

- Metadata estable; indexed conserva orden y valida cardinalidad/transparencia
- ExportManifest incluye dimensiones, hash, ruta y warnings; evitar cuantización implícita

## Proposed implementation

- Separar encode en memoria del commit a filesystem
- Validar formato/indexado/escala y escribir temporal hermano antes del commit

## Acceptance criteria

- [x] AC1: PNG decodificado es exactamente igual al RenderResult en escala 1
- [x] AC2: Fallo de escritura deja el destino anterior intacto y no devuelve éxito parcial

## Required tests

- [x] T1: Roundtrip RGBA e indexado, transparencia y escala nearest 1/2/4
- [x] T2: Paleta 256/257, destino existente, permiso denegado y fallo simulado durante escritura
- [x] T3: Carrera de dos escritores con overwrite=false: uno gana y el otro falla sin reemplazar; no usar exists+replace como exclusión.

## Expected deliverables

- Exportador PNG y manifiesto de salida con escritura atómica sin sobrescritura accidental.
- Roundtrips RGBA, pruebas de fallo de I/O y carrera entre escritores.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- Una comprobación exists seguida de replace puede sobreescribir por carrera; usar commit sin reemplazo cuando overwrite=false.

## Guía para agentes de IA

**Estado para agentes:** Completado; usar sólo como referencia del contrato entregado.

### 1. Preparación

- Rama: `feat/MOANA-011-exportar-png-manifiesto` creada desde `develop` actualizado: `git switch develop && git pull --ff-only && git switch -c feat/MOANA-011-exportar-png-manifiesto`.
- Verificar en `docs/issues/catalog.json` que este issue está `ready` y que sus dependencias ([MOANA-010](MOANA-010.md)) están `done`.
- Entorno: `uv sync --locked` (sin uv global: `sh scripts/bootstrap.sh` y después `sh scripts/uv.sh` en lugar de `uv`).
- Al empezar, cambiar `status` a `in_progress` en el catálogo y regenerar con `uv run python scripts/planning.py`.

### 2. Lectura obligatoria (en orden)

1. `CLAUDE.md` (Claude Code) o `AGENTS.md` (Codex) y [flujo de sesión](../guides/agent-workflow.md).
2. MOANA.md: §3 Arquitectura modular; §18 Exportación PNG, GIF y formatos adicionales; §25 Definition of Done. Estas secciones son el contrato normativo; ante duda, prevalecen sobre este issue.
3. [Contratos de módulos](../architecture/module-contracts.md) para: `export`.
4. Estándares: [python](../../docs/standards/python.md), [architecture](../../docs/standards/architecture.md), [testing](../../docs/standards/testing.md).
5. Issues de dependencia ([MOANA-010](MOANA-010.md)): leer su sección Evidence para conocer las APIs ya entregadas; no reimplementarlas.
6. ADR en `docs/architecture/` que mencionen los módulos afectados.

### 3. Requisitos de MOANA.md cubiertos

| ID | Requisito | Secciones | Verificación exigida |
| --- | --- | --- | --- |
| R022 | Exportación PNG RGBA/indexada | §18 | Roundtrip decoded y destino intacto al fallar |

### 4. Skills y subagentes

| Host | Skills a cargar | Revisión especializada |
| --- | --- | --- |
| Claude Code | `moana-graphics`, `moana-python`, `moana-code-review` | `moana-graphics-engineer`, `moana-python-engineer` (sólo lectura; el agente principal integra) |
| Codex | `$moana-graphics`, `$moana-python`, `$moana-code-review` | `moana_graphics_engineer`, `moana_python_engineer` |

### 5. Archivos

- Código o documentos a crear/modificar: `src/moana/export/`.
- Pruebas: `tests/unit/export/`.
- No crear módulos ni carpetas sin comportamiento real. No tocar otros módulos salvo exportaciones imprescindibles, justificadas en el PR.

### 6. Plan de pruebas

- T1: Roundtrip RGBA e indexado, transparencia y escala nearest 1/2/4
- T2: Paleta 256/257, destino existente, permiso denegado y fallo simulado durante escritura
- T3: Carrera de dos escritores con overwrite=false: uno gana y el otro falla sin reemplazar; no usar exists+replace como exclusión.
- Oráculos independientes (cálculo a mano o fórmula de MOANA.md); nunca copiar la salida de la implementación como expected.
- Incluir casos negativos con el error de dominio esperado y casos borde (vacío, mínimo, máximo, fuera de rango).

### 7. Procedimiento

1. Escribir las pruebas de los criterios AC y T antes o junto con la implementación.
2. Implementar sólo **Scope**; respetar **Out of scope** y las dependencias permitidas de MOANA.md §3.
3. Validación de módulo: `uv run pytest tests/unit/export/ -q` y `uv run mypy src/`.
4. Validación completa: `uv run python scripts/validate.py` y `uv run python scripts/check_wheel.py`.
5. Revisión: subagentes listados y skill `moana-code-review`; corregir hallazgos críticos y altos.
6. Si hay salida raster: mostrar el PNG a 1x y ampliado por vecino más cercano; si cambia un golden, presentar expected/actual/diff y justificar.

### 8. Cierre

1. En `docs/issues/catalog.json`, para este issue: `status` → `review` (o `done` tras aprobación); completar `acceptance_evidence` (AC1, AC2), `test_evidence` (T1, T2, T3) y `evidence` con rutas concretas de tests y archivos.
2. Issues que desbloquea ([MOANA-012](MOANA-012.md), [MOANA-020](MOANA-020.md), [MOANA-023](MOANA-023.md), [MOANA-024](MOANA-024.md), [MOANA-025](MOANA-025.md), [MOANA-029](MOANA-029.md)): si todas sus dependencias quedan `done`, pasarlos a `ready` con `blocking_reason: null`.
3. Ejecutar `uv run python scripts/planning.py` y `uv run python -m scripts.check_repository`.
4. Abrir PR hacia `develop` enlazando este issue de GitHub (`Closes #<número>`), con comandos ejecutados y evidencia por AC/T. El CI completo corre al integrar `develop` en `main`.
5. Commit y push sólo con autorización del usuario. No declarar CI remoto ni aprobación artística humana sin evidencia.

### 9. Prohibido en este issue

- Implementar alcance de otros issues, incluidos los que desbloquea ([MOANA-012](MOANA-012.md), [MOANA-020](MOANA-020.md), [MOANA-023](MOANA-023.md), [MOANA-024](MOANA-024.md), [MOANA-025](MOANA-025.md), [MOANA-029](MOANA-029.md)).
- Actualizar goldens automáticamente, desactivar checks, editar `uv.lock` a mano o añadir dependencias sin motivo técnico registrado.
- `eval`/`exec`/`pickle`, red o estado global mutable en el núcleo; lecturas de texto sin `encoding="utf-8"`.

## Evidence

- src/moana/export/png.py: encode_png/export_png reciben cualquier RasterFrame (width, height, rgba bytes; RenderResult lo cumple sin que export importe render), validan marco, opciones y presupuesto (export_dimension, export_area, buffer_bytes 24 B/px) antes de reservar, codifican RGBA maestro o indexado (paleta declarada en orden, ≤256 entradas, tRNS explícito, sin cuantización) con compress_level 9 sin chunks volátiles, escalan nearest 1..64 como preview y verifican en memoria la ida y vuelta de píxeles y los chunks PLTE/tRNS antes de escribir.
- src/moana/export/atomic.py: commit_bytes escribe un temporal hermano O_EXCL con fsync y hace commit con os.link (overwrite=False, nunca reemplaza; sin enlaces duros falla con no_replace_unavailable, también por winerror en Windows) u os.replace (overwrite=True); el temporal se borra siempre; errores ExportError con reason, nombre de archivo y errno, sin ruta completa; nombres no representables son invalid_name.
- ExportManifest con path, media_type, mode, dimensiones, frames, scale, master, dimensiones y digest de origen, pixel_digest, file_sha256, byte_size y warnings (scaled_preview); to_mapping ordenado.
- ADR-019 (docs/architecture/decisions/ADR-019-png-export.md); MOANA.md §13 indica que export_png ya existe; contratos de módulos, índice de ADR, overview, README, guía de desarrollo, AGENTS.md y CLAUDE.md actualizados; probe de check_wheel ampliado con export/.
- Gate: scripts/validate.py y scripts/check_wheel.py verdes; moana.export al 100 % de líneas y ramas; mypy también con --platform win32.
- Revisión: moana-python-engineer (cambios requeridos, aplicados: geteuid en win32, OSError de inspección envueltos sin rutas, nombres con NUL o no codificables, temporal con prefijo truncado para nombres largos, carrera determinista que tumba exists+replace, winerror sin enlaces duros, EEXIST tras link propio, rgba leído una vez) y moana-graphics-engineer (aprobado con cambios menores, aplicados: planos de índice sin int64 duplicado y desglose de memoria documentado, verificación de PLTE/tRNS, tests de chunks exactos, escala 64 sobre 1×1 indexado, bytes iguales entre procesos y presupuesto antes de cualquier temporal).
- Aprobado por el propietario el 2026-11-17 tras revisión; PR #49 hacia develop.
- AC1: tests/unit/export/test_export_png.py::test_ac1_rgba_png_decodes_exactly_to_the_frame y ::test_ac1_rendered_document_round_trips (render de examples minimal.moana.json exportado y decodificado igual a RenderResult.rgba, source_digest == digest).
- AC2: tests/unit/export/test_export_png.py::test_ac2_t2_failure_during_write_keeps_previous_content (fallos simulados en write, fsync, link y replace, con y sin overwrite: destino anterior intacto, sin temporales ni manifiesto), ::test_roundtrip_mismatch_writes_nothing y ::test_palette_chunks_are_verified.
- T1: tests/unit/export/test_export_png.py::test_t1_nearest_scale_replicates_blocks[1,2,4], ::test_t1_indexed_round_trip_keeps_declared_order_and_transparency[1,2,4] (PLTE/tRNS exactos), ::test_t1_transparent_frame_round_trips_in_both_modes, ::test_maximum_scale_on_a_single_indexed_pixel, ::test_encoding_is_stable_and_has_no_volatile_chunks y ::test_encoded_bytes_agree_across_fresh_processes_and_hash_seeds.
- T2: tests/unit/export/test_export_png.py::test_t2_palette_of_256_is_accepted_and_257_rejected, ::test_indexed_export_never_quantises, ::test_t2_existing_destination_is_kept_unless_overwrite, ::test_t2_permission_denied_leaves_nothing, ::test_unsearchable_parent_is_permission_denied, ::test_ac2_t2_failure_during_write_keeps_previous_content, ::test_budget_is_checked_before_scaling, ::test_unrepresentable_names_are_rejected_before_writing y ::test_errors_do_not_echo_full_paths.
- T3: tests/unit/export/test_export_png.py::test_t3_competitor_created_between_checks_and_commit_is_never_replaced (determinista: falla con exists+replace), ::test_t3_two_threads_one_wins_the_other_fails_without_replacing (25 repeticiones con barrera) y ::test_t3_two_processes_race_for_the_same_name.
