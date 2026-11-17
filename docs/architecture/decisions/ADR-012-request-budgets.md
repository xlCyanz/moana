# ADR-012 — Presupuestos de solicitud y plan de coste previo al render

Estado: aceptado · 2026-11-17 · Issue: [MOANA-003](../../issues/MOANA-003.md). La frase de §3 sobre MOANA-004 queda sustituida parcialmente por [ADR-013](ADR-013-canvas-buffer.md).

## Contexto

MOANA.md §20 fija presupuestos por solicitud (256 MiB de buffers estimados con temporales, 100 000 000 visitas de píxel, 16 777 216 píxeles de frames acumulados) y exige fallar en la fase de presupuesto, antes de cualquier asignación grande. Todavía no existen el lienzo (MOANA-004), los rasterizadores (MOANA-006) ni el orquestador (MOANA-010): el plan de coste tiene que fijar ahora una cota que esos issues respeten.

## Decisión

1. **`RenderLimits` en `core`.** Compone `GeometryLimits` (ADR-010) y añade `max_buffer_bytes`, `max_pixel_visits`, `max_frame_pixels`, `max_operations` y `max_layers`. Cualquier valor puede bajarse. Elevar un presupuesto por encima del valor de §20 exige `host_override=True`, una decisión explícita de la aplicación anfitriona (techo 2^62). Los conteos y la geometría nunca superan el contrato del formato. El documento no puede aportar límites: `RenderLimits` no forma parte del schema, y la API/CLI (MOANA-010 y siguientes) nunca lo construyen ni activan `host_override` a partir del JSON de la petición o de flags no confiables; sólo la configuración de la aplicación anfitriona lo hace.
2. **Estimador `budget-v1` en `render`.** `estimate_cost` es aritmética entera pura sobre el documento validado: no importa NumPy ni Pillow, no recorre píxeles y es lineal en operaciones y vértices. Para `A = ancho × alto`:
   - visitas por operación: `pixel` 1 si cae en el lienzo; `rect`/`ellipse`, área de la caja recortada; `polygon`, área recortada de los centros posibles más `filas × vértices` (cruces de scanline); `line`, `max(|dx|, |dy|) + 1` pasos **sin recortar**;
   - visitas por frame: `3A` (limpiar, normalizar alfa, copiar el resultado) + por capa visible `2A` (limpiar y componer) + visitas de sus operaciones. Las capas ocultas no cuestan visitas, pero sus operaciones cuentan para `max_operations`;
   - bytes: `4A` lienzo + `4A` capa + `32A` acumulador de composición (cuatro canales de 64 bits) + la mayor máscara de operación (1 byte por píxel de su caja recortada), más `frames × 4A` de resultados retenidos;
   - píxeles de frames: `frames × A`.
   Las fórmulas son una cota superior contractual. Una evaluación vectorizada ingenua puede superarla (la fórmula de composición de §11 en int64 crea varios temporales de 8A; la inclusión de la elipse usa productos por píxel de la caja), así que MOANA-004/006/010 deben trabajar por filas o tiles para que sus temporales queden dentro de los `32A` y de la máscara contabilizados, y añadir una prueba con `tracemalloc` que compare el pico real con `buffer_bytes`. Si no es posible, actualizan fórmulas, `ESTIMATOR_VERSION` y pruebas en el mismo cambio.
   `frames` cuenta renders idénticos del documento (máximo 256 por §17). Una animación cuyos frames cambian geometría mediante overrides suma un plan por frame evaluado. Los `frames × 4A` de resultados retenidos son conservadores frente al streaming de §22 y se pueden reducir cuando exista el exportador de animaciones.
3. **Rechazo antes de reservar.** `plan_budget(document, limits, *, frames, deadline)` lanza `BudgetExceeded` con un `ErrorDetail` por recurso excedido (`resource`, `limit`, `estimated`). El pointer señala el lienzo, la operación fuera de rango o la operación más costosa en visitas; `buffer_bytes` y `frame_pixels` son globales. Una solicitud exactamente en el límite se admite. Una `GeometryLimits` reducida por el anfitrión se informa también como presupuesto (`canvas_dimension`, `canvas_area`, `coordinate`; los vértices de polígono son coordenadas de píxel en schema 1.0), porque el documento es válido para el formato pero no para esa solicitud. `plan_budget` es la única puerta para los límites del anfitrión: MOANA-004 reserva buffers sólo con un `CostEstimate` aprobado y no vuelve a validar esos límites con otro código de salida. Los conteos (`layers`, `operations`) se rechazan antes de costear cada operación, y el deadline se comprueba por capa y cada 256 operaciones.
4. **Deadline cooperativo.** `Deadline(milliseconds, clock=time.monotonic)` se comprueba entre unidades de trabajo (`checkpoint(stage)`) y lanza `BudgetExceeded` con recurso `time`. El reloj sólo decide si se continúa: nunca influye en píxeles, orden ni semillas (§14). No interrumpe una llamada nativa en curso; un servicio expuesto debe aislar el render en un proceso con límites del SO.

## Alternativas descartadas

- Medir memoria real durante el render: detecta el exceso después de reservar, que es justo lo que §20 prohíbe.
- Recortar líneas antes de costearlas: un segmento de dos millones de pasos fuera del lienzo seguiría costando CPU al rasterizarlo.
- Permitir que el documento declare límites: un documento no confiable podría elevarlos.

## Consecuencias

- `moana.render` nace con el plan de coste; el orquestador se añade en MOANA-010.
- Grupos, máscaras, `flood_fill` y morfología no existen en schema 1.0; cada issue que los incorpore añade su fórmula (flood fill ≤ área, morfología con vecindad y radio) y sube la versión del estimador.
- Evidencia: `tests/unit/core/test_core_budget.py` y `tests/unit/render/` (oráculos a mano, límites exactos y +1, frames, capas profundas, coordenadas enormes, allocators falsos y `tracemalloc`).
