# Benchmarks de rendimiento y memoria (MOANA-031)

Mediciones **informativas** de MOANA.md §22. Los objetivos (render estático ≤ 100 ms de mediana, 16 frames ≤ 2 s, pico del proceso ≤ 256 MiB) no son un gate hasta disponer de un runner estable; los presupuestos de seguridad de §20 siguen vigentes aunque no se cumplan.

## Ejecutar

```sh
uv run python -m tests.benchmarks run                       # 5 warmups, 30 muestras, todo el corpus
uv run python -m tests.benchmarks run --warmups 1 --samples 3 --case static   # humo
uv run python -m tests.benchmarks run --output artifacts/benchmarks/mi-maquina
uv run python -m tests.benchmarks compare antes.json despues.json
```

`run` escribe `<output>.json` (formato `moana-benchmark/1`, JSON canónico con claves ordenadas) y `<output>.md` (resumen). Por defecto `artifacts/benchmarks/benchmark.*`, ignorado por Git. Las pruebas `uv run pytest tests/benchmarks -q` (marker `benchmark`) ejecutan una pasada de humo y nunca comprueban latencias.

## Corpus

Generado por código en `corpus.py` (sin llamar al motor) y validado por `moana.schema`:

- `static`: 128×128 `strict`, 32 capas (20 de 16 rects y 12 de 15) con 500 `rect` en total y 16 colores opacos. Los rects quedan a 4 píxeles de cada borde para que ningún override los recorte.
- `animation`: la misma base con 16 frames de igual complejidad; cada frame aplica 32 `translate` y 8 `set_color` distintos, así que cada uno es un render real y diferente.
- `corpus/<slug>`: los ejemplos revisados de `examples/corpus` (MOANA-027), casos reales más pequeños.

El digest del corpus (`corpus_digest`) cubre el nombre y los bytes canónicos de cada caso.

## Metodología

- **Proceso nuevo por caso** (`python -m tests.benchmarks worker`, `PYTHONHASHSEED=0`, sin stdin y con un timeout de 60 s + 30 s por warmup o muestra): el pico RSS es atribuible a ese caso. Las herramientas auxiliares (`git`, `sysctl`) tienen un timeout de 10 s; si fallan o se cuelgan el dato queda `null` y la medición sigue.
- **Fases separadas** con `time.perf_counter_ns`: `parse` (bytes JSON → `Document` validado); `render` en memoria y sin E/S (`moana.api.render`, o `moana.animation.render_animation` para la secuencia completa de 16 frames, que es la muestra); `render_frame` (cada frame ya evaluado y admitido fuera de la medición, dibujado con `moana.render.render_admitted`; estadísticas por frame); `encode_png` y `write_png` (codificación en memoria y exportación atómica a un directorio temporal). El render incluye la revalidación interna que forma parte del contrato de `render`; no incluye el parseo del JSON.
- **5 warmups y 30 muestras** por fase (configurable). Se informa min, mediana (`statistics.median`: media de los dos centrales con n par), p95 por **rango más cercano** (`sorted[ceil(0,95·n) − 1]`; con 30 muestras, la 29.ª), max y media. `gc.collect()` antes de cada muestra; el GC sigue activo dentro.
- **Sin caché engañosa**: cada muestra de render registra las llamadas al registro de rasterizadores del pipeline (un envoltorio contador temporal sobre `moana.render.pipeline._rasterize`), los checkpoints de un `Deadline` cuyo reloj cuenta sus llamadas y nunca expira, y el digest de salida, que se compara con una referencia renderizada una vez con `moana.api.render` antes de los warmups. `_rasterize` rasteriza cada operación primitiva y cada hoja de máscara; `outline`, `dither`, `shade` y `material` construyen además máscaras derivadas por su cuenta a partir de esas hojas, así que en general el contador es una cota inferior del trabajo de máscaras y en este corpus de sólo rects es exacto: una llamada por rect. El envoltorio sustituye un atributo de módulo: es global al proceso y no admite renders concurrentes (ni hilos ni workers de pytest-xdist en el mismo proceso). Las pruebas exigen contadores iguales en todas las muestras e iguales a los rects del JSON (500 por frame), que el motor no tenga memoización (`lru_cache`, `functools.cache`, `cached_property`) y que un rect cambiado produzca otro digest con el mismo trabajo. El informe incluye además el plan de coste admitido (`pixel_visits`, bytes, fills). La caché opcional de buffers de capa de MOANA-032 (`moana.render.RenderCache`, ADR-038) nunca se pasa en estas mediciones: el benchmark mide siempre la ruta por defecto, sin caché; sus mediciones caché on/off están en ADR-038.
- **Memoria**: pico RSS del proceso del caso en bytes (`peak_rss_bytes`, con su fuente en `peak_rss_source`). En Linux la fuente principal es `VmHWM` del fichero de estado del proceso, porque el `ru_maxrss` de un hijo creado con fork/exec puede heredar la marca máxima del padre; `ru_maxrss` se conserva como `ru_maxrss_bytes`. En macOS y BSD se usa `getrusage(RUSAGE_SELF).ru_maxrss` normalizado a bytes (macOS informa bytes; Linux y BSD, KiB). `peak_rss_before_case_bytes` es el pico tras arrancar el intérprete e importar Moana, antes de construir y medir el caso (no es un RSS instantáneo). Aparte, el pico de `tracemalloc` de un render no medido, relativo al tamaño trazado al empezar y etiquetado como sólo heap de Python; si ya había un trazador activo (por ejemplo `PYTHONTRACEMALLOC=1`) no se detiene.
- **Casos adversos** (`adversarial.py`, AC2): lienzo 2048×2048 con 512 rects a lienzo completo (visitas), el corpus con `max_operations=499` (operaciones) y una animación de 16 frames de 2048×2048 que cabe frame a frame pero no acumulada (`frame_pixels`, visitas y bytes). Deben rechazarse con `BudgetExceeded` antes de rasterizar (0 llamadas) y con un pico de heap muy inferior a un buffer RGBA del lienzo.
- **Entorno** registrado: modelo y número de CPU (en Linux ARM, `Hardware` o `CPU implementer`/`CPU part` si no hay `model name`), arquitectura, SO y versión, Python, numpy/Pillow/aggdraw/pydantic, sha256 de `uv.lock`, commit y si el árbol estaba modificado (`dirty`), `renderer_version`, `renderer_backend`, `estimator_version`. **Nunca** se registran hostname, usuario, rutas absolutas ni marcas de tiempo; `write_report` se niega a escribir un informe que los contenga. Las rutas absolutas (`/…`, `C:\`, `C:/`, `\\servidor`, `~/`) se buscan en cualquier posición de cualquier texto, y el home y la raíz del repositorio (también resueltos) con ambos separadores. Usuario y hostname se buscan sólo en los valores de `environment`, como palabra completa y distinguiendo mayúsculas, porque el vocabulario fijo del informe puede contener palabras como `runner` o `static`.

## Comparar

`compare` rechaza (código 2) informes no comparables: formato, digest del corpus, `renderer_version`/`renderer_backend`/`estimator_version`, warmups o muestras, casos o fases de un caso distintos, y también un informe mal formado (no es un objeto JSON, faltan claves o una mediana no es numérica: motivo `malformed`, sin traceback). Si son comparables imprime en bruto la mediana de cada fase y el pico RSS de cada caso, y marca `investigate` cuando `después × 100 > antes × 120` (subida de **más de un 20 %**, calculada sobre el texto decimal para que el límite sea exacto); un `antes` no positivo siempre es `investigate` y un RSS ausente es `unknown`. No hay tolerancia que oculte cambios. Una máquina distinta (CPU, SO, Python, librerías, lock) se avisa, no se rechaza, porque el cambio puede venir del hardware. El veredicto es informativo (código 0): una regresión se investiga repitiendo la medición en condiciones controladas antes de atribuirla al cambio (MOANA.md §22).

## Resultados

`results/` guarda líneas base revisadas, nombradas por plataforma y nunca por máquina o usuario (p. ej. `macos-arm64-py312`). El `.md` se genera siempre desde el JSON canónico y una prueba comprueba que se regenera idéntico. La línea base actual se midió sobre el commit indicado con el trabajo de MOANA-031 todavía sin commit, por eso registra `dirty: true`; conviene repetirla tras integrar el cambio.

## Límites

- En Windows no existe `resource`: el pico RSS queda `null` con su motivo y el objetivo de 256 MiB queda `null` (desconocido).
- `tracemalloc` ve el heap de Python y los buffers de NumPy, pero no la memoria nativa de Pillow, aggdraw ni del intérprete; el RSS sí, junto con todo lo importado (~57 MiB tras los imports en la línea base).
- Los runners compartidos de CI tienen ruido de vecinos, escalado de frecuencia y caché térmica; sus números no son comparables con una máquina local y no deben usarse como gate.
- El envoltorio contador y el `Deadline` contador añaden un coste mínimo (cientos de llamadas de Python por render) dentro de la muestra.
- Un usuario o hostname que coincida con una palabra completa de un valor de `environment` (p. ej. `Apple` en `Apple M4`) se informa como fuga: no puede distinguirse de una real.
