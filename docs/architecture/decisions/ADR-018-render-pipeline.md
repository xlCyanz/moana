# ADR-018 — Orquestador de render determinista, máscaras diferidas y `budget-v2`

Estado: aceptado · 2026-11-17 · Issue: [MOANA-010](../../issues/MOANA-010.md). Sustituye la fórmula de visitas por operación del punto 2 de [ADR-012](ADR-012-request-budgets.md), amplía [ADR-017](ADR-017-layers-composition.md) con `DeferredMask` y sustituye la consecuencia de [ADR-015](ADR-015-raster-primitives.md) sobre `import moana.render`; el resto sigue vigente.

## Contexto

MOANA.md §3 fija el flujo `validación → resolución → presupuesto → plan → máscaras → composición`, y §13 la firma `render(Document, *, frame_id, limits) -> RenderResult`. §14 exige además bytes RGBA idénticos entre procesos, semillas de hash y sistemas operativos, y una aleatoriedad por celda derivada de la identidad.

Las piezas ya existen: `schema` (MOANA-002), `budget-v1` (MOANA-003), rasterizadores (MOANA-006) y compositor (MOANA-009). Al unirlas aparecieron dos problemas.

1. **Memoria.** `LayerTree` exige que cada `Fill` tenga su máscara ya construida. Rasterizar el documento entero antes de componer mantiene vivas todas las máscaras a la vez. Una línea diagonal guarda su caja recortada, hasta `A` bytes, así que 10 000 líneas pueden ocupar `10 000·A` bytes, mientras `budget-v1` sólo contabiliza la máscara mayor.
2. **Trabajo.** El compositor pinta cada fill sobre toda la caja de su máscara, pero `budget-v1` cuenta una línea por sus pasos de Bresenham. Una diagonal de 2048 px cuesta 2049 visitas en el plan y unos 4,2 millones al pintarla. Por eso la comprobación propia de `compose` podía rechazar un documento que `plan_budget` había admitido, y el plan dejaba de ser una cota superior.

## Decisión

1. **Orquestador `moana.render.render`.** Ejecuta las fases en este orden, sin caché ni concurrencia:
   1. Valida el documento: vuelve a pasar el árbol canónico por `validate_document`, para que un modelo construido sin esa entrada también compruebe la unicidad de IDs, las referencias y el perfil.
   2. Comprueba el frame, después de validar el documento. `frame_id` debe ser `None`, porque schema 1.0 no tiene animaciones; cualquier otro identificador es `ReferenceError` sin puntero (es un parámetro de la solicitud, no del documento) con `field: "frame_id"`.
   3. Exige un rasterizador registrado para cada tipo de operación (`RENDERABLE_OPERATION_TYPES`); si falta, `UnsupportedOperation` con el puntero `.../type`.
   4. Convierte la paleta de `schema` en `palette.Palette` y resuelve cada color.
   5. Llama a `plan_budget`.
   6. Construye un `LayerTree` cuyos fills son máscaras diferidas.
   7. Llama a `compose`.

   El deadline cooperativo se comprueba al estimar el coste, antes de planificar cada capa y antes de cada nodo y cada operación al componer. El orden sale sólo de los arrays del documento. El render no lee ni escribe disco y no modifica el documento.
2. **`layers.DeferredMask(box, build)`.** Un `Fill` puede llevar, en lugar de una `Mask`, una caja declarada y un constructor. La validación y `composition_cost` usan la caja. `compose` llama a `build()` una sola vez por fill visible, justo antes de pintarlo y después del deadline, y lanza `RuntimeError` si la máscara sale de la caja: es un error del llamador, no una entrada inválida. En `render` la caja sale de `mask_box`, que coincide con la de `geometry`. `composition_cost` suma `A` bytes por la máscara construida cuando hay fills diferidos visibles; el trabajo de `build()` lo presupuesta el llamador (en `render`, `budget-v2`). Así sólo existe una máscara a la vez, y las de las capas ocultas o con caja `None` nunca se construyen. La igualdad es por identidad.
3. **`budget-v2`.** Las visitas de una operación son su trabajo de rasterizado más una pasada de pintado sobre su caja de máscara recortada, `mask_box(operation, dimensions)`, que coincide exactamente con la caja que devuelve el rasterizador. Por tipo:
   - `pixel`: 2 si cae en el lienzo;
   - `rect` y `ellipse`: `2·área`;
   - `polygon`: `2·área + filas·vértices`;
   - `line`: pasos sin recortar más el área de la caja recortada.

   Las visitas fijas por frame y los recuentos no cambian. El término de trabajo en bytes pasa a `max(40A, 14A + 80·tile) + máscara mayor`, con `tile = min(4096, max(1, A // 4))`; sólo difiere de `40A` en lienzos de uno a tres píxeles, donde los temporales mínimos del compositor superan la fórmula por píxel. Con esta fórmula, la comprobación interna de `compose` (`3A + 2A` por nodo visible más la caja de cada fill, y `14A + 80·tile_pixels` bytes con máscaras diferidas) queda siempre dentro del plan, y una prueba de propiedad lo verifica con límites exactos. `ESTIMATOR_VERSION = "budget-v2"`. Las fórmulas que ADR-015 (`flood_fill`) y ADR-017 (`4A` por nivel de grupo) habían reservado como `budget-v2` pasan a la siguiente versión del estimador que las active.
4. **`RenderResult` inmutable.** Contiene `width`, `height`, `rgba` (`bytes` en filas, de arriba abajo), `digest`, `warnings`, `renderer_version` y `provenance`.
   - El digest visual es el de §14, `sha256:` sobre ancho y alto en `uint32` big-endian seguidos del RGBA, y el constructor lo recalcula.
   - El resultado no expone objetos NumPy; `pixel(x, y)` lanza `OutOfBoundsError` fuera del frame.
   - `warnings` lista `RenderWarning("empty_bounds", ..., pointer)` para cada operación cuya caja de máscara recortada está vacía (`mask_box` es `None`: fuera del lienzo o polígono con caja degenerada), también en capas ocultas. Se decide sin rasterizar: una línea o elipse cuya caja toca el lienzo pero no pinta ningún píxel no avisa.
   - `Provenance` es el manifiesto de reproducción: ID, revisión y `snapshot_digest` del documento, versión de schema, semilla, perfil, frame, `renderer_version` (`render-v1`), backend (`integer`), versión del estimador y del RNG y `moana_version`. No incluye rutas, horas, lock ni plataforma: son hechos del entorno que registra el llamador. `RENDERER_VERSION` sube cuando un cambio en `geometry`, `layers` o `render` puede alterar píxeles del mismo documento.
   - El digest visual tiene una única implementación de biblioteca estándar, `moana.core.digest.visual_digest`, usada por `Canvas` y por `RenderResult`.
5. **Aleatoriedad por celda (`moana.core.procedural`).** Vive en `core` porque sus consumidores, las técnicas procedurales, no pueden importar `render` (§3). Literal de §14:
   - se calcula el SHA-256 del array JSON canónico `[seed, operation_id, x, y, channel, version]`, sin espacios y en UTF-8;
   - `u` son los 8 primeros bytes en big-endian;
   - un valor en `range(n)` es `u·n // 2^64`;
   - versión `cell-sha256-v1`.

   No hay flujo compartido, así que añadir una operación no altera la secuencia de otra. Ninguna operación de schema 1.0 la usa todavía; queda fijada y probada para las técnicas procedurales.

## Alternativas descartadas

- **Rasterizar todo antes de componer:** viola la cota de memoria (ver Contexto).
- **Componer capa a capa en lienzos separados:** necesita un segundo compositor de lienzos. Además, dividir los fills de una capa en subcapas no da el mismo resultado: la composición entera no es asociativa con alfa parcial.
- **Mantener `budget-v1` y que `compose` lo vuelva a comprobar:** el plan dejaría de ser cota superior y el error llegaría con otras cifras.
- **Exponer un array NumPy en el resultado:** §3 y ADR-013 dejan NumPy detrás de adaptadores. `numpy.frombuffer(result.rgba, numpy.uint8)` es explícito y no comparte estado mutable.

## Consecuencias

- Las cifras de `budget-v1` de MOANA-003 se actualizan en sus pruebas. Un documento con muchas líneas largas consume ahora más presupuesto de visitas, porque el pintado ya se contaba en la realidad.
- `import moana.render` carga NumPy y Pydantic, porque el orquestador usa `geometry`, `layers` y `schema`. La garantía de MOANA-003 (y la consecuencia de ADR-015) pasa a ser que `render/budget.py` no importa código raster, comprobado sobre su AST.
- Una prueba con `tracemalloc` verifica que el pico real de `render` queda por debajo de `buffer_bytes` con 100 máscaras de tamaño `A`.
- La serialización final (`to_bytes`), el digest visual y su comprobación en `RenderResult` recorren el frame dos o tres veces más de lo que cuentan las `3A` visitas fijas. Son pasadas lineales sin reserva adicional y quedan como margen conocido del estimador.
- Evidencia: `tests/unit/render/` (escenas calculadas a mano con digests recalculados con `hashlib`, que fijan los bytes en cada sistema operativo de CI; errores; presupuestos, incluida la propiedad «lo que admite `plan_budget` lo compone `render`»; cancelación y resultado), `tests/unit/core/test_core_procedural.py` (RNG) y `tests/integration/test_render_determinism.py` (subprocesos con `PYTHONHASHSEED` 0, 1, 4242 y `random`, orden de claves y espacios).
