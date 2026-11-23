# ADR-031 — Versiones de formato y migraciones: registro explícito, pasos puros y copia original preservada

Estado: aceptado · 2026-11-18 · Issue: [MOANA-021](../../issues/MOANA-021.md). Amplía [ADR-029](ADR-029-project-persistence.md) (miembro opcional `migrations` del sobre, ruta inmutable `migrations/<sha256>.json`, `Project.migrations`, `migrate_project`) y [ADR-011](ADR-011-schema-v1.md) (la fase de versión de `validate_document` consulta un registro y distingue `future`, `past`, `unknown` y `migration_required`). Aplica ADR-010 (`UnsupportedVersion`, `ValidationError`, `BudgetExceeded`, `ExportError`), [ADR-019](ADR-019-png-export.md)/ADR-029 (escritura atómica de `project._fs` y commit final del manifiesto) y la excepción previa a la primera publicación de [ADR-022](ADR-022-masks-regions.md), [ADR-025](ADR-025-ordered-dithering.md), [ADR-027](ADR-027-outlines-clusters.md) y [ADR-028](ADR-028-band-shading.md). Dos límites nuevos en `moana.core.limits`. No cambia `Document`, su JSON Schema, la fachada ni el CLI de [ADR-020](ADR-020-public-api-cli.md). Ampliado por [ADR-041](ADR-041-rename-moanart.md): `MigrationRecord` admite `member: "kind"` para el renombrado del sobre (paso `rename-to-moanart`), que conserva el historial.

## Contexto

MOANA.md §16 exige separar `schema_version` de la versión del paquete y del renderer, que el lector estricto soporte versiones explícitas sin «tolerar» versiones nuevas, y que las migraciones sean funciones puras probadas por fixture que preservan la copia original y registran la versión de origen, sin migrar destructivamente al abrir. §3 asigna las migraciones a `project`, que depende de `core`, `schema` y `editing`.

El issue registra un riesgo: no inventar un formato histórico publicado. Schema 1.0 es la única versión que ha existido; no hay tags ni paquete publicado, y las ampliaciones de 1.0 (ADR-022 a ADR-030) son la excepción previa a la primera publicación, que no exige migración. Una migración real de producción no tiene hoy ningún origen.

## Decisión

1. **Cuatro identidades de versión, una sola de formato por miembro.**
   - `schema_version` del documento (`SCHEMA_VERSION` = `1.0`) y `project_version` del sobre (`PROJECT_VERSION` = `1.0`) son versiones de formato `MAJOR.MINOR` y son las únicas que seleccionan una migración.
   - `moana.__version__` (paquete), `RENDERER_VERSION` (`render-v1`) y `ESTIMATOR_VERSION` (`budget-v7`) no son versiones de formato: no se comparan con un documento ni seleccionan migraciones. `parse_version` las rechaza (no son `MAJOR.MINOR`) y una prueba lo verifica.
2. **Registro explícito e inmutable (`moana.schema.versions`).** `MigrationRegistry(member, current, migrations)` es un dataclass congelado. `Migration(id, source, target, apply)` es un paso: `id` con la gramática de IDs, `source < target ≤ current` como `MAJOR.MINOR` (`0|[1-9]\d{0,3}` en cada parte, sin ceros a la izquierda), `apply` un invocable `dict → Mapping`. El constructor comprueba que cada versión de origen e ID se registra una vez y que toda cadena llega a la versión actual en como mucho `MAX_MIGRATION_STEPS` (16) pasos; si no, `ValueError`/`TypeError` (error de programación, no de datos). `versions` = la actual más los orígenes registrados.
   - **Producción:** `DOCUMENT_MIGRATIONS` (`schema_version`, `1.0`, sin pasos) y `PROJECT_MIGRATIONS` (`project_version`, `1.0`, sin pasos). Moana no afirma soporte de ningún formato que nunca existió.
   - **Pruebas:** los formatos `0.8` y `0.9` existen sólo en `tests/fixtures/migration/formats.py`, con un registro propio (`TEST_ONLY_MIGRATIONS`) que las pruebas pasan explícitamente. Cada fixture lleva el miembro `test_only_format`, que el último paso exige y elimina, de modo que un documento real no puede confundirse con uno de prueba.
3. **Clasificación de versiones; leer nunca migra.** `registry.check(tree)` se aplica antes del modelo (la gramática de otra versión nunca se reporta):
   - la versión actual pasa; un miembro ausente o no textual queda para la validación estructural (como antes);
   - una versión con cadena registrada es `UnsupportedVersion` `migration_required` con `target` y los IDs de `migrations`: el lector no migra;
   - cualquier otra es `UnsupportedVersion` `unsupported_version` con `relation` = `future` (posterior a la actual), `past` (anterior, sin migración) o `unknown` (no `MAJOR.MINOR`).

   El contexto incluye `field` (el miembro) y `supported` (`("1.0",)`, igual que antes); nunca repite la cadena no confiable. Variantes como `"1.0 "`, `" 1.0"`, `"1.00"`, `""`, `"1.0\n"` o dígitos de ancho completo son `unknown`. `validate_document` usa `DOCUMENT_MIGRATIONS` y `parse_manifest` usa `PROJECT_MIGRATIONS` justo después de comprobar `kind`. **Cambio de contrato:** un `project_version` textual distinto de `1.0` pasa de `ValidationError` `invalid_manifest` (`literal_error`) a `UnsupportedVersion` con puntero `/project_version`; un valor no textual sigue siendo `invalid_manifest`. En un sobre, la versión del documento embebido se informa bajo `/document/schema_version`; si el propio sobre declara otra `project_version`, gana ésta (`/project_version`).
   - `SUPPORTED_SCHEMA_VERSIONS` sigue existiendo y una prueba fija que es exactamente `{DOCUMENT_MIGRATIONS.current}`.
   - **Batches:** `moana.editing` (`parse_edit_batch`) conserva su contrato de versión anterior: otra `schema_version` del batch es `UnsupportedVersion` `unsupported_version` con `supported`, sin `field` ni `relation`. Un batch es un mensaje efímero, no un formato persistido que se migre; unificarlo queda para cuando haya una segunda versión.
4. **Migración pura de documentos (`moana.schema.migrations`).** `migrate_document(source, *, registry=DOCUMENT_MIGRATIONS, limits)` → `DocumentMigration(document, source_version, target_version, steps)`:
   - sin E/S, reloj ni estado global; el árbol de entrada nunca se modifica;
   - copia la entrada con `read_mapping` bajo `limits` (profundidad y nodos) antes de trabajar y exige que cada hoja sea `str`, `int`, `float`, `bool` o `None`; otra (un `set`, un objeto) es `ValidationError` `invalid_value` con su puntero, de modo que la copia no comparte nada mutable con el llamador;
   - cada paso recibe una copia privada; su salida debe ser un mapping JSON dentro de los límites, se vuelve a acotar igual y el motor fija el miembro de versión al destino del paso;
   - un paso que lanza cualquier `Exception` (no `BaseException`) distinta de `MoanaError` —incluidos `AttributeError` o `RecursionError` ante una fuente malformada— es `ValidationError` `migration_failed` con el ID del paso, sin encadenar la excepción ni citar su mensaje, que puede contener datos del documento. Un `MoanaError` del paso pasa con su propio código. Una salida que no es mapping, cíclica, con hojas no JSON o fuera de los límites también es `migration_failed`, con `cause` (`too_deep`, `too_many_nodes`, `invalid_value`, …);
   - el resultado pasa por `validate_document`;
   - un documento ya actual se devuelve validado con `steps == ()`: migrar el destino es la identidad (idempotencia);
   - el registro debe ser de `schema_version` con versión actual `SCHEMA_VERSION`.

   El registro vive en `schema/versions.py` (sin dependencia de `document`) y el motor en `schema/migrations.py`, para que `document` consulte el registro sin ciclo de imports.
5. **Migración de proyectos explícita a un destino nuevo (`moana.project.migrate_project`).** `migrate_project(source, destination, *, registry=DOCUMENT_MIGRATIONS, limits)` → `MigrationReport(source_version, target_version, steps, save)`:
   - lee la fuente con el mismo despacho de sólo lectura que `load_project` (directorio, ZIP o JSON; `consume_source`), nunca la escribe;
   - un documento simple o el documento de un sobre se migran con `migrate_document`; los assets del sobre se leen y verifican como al cargar y se conservan byte a byte;
   - guarda con `save_project` **sin** `overwrite` (el parámetro no existe): un manifiesto existente en el destino es `ExportError` `exists` antes de escribir contenido;
   - un destino igual a un directorio fuente o dentro de él (rutas resueltas, enlaces incluidos) es `ExportError` `destination_inside_source` antes de leer nada, sin rutas en el error. Una fuente JSON (`.moana.json`) sí puede migrarse a su propio directorio o a un subdirectorio: el archivo no se toca;
   - una fuente ya actual se verifica como `load_project` y no escribe nada (`save = None`);
   - **historial:** sus snapshots y batches no tienen contrato de migración, así que una fuente antigua con historial es `UnsupportedVersion` `history_not_migratable` (`/history`) antes de escribir. Fuera de alcance según el issue. El sobre entero se valida antes con el documento migrado, así que un `history` que no es una lista es `invalid_manifest`;
   - la carga compartida (despacho de fuentes, assets, historial y migraciones) vive en el módulo interno `moana.project._load`, que usan `store` y `migrate`; `manifest.relocated` (punteros bajo `/document`) es parte del `__all__` de `manifest` porque `migrate` informa igual que `parse_manifest`;
   - las migraciones de sobre se registrarían en `PROJECT_MIGRATIONS`; hoy no hay ninguna y `migrate_project` sólo encadena pasos de documento.
6. **Procedencia y copia original gestionadas por el proyecto.** El sobre admite el miembro opcional `migrations`: lista ordenada de `MigrationRecord {source_kind, member, source_version, target_version, steps, path, byte_length, sha256}` (`strict`, `extra='forbid'`, `frozen`).
   - `source_kind` (`document` o `project`) es la forma del original; `member` (`schema_version` o `project_version`) es el miembro cuyas versiones registran `source_version` < `target_version` (comparadas como pares enteros). Hoy toda migración es de documento, también desde un sobre, así que `member` es `schema_version`; el campo evita que un registro con `source_kind: "project"` se lea como versión del sobre.
   - `steps` tiene de 1 a `MAX_MIGRATION_STEPS` IDs válidos; `path` debe ser exactamente `migrations/<sha256>.json`; cada `sha256` es único entre los registros (`invalid_manifest`), y `Project` rechaza un original duplicado (`duplicate_migration`).
   - El archivo `migrations/<sha256>.json` guarda los bytes exactos del JSON original (el documento o el manifiesto de la fuente; de un ZIP, su manifiesto, porque los assets se conservan por hash). Es inmutable y direccionado por contenido como el resto de la disposición; el ZIP lo admite en su lista blanca.
   - En memoria, `Project.migrations` es una tupla de `MigrationBackup(record, data)` que verifica longitud y SHA-256 (`checksum_mismatch`). Guardar y cargar lo conservan: cargar verifica longitud y hash antes de construir el `Project` (`checksum_mismatch` con el índice), sin volver a interpretar el original.
   - Migrar un proyecto ya migrado añade un registro (los anteriores se conservan con sus copias).
   - `migrations` se omite al codificar cuando está vacío, así que el manifiesto, su hash y el ZIP de un proyecto nunca migrado no cambian. Un `migrations: []` explícito carga igual que la ausencia.
   - **Límites:** `MAX_PROJECT_MIGRATIONS` (8) registros (`ProjectLimits.max_migrations`, sólo se puede bajar; `BudgetExceeded` `project_migrations` en el constructor de `Project`, al codificar y al cargar antes de leer) y cada copia ≤ `max_manifest_bytes`, el límite con que se leyó (`migration_bytes`).
7. **Atomicidad.** La migración ocurre entera en memoria antes de escribir; la escritura es la de ADR-029 §4 (contenido con temporal y `fsync`, directorios sincronizados, manifiesto confirmado al final). Un fallo en cualquier llamada al sistema (lectura o escritura) deja la fuente intacta (bytes, inodo y `mtime`) y ningún manifiesto en el destino. Sin CLI ni fachada: MOANA.md §13 no prevé `migrate`.

## Alternativas descartadas

- **Registrar en producción una versión `0.x` ilustrativa:** afirmaría compatibilidad con un formato que nunca existió (riesgo del issue).
- **Migrar al abrir y devolver el documento migrado con un aviso:** convierte la lectura en una transformación implícita; §16 lo prohíbe y la escritura posterior podría sobrescribir el original.
- **Copia de seguridad junto al original (`x.moana.json.bak`):** escribe en la fuente, depende del nombre y no queda ligada al proyecto migrado; la copia por hash dentro del destino viaja con él y se verifica al cargar.
- **Migrar el historial reaplicando batches migrados:** los batches no tienen gramática versionada propia y un cambio de IDs los invalidaría; sin contrato, se rechaza explícitamente.
- **Comparar versiones como texto:** `"10.0" < "9.0"` lexicográficamente; se comparan pares enteros.

## Consecuencias

- `validate_document` informa `relation` en `UnsupportedVersion`; el código, el puntero y `supported` no cambian.
- Un proyecto migrado ocupa además su copia original (≤ 9 MiB por registro, ≤ 8 registros).
- Añadir una versión de schema publicada exigirá registrar su paso en `DOCUMENT_MIGRATIONS` con fixtures reales, subir el minor y revisar esta lista blanca.
- MOANA.md 0.1.18-draft recoge esta decisión en §16.
- Evidencia: `tests/unit/schema/test_schema_migrations.py` (AC1 puro, T1 registro, futuras/desconocidas, idempotencia y propiedad Hypothesis) y `tests/unit/project/test_project_migrations.py` (AC1 en disco, AC2, T1 y T2 con fallo en cada llamada al sistema).
