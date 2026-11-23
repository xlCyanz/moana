# MOANA-037 — Renombrado completo del proyecto a MoanArt

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-037
- Aliases históricos: Ninguno
- Phase: P5
- Priority: P1
- Status: review
- Complexity: XL (relativa, no estimación de tiempo)
- Dependencies: [MOANA-020](MOANA-020.md), [MOANA-021](MOANA-021.md), [MOANA-035](MOANA-035.md)
- Related modules: core, schema, cli, api, project, export, quality, render, agents, docs, tooling, release, examples
- Requirements: R030, R031, R033 ([trazabilidad](traceability.md))
- Bloqueo: Ninguno

## Context

El propietario decidió el 2026-11-20, tras publicar la prerelease de GitHub v0.1.0rc1 con el nombre Moana, renombrar el proyecto a MoanArt de forma completa (API, CLI, formatos, skills y agentes) en la siguiente versión. El nombre aparece en 513 de 566 archivos versionados (~8.800 menciones, 203 rutas). La distribución `moanart` no existía en PyPI al comprobarlo ese día.

## Objective

Que el producto, su API, su CLI y sus formatos se llamen MoanArt de forma coherente y comprobada, sin cambiar ningún píxel ni digest y con una migración explícita para lo guardado con el nombre anterior.

## Scope

Renombrar el producto de Moana a MoanArt en todas las superficies: distribución `moanart`, paquete importable `moanart`, comando `moanart`, clases y campos públicos (`MoanArtError`, `moanart_version`), extensiones `.moanart`/`.moanart.json`, identificadores de formato versionados `moanart-*/1` y `$id` del JSON Schema, variables de entorno `MOANART_*`, documentación, skills, agentes, hooks y ejemplos; con un ADR que fije la ruptura y una ruta de migración explícita para proyectos y artefactos con el nombre antiguo.

## Out of scope

No cambiar la semántica del render, del schema 1.0, de la edición ni de los presupuestos; no renombrar los IDs históricos de issues (MOANA-xxx), los aliases MOA-xxx ni el tag `v0.1.0rc1`; no renombrar el repositorio remoto, publicar 0.1.0rc2 ni subir a PyPI (acciones del propietario con autorización aparte).

## Technical requirements

- Ruptura deliberada antes de 1.0: sin alias de importación ni comando `moana` salvo que el ADR justifique un shim temporal con fecha de retirada; el renombrado no altera documentos, revisiones, `snapshot_digest` ni RGBA
- Los identificadores con el nombre antiguo (`.moana`, `.moana.json`, `moana-rubric/1`, `moana-spritesheet`, `moana-tile-layout/1`, `moana-layer-cache/1`, `moana-benchmark/1`, `moana-determinism-*/1`, `moana-corpus-entry/1`) se rechazan con `UnsupportedVersion` o un error de dominio que nombra el reemplazo; sólo `migrate_project` (y el equivalente para manifiestos, si el ADR lo decide) los lee, a un destino nuevo y conservando el original
- Los IDs de issue MOANA-xxx siguen siendo canónicos (historial, mapa de GitHub, ADR y trazabilidad) y el checker de repositorio lo hace explícito; los nombres de skills y agentes pasan a `moanart-*` con fuente canónica y envoltorios coincidentes

## Proposed implementation

- ADR nuevo con la tabla nombre antiguo → nuevo, la política de compatibilidad (sin alias por defecto), la lista de excepciones y la ruta de migración; ADR afectados sólo con «Ampliado por ADR-0xx»
- Renombrado mecánico en pasos verificables: `git mv src/moana src/moanart` y rutas, luego identificadores de código, luego formatos versionados con sus migraciones, luego docs/skills/agentes/hooks; gate completo tras cada paso
- Prueba de repositorio contra el nombre antiguo y regeneración de catálogo, inventario, RELEASE.md y artefactos derivados (sin tocar goldens de píxeles)

## Acceptance criteria

- [ ] AC1: `pip install moanart` desde el wheel y el sdist limpios ofrece `import moanart`, el comando `moanart` y los mismos resultados (documentos, digests, RGBA, códigos de salida) que 0.1.0rc1 sobre los ejemplos, el corpus, los tiles y el tutorial
- [ ] AC2: Ninguna superficie pública ni archivo del repositorio usa el nombre antiguo fuera de una lista de excepciones auditada (IDs MOANA-xxx, historial del CHANGELOG, ADR aceptados, release 0.1.0rc1 y las tablas de migración) que el checker de repositorio comprueba
- [ ] AC3: Un proyecto y los manifiestos guardados con el nombre antiguo se migran de forma explícita y reversible a los nuevos identificadores, y cargarlos sin migrar falla con un error que indica la migración

## Required tests

- [ ] T1: Prueba de repositorio que busca el nombre antiguo (sin distinguir mayúsculas) en rutas, código, docs y metadatos del wheel/sdist y falla fuera de la lista de excepciones
- [ ] T2: Regresión de digests: el corpus, los tiles, el tutorial y los fixtures de determinismo producen los mismos `snapshot_digest` y RGBA que en 0.1.0rc1; la matriz CI y el job de determinismo verdes
- [ ] T3: Migración de proyectos directorio, `.moana` ZIP y `.moana.json` y de manifiestos de spritesheet/rúbrica con el nombre antiguo, rechazo sin migrar y conservación del original; `check_wheel` instala `moanart` limpio

## Expected deliverables

- Paquete, CLI y formatos con el nombre MoanArt, con versión 0.1.0rc2 preparada en el CHANGELOG como ruptura documentada.
- ADR del renombrado, migración de proyectos y manifiestos antiguos, y prueba que impide reintroducir el nombre antiguo.

## Definition of Done

Cumplir [MOANART.md §25](../../MOANART.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- Un reemplazo masivo puede tocar texto que no es el nombre (p. ej. otras palabras con la subcadena) o IDs históricos: revisar el diff por categorías y mantener la lista de excepciones mínima.
- Cambiar identificadores de formato invalida artefactos ya generados (spritesheets, rúbricas, informes de benchmark): deben regenerarse o migrarse, nunca editarse a mano para hacer pasar digests.

## Guía para agentes de IA

**Estado para agentes:** En revisión: sólo correcciones de la revisión; no añadir alcance.

### 1. Preparación

- Rama: `feat/MOANA-037-renombrado-completo-proyecto` creada desde `develop` actualizado: `git switch develop && git pull --ff-only && git switch -c feat/MOANA-037-renombrado-completo-proyecto`.
- Verificar en `docs/issues/catalog.json` que este issue está `ready` y que sus dependencias ([MOANA-020](MOANA-020.md), [MOANA-021](MOANA-021.md), [MOANA-035](MOANA-035.md)) están `done`.
- Entorno: `uv sync --locked` (sin uv global: `sh scripts/bootstrap.sh` y después `sh scripts/uv.sh` en lugar de `uv`).
- Al empezar, cambiar `status` a `in_progress` en el catálogo y regenerar con `uv run python scripts/planning.py`.

### 2. Lectura obligatoria (en orden)

1. `CLAUDE.md` (Claude Code) o `AGENTS.md` (Codex) y [flujo de sesión](../guides/agent-workflow.md).
2. MOANART.md: §3 Arquitectura modular; §4 Stack tecnológico; §25 Definition of Done. Estas secciones son el contrato normativo; ante duda, prevalecen sobre este issue.
3. [Contratos de módulos](../architecture/module-contracts.md) para: `core`, `schema`, `cli`, `api`, `project`, `export`, `quality`, `render`, `agents`, `docs`, `tooling`, `release`, `examples`.
4. Estándares: [python](../../docs/standards/python.md), [architecture](../../docs/standards/architecture.md), [testing](../../docs/standards/testing.md), [security](../../docs/standards/security.md), [pixel-art](../../docs/standards/pixel-art.md).
5. Issues de dependencia ([MOANA-020](MOANA-020.md), [MOANA-021](MOANA-021.md), [MOANA-035](MOANA-035.md)): leer su sección Evidence para conocer las APIs ya entregadas; no reimplementarlas.
6. ADR en `docs/architecture/` que mencionen los módulos afectados.

### 3. Requisitos de MOANART.md cubiertos

| ID | Requisito | Secciones | Verificación exigida |
| --- | --- | --- | --- |
| R030 | Arquitectura modular y documentación | §3 | Dependencias internas y ADR revisados |
| R031 | Paquete instalable y artefactos | §4, §25 | Build y smoke de wheel/sdist aislados |
| R033 | Siete skills especializadas | §3, §25 | Frontmatter, UI metadata, referencias y validador de skills |

### 4. Skills y subagentes

| Host | Skills a cargar | Revisión especializada |
| --- | --- | --- |
| Claude Code | `moanart-python`, `moanart-graphics`, `moanart-architecture`, `moanart-pixel-art`, `moanart-testing`, `moanart-issue-planning`, `moanart-code-review` | `moanart-python-engineer`, `moanart-architect`, `moanart-graphics-engineer`, `moanart-pixel-artist`, `moanart-qa-engineer`, `moanart-documentation` (sólo lectura; el agente principal integra) |
| Codex | `$moanart-python`, `$moanart-graphics`, `$moanart-architecture`, `$moanart-pixel-art`, `$moanart-testing`, `$moanart-issue-planning`, `$moanart-code-review` | `moanart_python_engineer`, `moanart_architect`, `moanart_graphics_engineer`, `moanart_pixel_artist`, `moanart_qa_engineer`, `moanart_documentation` |

### 5. Archivos

- Código o documentos a crear/modificar: `src/moanart/core/`, `src/moanart/schema/`, `src/moanart/cli/`, `src/moanart/api/`, `src/moanart/project/`, `src/moanart/export/`, `src/moanart/quality/`, `src/moanart/render/`, `docs/guides/`, `.agents/skills/`, `.claude/`, `docs/`, `scripts/`, `pyproject.toml`, `CHANGELOG.md`, `README.md`, `examples/`.
- Pruebas: `tests/unit/core/`, `tests/unit/schema/`, `tests/unit/cli/`, `tests/unit/api/`, `tests/unit/project/`, `tests/unit/export/`, `tests/unit/quality/`, `tests/unit/render/`, `tests/test_repository_tools.py`, `tests/`, `scripts/check_wheel.py`, `tests/integration/`.
- No crear módulos ni carpetas sin comportamiento real. No tocar otros módulos salvo exportaciones imprescindibles, justificadas en el PR.

### 6. Plan de pruebas

- T1: Prueba de repositorio que busca el nombre antiguo (sin distinguir mayúsculas) en rutas, código, docs y metadatos del wheel/sdist y falla fuera de la lista de excepciones
- T2: Regresión de digests: el corpus, los tiles, el tutorial y los fixtures de determinismo producen los mismos `snapshot_digest` y RGBA que en 0.1.0rc1; la matriz CI y el job de determinismo verdes
- T3: Migración de proyectos directorio, `.moana` ZIP y `.moana.json` y de manifiestos de spritesheet/rúbrica con el nombre antiguo, rechazo sin migrar y conservación del original; `check_wheel` instala `moanart` limpio
- Oráculos independientes (cálculo a mano o fórmula de MOANART.md); nunca copiar la salida de la implementación como expected.
- Incluir casos negativos con el error de dominio esperado y casos borde (vacío, mínimo, máximo, fuera de rango).

### 7. Procedimiento

1. Escribir las pruebas de los criterios AC y T antes o junto con la implementación.
2. Implementar sólo **Scope**; respetar **Out of scope** y las dependencias permitidas de MOANART.md §3.
3. Validación de módulo: `uv run pytest tests/unit/core/ tests/unit/schema/ tests/unit/cli/ tests/unit/api/ tests/unit/project/ tests/unit/export/ tests/unit/quality/ tests/unit/render/ tests/test_repository_tools.py tests/ scripts/check_wheel.py tests/integration/ -q` y `uv run mypy src/`.
4. Validación completa: `uv run python scripts/validate.py` y `uv run python scripts/check_wheel.py`.
5. Revisión: subagentes listados y skill `moanart-code-review`; corregir hallazgos críticos y altos.
6. Si hay salida raster: mostrar el PNG a 1x y ampliado por vecino más cercano; si cambia un golden, presentar expected/actual/diff y justificar.

### 8. Cierre

1. En `docs/issues/catalog.json`, para este issue: `status` → `review` (o `done` tras aprobación); completar `acceptance_evidence` (AC1, AC2, AC3), `test_evidence` (T1, T2, T3) y `evidence` con rutas concretas de tests y archivos.
2. Issues que desbloquea (ninguno): si todas sus dependencias quedan `done`, pasarlos a `ready` con `blocking_reason: null`.
3. Ejecutar `uv run python scripts/planning.py` y `uv run python -m scripts.check_repository`.
4. Abrir PR hacia `develop` enlazando este issue de GitHub (`Closes #<número>`), con comandos ejecutados y evidencia por AC/T. El CI completo corre al integrar `develop` en `main`.
5. Commit y push sólo con autorización del usuario. No declarar CI remoto ni aprobación artística humana sin evidencia.

### 9. Prohibido en este issue

- Implementar alcance de otros issues, incluidos los que desbloquea (ninguno).
- Actualizar goldens automáticamente, desactivar checks, editar `uv.lock` a mano o añadir dependencias sin motivo técnico registrado.
- `eval`/`exec`/`pickle`, red o estado global mutable en el núcleo; lecturas de texto sin `encoding="utf-8"`.

## Evidence

- Renombrado mecánico verificado de 406 archivos y 169 rutas (src/moanart, examples/**/*.moanart.json, MOANART.md, skills .agents/skills/moanart-*, subagentes .claude/agents/moanart-*, roles Codex moanart_*), distribución moanart 0.1.0rc2 en pyproject.toml, uv.lock regenerado con uv lock (sólo cambia el nombre del paquete), variables MOANART_*, JSON Schema schemas/moanart-document-1.0.schema.json. Sin alias de import ni comando del nombre anterior.
- ADR-041 (tabla nombre antiguo -> nuevo, política sin alias, excepciones auditadas y ruta de migración); ADR-003, ADR-004, ADR-006, ADR-009, ADR-011, ADR-021, ADR-029, ADR-031, ADR-033, ADR-037 y ADR-038 sólo con «Ampliado por ADR-041».
- Proyectos de 0.1.0rc1: moanart.project.manifest.LEGACY_MANIFEST_NAME/LEGACY_PROJECT_KIND, legacy_name_error; _load.consume_source(legacy=...) y ArchiveReader.has; migrate.py::_rename_legacy (registro member kind, paso rename-to-moanart, historial y assets conservados, original en migrations/<sha256>.json). Manifiestos: moanart.export.migrate_spritesheet_manifest y moanart.quality.migrate_rubric (puras), rechazo legacy_name en parse_spritesheet_manifest/slice/load y parse_rubric.
- Comprobador scripts/legacy_name.py integrado en scripts/check_repository.py y en audit_wheel/audit_sdist de scripts/check_wheel.py; excepciones con motivo: CHANGELOG, ADR aceptados, ADR-041, MOANA-037, metadata de documentos con digest fijado, procedencia del layout de tiles, tablas de migración, etiqueta remota del backlog y el propio comprobador.
- Equivalencia independiente rc1/rc2: el tag v0.1.0rc1 (paquete moana) y esta rama (moanart) sobre los 30 documentos de examples/ de rc1, sus 3 batches y un archivo inexistente dan los mismos snapshot_digest, RGBA, bytes PNG exportados a 2x, salidas JSON de validate/inspect/export/edit y códigos de salida; la única diferencia es la versión del paquete en la procedencia.
- Línea base del benchmark regenerada (moanart-benchmark/1, dde4ff8 con el renombrado sin commit): estático 29,7 ms, 16 frames 652,7 ms, pico 61,0 MiB; compare contra la anterior sólo marcó fases PNG sub-ms de chest/frog, que una repetición controlada devolvió a la línea base anterior (ruido). scripts/determinism.py report: ok contra expected.json. CHANGELOG 0.1.0rc2, RELEASE.md, MOANART.md §16 y cabecera, CLAUDE.md y AGENTS.md actualizados.
- Fuera de alcance y sin cambios: IDs MOANA-xxx y MOA-xxx, tag v0.1.0rc1, repositorio remoto xlCyanz/moana y etiqueta moana de GitHub (scripts/github_sync.py); 0.1.0rc2 no se publica ni se sube a PyPI.
- Revisión del subagente moana-python-engineer aplicada: manifiesto heredado con kind actual rechazado (inconsistent_legacy_manifest) en vez de quedar sin migrar; registro kind con un único paso y como mucho uno por proyecto; patrones del comprobador anclados (MOANA_HOME, MOANA-ENGINE, xlCyanz/moana_old, moana-projectx ya fallan) y líneas reales; migrate_rubric con copia profunda; JSON intermedio compacto en migrate_spritesheet_manifest; oráculo con artefactos reales de v0.1.0rc1.
- AC1: scripts/check_wheel.py construye wheel y sdist moanart-0.1.0rc2, los instala limpios en entornos separados y ejecuta import moanart, el comando moanart (CLI, tutorial de 18 pasos, migraciones y corpus con digests fijados); la comparación independiente contra el tag v0.1.0rc1 da documentos, digests, RGBA, PNG, salidas y códigos de salida idénticos sobre ejemplos, corpus, tiles y tutorial.
- AC2: scripts/legacy_name.py (en check_repository y en la auditoría de wheel/sdist): ninguna ruta ni texto usa el nombre antiguo fuera de EXCEPTIONS, cada una con motivo y patrones que existen; tests/test_legacy_name.py.
- AC3: tests/unit/project/test_project_rename.py (directorio, ZIP y sobre JSON de 0.1.0rc1: legacy_name al cargar, migrate_project con historial, assets y original conservados, identidad al repetir) y las pruebas t3 de tests/unit/export/test_export_spritesheet.py y tests/unit/quality/test_quality_rubric.py (rechazo legacy_name y migración pura a los bytes/registro actuales).
- T1: tests/test_legacy_name.py::test_t1_the_repository_uses_the_old_name_only_in_audited_exceptions, ::test_t1_every_exception_names_existing_files_and_a_reason, ::test_t1_stray_occurrences_are_reported (rutas, mayúsculas, texto, formatos fuera de tablas, tabla de migración con otro uso, documento fuera de metadata, catálogo fuera de MOANA-037), ::test_t1_audited_occurrences_are_allowed, ::test_t1_sdist_audit_reports_the_old_name y ::test_t1_wheel_audit_reports_the_old_name; auditoría real en scripts/check_wheel.py.
- T2: Sin regenerar goldens: scripts/corpus.py check (5 ejemplos con digests fijados), scripts/tiles.py check, tests/unit/api/test_tutorial.py, tests/integration (corpus, tiles, desk) y scripts/determinism.py report ok contra tests/fixtures/determinism/expected.json; comparación rc1/rc2 idéntica. La matriz CI y el job de determinismo remotos sólo corren al integrar en main: pendientes.
- T3: tests/unit/project/test_project_rename.py: ::test_t3_real_rc1_projects_are_rejected_then_migrated (directorio y ZIP escritos por el código de v0.1.0rc1 en tests/fixtures/rename/rc1/, historial de tres snapshots y asset), ::test_t3_legacy_directory_is_rejected_then_migrated, ::test_t3_legacy_archive_is_rejected_then_migrated, ::test_t3_legacy_envelope_file_is_rejected_then_migrated, ::test_t3_plain_document_carries_no_name, ::test_t3_migrating_twice_is_the_identity, ::test_t3_a_current_manifest_wins_over_a_legacy_one, ::test_t3_legacy_name_with_current_kind_is_refused, ::test_t3_previous_migration_records_are_kept, ::test_t3_a_project_is_renamed_at_most_once, ::test_t3_kind_records_*; tests/unit/export/test_export_spritesheet.py::test_t3_* (incluido el spritesheet real de rc1: migra a los bytes que export_spritesheet escribe hoy, con el mismo atlas); tests/unit/quality/test_quality_rubric.py::test_t3_* (incluida la rúbrica real de rc1); scripts/check_wheel.py instala moanart limpio.
