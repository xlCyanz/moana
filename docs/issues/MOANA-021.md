# MOANA-021 — Versionar y migrar formatos de proyecto

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-021
- Aliases históricos: MOA-021
- Phase: P4
- Priority: P1
- Status: done
- Complexity: M (relativa, no estimación de tiempo)
- Dependencies: [MOANA-020](MOANA-020.md)
- Related modules: project, schema
- Requirements: R019 ([trazabilidad](traceability.md))
- Bloqueo: Ninguno

## Context

La evolución de datos no debe corromper originales ni aceptar versiones desconocidas.

## Objective

Migrar versiones soportadas mediante transformaciones puras y copia preservada.

## Scope

Implementar registro explícito de versiones de schema y migraciones puras con copia original preservada.

## Out of scope

No prometer compatibilidad con formatos que no tengan contrato de migración registrado.

## Technical requirements

- Distinguir versión paquete/schema/renderer y rechazar futuras desconocidas
- Migración offline sin I/O interno; metadata de procedencia y backup gestionados por proyecto

## Proposed implementation

- Registrar rutas explícitas origen/destino y fixtures de versiones reales
- Probar migración y guardado por separado; mantener backup antes de commit

## Acceptance criteria

- [x] AC1: Una fixture de versión anterior migra a v1 conservando semántica y render
- [x] AC2: Abrir un archivo no lo sobrescribe ni aplica migración destructiva silenciosa

## Required tests

- [x] T1: Fixtures de migración, migración repetida/idempotencia del destino y versión futura
- [x] T2: Simular fallo intermedio y comprobar que el original permanece intacto

## Expected deliverables

- Registro explícito de versiones/migraciones y política de incompatibilidad.
- Fixtures de formatos soportados, errores de versiones futuras y migración preservando IDs.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- No inventar un formato histórico publicado; una fixture de prueba debe identificarse como tal.

## Guía para agentes de IA

**Estado para agentes:** Completado; usar sólo como referencia del contrato entregado.

### 1. Preparación

- Rama: `feat/MOANA-021-versionar-migrar-formatos` creada desde `develop` actualizado: `git switch develop && git pull --ff-only && git switch -c feat/MOANA-021-versionar-migrar-formatos`.
- Verificar en `docs/issues/catalog.json` que este issue está `ready` y que sus dependencias ([MOANA-020](MOANA-020.md)) están `done`.
- Entorno: `uv sync --locked` (sin uv global: `sh scripts/bootstrap.sh` y después `sh scripts/uv.sh` en lugar de `uv`).
- Al empezar, cambiar `status` a `in_progress` en el catálogo y regenerar con `uv run python scripts/planning.py`.

### 2. Lectura obligatoria (en orden)

1. `CLAUDE.md` (Claude Code) o `AGENTS.md` (Codex) y [flujo de sesión](../guides/agent-workflow.md).
2. MOANA.md: §3 Arquitectura modular; §16 Formato de proyectos; §25 Definition of Done. Estas secciones son el contrato normativo; ante duda, prevalecen sobre este issue.
3. [Contratos de módulos](../architecture/module-contracts.md) para: `project`, `schema`.
4. Estándares: [python](../../docs/standards/python.md), [architecture](../../docs/standards/architecture.md), [testing](../../docs/standards/testing.md), [security](../../docs/standards/security.md).
5. Issues de dependencia ([MOANA-020](MOANA-020.md)): leer su sección Evidence para conocer las APIs ya entregadas; no reimplementarlas.
6. ADR en `docs/architecture/` que mencionen los módulos afectados.

### 3. Requisitos de MOANA.md cubiertos

| ID | Requisito | Secciones | Verificación exigida |
| --- | --- | --- | --- |
| R019 | Versionado y migraciones | §16 | Fixtures entre versiones y original preservado |

### 4. Skills y subagentes

| Host | Skills a cargar | Revisión especializada |
| --- | --- | --- |
| Claude Code | `moana-python`, `moana-architecture`, `moana-code-review` | `moana-python-engineer`, `moana-architect` (sólo lectura; el agente principal integra) |
| Codex | `$moana-python`, `$moana-architecture`, `$moana-code-review` | `moana_python_engineer`, `moana_architect` |

### 5. Archivos

- Código o documentos a crear/modificar: `src/moana/project/`, `src/moana/schema/`.
- Pruebas: `tests/unit/project/`, `tests/unit/schema/`.
- No crear módulos ni carpetas sin comportamiento real. No tocar otros módulos salvo exportaciones imprescindibles, justificadas en el PR.

### 6. Plan de pruebas

- T1: Fixtures de migración, migración repetida/idempotencia del destino y versión futura
- T2: Simular fallo intermedio y comprobar que el original permanece intacto
- Oráculos independientes (cálculo a mano o fórmula de MOANA.md); nunca copiar la salida de la implementación como expected.
- Incluir casos negativos con el error de dominio esperado y casos borde (vacío, mínimo, máximo, fuera de rango).

### 7. Procedimiento

1. Escribir las pruebas de los criterios AC y T antes o junto con la implementación.
2. Implementar sólo **Scope**; respetar **Out of scope** y las dependencias permitidas de MOANA.md §3.
3. Validación de módulo: `uv run pytest tests/unit/project/ tests/unit/schema/ -q` y `uv run mypy src/`.
4. Validación completa: `uv run python scripts/validate.py` y `uv run python scripts/check_wheel.py`.
5. Revisión: subagentes listados y skill `moana-code-review`; corregir hallazgos críticos y altos.
6. Si hay salida raster: mostrar el PNG a 1x y ampliado por vecino más cercano; si cambia un golden, presentar expected/actual/diff y justificar.

### 8. Cierre

1. En `docs/issues/catalog.json`, para este issue: `status` → `review` (o `done` tras aprobación); completar `acceptance_evidence` (AC1, AC2), `test_evidence` (T1, T2) y `evidence` con rutas concretas de tests y archivos.
2. Issues que desbloquea ([MOANA-030](MOANA-030.md), [MOANA-035](MOANA-035.md)): si todas sus dependencias quedan `done`, pasarlos a `ready` con `blocking_reason: null`.
3. Ejecutar `uv run python scripts/planning.py` y `uv run python -m scripts.check_repository`.
4. Abrir PR hacia `develop` enlazando este issue de GitHub (`Closes #<número>`), con comandos ejecutados y evidencia por AC/T. El CI completo corre al integrar `develop` en `main`.
5. Commit y push sólo con autorización del usuario. No declarar CI remoto ni aprobación artística humana sin evidencia.

### 9. Prohibido en este issue

- Implementar alcance de otros issues, incluidos los que desbloquea ([MOANA-030](MOANA-030.md), [MOANA-035](MOANA-035.md)).
- Actualizar goldens automáticamente, desactivar checks, editar `uv.lock` a mano o añadir dependencias sin motivo técnico registrado.
- `eval`/`exec`/`pickle`, red o estado global mutable en el núcleo; lecturas de texto sin `encoding="utf-8"`.

## Evidence

- Versiones de formato separadas: sólo schema_version y project_version (MAJOR.MINOR, comparadas como enteros) seleccionan migraciones; moana.__version__, RENDERER_VERSION y ESTIMATOR_VERSION nunca (test).
- Registro inmutable moana.schema.versions (MigrationRegistry, Migration) validado al construirse (origen < destino ≤ actual, un paso por origen e ID, cadenas ≤ MAX_MIGRATION_STEPS=16); DOCUMENT_MIGRATIONS y PROJECT_MIGRATIONS de producción sólo conocen 1.0 y no registran migraciones; SUPPORTED_SCHEMA_VERSIONS fijado a la misma fuente por test; los batches conservan su contrato de versión anterior.
- Sin formatos históricos inventados: 0.8 y 0.9 existen sólo en tests/fixtures/migration (registro TEST_ONLY_MIGRATIONS y miembro test_only_format exigido y retirado por el último paso); src/ no menciona esas versiones.
- Leer nunca migra: validate_document y parse_manifest comprueban la versión antes del modelo y lanzan UnsupportedVersion (relation future/past/unknown o migration_required, con field y supported) sin repetir la versión no confiable; load_project no escribe (bytes, inodo y mtime intactos en .moana.json, directorio y ZIP).
- Migración pura moana.schema.migrate_document: sin E/S, rechaza hojas no JSON antes del primer paso (invalid_value), copia acotada antes y después de cada paso, cualquier excepción de un paso es migration_failed con el ID del paso y sin datos del documento, salida cíclica o no JSON también; el resultado se valida y un documento actual es la identidad.
- moana.project.migrate_project: lee la fuente con el mismo despacho de sólo lectura que load_project (project/_load.py), migra en memoria, conserva assets, guarda en un destino nuevo sin sobrescribir (exists) y rechaza un destino igual o dentro de la fuente (destination_inside_source); una fuente actual no escribe nada; un proyecto antiguo con historial es history_not_migratable.
- Procedencia y copia original: miembro opcional migrations del sobre (MigrationRecord: source_kind, member, source/target_version con origen < destino, steps 1–16, path, byte_length, sha256 único), omitido si vacío (hashes de manifiestos existentes intactos); JSON original exacto en migrations/<sha256>.json (lista blanca en ZIP), verificado al cargar; límites MAX_PROJECT_MIGRATIONS=8 y copia ≤ max_manifest_bytes.
- Sin CLI ni fachada (MOANA.md §13 no prevé migrate). ADR-031 (docs/architecture/decisions/ADR-031-format-versions-migrations.md) con notas de cabecera en ADR-011 y ADR-029; MOANA.md 0.1.18-draft (§16); contratos de módulos, índice de ADR, overview, README, AGENTS.md y CLAUDE.md actualizados; tests/__init__.py añadido (descubrimiento y tests/visual sin cambios).
- Gate sobre 55e564e: scripts/validate.py (2419 passed, src/moana al 100 % de líneas y ramas) y scripts/check_wheel.py verdes; mypy también con --platform win32; generate_schema --check al día. Evidencia de plataforma: local macOS; matriz pendiente en main.
- Revisión: moana-architect (aprobado; medios aplicados: member en MigrationRecord, módulo interno _load sin importar privados, fuente única de versiones), moana-python-engineer con foco en seguridad (cambios requeridos, aplicados: cualquier excepción de un paso como migration_failed sin filtrar datos, hojas no JSON rechazadas, registros estrictos y únicos, destino dentro de la fuente rechazado) y moana-qa-engineer (cambios menores, aplicados: origen ZIP en AC1/AC2, estado de directorios en las comprobaciones, bordes de versión y presupuesto, fallo en el segundo paso, Hypothesis contra 1.0 construido a mano).
- Aprobado por el propietario el 2026-11-17 tras revisión; PR #60 hacia develop.
- AC1: tests/unit/schema/test_schema_migrations.py::test_ac1_test_only_fixture_migrates_to_v1_keeping_semantics_and_render; tests/unit/project/test_project_migrations.py::test_ac1_document_fixture_migrates_into_a_new_project, ::test_ac1_project_fixture_keeps_assets_and_render, ::test_ac1_migration_records_survive_saving_again, ::test_ac1_a_migrated_project_can_be_migrated_again, ::test_ac1_archive_fixture_migrates_and_stays_intact.
- AC2: tests/unit/project/test_project_migrations.py::test_ac2_opening_an_old_file_neither_writes_nor_migrates, ::test_ac2_migration_never_replaces_an_existing_project, ::test_ac2_destination_inside_the_source_is_refused, ::test_ac2_a_document_migrated_beside_itself_stays_intact, ::test_ac2_unresolvable_paths_are_compared_as_absolute.
- T1: tests/unit/schema/test_schema_migrations.py::test_t1_production_registry_claims_no_unpublished_format, ::test_t1_format_versions_are_distinct_from_package_and_renderer, ::test_t1_parse_version, ::test_t1_future_and_unknown_versions_are_rejected, ::test_t1_registered_older_version_requires_explicit_migration, ::test_t1_registry_is_checked_on_construction, ::test_t1_chains_longer_than_the_limit_are_rejected, ::test_t1_migrating_the_destination_again_is_the_identity, ::test_t1_step_failures_are_domain_errors, ::test_t1_intermediate_trees_stay_bounded, ::test_t1_hostile_step_output_is_a_migration_failure, ::test_t1_malformed_test_only_sources_fail_with_the_step_id, ::test_t1_step_exceptions_never_leak_document_data, ::test_t1_non_json_input_is_rejected_before_any_step, ::test_t1_migration_result_is_validated, ::test_t1_registry_must_target_the_current_document_schema, ::test_t1_non_string_version_is_left_to_validation, ::test_t1_version_spelling_variants_are_unknown, ::test_t1_supported_versions_have_one_source, ::test_t1_property_migration_preserves_ids_and_is_idempotent; tests/unit/project/test_project_migrations.py::test_t1_migrating_the_destination_again_writes_nothing, ::test_t1_unknown_document_versions_are_rejected_before_writing, ::test_t1_unknown_project_versions_are_rejected, ::test_t1_envelope_errors_keep_their_pointers, ::test_t1_history_has_no_migration_contract, ::test_t1_registry_must_migrate_documents_to_the_current_schema, ::test_t1_preserved_originals_are_verified_and_bounded, ::test_t1_migration_records_are_strict, ::test_t1_each_original_is_preserved_once, ::test_t1_migration_budget_is_checked_before_writing, ::test_t1_future_envelope_wins_over_an_old_document, ::test_t1_backups_are_checked_in_memory.
- T2: tests/unit/project/test_project_migrations.py::test_t2_failure_at_every_step_keeps_the_original_intact, ::test_t2_a_failing_second_step_writes_nothing.
