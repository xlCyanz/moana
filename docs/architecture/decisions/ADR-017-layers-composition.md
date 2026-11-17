# ADR-017 — Árbol de capas y composición source-over entera

Estado: aceptado · 2026-11-17 · Issue: [MOANA-009](../../issues/MOANA-009.md). Aplica ADR-012 (presupuestos), ADR-013 (lienzo), ADR-014 (paleta) y ADR-015 (máscaras). Ampliado por [ADR-018](ADR-018-render-pipeline.md): `DeferredMask`; `budget-v2` pasa a ser la pasada de pintado y el término de `4A` por nivel de grupo queda para una versión posterior del estimador.

## Contexto

MOANA.md §11 define la lista de capas de abajo arriba, los grupos con buffer aislado, la opacidad aplicada una vez y una única fórmula source-over entera sobre RGBA recto con `round_half_up`. También fija la profundidad máxima de grupos en 16. §3 permite a `layers` depender de `core`, `palette` y `geometry`, pero no de `schema`. Por eso el árbol no puede ser el modelo Pydantic del documento: `render` (MOANA-010) traducirá el documento a este árbol. El esquema 1.0 no tiene grupos, máscaras semánticas ni transformaciones de grupo.

## Decisión

1. **Árbol inmutable propio de `layers`.**
   - `Fill(mask, color)`: una máscara binaria de `geometry` pintada con un `Rgba` de `palette`.
   - `Layer(id, name, fills, visible, locked, opacity, blend)`: hoja con relleno.
   - `Group(id, name, children, visible, locked, opacity)`: nodo interior.
   - `LayerTree(dimensions, children, profile)`: árbol completo.

   Los cuatro son dataclasses congelados con tuplas. Cada nodo valida sus campos: ID léxico, nombre UTF-8 válido (sin surrogates sueltos, `invalid_utf8`) de hasta 4096 bytes, booleanos reales, opacidad entera de 0 a 255, `blend` sólo `normal` y como mucho 10 000 fills o 128 hijos.

   `LayerTree` valida el árbol completo con un recorrido iterativo:
   - IDs únicos entre capas y grupos (`duplicate_id`);
   - profundidad de grupos de hasta 16 (`too_deep`, sobre el grupo que la excede);
   - como mucho 128 capas y grupos en total (§20);
   - máscaras dentro del lienzo (`outside_canvas`);
   - en el perfil `strict`, opacidad 255 (`partial_opacity`, igual que el esquema) y colores de relleno con alfa 0 o 255 (`partial_alpha`), ambos con `profile: "strict"` en el contexto. La pertenencia del color a la paleta no se comprueba aquí: `Fill` lleva un `Rgba` resuelto, y la referencia por ID la valida `schema`/`render`.

   La validación se detiene en el primer problema, en orden de abajo arriba y en profundidad. El árbol lo construye código (`render`) a partir de un documento que `schema` ya validó con errores agregados, así que no hay un agente corrigiéndolo a mano.

   Los errores llevan `node_id` y el índice `fill`, no un puntero JSON, porque el árbol no tiene forma de documento. `render` añadirá el puntero al traducir. `locked` se conserva para la edición y no altera el render.
2. **Una sola fórmula, un único kernel.** `_over` implementa literalmente §11 sobre planos `uint32`. El intermedio más grande, `2·(sc·sa·255 + dc·da·(255−sa)) + D`, es menor que 2²⁷. Si alfa vale 0, que ocurre exactamente cuando `D = 0`, el resultado se normaliza a `(0,0,0,0)`. El kernel trabaja por bloques de, como mucho, `tile_pixels = min(4096, A // 4)` píxeles, con hasta 64 filas. Sus temporales, unos 66 bytes por píxel de bloque medidos y 80 declarados (`COMPOSITE_TEMP_BYTES_PER_PIXEL`), no superan nunca 20·A ni 320 KiB.
3. **Regla dentro de una capa.** Los fills se pintan en orden sobre un buffer de capa transparente con source-over a opacidad 255, sólo en la caja de cada máscara. Después la capa se compone sobre su padre con su opacidad. Así, un color con alfa parcial se acumula igual que dos capas superpuestas y la opacidad de capa se aplica una sola vez. Un fill con alfa 0 no cambia nada: no es una goma. Borrar requerirá una operación explícita con su propio contrato.
4. **Grupos aislados.** Cada grupo visible compone sus hijos en un buffer transparente propio y lo compone sobre su padre con la opacidad del grupo, una sola vez. Un nodo oculto, y todo su subárbol, no cuesta nada.
5. **Presupuesto antes de reservar.** `composition_cost(tree)` es aritmética pura sobre el árbol.
   - Visitas: el raíz cuesta 3A (limpiar, normalizar alfa y copiar, como `budget-v1`). Cada capa o grupo visible cuesta 2A (limpiar y componer). Cada fill suma el área de la caja de su máscara.
   - Bytes: `(3 + profundidad)·4A` (raíz, un buffer por grupo abierto, capa y copia final del `Canvas`), más `A` para la copia de la máscara más grande, más `80·tile_pixels` de temporales.
   - Recuentos: `layers` cuenta todas las capas y grupos, y `operations` todos los fills, visibles o no, igual que `budget-v1` cuenta capas y operaciones del documento.

   `compose(tree, *, limits, deadline)` compara ese coste con los límites de geometría del anfitrión (`canvas_dimension`, `canvas_area`) y con `frame_pixels`, `layers`, `operations`, `pixel_visits` y `buffer_bytes`. Si algo no cabe, lanza `BudgetExceeded` con el formato de `plan_budget` antes de crear ningún buffer. Comprueba el deadline cooperativo antes de cada nodo visible y de cada fill. Una prueba con `tracemalloc` verifica que el pico no supera el coste declarado.
6. **Fuera de alcance.**
   - Modos `multiply`/`screen`, que serán una extensión con contrato y fixtures propios.
   - Máscaras semánticas (`mask_id`, DAG union/intersect/subtract/xor) y regiones.
   - El campo `transform` de grupo. Se aplicará con `geometry.Transform` cuando el esquema añada grupos (MOANA-010 o posterior).
   - La traducción del documento al árbol, que pertenece a `render`.

## Alternativas descartadas

- Que `layers` use los modelos de `schema`: lo prohíbe §3 y obligaría a cargar Pydantic en el raster.
- Que las capas guarden un `Canvas` ya pintado: es mutable y duplicaría la propiedad del buffer. Con fills inmutables, el compositor es el único dueño de sus buffers.
- Componer el lienzo entero en un solo paso vectorizado: unos 66 bytes de temporales por píxel, que en un lienzo de 2048² son unos 260 MiB. Los bloques los acotan sin cambiar el resultado.
- Bandas de filas completas: en lienzos bajos y anchos, por ejemplo de 2048×64, los temporales superan las 32A de `budget-v1`. Los bloques limitados por píxeles no.
- Aplicar la opacidad del grupo a cada hijo: contradice §11 y cambia el resultado donde los hijos se solapan.

## Consecuencias

- Para documentos del esquema 1.0, sin grupos, el coste en bytes es `13A + 80·tile_pixels`, como mucho 33A. Eso queda por debajo del conjunto de trabajo de `budget-v1` (`8A + 32A + máscara`) para todo lienzo de al menos 4 píxeles, así que el estimador no cambia. Una prueba lo comprueba en lienzos bajos y anchos. En lienzos minúsculos, la sobrecarga fija de Python y NumPy domina cualquier fórmula por píxel. Cuando el esquema añada grupos, `budget-v2` sumará `4A` por nivel de grupo.
- `render` construirá `LayerTree` a partir del documento validado: rasterizará cada operación a una máscara y resolverá su color de paleta.
- Evidencia: `tests/unit/layers/`. Incluye un fixture semitransparente calculado a mano, un oráculo escalar independiente con Hypothesis sobre árboles con grupos, casos de alfa 0/1/127/255, normalización, orden, visibilidad, opacidad de grupo aplicada una vez, profundidad 16/17, perfil strict, presupuestos con `tracemalloc` y arquitectura de imports.
