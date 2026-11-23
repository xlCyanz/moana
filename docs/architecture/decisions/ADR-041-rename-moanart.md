# ADR-041 — Renombrado completo del proyecto a MoanArt

Estado: aceptado · 2026-11-22 · Issue: [MOANA-037](../../issues/MOANA-037.md). Amplía [ADR-003](../ADR-003-toolchain.md) (distribución, import y comando), [ADR-004](../ADR-004-agent-infrastructure.md) y [ADR-009](ADR-009-claude-code-layer.md) (skills y agentes), [ADR-006](ADR-006-backlog-identity-and-lifecycle.md) (los IDs del backlog no cambian), [ADR-011](ADR-011-schema-v1.md) (`$id` y título del JSON Schema), [ADR-021](ADR-021-cross-platform-determinism.md) (formatos del harness de determinismo), [ADR-029](ADR-029-project-persistence.md) (manifiesto y `kind` del proyecto), [ADR-031](ADR-031-format-versions-migrations.md) (registro de migración con `member: "kind"`), [ADR-033](ADR-033-spritesheet-export.md) (formato del manifiesto de spritesheet), [ADR-037](ADR-037-art-corpus-rubric.md) (formatos de rúbrica y de ficha del corpus) y [ADR-038](ADR-038-layer-buffer-cache.md) (prefijo de la clave de caché). No cambia el schema 1.0, el renderer (`render-v1`), el estimador (`budget-v8`), la semántica de la edición ni ningún `snapshot_digest` o RGBA.

## Contexto

La versión 0.1.0rc1 se publicó el 2026-11-20 como prerelease de GitHub con el nombre Moana: distribución `moana-pixel-engine`, paquete `moana`, comando `moana`, extensiones `.moana` y `.moana.json` y formatos `moana-*`. Ese mismo día el propietario decidió renombrar el proyecto a MoanArt de forma completa en la versión siguiente. El nombre aparecía en 513 de 566 archivos versionados. MOANA-037 pide que el producto, su API, su CLI y sus formatos se llamen MoanArt sin cambiar ningún píxel ni digest, con una migración explícita para lo guardado con el nombre anterior y una prueba que impida reintroducirlo.

## Decisión

1. **Ruptura sin alias.** Antes de 1.0 no se mantiene un import `moana`, un comando `moana` ni una distribución de transición. Un shim sólo añadiría una segunda superficie pública que habría que retirar; la prerelease no está en PyPI y se publicó dos días antes de esta decisión. La versión pasa a `0.1.0rc2`.
2. **Tabla de nombres.**

   | Antes (0.1.0rc1) | Después |
   | --- | --- |
   | distribución `moana-pixel-engine` | `moanart` |
   | paquete `moana`, `src/moana/` | `moanart`, `src/moanart/` |
   | comando `moana` | `moanart` |
   | `MoanaError` y `Moana*` | `MoanArtError` y `MoanArt*` |
   | campo `moana_version` | `moanart_version` |
   | proyecto `.moana`, documento `.moana.json` | `.moanart`, `.moanart.json` |
   | manifiesto `project.moana.json`, `kind: "moana-project"` | `project.moanart.json`, `kind: "moanart-project"` |
   | `moana-spritesheet` | `moanart-spritesheet` |
   | `moana-rubric/1`, `moana-corpus-entry/1` | `moanart-rubric/1`, `moanart-corpus-entry/1` |
   | `moana-tile-layout/1` | `moanart-tile-layout/1` |
   | `moana-layer-cache/1` | `moanart-layer-cache/1` |
   | `moana-benchmark/1`, `moana-visual-diff/1`, `moana-determinism-*/1` | `moanart-benchmark/1`, `moanart-visual-diff/1`, `moanart-determinism-*/1` |
   | `moana-document-1.0.schema.json` | `moanart-document-1.0.schema.json` |
   | `MOANA_ROOT`, `MOANA_UPDATE_GOLDENS`, `MOANA_VISUAL_ARTIFACTS`, `MOANA_BOOTSTRAP_PYTHON` | `MOANART_*` |
   | `MOANA.md` | `MOANART.md` |
   | skills `moana-*`, subagentes `moana-*`, roles Codex `moana_*` | `moanart-*`, `moanart-*`, `moanart_*` |

3. **Lo que no se renombra.** Los IDs de issue `MOANA-xxx` y los aliases `MOA-xxx` (historial, mapa de GitHub, ADR y trazabilidad; ADR-006); el tag `v0.1.0rc1` y su release; el repositorio remoto `xlCyanz/moana` y la etiqueta `moana` del backlog en GitHub (`scripts/github_sync.py`): son recursos remotos cuyo cambio exige una autorización aparte, y cambiar la etiqueta haría que la sincronización creara una nueva. Los ADR aceptados conservan su texto, que describe las decisiones con los nombres de entonces; este ADR los amplía.
4. **Documentos sin migración.** Un documento schema 1.0 no contiene el nombre del producto: el cargador nunca dependió de la extensión. Un `.moana.json` se carga tal cual con `load_project` o `load_document`, y `migrate_project` es la identidad (no escribe nada). Basta con renombrar el archivo. Por la misma razón, los documentos de `examples/` conservan byte a byte sus `metadata` (autor y procedencia redactados con el nombre de entonces): cambiarlas cambiaría `snapshot_digest`, que el corpus, los tiles, el tutorial y el determinismo tienen fijado.
5. **Proyectos de 0.1.0rc1.** Un proyecto directorio o `.moana` ZIP cuyo único manifiesto es `project.moana.json`, o un sobre JSON con `kind: "moana-project"`, es `UnsupportedVersion` al cargarlo, con `reason: "legacy_name"`, `field` (`manifest` o `kind`) y `replacement` (`project.moanart.json` o `moanart-project`); el mensaje nombra `migrate_project`. Si coexisten los dos manifiestos manda el actual. El ZIP inspeccionado admite el nombre heredado sólo para poder informar o migrar; esa entrada pasa las mismas comprobaciones de nombre, ratio y tamaño que las demás.
6. **Migración del sobre.** `migrate_project` lee el nombre heredado (`consume_legacy_source`, que le dice si el manifiesto leído era el heredado) y sólo renombra el sobre: `kind` pasa a `moanart-project` y el manifiesto se escribe como `project.moanart.json` en un destino nuevo, sin `overwrite`. Documento, assets e historial se verifican como en una carga y se conservan: el nombre antiguo sólo existió con schema y sobre 1.0, así que todo `snapshot_digest` y el historial completo (snapshots, batches, cursor y ramas) siguen siendo los mismos. El registro tiene `source_kind: "project"`, `member: "kind"`, `source_version: "moana-project"`, `target_version: "moanart-project"` y el paso `rename-to-moanart`; el manifiesto heredado se guarda byte a byte en `migrations/<sha256>.json`. `MigrationRecord` sólo acepta `member: "kind"` con exactamente esos valores y ese paso, y un proyecto tiene como mucho un registro `kind`; los registros de migraciones anteriores se conservan delante. Un manifiesto con nombre heredado y `kind` actual, que ninguna versión escribió, es `ValidationError` `inconsistent_legacy_manifest` y no se migra. Migrar el resultado otra vez es la identidad.
7. **Manifiestos fuera del proyecto.** `parse_spritesheet_manifest`, `slice_spritesheet` y `load_spritesheet` rechazan `format: "moana-spritesheet"` con `UnsupportedVersion` `legacy_name`; `migrate_spritesheet_manifest(data) -> bytes` es pura, sólo cambia `format`, valida el resultado y devuelve los bytes canónicos que `export_spritesheet` escribe hoy. `parse_rubric` rechaza `moana-rubric/1` igual, y `migrate_rubric(record) -> dict` devuelve una copia con el formato nuevo sin tocar revisiones, puntuaciones ni el digest al que se ligan. Ninguna de las dos escribe: el original queda en manos de quien llama. Las dos rechazan con `not_legacy` lo que no es del formato heredado.
8. **Formatos de las herramientas del repositorio.** `moanart-tile-layout/1`, `moanart-corpus-entry/1`, `moanart-benchmark/1`, `moanart-visual-diff/1`, `moanart-determinism-*/1` y la clave de caché `moanart-layer-cache/1` cambian de nombre sin migración: no forman parte de la API pública y sus lectores ya rechazan un formato desconocido. Sus archivos versionados se renombran en el mismo cambio y se comprueban con sus propias herramientas (`scripts/tiles.py check`, `scripts/corpus.py check`, `scripts/determinism.py report`). La línea base del benchmark se vuelve a medir, porque `compare` rechaza con razón un formato distinto.
9. **Prueba contra el nombre antiguo.** `scripts/legacy_name.py` busca `moana` sin distinguir mayúsculas (excluido `moanart`) en rutas y texto de los archivos que Git conoce, y `check_repository` lo ejecuta en cada gate. `scripts/check_wheel.py` aplica las mismas reglas a cada miembro del wheel y del sdist, incluidos `METADATA` y `PKG-INFO`. Siempre se permiten los IDs de issue (`MOANA-037`, `MOANA_037`, los marcadores `MOANA-xxx` y `MOANA-…`, el patrón `MOANA-\d{3}` y el prefijo literal `"MOANA-"`) y el repositorio remoto `xlCyanz/moana` sin sufijo; cualquier otra palabra con ese prefijo, como una variable de entorno, falla. Los archivos que no son UTF-8 (PNG, el ZIP de fixtures) sólo se comprueban por ruta. Las excepciones auditadas, cada una con su motivo, son: los artefactos reales de 0.1.0rc1 de `tests/fixtures/rename/rc1/` (ruta y contenido), sus rutas en `docs/FILE_INVENTORY.md`, el CHANGELOG, los ADR aceptados antes de este, este ADR, el issue MOANA-037 (su documento y su entrada del catálogo), las `metadata` de los documentos con digest fijado (y la procedencia del layout que la escena copia), las tablas de migración (`manifest.py`, `migrate.py`, `spritesheet.py`, `rubric.py` y sus pruebas, sólo para los identificadores heredados), la etiqueta remota del backlog y el propio comprobador.

## Alternativas descartadas

- **Alias de import y comando `moana` con fecha de retirada.** Duplica la superficie pública y las pruebas por una prerelease que no está en PyPI.
- **Aceptar los formatos heredados al leer.** Rompe la regla de ADR-031 de que leer nunca migra y deja dos nombres válidos para siempre.
- **Reescribir las `metadata` de los ejemplos.** Cambiaría todos los digests fijados; T2 exige que sigan iguales.
- **Renombrar el repositorio y la etiqueta de GitHub.** Son recursos remotos fuera del alcance del issue.

## Consecuencias

- Instalar `moanart` da `import moanart` y el comando `moanart`. Quien tenga un checkout o un entorno de 0.1.0rc1 debe reinstalar: `moana` deja de existir.
- Proyectos de 0.1.0rc1: `migrate_project(origen, destino)`. Manifiestos de spritesheet y rúbricas: las funciones puras de la decisión 7. Documentos: renombrar el archivo.
- Una mención nueva del nombre antiguo fuera de las excepciones hace fallar `check_repository`, `check_wheel` y `tests/test_legacy_name.py`.

## Pruebas

- T1: `tests/test_legacy_name.py` (repositorio limpio fuera de las excepciones, cada excepción existe y tiene motivo, casos de rutas, texto, mayúsculas, binarios, catálogo, `metadata` y tablas de migración, wheel y sdist sintéticos) y la auditoría real de `scripts/check_wheel.py`.
- T2: `scripts/corpus.py check`, `scripts/tiles.py check`, `tests/unit/api/test_tutorial.py`, el resto de la suite con sus digests fijados y `scripts/determinism.py report` contra `tests/fixtures/determinism/expected.json`, sin regenerar ningún golden.
- T3: `tests/unit/project/test_project_rename.py` (proyecto directorio y ZIP escritos de verdad por el código de `v0.1.0rc1`, con historial ramificado y un asset, en `tests/fixtures/rename/rc1/`; además directorio, ZIP y sobre JSON heredados construidos desde los identificadores publicados: rechazo, migración con historial, assets, migraciones previas y original conservados, documento sin nombre, identidad al repetir, prioridad del manifiesto actual, manifiesto incoherente rechazado y registros `kind` estrictos y únicos), y las pruebas `t3` de `tests/unit/export/test_export_spritesheet.py` (incluido el spritesheet real de rc1, que migra a los bytes que `export_spritesheet` escribe hoy con el mismo atlas) y `tests/unit/quality/test_quality_rubric.py` (incluida la rúbrica real de la rana de rc1).
