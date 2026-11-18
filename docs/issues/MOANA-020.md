# MOANA-020 — Persistir proyectos y assets seguros

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-020
- Aliases históricos: MOA-020
- Phase: P4
- Priority: P1
- Status: done
- Complexity: L (relativa, no estimación de tiempo)
- Dependencies: [MOANA-018](MOANA-018.md), [MOANA-019](MOANA-019.md), [MOANA-011](MOANA-011.md)
- Related modules: project
- Requirements: R018, R026 ([trazabilidad](traceability.md))
- Bloqueo: Ninguno

## Context

Los assets y archivos de proyecto atraviesan una frontera de datos no confiables.

## Objective

Guardar/cargar documentos y assets de forma confinada, íntegra y atómica.

## Scope

Crear formato .moana.json, proyecto directorio y contenedor ZIP opcional con assets declarados, hashes y escritura atómica.

## Out of scope

No soporte PSD/Aseprite ni assets remotos o ejecutables.

## Technical requirements

- Confinar rutas y rechazar symlinks, duplicados y traversal antes de extracción
- Limitar entradas, expansión/ratio, bytes y decode Pillow; guardar temporal y conservar destino al fallar
- Modelar ProjectManifest separado de Document y persistir assets/snapshots bajo rutas inmutables por hash antes del commit del manifiesto.

## Proposed implementation

- Definir manifiesto separado del documento y almacenamiento content-addressed de assets
- Inspeccionar ZIP/paths/tamaños antes de escribir y comprometer manifiesto al final

## Acceptance criteria

- [x] AC1: Guardar/cargar preserva IDs, revisiones, historial y RGBA
- [x] AC2: Un asset con checksum incorrecto o ruta maliciosa no escribe fuera de la raíz ni carga parcialmente

## Required tests

- [x] T1: Roundtrip proyecto geométrico y con PNG; fallo simulado de disco
- [x] T2: ZIP con ../, rutas absolutas, symlink, nombres en colisión, ratio excesivo y bomba de imagen
- [x] T3: Fallo después de escribir nuevos assets conserva manifiesto y assets previos; el envelope rechaza campos extra sin alterar el schema de Document.

## Expected deliverables

- ProjectManifest, persistencia de assets verificados y guardado con commit final atómico.
- Roundtrips, rechazo de rutas/archivos peligrosos y fallos durante la escritura.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- Guardar el mismo asset path in-place antes del manifiesto rompe atomicidad; versiones inmutables necesarias.
- Convergencia del historial (MOANA-019, ADR-026 §4): un digest alcanzado desde otro padre se rechaza con EditConflict (existing_snapshot); permitirla exige separar la identidad de la entrada de historial (padre + batch + digest) del almacén por contenido, con un ADR nuevo antes de persistir.

## Guía para agentes de IA

**Estado para agentes:** Completado; usar sólo como referencia del contrato entregado.

### 1. Preparación

- Rama: `feat/MOANA-020-persistir-proyectos-assets` creada desde `develop` actualizado: `git switch develop && git pull --ff-only && git switch -c feat/MOANA-020-persistir-proyectos-assets`.
- Verificar en `docs/issues/catalog.json` que este issue está `ready` y que sus dependencias ([MOANA-018](MOANA-018.md), [MOANA-019](MOANA-019.md), [MOANA-011](MOANA-011.md)) están `done`.
- Entorno: `uv sync --locked` (sin uv global: `sh scripts/bootstrap.sh` y después `sh scripts/uv.sh` en lugar de `uv`).
- Al empezar, cambiar `status` a `in_progress` en el catálogo y regenerar con `uv run python scripts/planning.py`.

### 2. Lectura obligatoria (en orden)

1. `CLAUDE.md` (Claude Code) o `AGENTS.md` (Codex) y [flujo de sesión](../guides/agent-workflow.md).
2. MOANA.md: §3 Arquitectura modular; §16 Formato de proyectos; §20 Seguridad y validación; §25 Definition of Done. Estas secciones son el contrato normativo; ante duda, prevalecen sobre este issue.
3. [Contratos de módulos](../architecture/module-contracts.md) para: `project`.
4. Estándares: [python](../../docs/standards/python.md), [architecture](../../docs/standards/architecture.md), [testing](../../docs/standards/testing.md), [security](../../docs/standards/security.md).
5. Issues de dependencia ([MOANA-018](MOANA-018.md), [MOANA-019](MOANA-019.md), [MOANA-011](MOANA-011.md)): leer su sección Evidence para conocer las APIs ya entregadas; no reimplementarlas.
6. ADR en `docs/architecture/` que mencionen los módulos afectados.

### 3. Requisitos de MOANA.md cubiertos

| ID | Requisito | Secciones | Verificación exigida |
| --- | --- | --- | --- |
| R018 | Formato de proyectos y assets | §16 | Roundtrip y escritura atómica confinada |
| R026 | Validación y seguridad de datos | §20 | Entradas adversarias rechazadas antes de reservar/IO |

### 4. Skills y subagentes

| Host | Skills a cargar | Revisión especializada |
| --- | --- | --- |
| Claude Code | `moana-python`, `moana-code-review` | `moana-python-engineer`, `moana-architect` (sólo lectura; el agente principal integra) |
| Codex | `$moana-python`, `$moana-code-review` | `moana_python_engineer`, `moana_architect` |

### 5. Archivos

- Código o documentos a crear/modificar: `src/moana/project/`.
- Pruebas: `tests/unit/project/`.
- No crear módulos ni carpetas sin comportamiento real. No tocar otros módulos salvo exportaciones imprescindibles, justificadas en el PR.

### 6. Plan de pruebas

- T1: Roundtrip proyecto geométrico y con PNG; fallo simulado de disco
- T2: ZIP con ../, rutas absolutas, symlink, nombres en colisión, ratio excesivo y bomba de imagen
- T3: Fallo después de escribir nuevos assets conserva manifiesto y assets previos; el envelope rechaza campos extra sin alterar el schema de Document.
- Oráculos independientes (cálculo a mano o fórmula de MOANA.md); nunca copiar la salida de la implementación como expected.
- Incluir casos negativos con el error de dominio esperado y casos borde (vacío, mínimo, máximo, fuera de rango).

### 7. Procedimiento

1. Escribir las pruebas de los criterios AC y T antes o junto con la implementación.
2. Implementar sólo **Scope**; respetar **Out of scope** y las dependencias permitidas de MOANA.md §3.
3. Validación de módulo: `uv run pytest tests/unit/project/ -q` y `uv run mypy src/`.
4. Validación completa: `uv run python scripts/validate.py` y `uv run python scripts/check_wheel.py`.
5. Revisión: subagentes listados y skill `moana-code-review`; corregir hallazgos críticos y altos.
6. Si hay salida raster: mostrar el PNG a 1x y ampliado por vecino más cercano; si cambia un golden, presentar expected/actual/diff y justificar.

### 8. Cierre

1. En `docs/issues/catalog.json`, para este issue: `status` → `review` (o `done` tras aprobación); completar `acceptance_evidence` (AC1, AC2), `test_evidence` (T1, T2, T3) y `evidence` con rutas concretas de tests y archivos.
2. Issues que desbloquea ([MOANA-021](MOANA-021.md), [MOANA-030](MOANA-030.md), [MOANA-033](MOANA-033.md), [MOANA-034](MOANA-034.md)): si todas sus dependencias quedan `done`, pasarlos a `ready` con `blocking_reason: null`.
3. Ejecutar `uv run python scripts/planning.py` y `uv run python -m scripts.check_repository`.
4. Abrir PR hacia `develop` enlazando este issue de GitHub (`Closes #<número>`), con comandos ejecutados y evidencia por AC/T. El CI completo corre al integrar `develop` en `main`.
5. Commit y push sólo con autorización del usuario. No declarar CI remoto ni aprobación artística humana sin evidencia.

### 9. Prohibido en este issue

- Implementar alcance de otros issues, incluidos los que desbloquea ([MOANA-021](MOANA-021.md), [MOANA-030](MOANA-030.md), [MOANA-033](MOANA-033.md), [MOANA-034](MOANA-034.md)).
- Actualizar goldens automáticamente, desactivar checks, editar `uv.lock` a mano o añadir dependencias sin motivo técnico registrado.
- `eval`/`exec`/`pickle`, red o estado global mutable en el núcleo; lecturas de texto sin `encoding="utf-8"`.

## Evidence

- Módulo moana.project (ADR-029): Project, Asset.from_png, save_project (directorio), save_project_archive (.moana ZIP), save_document (.moana.json), load_project, encode_project, ProjectLimits (sólo se pueden bajar) y SaveReport; depende sólo de core, schema (API pública, incluida document_ids), editing, Pydantic y Pillow encapsulado; nada inferior lo importa (test AST con rglob). Sin fachada ni CLI (MOANA.md §13 no los prevé).
- Sobre ProjectManifest {kind, project_version 1.0, document, assets, history} estricto, congelado y separado de Document (JSON Schema de Document intacto); lector propio acotado (bytes, profundidad, nodos, claves duplicadas, números no finitos); un documento plano se valida con el lector de schema.
- Almacén inmutable por hash: assets/<sha256>.png, history/snapshots/<digest>.json y history/batches/<sha256>.json escritos antes de confirmar el manifiesto; el guardado comprueba antes de escribir todo lo que la carga comprobará (forma canónica del documento, snapshots, batches, manifiesto, historial), de modo que lo guardado siempre carga con los mismos límites.
- Escritura atómica (temporal O_EXCL, fsync, os.replace/os.link, fsync de directorios con aborto en fallo) con la misma tabla de razones que export.atomic (no_replace_unavailable, permission_denied, invalid_name; test de paridad); en POSIX toda E/S va por descriptores de directorio O_DIRECTORY|O_NOFOLLOW (cierra el TOCTOU por symlink intermedio; fallback documentado en Windows); errores sin rutas sensibles.
- ZIP inspeccionado sin extraer: EOCD estricto (sin comentario ni ZIP64, directorio central acotado), cifrado, compresión exótica, symlinks, rutas absolutas/unidad/traversal/barra invertida, duplicados y colisiones NFC+casefold, ratio ≤ 100:1, expansión ≤ 256 MiB, ≤ 256 entradas y 64 MiB; escritura determinista con la misma zlib (identidad estable = hash del manifiesto).
- Assets PNG RGBA de 8 bits: longitud y SHA-256 exactos, IHDR ≤ 2048 por eje y presupuesto de píxeles antes de Pillow; APNG, ICC, PNG truncado (IEND) y DecompressionBombError rechazados como errores de dominio; IDAT CRC no verificado por Moana (riesgo bajo aceptado: el SHA-256 va antes).
- Historial: entradas {snapshot, parent, batch, redo} reconstruidas reaplicando cada batch y con el constructor validado de History; convergencia rechazada como en ADR-026 §4; HistoryLimits es configuración del anfitrión que carga; cubre documentos con shade (affected_ids con IDs de banda). IDs de assets distintos de schema.document_ids (incluidas bandas).
- Diez límites nuevos en moana.core.limits (MAX_PROJECT_*, MAX_ASSET_*, MAX_ARCHIVE_*). ADR-029 con notas de cabecera en ADR-010, ADR-024 y ADR-026; MOANA.md 0.1.17-draft (§16); contratos de módulos, índice de ADR, overview, README, AGENTS.md y CLAUDE.md actualizados. Seguimientos: causa raíz de documentos cuya forma canónica supera el límite (schema/History), módulo común de escritura atómica, recolección de huérfanos, previews, migraciones y fachada/CLI.
- Gate sobre develop 4265cdf (MOANA-015 incluido): scripts/validate.py (2318 passed, src/moana al 100 % de líneas y ramas) y scripts/check_wheel.py verdes; mypy también con --platform win32; generate_schema --check al día. Evidencia de plataforma: local macOS; la rama Windows sin dir_fd sólo se prueba forzando el fallback; matriz pendiente en main.
- Revisión: moana-architect (cambios requeridos, aplicados: document_ids de schema, paridad con export.atomic, determinismo del ZIP acotado, clases de error, superficie pública documentada), moana-python-engineer con foco en seguridad (cambios requeridos, aplicados: ruta filtrada en PermissionError, directorio central acotado, ZIP64 y comentario rechazados, TOCTOU de escritura con dir_fd, Pillow, números no finitos, criterio único de symlinks) y moana-qa-engineer (cambios requeridos, aplicados: guardados que no recargaban, fallos de disco paso a paso con assets e historial, orden de fsync, propiedad Hypothesis de roundtrip, bordes exactos).
- Aprobado por el propietario el 2026-11-17 tras revisión; PR #59 hacia develop.
- AC1: tests/unit/project/test_project_roundtrip.py::test_ac1_directory_roundtrip_preserves_ids_revisions_history_and_rgba, ::test_ac1_history_limits_are_the_loader_configuration, ::test_ac1_loaded_history_keeps_navigating_and_editing, ::test_ac1_archive_roundtrip_is_deterministic, ::test_ac1_shaded_document_history_roundtrip.
- AC2: tests/unit/project/test_project_security.py::test_ac2_asset_path_outside_the_layout_is_rejected, ::test_ac2_wrong_checksum_never_loads_partially, ::test_ac2_longer_asset_file_is_a_checksum_mismatch, ::test_ac2_linked_assets_never_leave_the_root, ::test_ac2_special_files_are_not_read, ::test_ac2_asset_ids_are_unique_and_distinct_from_document_ids, ::test_ac2_asset_id_of_a_shade_band_is_an_id_collision.
- T1: tests/unit/project/test_project_atomic.py::test_t1_failure_at_every_step_keeps_the_previous_project, ::test_t1_commit_order_content_then_directories_then_manifest, ::test_t1_directory_sync_failure_aborts_before_the_commit, ::test_t1_archive_failure_keeps_the_previous_archive, ::test_t1_single_file_saves_never_overwrite_implicitly, ::test_t1_atomic_write_errors_match_export_atomic, ::test_t1_eexist_for_the_same_file_is_success, ::test_t1_missing_hard_links_fail_before_writing_content, ::test_t1_directory_creation_failures, ::test_t1_subdirectory_creation_failures, ::test_t1_temporary_file_creation_failures, ::test_t1_unsafe_project_directories_are_refused, ::test_t1_linked_directories_are_refused, ::test_t1_caller_path_links_are_followed, ::test_t1_link_swapped_in_after_mkdir_is_refused, ::test_t1_link_swapped_in_after_opening_never_redirects_writes, ::test_t1_unreadable_ancestor_is_permission_denied_without_the_path, ::test_t1_inspection_failures_of_the_destination; tests/unit/project/test_project_budgets.py::test_t1_canonical_form_over_the_node_limit_is_refused_before_writing, ::test_t1_one_operation_less_saves_and_loads_in_every_format, ::test_t1_every_stored_part_is_checked_with_the_reader_bounds, ::test_t1_an_archive_holds_128_snapshots_but_not_129, ::test_t1_property_any_saved_project_loads_back_identically; tests/unit/project/test_project_roundtrip.py::test_t1_geometric_document_roundtrip, ::test_t1_project_without_assets_or_history, ::test_t1_png_asset_roundtrip_keeps_source_bytes, ::test_t1_layout_uses_immutable_hash_paths, ::test_t1_envelope_file_loads_with_assets_beside_it, ::test_t1_resave_reuses_content_and_needs_overwrite, ::test_t1_corrupt_content_file_is_rewritten_on_save, ::test_t1_missing_project_is_a_read_error, ::test_t1_cursor_document_is_the_manifest_document.
- T2: tests/unit/project/test_project_budgets.py::test_t2_expansion_ratio_border_is_exactly_100_to_1; tests/unit/project/test_project_security.py::test_t2_archive_names_are_rejected_before_extraction, ::test_t2_symlink_entries_are_rejected, ::test_t2_duplicate_and_colliding_names_are_rejected, ::test_t2_excessive_expansion_ratio_is_rejected, ::test_t2_archive_budgets_are_checked_from_the_central_directory, ::test_t2_encrypted_or_exotic_entries_are_rejected, ::test_t2_corrupt_archives_are_rejected, ::test_t2_corrupt_entry_data_fails_its_crc, ::test_t2_archive_without_manifest_or_declared_file, ::test_t2_dense_entries_are_stored_so_saved_archives_always_load, ::test_t2_image_bomb_is_rejected_before_decoding, ::test_t2_asset_pixel_and_byte_budgets, ::test_t2_project_pixel_budget_across_assets, ::test_t2_png_assets_are_checked_before_full_decode, ::test_t2_truncated_png_is_rejected_even_if_pillow_tolerates_it, ::test_t2_pillow_decompression_bomb_is_a_domain_error, ::test_t2_asset_values_are_consistent.
- T3: tests/unit/project/test_project_atomic.py::test_t3_failure_after_new_assets_keeps_previous_manifest_and_assets, ::test_t3_new_save_never_rewrites_referenced_bytes; tests/unit/project/test_project_budgets.py::test_t3_finite_floats_are_read_and_overflowing_ones_rejected, ::test_t3_too_many_asset_references_is_a_budget, ::test_t3_declared_asset_length_over_the_limit_is_a_budget, ::test_t3_too_many_history_entries_is_a_budget; tests/unit/project/test_project_manifest.py::test_t3_envelope_rejects_extra_fields_without_touching_document_schema, ::test_t3_extra_document_member_keeps_its_document_error, ::test_t3_envelope_members_are_strict, ::test_t3_missing_history_defaults_to_empty, ::test_t3_parse_manifest_requires_an_object, ::test_t3_manifest_reading_is_bounded, ::test_t3_manifest_byte_limit, ::test_t3_plain_json_files_are_documents_or_envelopes, ::test_t3_tampered_snapshot_file_is_a_checksum_mismatch, ::test_t3_batch_that_does_not_reproduce_its_snapshot, ::test_t3_unusable_batches_are_rejected, ::test_t3_unusable_snapshots_are_rejected, ::test_t3_inconsistent_history_entries_are_rejected, ::test_t3_history_budgets_are_checked_while_reading, ::test_t3_convergent_branches_stay_rejected_after_loading.
