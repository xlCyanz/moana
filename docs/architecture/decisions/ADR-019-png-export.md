# ADR-019 — Exportación PNG verificada y escritura atómica sin sobrescritura

Estado: aceptado · 2026-11-17 · Issue: [MOANA-011](../../issues/MOANA-011.md). Aplica ADR-013 (frontera Pillow), ADR-014 (paleta) y ADR-018 (`RenderResult`).

## Contexto

MOANA.md §18 define el PNG RGBA como formato maestro, el PNG indexado con el orden declarado de la paleta, transparencia explícita y sin cuantización, la escala entera y la creación atómica de archivos. Con `overwrite=False`, el commit no puede reemplazar el destino, y una comprobación `exists()` seguida de `replace()` no sirve, porque otro proceso puede crear el archivo entre ambas. §3 sólo permite a `export` depender de `core` y `palette`, así que no puede importar `RenderResult`. §13 fija `export_png(RenderResult, path, *, scale=1, overwrite=False) -> ExportManifest`.

## Decisión

1. **Marco estructural.** `export` recibe cualquier valor con `width`, `height` y `rgba: bytes` en orden de filas (`RasterFrame`, un `Protocol`); `RenderResult` cumple ese contrato sin que `export` lo importe. El marco se valida: tamaño de los bytes, dimensiones dentro de §5 y alfa 0 normalizado.
2. **Codificación en memoria, separada del commit.** `encode_png(frame, *, scale, mode, palette, limits)` produce `EncodedPng` y no toca el disco.
   - **RGBA:** modo `RGBA`, `compress_level=9`, sin `optimize`. No escribe chunks de texto, hora ni perfil, sólo `IHDR`, `IDAT` e `IEND`. Los mismos píxeles con la misma versión de Pillow dan los mismos bytes.
   - **Indexado:**
     - modo `P` con todas las entradas de una `moana.palette.Palette`, en orden declarado (índice = posición de declaración), incluidas las no usadas;
     - `tRNS` explícito con el alfa de cada entrada;
     - las entradas con alfa 0 se escriben normalizadas a `(0,0,0)`;
     - un píxel usa la primera entrada declarada con su mismo valor, y si no hay ninguna se lanza `ValidationError` (`color_not_in_palette`, con `x`, `y` y número de píxeles): no se cuantiza nunca;
     - como mucho 256 entradas (`too_many_colors`).
   - **Escala:** entero `1..64`, vecino más cercano por bloques `k×k`. Antes de reservar nada se comprueban `export_dimension` y `export_area` (límites de geometría del anfitrión) y `buffer_bytes` (24 bytes por píxel de salida, más los 4 por píxel del marco). Si no caben, `BudgetExceeded`, antes de cualquier temporal. Los 24 B/px cubren RGBA escalado, imagen Pillow, imagen decodificada y su copia (4 + 4 + 4 + 4) más el PNG; el modo indexado usa además, por píxel de origen, una posición `intp` (8), una consulta `uint32` (4), una marca (1) y el índice `uint8` (1). Los picos medidos de RSS con datos incompresibles quedaron entre 15,7 y 24,0 B/px de salida.
   - **Verificación:** los bytes se decodifican de nuevo en memoria y se comparan con los píxeles esperados. Si no coinciden, `ExportError` (`roundtrip_mismatch`) y no se escribe nada. En modo indexado se comparan además los chunks `PLTE` y `tRNS` crudos con las entradas declaradas (`palette_mismatch`), para que un cambio de Pillow que recorte o reordene la paleta no pase en silencio.
3. **Commit atómico (`moana.export.atomic.commit_bytes`).**
   1. Se valida el nombre: una ruta con NUL o no codificable por el sistema de archivos es `ValidationError` (`invalid_name`). La inspección del directorio y del destino envuelve cualquier `OSError`.
   2. Se crea un temporal hermano oculto `.{32 primeros caracteres del nombre}.{16 hex}.tmp` con `O_CREAT | O_EXCL` y permisos `0o666` filtrados por la umask; un nombre en conflicto se reintenta. El prefijo truncado mantiene el temporal dentro de `NAME_MAX` para cualquier nombre válido.
   3. Se escriben todos los bytes y se hace `fsync`.
   4. Se hace el commit:
      - `overwrite=False`: `os.link(temporal, destino)`. Es atómico y falla si el destino existe, así que de dos escritores gana uno y el otro recibe `exists` sin reemplazar nada. Si `link` informa `EEXIST` pero el destino ya es nuestro temporal (respuesta perdida en NFS), es éxito. Si el sistema de archivos no admite enlaces duros (`EPERM`, `ENOTSUP`, `EXDEV`, `EMLINK`, `ENOSYS`, o en Windows `winerror` 1, 17, 50 o 1142), la exportación falla con `no_replace_unavailable`, sin alternativa insegura. `EPERM` también puede venir de atributos inmutables o de un sandbox; el fallo sigue siendo seguro y el contexto incluye el `errno`.
      - `overwrite=True`: `os.replace`. Sobre un enlace simbólico reemplaza el enlace, no su objetivo, y el archivo nuevo no hereda modo ni propietario.
   5. El temporal se borra siempre.
   6. En POSIX se sincroniza el directorio. Los fallos posteriores al commit (borrar el temporal, `fsync` del directorio) no convierten el éxito en error.

   Cualquier fallo deja el destino con su contenido anterior y lanza `ExportError` (código de salida 5), con `reason` (`exists`, `permission_denied`, `io_error`, `missing_directory`, `is_directory`, `invalid_name`, `no_replace_unavailable`), el nombre del archivo y el nombre del `errno`, nunca la ruta completa. El directorio no se crea implícitamente.
4. **Manifiesto.** `export_png` devuelve `ExportManifest` sólo después del commit. Contiene:
   - `path` y `media_type` (`image/png`);
   - `mode`, `width`/`height` exportados, `frames` (1), `scale` y `master` (`scale == 1`);
   - las dimensiones de origen;
   - `source_digest` (digest visual de §14 del marco) y `pixel_digest` (digest de lo decodificado);
   - `file_sha256` y `byte_size`;
   - `warnings`: `scaled_preview` si hay escala, para no confundir un preview con el maestro.

   `to_mapping()` ordena las claves.

## Alternativas descartadas

- **`exists()` + `replace()` o `open(..., "x")` directamente sobre el destino.** Lo primero tiene la carrera que prohíbe §18. Lo segundo deja un archivo parcial visible si la escritura falla a mitad.
- **`renameat2(RENAME_NOREPLACE)`.** Sólo existe en Linux y la biblioteca estándar no lo expone. `os.link` da la misma garantía en Linux, macOS y NTFS.
- **Cuantizar o convertir modos automáticamente:** cambiaría píxeles sin avisar (§18).
- **Importar `RenderResult`:** violaría §3. El `Protocol` evita el acoplamiento.

## Consecuencias

- La exportación queda limitada a sistemas de archivos con enlaces duros cuando `overwrite=False`. En los demás, el error es explícito y `overwrite=True` sigue disponible.
- Los bytes PNG dependen de la versión de Pillow. La garantía de §14 compara píxeles decodificados; la igualdad byte a byte sólo se promete con el codec fijado.
- Evidencia en `tests/unit/export/`:
  - ida y vuelta RGBA e indexada, también a escala 1, 2 y 4;
  - orden de paleta, `tRNS` y paletas de 256 y 257 entradas;
  - ausencia de cuantización y presupuesto comprobado antes de reservar;
  - destino existente, permiso denegado y fallos simulados en `write`, `fsync`, `link` y `replace`;
  - una carrera determinista (otro escritor crea el nombre justo antes del `link`, que una implementación «comprobar y reemplazar» no supera) y carreras reales entre dos hilos (25 repeticiones) y entre dos procesos;
  - bytes idénticos en procesos nuevos con distintos `PYTHONHASHSEED`;
  - nombres no representables, nombres largos válidos y padres sin permiso de búsqueda.
