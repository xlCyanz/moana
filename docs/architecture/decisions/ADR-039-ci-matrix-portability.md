# ADR-039 — Portabilidad de la matriz de CI: nombres portables, clasificación por `os.stat`, nombres ZIP almacenados y pruebas sin reloj

Estado: aceptado · 2026-11-20 · Sin issue propio (corrección de la primera ejecución remota de la matriz). Amplía [ADR-019](ADR-019-png-export.md) (nombres de destino representables y diagnóstico del directorio), [ADR-024](ADR-024-atomic-edits.md) (cómo se acota el peor caso de un batch) y [ADR-029](ADR-029-project-persistence.md) (nombres del llamador, nombres de entradas ZIP y `fsync` de directorio en Windows). Aplica ADR-010 (errores de dominio) y [ADR-021](ADR-021-cross-platform-determinism.md) (mismo contrato en todas las plataformas). No cambia el schema, el renderer (`render-v1`), el estimador (`budget-v8`), la fachada, el CLI ni los formatos de proyecto. Ampliado por [ADR-040](ADR-040-incremental-edit-index.md): la prueba del peor caso de edición (punto 5) cuenta ahora una construcción del índice por batch, los nodos indexados y una consulta O(1) por comando.

## Contexto

La primera ejecución remota de la matriz completa (ubuntu, macOS y Windows × Python 3.12, 3.13 y 3.14; run 44768996258 sobre `develop` 714c2f6) mostró fallos que no aparecían en macOS con 3.12:

- Python 3.14 cambió `Path.is_dir()`: devuelve `False` ante cualquier `OSError`. Un directorio padre sin permiso de búsqueda se diagnosticaba como `missing_directory` en vez de `permission_denied`.
- En Windows el codec de rutas (`surrogatepass`) acepta sustitutos sueltos, así que `os.fsencode` no rechazaba `"a\ud800.png"`; en POSIX `surrogateescape` acepta `\udc80`–`\udcff`.
- En Windows `os.path.isdir` es `nt._path_isdir` y no pasa por `os.stat`: la razón de un fallo de apertura (`is_directory`/`io_error`) dependía de la plataforma.
- `zipfile.ZipInfo` reescribe `filename`: lo corta en el primer NUL (en todas las plataformas) y, donde `os.sep` es `\`, cambia `\` por `/`. Las comprobaciones de nombre miraban el nombre ya reescrito: una entrada `assets/a\x00.png` llegaba como `unexpected_entry` y no como `invalid_name`, y en Windows una barra invertida pasaba la comprobación de nombre.
- Windows no permite abrir un directorio para `fsync`; `Folder.sync` ya era un no-op allí, pero dos pruebas exigían el comportamiento POSIX.
- Fallos de pruebas, no del producto: un umbral de reloj (30 s) para el peor caso de edición, una sonda de memoria con `ru_maxrss` que en Linux hereda el pico del proceso padre (crecimiento medido 0) y un PNG «de ruido» periódico que zlib 1.3.1 comprime a 199 bytes, de modo que truncar 200 bytes eliminaba el `IHDR`.
- Los trabajos de Python 3.12 tardaban hasta ~12,5 min sólo en la suite con cobertura; con `timeout-minutes: 15`, Windows 3.12 se canceló y faltó su informe de determinismo.

## Decisión

1. **Nombres portables del llamador.** Las rutas que elige el llamador (`moana.export.png.destination_path`, `moana.project._fs.caller_path`, `moana.api.loading.source_path`) deben, además de no estar vacías ni contener NUL, codificarse en UTF-8 estricto y con el codec del sistema de archivos. Un sustituto suelto es `ValidationError` (`invalid_name`) en todas las plataformas; en POSIX esto también rechaza ahora los nombres con caracteres `surrogateescape` (bytes no UTF-8), antes aceptados.
2. **Clasificación de directorios con `os.stat`.** `commit_bytes` usa `os.stat` + `S_ISDIR`: sólo `FileNotFoundError`, `NotADirectoryError` y `ValueError` significan «no es un directorio»; `PermissionError` sigue siendo `permission_denied` y otro `OSError`, `io_error` con su `errno`. Se falla cerrado: un bucle de enlaces simbólicos (`ELOOP`) en el destino o en su directorio, o un nombre inválido para Windows (`winerror` 123), es `io_error` y no `missing_directory`, aunque se pida `overwrite=True` (antes `Path.is_dir()` lo ignoraba en silencio). El `ValueError` de un NUL sólo llega aquí si se llama a `commit_bytes` directamente: las entradas de exportación lo rechazan antes como `invalid_name`. Para nombrar la razón de una apertura ya fallida (`is_directory` frente a otra), un único primitivo `os.stat` que nunca lanza sustituye a `os.path.isdir` y `Path.is_dir` en `moana.export.atomic.stat_is_directory` (usado también por la lectura de spritesheets), `moana.project._fs.stat_is_directory` (lecturas del llamador y la comprobación `destination_inside_source` de `migrate_project`) y una copia privada en `moana.api.loading`. Son copias porque `project` no importa `export` (§3) y `api.loading` no debe cargar Pillow; `core` es independiente del disco. Cada copia tiene su prueba.
3. **Nombres ZIP almacenados.** Las comprobaciones de nombre de una entrada (`invalid_name`, `absolute_path`, `parent_reference`) se aplican a `ZipInfo.orig_filename`, el nombre tal como está en el archivo, antes de la reescritura de `zipfile`. Un NUL o una barra invertida es `invalid_name` en todas las plataformas.
4. **`fsync` de directorio en Windows.** Sigue siendo un no-op (NTFS registra las entradas en su journal). Las pruebas del orden de commit y del fallo de `fsync` de directorio afirman el comportamiento POSIX donde existe y, en Windows, que no se sincroniza ningún directorio; el caso `EIO` se omite allí con el motivo explícito.
5. **Peor caso de edición por conteo.** La prueba del batch de 1024 `translate` sobre un path de 3001 comandos cuenta los pasos caros: exactamente un `index_nodes` por comando, ninguna revalidación de nodo y una única `validate_document`, con dos tamaños de batch (256 y 1024) para comprobar que los conteos escalan linealmente. El tiempo de reloj queda sólo como guarda contra cuelgues (300 s).
6. **Sonda de memoria en Linux.** Mide `VmHWM − VmRSS` de `/proc/self/status` tras reiniciar el pico con `clear_refs` (`5`); si el reinicio no es posible, `VmHWM` puede conservar un pico anterior mayor y el resultado sólo puede sobrestimar: la cota sigue siendo conservadora (un fallo falso es posible, un acierto falso no). macOS sigue con `ru_maxrss`.
7. **Fixture PNG truncado.** Los píxeles son salida SHA-256 (incompresibles), con una aserción de tamaño que garantiza que el truncado conserva el `IHDR` con cualquier build de zlib.
8. **CI.** `timeout-minutes: 30` en el trabajo de la matriz; acciones fijadas por SHA y permisos sin cambios.

## Alternativas descartadas

- **Aceptar en cada plataforma lo que su codec admita:** el mismo documento o la misma ruta tendría resultados distintos según el sistema (ADR-021).
- **Seguir usando `Path.is_dir()` o `os.path.isdir`:** su manejo de errores cambia entre versiones y plataformas.
- **Comprobar `filename` y además rechazar `filename != orig_filename`:** equivalente pero indirecto; el nombre almacenado es lo que hay que validar.
- **Subir el umbral de reloj:** sigue siendo frágil en runners cargados y no detecta una regresión de complejidad en máquinas rápidas.

## Consecuencias

- Contrato más estricto en POSIX: un nombre con bytes no UTF-8 (representado con `surrogateescape`) ya no puede usarse como destino ni como origen del llamador.
- Un ZIP con un NUL en el nombre de una entrada era aceptado hasta la comprobación de layout (`unexpected_entry`); ahora es `invalid_name` antes de cualquier descompresión. No se extraía nada en ningún caso.
- Un bucle de enlaces en el destino o en su directorio deja de diagnosticarse como directorio ausente o destino libre: es `io_error` (`errno` `ELOOP`) y no se escribe nada; el enlace no se sustituye ni con `overwrite=True`.
- `SECURITY_MODEL.md` remite a esta decisión para las reglas de nombres.

## Verificación

- Reproducido y corregido localmente: el cambio de `Path.is_dir()` en Python 3.14 (macOS), el NUL en nombres ZIP (macOS), los bucles de enlaces como destino y como directorio (`io_error`/`ELOOP`, POSIX), el PNG de 199 bytes y la sonda con crecimiento 0 (Linux 3.12 en Docker, ejecutando pytest desde un proceso padre grande y como usuario no root).
- Simulado: la barra invertida de Windows en `zipfile` (con `os.sep = "\\"`).
- Razonado hasta la siguiente ejecución remota: sustitutos sueltos, `nt._path_isdir`, `fsync` de directorio y el tiempo de los trabajos en Windows, y que `clear_refs` sea escribible en los runners de ubuntu.
