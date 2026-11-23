# ADR-029 — Persistencia de proyectos: sobre separado, almacén inmutable por hash y ZIP inspeccionado

Estado: aceptado · 2026-11-18 · Issue: [MOANA-020](../../issues/MOANA-020.md). Amplía [ADR-026](ADR-026-edit-history.md) (el historial se persiste y se reconstruye con su constructor validado; la convergencia sigue rechazada) y [ADR-024](ADR-024-atomic-edits.md) (cada batch persistido se vuelve a aplicar al cargar). Aplica [ADR-019](ADR-019-png-export.md) (escritura atómica, sin importar `export`), ADR-010 (`ReadError`, `ExportError`, `ValidationError`, `BudgetExceeded`), ADR-011 (`validate_document`, `canonical_json`, `snapshot_digest`) y ADR-013 (Pillow sólo detrás de una frontera). Diez límites nuevos en `moana.core.limits`. No cambia `Document`, su JSON Schema, la fachada ni el CLI de [ADR-020](ADR-020-public-api-cli.md). Ampliado por [ADR-031](ADR-031-format-versions-migrations.md): miembro opcional `migrations` del sobre (registros de procedencia, omitido si está vacío), copia original inmutable en `migrations/<sha256>.json`, `Project.migrations`, `migrate_project` hacia un destino nuevo y `project_version` distinto de 1.0 como `UnsupportedVersion`. Ampliado por [ADR-039](ADR-039-ci-matrix-portability.md): nombres del llamador en UTF-8 estricto, nombres ZIP comprobados sobre `orig_filename` y pruebas de `fsync` de directorio por plataforma. Ampliado por [ADR-041](ADR-041-rename-moanart.md): manifiesto `project.moanart.json`, `kind: "moanart-project"` y extensiones `.moanart`/`.moanart.json`; un proyecto con el nombre de 0.1.0rc1 es `legacy_name` y sólo `migrate_project` lo lee.

## Contexto

MOANA.md §16 fija el formato: `.moana.json` autocontenido; proyecto en directorio con `project.moana.json`, `assets/`, `history/` y `previews/` derivado; contenedor `.moana` ZIP opcional con las mismas rutas. El sobre `ProjectManifest` está separado de `Document`, con `extra=forbid`. Los assets y snapshots viven en rutas inmutables derivadas del hash, y el manifiesto se confirma al final. §20 exige confinar rutas, verificar digests, limitar ZIP y Pillow y no filtrar rutas en los errores. §3 permite a `project` depender sólo de `core`, `schema` y `editing`.

El issue registra dos riesgos. Primero, guardar in situ un asset antes del manifiesto rompe la atomicidad. Segundo, la convergencia del historial: ADR-026 §4 rechaza con `existing_snapshot` un digest alcanzado desde otro padre, y permitirla exigiría separar la identidad de la entrada del almacén por contenido.

## Decisión

1. **Módulo `moana.project`.** Depende de `core`, `schema` (sólo su API pública), `editing`, Pydantic y Pillow (encapsulado en `assets.py`). No importa `export` ni `api`, y ningún módulo inferior importa `project`; una prueba AST lo verifica. API pública:
   - `Project(document, assets=(), history=None)`: congelado. Los IDs de asset son únicos y distintos de todo ID del documento según `moana.schema.document_ids`, que incluye los IDs de `item` como las bandas de `shade` ([ADR-028](ADR-028-band-shading.md)) (`duplicate_asset_id`, `id_collision`). Como mucho `MAX_PROJECT_ASSETS` assets y `MAX_ASSET_PIXELS` píxeles decodificados; superarlos es `BudgetExceeded` (`project_assets`, `asset_pixels`), igual que al cargar. Si hay `history`, su cursor es el documento (`cursor_mismatch`).
   - `Asset.from_png(id, data, *, max_bytes, max_pixels)` y `Asset(id, data, width, height, rgba)`. El constructor vuelve a decodificar y exige coincidencia (`pixel_mismatch`). Conserva los bytes fuente sin cambios y expone `sha256`, `path`, `mime` y `pixels`.
   - `save_project(project, directory, *, overwrite=False, limits)`, `save_project_archive(project, path, *, overwrite=False, limits)` y `save_document(document, path, *, overwrite=False, limits: ParseLimits)` devuelven `SaveReport(sha256, written, reused)` con rutas relativas.
   - `load_project(path, *, limits)` y `encode_project(project, *, limits)`.
   - `ProjectLimits`: límites que sólo se pueden bajar (`require_int`), con `parse: ParseLimits` y `history: HistoryLimits`.
   - Modelos del sobre: `ProjectManifest`, `AssetRef` y `HistoryEntry`.
   - Auxiliares públicos: `snapshot_path(digest)` y `batch_path(digest)` (rutas de la disposición), `asset_path(sha256)`, y las constantes `MANIFEST_NAME`, `PROJECT_KIND`, `PROJECT_VERSION`, `PNG_MIME` y `ZIP_MAGIC` (firma `PK\x03\x04` con la que el lector distingue un `.moana`).
   - Clases de error: todo conteo o tamaño que supera un límite es `BudgetExceeded`, nunca un error de Pydantic. Por eso el sobre no declara `max_length` ni `le`: `project_assets`, `asset_bytes` y `history_snapshots` se comprueban con `ProjectLimits` antes de leer ningún archivo.
2. **Sobre estricto separado de `Document`.**
   - Forma: `{kind: "moana-project", project_version: "1.0", document, assets, history}`. Los modelos Pydantic son `strict`, `extra='forbid'` y `frozen`; `history` es opcional y vale `[]` por defecto.
   - El lector distingue por `kind`: si el objeto raíz tiene un miembro `kind`, el JSON es un sobre; si no, es un `Document` y carga como proyecto sin assets ni historial. Un documento simple se valida después con `validate_document` y `limits.parse`, que dan sus propios límites y punteros detallados.
   - Un sobre cargado por su ruta (`x.moana.json` con `kind`) lee sus archivos junto a él, exactamente como `project.moana.json` dentro de un directorio: el directorio padre se abre sólo en la primera lectura, así que un documento simple nunca lo toca.
   - Un archivo que no empieza por `PK` se lee como mucho hasta `max_manifest_bytes + 1`; sólo tras la firma ZIP se amplía la lectura a `max_archive_bytes`.
   - El documento embebido se valida con `validate_document` y sus propios `ParseLimits`. Sus errores conservan el código, con punteros bajo `/document`.
   - Los errores del sobre son `ValidationError` `invalid_manifest`, con un detalle por problema (`reason` = tipo de Pydantic). El puntero nombra sólo miembros conocidos del sobre: un miembro desconocido nunca se repite.
   - `Document`, sus modelos y `schemas/moana-document-1.0.schema.json` no cambian.
   - El sobre embebe hasta 8 MiB de documento, así que no puede usar el lector de `schema` (20 000 nodos). `project` tiene su propio lector acotado:
     - antes de `json.loads`, comprueba `MAX_PROJECT_MANIFEST_BYTES` (9 MiB) y hace un escaneo lineal de `MAX_PROJECT_MANIFEST_DEPTH` (34) y `MAX_PROJECT_MANIFEST_NODES` (32 768);
     - rechaza claves duplicadas, `NaN`, `Infinity` y los números que desbordan a infinito (`1e999`): `non_finite_number`.
   - El manifiesto se escribe en JSON canónico (claves ordenadas, sin espacios, UTF-8), con el documento normalizado de §14.
3. **Disposición y almacén inmutable por contenido.**
   - Archivos:
     - `assets/<sha256>.png`: bytes fuente del asset;
     - `history/snapshots/<hex>.json`: `canonical_json` del documento, con `<hex>` igual al de su `snapshot_digest`, así que el nombre es el hash de los bytes;
     - `history/batches/<sha256>.json`: el batch canónico de `canonical_batch`.
   - `AssetRef.path` no se elige: debe ser exactamente `assets/<sha256>.png`. Así una ruta maliciosa (`..`, absoluta, con barra invertida o con letra de unidad) es un error de sobre antes de cualquier E/S, y ningún nombre derivado puede salir de la raíz ni ser un nombre reservado de Windows.
   - `previews/` no se genera: es derivado y opcional.
4. **Guardado de directorio con commit final del manifiesto.** El orden es:
   1. codificar todo en memoria (`encode_project`) y comprobar que se podrá cargar con los mismos `ProjectLimits`, antes de escribir nada:
      - `project_assets`, `asset_bytes`, `asset_pixels`, `history_snapshots`, `history_bytes`;
      - el JSON canónico del documento, de cada snapshot y de cada batch frente a `limits.parse` (`document_bytes`/`_depth`/`_nodes`, `batch_*`);
      - el manifiesto frente a `max_manifest_bytes`, `_depth` y `_nodes` (`manifest_*`).

      `save_document` aplica la misma comprobación (`document_*`) con su `limits: ParseLimits`. Un documento cuyo origen cabe en 20 000 nodos puede no caber en su forma canónica, que escribe todos los miembros opcionales (sondeo de la revisión: 2163 rects en 128 capas, 19 993 nodos de origen y 20 512 canónicos). Sin esta comprobación se guardaría y no volvería a cargar. **Seguimiento:** la causa raíz es que `schema` y `History` aceptan ese documento; acotar la forma canónica al validar queda para un issue posterior;
   2. abrir la raíz (se crea si falta, un nivel). Con `overwrite=False`: `exists` si ya hay manifiesto y `no_replace_unavailable` si el sistema de archivos no tiene enlaces duros (se prueba con dos temporales vacíos), las dos cosas antes de escribir contenido;
   3. crear y abrir los subdirectorios sin seguir enlaces (`unsafe_path` para un enlace o junction, `not_a_directory`);
   4. escribir cada archivo de contenido que falte o no coincida byte a byte, con temporal hermano `O_EXCL`, `fsync` y `os.replace`. Un archivo que ya existe con los bytes correctos se reutiliza y nunca se reescribe; si no se puede comprobar, el error conserva el motivo de la lectura (`is_directory`, `not_a_file`, `permission_denied`, `io_error`);
   5. `fsync` de cada directorio. Un fallo aquí aborta con `io_error` antes del commit, porque el manifiesto no puede referenciar entradas que quizá no son duraderas; sólo se aceptan los sistemas que no admiten `fsync` de directorio (`EINVAL`, `ENOTSUP`);
   6. commit del manifiesto (`os.link` sin sobrescritura, u `os.replace` con `overwrite=True`) y `fsync` de la raíz, éste ya sin error porque el commit ocurrió.

   Un fallo en cualquier paso deja intactos el manifiesto anterior y todo lo que referencia, bytes e inodos. Los archivos nuevos quedan como huérfanos recuperables; su recolección es una acción explícita posterior, fuera de este issue. La escritura atómica reproduce la de ADR-019 en `project/_fs.py`, porque §3 no permite importar `export`, con la misma tabla de motivos, que una prueba de paridad compara con `export.atomic`:
   - `no_replace_unavailable` para `EPERM`, `ENOTSUP`/`EOPNOTSUPP`, `EXDEV`, `EMLINK`, `ENOSYS` y `winerror` 1, 17, 50 y 1142;
   - `EEXIST` del enlace es éxito si destino y temporal son el mismo archivo (reintento NFS) y `exists` en otro caso;
   - `permission_denied` al crear el temporal y al reemplazar, `invalid_name` para un nombre no representable, `io_error` para el resto.

   Los fallos de escritura son `ExportError` (salida 5), con `reason`, nombre relativo y `errno`, nunca la ruta completa. Ninguna inspección deja escapar un `OSError`: un ancestro sin permiso es `permission_denied`. No se añade un código de error a ADR-010. **Seguimiento:** extraer un módulo común de escritura atómica para `export` y `project`, en una capa que §3 permita a ambos, queda para un issue posterior.
5. **ZIP inspeccionado antes de extraer, sin extraer a disco.**
   - **Antes de `zipfile`:** el archivo se lee acotado a `MAX_ARCHIVE_BYTES` (64 MiB). Se valida un registro de fin de directorio central estricto, el que Moana escribe; cualquier otra forma es `corrupt_archive`:
     - el registro ocupa exactamente los últimos 22 bytes, con comentario de longitud 0 (un comentario podría esconder un segundo registro);
     - un solo disco, el mismo número de entradas en el disco y en total, y sin valores centinela de ZIP64 ni localizador ZIP64 (`PK\x06\x07`) en los 20 bytes previos;
     - `desplazamiento + tamaño` del directorio central es exactamente la posición del registro: sin huecos ni solapes;
     - el tamaño del directorio no supera `entradas × (46 + el nombre más largo de la disposición)`, así que un directorio inflado se rechaza antes de que `zipfile` lo recorra.

     Del registro se obtiene el número de entradas (`MAX_ARCHIVE_ENTRIES` = 256), que debe coincidir con las que lee `zipfile`.
   - **Sobre el directorio central, antes de descomprimir nada:** se rechazan cifrado, compresión distinta de *stored*/*deflate*, enlaces simbólicos (`S_IFLNK`), nombres absolutos o con letra de unidad, `..`, segmentos vacíos o `.`, barra invertida y NUL. También los duplicados exactos y las colisiones tras NFC + `casefold`. El ratio de cada entrada debe ser como mucho `MAX_ARCHIVE_RATIO` (100:1, con al menos 1 byte comprimido), lo que acota también el total, y la expansión declarada como mucho `MAX_ARCHIVE_EXPANDED_BYTES` (256 MiB). Por último, cada archivo debe ser un nombre de la disposición; un directorio de la disposición se ignora.
   - **Errores:** `ValidationError` `unsafe_archive` con `entry_reason` e índice de entrada (sin eco del nombre), `corrupt_archive`, `missing_entry`, o `BudgetExceeded` (`archive_*`).
   - **Lectura:** se descomprime sólo lo que pide el manifiesto, como mucho su tamaño declarado; `zipfile` verifica el CRC.
   - **Escritura:** determinista (nombres ordenados con el manifiesto primero, fecha fija de 1980, modo 0644, deflate 9). Una entrada cuyo deflate superaría el ratio se guarda *stored*. El archivo resultante se inspecciona con las reglas del lector antes de confirmarlo atómicamente; así un proyecto guardado siempre carga. Como cada snapshot y cada batch es una entrada, un ZIP admite exactamente 128 snapshots (manifiesto + 128 snapshots + 127 batches = 256 entradas); 129 es `BudgetExceeded` `archive_entries`, y el directorio no tiene ese tope (sólo los 1024 de `HistoryLimits`).
   - **Determinismo:** los bytes de un `.moana` son deterministas para una misma implementación de zlib, pero dependen de ella (versión, zlib-ng). La identidad estable entre plataformas es el hash del manifiesto, que nombra por SHA-256 todo lo demás; `SaveReport.sha256` de un archivo ZIP es el hash del ZIP.
6. **Assets PNG verificados antes de decodificar.** Sólo se admite PNG RGBA de 8 bits.
   - **Antes de Pillow:** el número de assets y los bytes declarados se comprueban contra los límites. Después, longitud y SHA-256 exactos (`checksum_mismatch`). Luego, la firma PNG y un `IHDR` inicial con profundidad 8 y tipo de color 6 (`not_png`, `wrong_mode`). Finalmente, las dimensiones frente al contrato del lienzo (2048 por eje; `image_too_large`) y el presupuesto acumulado de píxeles (`asset_pixels`).
   - **Con Pillow:** se abre sólo la cabecera; se rechazan APNG (`multiple_frames`) y perfiles ICC (`color_profile`), y se decodifica. Cualquier fallo de Pillow, incluida `DecompressionBombError`, es `unreadable_image`. Las protecciones de Pillow siguen activas y no se tocan globalmente. Un PNG debe terminar en `IEND`, así que un archivo truncado se rechaza aunque el proceso tenga activado `ImageFile.LOAD_TRUNCATED_IMAGES`.
   - **Riesgo bajo aceptado:** Pillow no verifica el CRC de los chunks `IDAT` y Moana no lo recalcula. Basta con el SHA-256 exacto de los bytes, comprobado antes de decodificar: un asset alterado después del guardado nunca llega a Pillow. Un PNG con CRC de `IDAT` incorrecto pero datos decodificables sólo puede entrar si ya venía así al crear el asset.
7. **Historial persistido tal cual; la convergencia sigue rechazada.**
   - Cada `HistoryEntry` es `{snapshot, parent, batch, redo}`, en el orden de inserción del `History`, con el padre antes que el hijo. `redo` marca el hijo redo activo de su padre. El cursor es el documento del sobre. `affected_ids` y `size` no se guardan: se recalculan.
   - Al cargar, cada entrada se reconstruye así:
     - se comprueba el hash del archivo del snapshot y del batch;
     - el snapshot debe ser un documento válido y canónico;
     - el batch debe ser canónico;
     - `apply_batch(padre, batch)` debe reproducir exactamente el digest.

     Así un historial manipulado no puede afirmar una transición falsa. Reaplicar los batches cubre también los documentos con `shade` (ADR-028): las máscaras de banda movidas y los IDs de banda que un borrado aporta a `affected_ids` se recalculan con `apply_batch`, no se leen del disco. El chequeo de colisión de IDs de asset usa `schema.document_ids`, el mismo espacio de nombres que la edición.
   - Fallos: `ValidationError` `invalid_history`, con el índice de la entrada. Superar los presupuestos es `BudgetExceeded`: `history_snapshots` antes de leer nada, `history_bytes` y `history_file_bytes` durante la lectura. El resultado pasa por el constructor validado de `History` (ADR-026 §1), con argumentos por nombre.
   - **`HistoryLimits` no se persiste:** es configuración del anfitrión que carga, no dato del proyecto. El historial cargado usa `limits.history` del cargador; dos proyectos que sólo difieren en sus `HistoryLimits` se codifican igual, y las pruebas comparan los campos semánticos.
   - **Convergencia:** se mantiene el rechazo de ADR-026 §4. Un digest tiene un único padre, en memoria y en disco: una entrada duplicada es `invalid_history`, y tras cargar, `edit` sigue respondiendo `existing_snapshot`. Permitir la convergencia exigiría identificar la entrada por (padre, batch, digest) separada del almacén por contenido. Los snapshots ya se guardan por contenido, así que ese cambio sólo tocaría el manifiesto y `History`, y queda para un ADR futuro si un caso real lo pide.
8. **Rutas confinadas.** Criterio único para los enlaces: la ruta pasada a la API es del llamador y se resuelve como cualquier API de archivos, enlaces incluidos (como en ADR-020); toda ruta *interna* se deriva de un hash y nunca sigue un enlace (`unsafe_path` al escribir, `not_a_file` al leer).
   - **POSIX (`dir_fd`):** la raíz se abre una vez como descriptor y cada nivel se crea y se abre relativo al descriptor de su padre con `O_DIRECTORY | O_NOFOLLOW`. Archivos, temporales, enlaces, reemplazos, `stat` y `fsync` usan esos descriptores. Cambiar un directorio comprobado por un enlace después de abrirlo no puede desviar una lectura ni una escritura fuera de la raíz: lo escrito queda en el directorio abierto. Una prueba de carrera lo verifica en los dos momentos (antes y después de abrir).
   - **Windows (sin `dir_fd`):** recurso explícito a rutas, con `lstat` y comprobación de junctions antes de cada uso. Riesgo residual: un atacante local con escritura en el directorio del proyecto podría cambiar un directorio por un enlace entre la comprobación y el uso. Un servicio expuesto debe usar un directorio propio o el contenedor ZIP, que nunca toca el sistema de archivos. Las pruebas ejecutan los dos modos.
   - El archivo final se abre con `O_NOFOLLOW` donde existe y sin bloquear, y debe ser regular según `fstat`: FIFOs y dispositivos se rechazan. Se leen como mucho `límite + 1` bytes.
   - Errores: `ReadError` con `not_found`, `is_directory`, `not_a_file`, `permission_denied` o `io_error`, más el nombre relativo y `errno`.
   - Todo se lee en memoria y se verifica antes de construir el `Project`; un fallo no devuelve nada, así que no hay carga parcial.
9. **Límites nuevos** en `moana.core.limits` (bloque final, ADR-029): `MAX_PROJECT_MANIFEST_BYTES`, `MAX_PROJECT_MANIFEST_DEPTH`, `MAX_PROJECT_MANIFEST_NODES`, `MAX_PROJECT_ASSETS` (128), `MAX_ASSET_BYTES` (32 MiB), `MAX_ASSET_PIXELS` (16 777 216, el presupuesto de frames de §20), `MAX_ARCHIVE_ENTRIES`, `MAX_ARCHIVE_BYTES`, `MAX_ARCHIVE_EXPANDED_BYTES` y `MAX_ARCHIVE_RATIO`, los cuatro últimos con los valores de §16.
10. **Sin fachada ni CLI nuevos.** MOANA.md §13 no prevé `save`/`load` en `moana.api` ni en el CLI, y los AC no lo exigen. `moana edit` sigue sin escribir. Exponerlos (y un `moana edit --save`) queda para un issue posterior.

## Alternativas descartadas

- **Asset en una ruta elegida y reescrito en el sitio:** rompe la atomicidad (el riesgo del issue) y abre el traversal.
- **Extraer el ZIP a un directorio temporal:** escribe en disco datos no verificados; la lectura en memoria acotada basta para 64 MiB.
- **Batches y `affected_ids` dentro del manifiesto:** con 1024 entradas, `affected_ids` podría superar con mucho el límite de bytes del manifiesto; los archivos por hash y el recálculo mantienen el manifiesto pequeño.
- **Confiar en el historial sin reaplicar los batches:** un manifiesto manipulado podría asociar un batch a una transición que no produce.
- **Importar `moana.export.atomic`:** viola §3.
- **Nuevo código de error para escritura de proyecto:** `ExportError` ya significa «fallo al escribir un artefacto» con salida 5.

## Consecuencias

- Cargar un historial cuesta una validación y una aplicación de batch por snapshot, acotadas por `HistoryLimits` (1024 snapshots, 32 MiB).
- Un ZIP admite menos historial que un directorio (128 snapshots, 256 entradas en total).
- Los huérfanos tras un fallo ocupan disco hasta una recolección explícita.
- MOANA.md 0.1.17-draft recoge esta decisión en §16.
- Evidencia: `tests/unit/project/` (con `shade`: `test_project_roundtrip.py::test_ac1_shaded_document_history_roundtrip` y `test_project_security.py::test_ac2_asset_id_of_a_shade_band_is_an_id_collision`). AC1/T1: `test_project_roundtrip.py`, `test_project_atomic.py`; AC2/T2: `test_project_security.py`; T3: `test_project_atomic.py::test_t3_*` y `test_project_manifest.py`; presupuestos de guardado y carga, bordes y la propiedad Hypothesis: `test_project_budgets.py`. Fronteras: `test_project_model.py`.
