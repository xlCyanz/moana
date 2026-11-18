# ADR-020 — Fachada pública `moana.api` y CLI estático `moana`

Estado: aceptado · 2026-11-17 · Issue: [MOANA-012](../../issues/MOANA-012.md). Aplica ADR-011 (schema 1.0), ADR-018 (`render`) y ADR-019 (`export_png`). Amplía ADR-010 §4 con `READ_ERROR` (5). Ampliado por [ADR-022](ADR-022-masks-regions.md): `resolve_region`/`ResolvedRegion` en la fachada, `masks`/`regions`/`mask_id` en `inspect_document` y `collections`/`mask_types`/`planned_mask_types` en `capabilities()`. Ampliado por [ADR-023](ADR-023-aggdraw-paths.md): `capabilities()` añade `backends` (`BackendSummary`) y lista `path` como previsto cuando `aggdraw-v1` falta o no está ensayado. Ampliado por [ADR-025](ADR-025-ordered-dithering.md): `capabilities()` lista `dither` como disponible, `inspect_document` resume su color A y `BudgetReport` añade `fills` (fills rasterizados, el valor `estimated` del recurso `operations`). Ampliado por [ADR-024](ADR-024-atomic-edits.md): `apply_edit`, `edit_document` y `load_edit_batch` se exportan (`PLANNED_FUNCTIONS` queda vacío), `capabilities()` añade `edit_commands` y `moana edit DOC BATCH` deja de ser previsto (salidas 0/2/4/5, sin escribir archivos). Ampliado por [ADR-027](ADR-027-outlines-clusters.md): `analyze_clusters` en la fachada (sin comando CLI) y `outline` disponible en `capabilities()`. Ampliado por [ADR-028](ADR-028-band-shading.md): `shade` disponible en `capabilities()` y `OperationSummary.color` es `null` para una operación sin miembro de color.

## Contexto

MOANA.md §13 define la fachada objetivo (`load_document`, `render`, `export_png`, `apply_edit`) y el CLI (`validate`, `render`, `edit`, `inspect`, `export`) con códigos de salida 0/1/2/3/4/5, sin tracebacks por defecto. §3 sitúa `api`/`cli` por encima de todos los módulos: componen servicios y no duplican algoritmos. `render` (MOANA-010) y `export_png` (MOANA-011) ya existen; `apply_edit` depende de `editing` (MOANA-018), que aún no existe. §20 exige que los paths procedan sólo de la capa de confianza y que los errores no filtren rutas sensibles. El riesgo del issue es anunciar como disponible una operación que todavía no lo está.

## Decisión

1. **Fachada `moana.api`, sólo composición.**
   - `load_document(source, *, limits=DEFAULT_PARSE_LIMITS) -> Document`.
     - Un `str` u `os.PathLike[str]` es un path autorizado por el llamador. Un `str` que empieza (tras espacios) por `{` o `[` se rechaza con `ValidationError` (`json_text`): el JSON entra como `bytes` o mapping. `""`, un NUL o un nombre no codificable son `ValidationError` (`invalid_name`).
     - El archivo se abre con `O_NONBLOCK` donde existe, para que un FIFO o un dispositivo no bloqueen. `fstat` exige un archivo regular (`is_directory` o `not_a_file` si no lo es) y se leen como mucho `limits.max_bytes + 1` bytes. Así `moana.schema` rechaza un archivo demasiado grande (`too_large`) sin leerlo entero.
     - Después se valida exactamente igual que los bytes.
   - `render(document, *, frame_id=None, limits=None, deadline=None) -> RenderResult` delega en `moana.render.render`; no escribe archivos ni modifica el documento.
   - `export_png(result, path, *, scale=1, overwrite=False, limits=None) -> ExportManifest` delega en `moana.export.export_png` en modo RGBA y exige un `RenderResult`. El PNG indexado sigue disponible en `moana.export`, porque necesita una paleta resuelta.
   - `inspect_document(document, *, limits=None) -> DocumentReport` resume identidad, lienzo, paleta, capas y operaciones, y estima el render con `budget-v2`. Un exceso de presupuesto se **informa** (`within_limits: false` y la lista `exceeded` con `resource`, `limit`, `estimated` y `json_pointer`), no se lanza, para que el llamador vea por qué `render` lo rechazaría.
   - `capabilities() -> Capabilities` separa lo implementado de lo previsto: versiones de schema, perfiles, operaciones, modos de fusión, colecciones y campos de capa, formatos de exportación, funciones (`AVAILABLE_FUNCTIONS`) y funciones previstas (`PLANNED_FUNCTIONS = ("apply_edit",)`). Una operación sólo es disponible si el schema la acepta **y** tiene rasterizador; una que sólo admite el schema se lista como prevista. Hoy ambos conjuntos coinciden, y lo comprueba una prueba.
   - Se reexportan `MAX_SCALE`, `snapshot_digest`, `ReadError`, `RenderLimits`, `ParseLimits`, `Deadline` y los tipos de retorno, para que un cliente no necesite nada por debajo de la fachada.
   - Todos los retornos son valores congelados (dataclasses con `slots`, `Document` Pydantic `frozen`, `bytes` RGBA) sin arrays NumPy, imágenes Pillow ni handles abiertos. `to_mapping()` da JSON con claves ordenadas.
   - `apply_edit` **no** se exporta: aparece sólo en `PLANNED_FUNCTIONS`.
2. **`ReadError` en `moana.core.errors`.**
   - Abrir el documento es I/O de aplicación y debe salir con 5, igual que la exportación. `ExportError` no describe una lectura, así que `ReadError(MoanaError)` declara `code = "READ_ERROR"` y `exit_code = 5`, con las mismas convenciones que las demás clases (contexto inmutable, picklable).
   - Vive en `core.errors`, junto al resto de la jerarquía, para que `project` (MOANA-020) pueda usarlo sin depender de `api`. Esta decisión **amplía ADR-010 §4** con el código `READ_ERROR` (5); ADR-010 no se modifica.
   - Su contexto lleva:
     - `reason`: `not_found`, `is_directory`, `not_a_file`, `permission_denied` o `io_error`;
     - `file_name`, truncado a 255 caracteres;
     - el nombre del `errno`.

     Nunca incluye la ruta completa, igual que ADR-019. Un `PermissionError` al abrir se distingue de un directorio con `os.path.isdir`, que nunca lanza: Windows informa así de un directorio, y un padre sin permiso de búsqueda no debe convertirse en otra excepción.
3. **CLI estático `moana`** (`moana.cli`, `argparse`, entrypoint `moana = "moana.cli:main"`, también `python -m moana.cli`).
   - **Comandos disponibles:** `validate DOC`, `inspect DOC`, `render DOC` (en memoria; informa digest, advertencias y procedencia sin escribir), `export DOC OUT.png [--scale N] [--overwrite]` y `capabilities`.
   - **Opciones globales:** `--version` y `--debug`. `--debug` se acepta antes o después del comando.
   - **Sin abreviaturas** (`allow_abbrev=False`): `--sc` es un error de uso.
   - **`--scale`:** sólo admite 1 o 2 dígitos ASCII en `1..64`. Rechaza signos, espacios, `_` y dígitos no ASCII. Una escala válida cuya salida supera los límites de geometría sigue siendo `BUDGET_EXCEEDED` (3).
   - **Comando previsto:** `edit` está registrado sólo para responder `UNSUPPORTED_OPERATION` (`reason: planned_command`, salida 2). Su `--help` y la ayuda general lo marcan «PLANNED, NOT AVAILABLE», y el epílogo lista por separado los comandos disponibles, los previstos y los códigos de salida.
   - **Salida parseable:** cada invocación escribe exactamente un objeto JSON en una línea de stdout (claves ordenadas, ASCII), con `ok` y `command`.
     - El éxito añade `document`, `render`, `export` o `capabilities`.
     - El fallo añade `error = {code, exit_code, message, json_pointer, context, details[]}` y una línea breve en stderr (`moana: error: CODE: mensaje`).
     - Sólo `--help` y `--version` escriben texto para humanos.
   - **Errores de uso:** son `VALIDATION_ERROR` con `message` fijo («invalid command line usage») y `context = {"reason": "usage"}`, con salida 2. La explicación de `argparse` y el uso van sólo a stderr. `command` se rellena cuando el subcomando se conoce, por el subparser o por el primer argumento que no es una opción.
   - **Códigos de salida:** el `exit_code` de la clase de error (ADR-010), sin tabla paralela.

     | Código | Situación |
     | --- | --- |
     | 0 | Éxito |
     | 2 | Entrada inválida, uso, versión, referencia u operación no disponible |
     | 3 | Presupuesto |
     | 4 | Conflicto de edición |
     | 5 | I/O (`READ_ERROR`, `EXPORT_ERROR` o stdout cerrado) |
     | 1 | Fallo interno |
     | 130 | Interrupción |

   - **Fallo interno:** una excepción inesperada sale con 1 y `INTERNAL_ERROR`, sin traceback ni mensaje interno. `--debug` imprime el traceback en stderr.
   - **Interrupción (decisión):** `Ctrl+C` en cualquier fase (análisis, trabajo o informe) sale con 130 = 128 + SIGINT. Mantiene la regla de un solo JSON: emite `{"ok": false, "error": {"code": "INTERRUPTED", "exit_code": 130, "context": {"reason": "keyboard_interrupt"}, ...}}`, más `moana: interrupted` en stderr. `INTERRUPTED` no es una clase de dominio: es una señal del proceso.
   - **stdout cerrado (decisión):** si escribir el resultado en stdout falla (`BrokenPipeError` u otro `OSError`), el CLI no escribe nada más en stdout. Redirige el descriptor de stdout a `os.devnull` (`os.dup2`) para que el vaciado final del intérprete no imprima «Exception ignored», escribe un aviso en stderr si puede y sale con **5** (`EXIT_OUTPUT_CLOSED`), porque es un fallo de I/O de la tabla de §13. Un efecto ya hecho (por ejemplo un PNG exportado) no se deshace. Los fallos al escribir en stderr se ignoran.
   - **Paths:** el CLI sólo abre los paths de sus argumentos, sin resolverlos; los errores informan del nombre de archivo, no de la ruta. El manifiesto de éxito repite el path tal como lo pasó el usuario.
   - **Presupuestos:** el CLI no fija límites propios; usa los de §20. Subirlos queda para una configuración de anfitrión explícita.
4. **Fronteras.**
   - `api` importa `core`, `schema`, `render` y `export`, nunca Pillow, NumPy, Pydantic ni `cli`.
   - `cli` importa sólo `moana.api`, `moana.core.errors` y `moana.__version__`.
   - Ningún módulo de dominio importa `api` ni `cli`.
   - Las tres reglas se comprueban con pruebas de arquitectura.
5. **Wheel limpio (AC1).** `scripts/check_wheel.py`:
   - crea un entorno nuevo e instala las dependencias de ejecución fijadas por `uv.lock` (`uv export --frozen --no-dev --no-emit-project`, con hashes). Primero lo intenta `--offline` desde la caché de uv; si falta algo, avisa y reintenta en línea. **Con la caché vacía necesita red** hacia el índice de paquetes;
   - instala después el wheel sin dependencias;
   - ejecuta el `moana` instalado desde un directorio temporal fuera del repositorio, con espacios en los paths, sin `PYTHONPATH`, `PYTHONHOME`, `VIRTUAL_ENV` ni `PYTHONSTARTUP` y con tiempo máximo. Corre `validate` y `export` del ejemplo mínimo y decodifica el PNG de 128 × 128 con Pillow. Los fallos muestran stdout y stderr por separado.

## Alternativas descartadas

- **Exponer `apply_edit` o `edit` lanzando `NotImplementedError`:** anunciaría como disponible lo que no existe. Una función ausente más una lista de previstas es explícita y no rompe la detección por `hasattr`.
- **Usar `ExportError` o `ValidationError` para la lectura:** el primero confunde el diagnóstico; el segundo sacaría con 2 un fallo de I/O, en contra de §13.
- **Definir `ReadError` en `api`:** `project` no puede importar `api` (§3), así que habría que moverlo después y romper la ruta de import.
- **JSON sólo en el éxito y texto libre en el error:** obligaría a los agentes a parsear dos formatos. Un único objeto por invocación, con el error estructurado, se procesa igual en ambos casos.
- **Salir con 141 (128 + SIGPIPE) ante stdout cerrado:** es la convención del shell, pero no está en la tabla de §13; 5 la mantiene cerrada.
- **Interrupción sin JSON:** rompería la regla de un objeto por invocación para los agentes que leen stdout.
- **Click/Typer:** dependencia nueva sin necesidad; `argparse` basta para un CLI estático.
- **Que `inspect` falle con salida 3 al superar el presupuesto:** ocultaría el informe que explica el exceso. `render` y `export` sí fallan con 3.

## Consecuencias

- Agentes y programas usan el mismo contrato: el CLI es una capa fina sobre `moana.api` y sus errores son los de dominio.
- Añadir `apply_edit` o `edit` (MOANA-018) moverá el nombre de `PLANNED_*` a `AVAILABLE_*` y sustituirá el manejador previsto; la ayuda y `capabilities` cambian a la vez.
- `READ_ERROR` (5) es un código público nuevo de `moana.core.errors`.
- `check_wheel.py` puede necesitar red con la caché de uv vacía.
- Evidencia:
  - `tests/unit/api/`: fuentes equivalentes (str, `Path`, bytes, mapping), lectura acotada probada con un espía de `read`, `ReadError` sin ruta completa (no existe, directorio, FIFO, dispositivo, permiso del archivo y del padre, `fstat` y `read` fallidos, nombre largo truncado), texto JSON como path, paso de errores de schema, oráculo de píxeles a mano, valores congelados sin objetos de biblioteca, exportación, `inspect_document`, `capabilities` (incluida la regla schema ⊆ rasterizadores) y arquitectura de imports.
  - `tests/unit/core/test_core_errors.py`: el código y la salida de `ReadError`.
  - `tests/unit/cli/`: cada comando con stdout JSON de una línea, la correspondencia de todas las clases de error con su código de salida, errores de uso (mensaje fijo, comando conocido, escala estricta, sin abreviaturas), operación prevista y su ayuda, `--debug` en ambas posiciones, ausencia de traceback, interrupción en cada fase, stdout cerrado en proceso y con un pipe real.
  - `tests/integration/test_cli_paths.py`: script instalado y `python -m moana.cli` en un directorio fuera del repositorio con espacios y caracteres no ASCII.
  - `scripts/check_wheel.py`: comprobación del wheel limpio.
