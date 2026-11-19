# Regresión visual exacta

Harness de pruebas (no forma parte del paquete `moana`) para MOANA-028 y MOANA.md §21. Compara **píxeles decodificados**, nunca bytes PNG: dimensiones y RGBA deben coincidir exactamente, con todo píxel de alfa cero normalizado a `(0, 0, 0, 0)` (§5). No hay tolerancia perceptual; SSIM no es criterio de aprobación.

## Uso

```python
from .harness import GOLDENS_DIR, assert_matches_golden

assert_matches_golden(canvas, GOLDENS_DIR / "mi-caso.png", source="fixture o documento de origen")
```

Importación: dentro de `tests/visual/` se usa el import relativo `from .harness import ...`. Desde otra carpeta de tests (`tests/integration/`, ...) se usa `from tests.visual.harness import ...`: desde MOANA-021 existe `tests/__init__.py` (junto con `tests/fixtures/__init__.py` para las fixtures de migración), así que mypy (`files = ["tests"]`) registra el módulo una sola vez como `tests.visual.harness`.

- `compare_rgba(expected, actual)` devuelve tamaños, digests (§14: SHA-256 de ancho y alto uint32 big-endian + RGBA row-major), conteo de píxeles distintos y bbox semiabierta. Con dimensiones distintas ambas imágenes se anclan arriba a la izquierda y cuentan como diferentes los píxeles cubiertos por una sola.
- `assert_matches_golden` acepta `Canvas` o un array `uint8 (alto, ancho, 4)`. El golden debe ser PNG RGBA de un frame; se decodifica con los presupuestos de `canvas_from_pillow`.
- Todas las pruebas de esta carpeta llevan el marker `visual`: `uv run pytest -m visual`.
- Goldens fuera de `goldens/`: las previews del corpus artístico (MOANA-027) viven en `examples/corpus/*/previews/` y las compara `test_corpus_previews.py` con `name="corpus__<slug>__<vista>"`, así que su diagnóstico va a `artifacts/visual/corpus__<slug>__<vista>/`. El flujo de actualización es el mismo; ver [el README del corpus](../../examples/corpus/README.md).

## Diagnóstico al fallar

Sólo cuando falla, el harness escribe en `<artefactos>/<nombre>/`, ignorado por Git. Por defecto es `artifacts/visual/<nombre>/`; el directorio se configura con `MOANA_VISUAL_ARTIFACTS` o el argumento `artifacts`. `<nombre>` es la ruta del golden bajo `goldens/` sin extensión y con `/` como `__` (`sprites/hero.png` → `sprites__hero`, sin colisiones entre subcarpetas); para goldens fuera de `goldens/` es el stem del archivo, así que dos goldens externos con el mismo stem deben pasar `name=` explícito. Antes de escribir, y también cuando la comparación pasa, se borran los cuatro archivos de diagnóstico de una ejecución anterior con ese nombre (no otros archivos).

| Archivo | Contenido |
| --- | --- |
| `expected.png` | Baseline normalizado (ausente si no existe baseline). |
| `actual.png` | Resultado normalizado. |
| `diff.png` | Unión de ambos tamaños, opaca: magenta `(255,0,255)` = píxel distinto; cian `(0,255,255)` = píxel presente en una sola imagen; gris 16–96 según la luma del expected = sin cambios; negro `(0,0,0)` = fuera de ambas imágenes (nunca se confunde con un píxel sin cambios). |
| `manifest.json` | `format` (`moana-visual-diff/1`), `golden`, `source` (procedencia opcional), `baseline_found`, `dimensions_match`, `expected`/`actual` (ancho, alto, digest), `differing_pixels` = `changed_pixels` + `only_in_one_pixels`, `bbox` (`x0,y0,x1,y1` semiabierta), `files` (rutas relativas al manifiesto), leyenda del diff y entorno (Python, plataforma, NumPy, Pillow). |

Las entradas y el lienzo unión pasan por `check_canvas_budget` antes de reservar buffers. Los archivos se escriben de forma atómica con permisos `0644`.

El baseline nunca se escribe ni modifica en una comparación normal.

## Aceptar un cambio de baseline

La actualización es una acción local, explícita y revisada. CI nunca escribe baselines: si `CI` tiene un valor distinto de vacío, `0` o `false`, la escritura se rechaza con `RuntimeError` justo antes de tocar el golden, tanto si la actualización se pidió con la variable como con `update=True`.

1. Explicar la causa del cambio (issue, contrato o corrección) antes de tocar goldens.
2. Ejecutar sólo los casos afectados: `MOANA_UPDATE_GOLDENS=1 uv run pytest tests/visual -m visual -k <caso>`. Sólo el valor exacto `1` activa la escritura (`" 1"`, `true` o `yes` no). Los goldens distintos o ausentes se reescriben de forma atómica, se generan los diagnósticos con el baseline anterior como `expected.png` y la prueba **falla** a propósito; un golden igual no se reescribe.
3. Inspeccionar `artifacts/visual/<caso>/` (`expected.png`, `actual.png`, `diff.png` a 1× y ampliados por vecino más cercano) y `git diff --stat tests/visual/goldens`.
4. Volver a ejecutar sin la variable: `uv run pytest tests/visual -m visual` debe pasar.
5. En el PR presentar expected/actual/diff, conteo y bbox del manifiesto y la justificación; la aprobación la da el responsable de revisión, no el agente ni CI.

## Fixtures y procedencia

- Los oráculos son literales escritos a mano en las pruebas; el harness no es su propio oráculo y no se usa el renderer (aún inexistente).
- `goldens/harness-reference-4x3.png`: PNG RGBA 4×3 sin metadatos, generado con `write_png` a partir del literal `REFERENCE_ROWS` de `test_visual_harness.py` (colores opacos, uno semitransparente y transparentes). La prueba lo decodifica también con Pillow directamente y lo compara con el literal. Contenido técnico propio del proyecto, sin valor artístico.
