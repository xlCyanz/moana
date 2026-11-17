# ADR-013 — Lienzo RGBA propietario y adaptadores NumPy/Pillow en `core`

Estado: aceptado · 2026-11-17 · Issue: [MOANA-004](../../issues/MOANA-004.md). Complementa ADR-010 y sustituye parcialmente ADR-012 §3 (frase sobre MOANA-004).

## Contexto

MOANA.md §3 asigna a `core` los buffers y §5 fija el array canónico (`uint8`, C-contiguo, `(height, width, 4)`, RGBA recto, alfa cero como `(0,0,0,0)`, vistas públicas inmutables o copias). Los [contratos de módulos](../module-contracts.md) declararon `moana.core` libre de NumPy y Pillow para que `schema` y `render.budget` lo importen sin cargar bibliotecas gráficas. MOANA-004 pide el lienzo y sus adaptadores dentro de `src/moana/core/`. ADR-012 estableció que `plan_budget` es la puerta de los límites del anfitrión y que el lienzo reserva sólo con un `CostEstimate` aprobado.

## Decisión

1. **Adaptadores como submódulos explícitos de `core`.** `moana.core.canvas` (NumPy) y `moana.core.pillow_adapter` (NumPy y Pillow) no se importan desde `moana.core/__init__`. `import moana.core` sigue sin cargar NumPy, Pillow ni Pydantic; `tests/unit/core/test_core_architecture.py` permite NumPy sólo en `canvas.py` y Pillow sólo en `pillow_adapter.py`. Ningún otro módulo de `core` importa bibliotecas externas. `core` sigue sin dependencias internas (§3).
2. **`Canvas` es propietario exclusivo de su buffer.** Clase mutable sin hash (igualdad por tamaño y bytes). Se construye sólo con `Canvas.blank(dimensions, *, limits)` o `Canvas.from_array(array, *, limits)`: llamar a `Canvas(...)` lanza `TypeError` y `copy.copy`/`copy.deepcopy` copian el buffer. Ningún array entra ni sale por referencia: `from_array` copia a un buffer C-contiguo nuevo sin modificar el del llamador y `to_array()` devuelve una copia escribible e independiente. `copy()`, `to_bytes()` y `visual_digest()` (SHA-256 de ancho y alto `uint32` big-endian + RGBA fila a fila, §14) completan la superficie. Toda escritura e importación normaliza alfa cero a `(0,0,0,0)`.
3. **Acceso por píxel sin wraparound.** `get_pixel`/`set_pixel` reciben `Point` y usan `Dimensions.check_pixel`: fuera del lienzo, incluidas coordenadas negativas, lanzan `OutOfBoundsError` antes de indexar. Los canales son `int` reales en 0–255 en una tupla de cuatro; `bool`, floats y escalares NumPy se rechazan con `ValidationError` sin escribir.
4. **Validación antes de copiar o reservar.** `from_array` exige un `numpy.ndarray` exacto (no subclases como `MaskedArray`, que descartarían datos), `dtype uint8`, forma `(h, w, 4)` y ejes 1–2048 antes de copiar. `canvas_from_pillow` acepta sólo una `PIL.Image.Image` ya abierta en modo `RGBA` y de un frame; no convierte modos implícitamente (`RGB`, `RGBa`, `LA`, `P` se rechazan) y comprueba tamaño y presupuesto antes de leer los píxeles; si Pillow no puede leerlos (imagen cerrada o truncada) lanza `ValidationError` (`unreadable_image`) sin rutas. La normalización de alfa usa una máscara de `A` bytes, no índices. Decodificar archivos pertenece a `project`/`export`.
5. **Defensa en profundidad del presupuesto con el mismo error.** `limits` es un argumento obligatorio, para que olvidar los límites reducidos del anfitrión no los sustituya en silencio por los predeterminados. `check_canvas_budget(dimensions, limits)` comprueba la geometría del anfitrión y `4 × A` bytes contra `RenderLimits` antes de reservar, y lanza `BudgetExceeded` (código y salida 3, recursos `canvas_dimension`, `canvas_area`, `buffer_bytes`) idéntico al de `plan_budget`. Sustituye la frase de ADR-012 §3 «reserva buffers sólo con un `CostEstimate` aprobado», imposible desde `core` porque `CostEstimate` vive en `render`: el orquestador sigue llamando primero a `plan_budget`, que cubre todos los buffers del render, y crea lienzos sólo después; el lienzo repite su parte para que una llamada directa (tests, `quality`, `export`) no reserve sin presupuesto, y no introduce otro código de salida. Su `estimated` de `buffer_bytes` es `4A` (sólo el lienzo), menor que el del plan; con un plan aprobado esta comprobación nunca falla.

## Alternativas descartadas

- Lienzo en `render` o en un paquete `raster`: `geometry`, `layers`, `quality` y `export` necesitan el buffer, y no pueden depender de `render` según §3.
- Exportar `Canvas` desde `moana.core`: cargaría NumPy en `schema` y en el plan de coste.
- Devolver vistas de sólo lectura (`writeable=False`): el llamador puede reactivar la escritura en una vista; la copia es la única garantía sin alias.
- Convertir modos de Pillow automáticamente: cambiaría colores o alfa de forma silenciosa.

## Consecuencias

- `core.canvas` sólo añadirá escrituras masivas acotadas (rellenar una caja o máscara con un color, escribir filas desde una copia) cuando MOANA-006/010 las necesiten; rasterización y composición (§6, §11) se quedan en `geometry` y `layers`. Cualquier vista pública del buffer exige un ADR. `geometry` y `layers` pueden usar NumPy internamente para máscaras y acumuladores (adaptadores internos de §3) sin exponer arrays; cada issue añade su propia prueba de fronteras.
- `RenderResult` (MOANA-010, §13 «RGBA inmutable») nunca expone un `Canvas`, un `ndarray` ni una imagen de Pillow: guarda `to_bytes()`, ancho, alto y digest. `to_array()` y `canvas_to_pillow()` son copias para adaptadores internos, no para la fachada.
- La copia de `canvas_from_pillow` usa temporalmente `8 × A` (bytes de Pillow y buffer); el presupuesto del lienzo cuenta `4 × A` porque la imagen de origen ya pertenece al llamador.
- Evidencia: `tests/unit/core/test_core_canvas.py` y `tests/unit/core/test_core_architecture.py`.
