# ADR-022 — Máscaras semánticas en DAG, regiones por ID y `budget-v3`

Estado: aceptado · 2026-11-17 · Issue: [MOANA-013](../../issues/MOANA-013.md). Amplía [ADR-011](ADR-011-schema-v1.md) (las colecciones `masks` y `regions` y el campo `mask_id` de capa dejan de ser capacidades previstas), [ADR-017](ADR-017-layers-composition.md) (máscara de capa en el compositor), [ADR-018](ADR-018-render-pipeline.md) (estimador `budget-v3`) y [ADR-020](ADR-020-public-api-cli.md) (`resolve_region`, informe y capacidades). Aplica ADR-012 (presupuestos), ADR-015 (máscaras de primitivas) y ADR-016 (transformaciones). Ampliado por [ADR-023](ADR-023-aggdraw-paths.md): la hoja de máscara `path` deja de estar prevista (`PLANNED_MASK_TYPES` queda vacío) y el estimador pasa a `budget-v4`.

## Contexto

MOANA.md §11 define las máscaras como nodos con ID, geometría binaria y combinaciones union/intersect/subtract/xor que no pueden depender del render de una capa. Sus referencias forman un DAG: los ciclos y las referencias inexistentes se rechazan antes de ejecutar. Una región es un ID semántico con `mask_id` y una lista opcional de IDs de operaciones, de modo que un agente pueda pedir «el ojo izquierdo» sin inferir coordenadas desde el PNG. La composición aplica la máscara y la opacidad antes de la fórmula source-over.

Hasta ahora el schema 1.0 aceptaba `masks` y `regions` sólo vacías y respondía `UNSUPPORTED_OPERATION` a cualquier contenido o a `mask_id` en una capa (ADR-011). §12 prevé ampliar el schema y documentar los payloads junto al issue que los implementa. El compositor (ADR-017) no tenía máscaras de capa, y el estimador `budget-v2` (ADR-018) no contaba su trabajo ni su memoria.

Hay que decidir también qué significa una máscara bajo un grupo transformado: el issue lo señala como riesgo, aunque el schema 1.0 todavía no tiene grupos ni `transform`.

## Decisión

1. **Payloads de schema 1.0.** Todos los IDs entran en la unicidad global del documento.
   - `masks` (opcional, ≤1024): unión discriminada por `type`.
     - Hojas `pixel`, `line`, `rect`, `ellipse` y `polygon`, con los mismos parámetros y reglas raster que las operaciones de §6, sin `color`, en coordenadas de lienzo.
     - Combinaciones `union`, `intersect`, `subtract` y `xor` con `masks`: de 2 a 64 IDs de máscara, plegados en el orden del array.
   - `regions` (opcional, ≤1024): `{id, mask_id, operation_ids}`. `operation_ids` vale `[]` por defecto.
   - Capa: `mask_id` opcional. Se omite si no hay máscara; `null` explícito se rechaza.

   Ejemplo:

   ```json
   "masks": [
     {"id": "eye_left_shape", "type": "rect", "box": [4, 6, 7, 9]},
     {"id": "eye_right_shape", "type": "rect", "box": [9, 6, 12, 9]},
     {"id": "eyes", "type": "union", "masks": ["eye_left_shape", "eye_right_shape"]},
     {"id": "lid", "type": "rect", "box": [0, 6, 16, 7]},
     {"id": "eyes_open", "type": "subtract", "masks": ["eyes", "lid"]}
   ],
   "regions": [{"id": "eye_left", "mask_id": "eye_left_shape", "operation_ids": ["iris_left"]}],
   "layers": [{"id": "irises", "name": "Iris", "mask_id": "eyes_open", "operations": ["…"]}]
   ```

   El documento completo está en `examples/specs/masked-eyes.moana.json`.

   **Amplía 1.0 sin subir la versión, como excepción previa a la primera publicación.** MOANA.md §16 establece que un minor de schema sólo añade campos con defaults compatibles; esta ampliación cabría en un minor, pero todavía no hay tags, paquete publicado ni documentos de terceros, y la especificación es `-draft`. Por eso 1.0 sigue abierta hasta la primera publicación; después, toda ampliación de gramática sube el minor (§12 y §16). La ampliación es además compatible hacia atrás:
   - Todo documento válido antes sigue siendo válido, con la misma forma canónica y el mismo `snapshot_digest`: las colecciones vacías ya se materializaban y `mask_id` ausente se omite.
   - Ningún documento aceptado antes cambia de significado, porque el contenido de esas colecciones siempre se rechazaba.
   - Un lector anterior rechaza un documento con máscaras mediante `UNSUPPORTED_OPERATION`, explícitamente y sin ignorarlo, que es la regla de §12 para capacidades previstas.

   El JSON Schema revisado (`schemas/moana-document-1.0.schema.json`) se regenera: `maxItems: 0` se sustituye por los modelos reales. `path` como hoja de máscara queda previsto (`PLANNED_MASK_TYPES`) y llegará con los paths (MOANA-007). `materials` y `animations` siguen aceptándose sólo vacías.
2. **Resolución en DAG antes del render (`moana.schema.references`).** Forma parte de la fase semántica de `validate_document`, que `render` vuelve a ejecutar. Por eso ningún ciclo ni referencia rota llega al plan de coste ni a un rasterizador.
   - Un operando, `mask_id` de capa o máscara de región que no nombra una máscara es `REFERENCE_ERROR` `unknown_mask`, con el puntero del miembro (`/masks/i/masks/j`, `/layers/i/mask_id`, `/regions/i/mask_id`). Un ID de capa, operación o color tampoco es una máscara: así una máscara no puede depender del render de una capa.
   - Una operación de región inexistente es `unknown_operation`. Un operando u operación repetido es `VALIDATION_ERROR` `duplicate_reference`, porque no tiene significado propio.
   - Los ciclos, directos o indirectos, se detectan con Tarjan iterativo sobre los arrays de operandos. Se informa de cada arista cuyo origen y destino comparten componente (`mask_cycle`, en `/masks/i/masks/j`). Una máscara que sólo depende de un ciclo no se marca.
   - Si el grafo es acíclico, la cadena de referencias más larga admite como mucho 16 nodos (`MAX_MASK_DEPTH`, como los grupos). Se informa de la primera máscara que lo supera (`too_deep`).
   - Todo depende de IDs, no del orden de los arrays: una máscara puede referenciar otra declarada después.
3. **Álgebra en `geometry` (`moana.geometry.algebra`).**
   - `union`: píxeles de algún operando.
   - `intersect`: píxeles de todos los operandos.
   - `subtract`: píxeles del primer operando que no están en ninguno de los demás (`a − b − c = a − (b ∪ c)`).
   - `xor`: paridad n-aria.

   `union`, `intersect` y `xor` son asociativas y conmutativas; `subtract` no. La máscara vacía es neutra para `union`/`xor`/`subtract` y absorbente para `intersect`. Un resultado vacío no tiene almacenamiento.

   `combined_box` calcula la caja del resultado sólo con aritmética: la envolvente de los operandos en `union`/`xor`, su intersección en `intersect` y la del primero en `subtract`, recortada al lienzo. `MaskBuilder` pliega los operandos uno a uno, en su lugar y sin temporales, sobre un único buffer de esa caja. Lo que cae fuera de la caja se descarta, y así se recorta al lienzo.
4. **Máscara de capa en `layers`.**
   - `MaskShape(id, mask)` es una hoja con `Mask` o `DeferredMask`. `MaskCombination(id, operator, operands)` tiene de 2 a 64 operandos y una profundidad derivada ≤16. Ambos son inmutables y se construyen de abajo arriba, así que el DAG es acíclico por construcción. `Layer(..., mask=...)` acepta uno de ellos o `None`.
   - `LayerTree` rechaza hojas guardadas fuera del lienzo (`outside_canvas`, con `mask_id`).
   - `compose` evalúa la máscara después de pintar los fills de la capa y pone a cero el buffer de capa fuera de ella antes de componerlo con su opacidad. Equivale a multiplicar el alfa fuente por la máscara binaria antes de §11: fuera, `sa = 0`, y la fórmula deja el píxel padre exactamente igual. Dentro, la opacidad se aplica una sola vez. Una máscara vacía omite la capa.
   - La evaluación recorre en profundidad, operando a operando, con un `MaskBuilder` por nodo. No hay memo: un nodo compartido se evalúa en cada referencia; se cambia CPU por memoria acotada, y el coste lo cuenta así. Un nodo cuya caja de resultado (`combined_box`) es vacía devuelve `Mask.empty()` sin evaluar sus operandos ni construir la hoja diferida. El deadline se comprueba antes de cada nodo de máscara (`compose_mask`).
   - `MaskCombination` tiene igualdad por identidad (`eq=False`), como `DeferredMask`: una igualdad o un hash estructural de un DAG compartido costaría tanto como expandirlo.
5. **Grupos transformados (norma para cuando existan).** Las máscaras están siempre en coordenadas de lienzo. Una transformación de grupo (ADR-016, todavía no está en el schema) moverá la geometría de los hijos, no sus máscaras; hoy sólo `moana.layers` puede construir ese caso. Por eso la máscara de una capa recorta el contenido ya transformado: `transformado(fill) ∩ máscara`, no `transformado(fill ∩ máscara)`. Los grupos de `layers` no llevan máscara, porque §11 sólo la define para capas. La opacidad de grupo sigue aplicándose una vez sobre el resultado aislado, que ya incluye a los hijos enmascarados.
6. **`budget-v3` (`ESTIMATOR_VERSION`).** Un documento sin máscaras cuesta exactamente lo mismo que con `budget-v2`. Para cada capa visible con `mask_id` se expande la expresión: una máscara compartida cuenta una vez por referencia.
   - **Suelo.** Cada nodo evaluado de la expresión expandida cuesta al menos `MASK_NODE_VISITS` = 1 visita. Sin él, las hojas fuera del lienzo y sus combinaciones costaban 0, y un DAG de 64 operandos por nivel y 16 niveles (64^15 referencias) pasaba el plan con coste 0 y bloqueaba el compositor. Un nodo con caja vacía cuesta sólo el suelo, porque no se evalúan sus operandos: el coste coincide con el trabajo real del compositor.
   - **Visitas.** Una hoja no vacía suma su trabajo de rasterizado, sin pasada de pintado. Una combinación no vacía suma `2 ×` la caja de su resultado (puesta a cero y comprobación final) más, por cada operando, su coste y un plegado sobre su caja. Copiar los bits del resultado suma su caja, y limpiar la capa fuera de la máscara, `A`.
   - **Bytes.** El pico de evaluación (la caja de una hoja, o la caja propia más el operando más caro; 0 si está vacía) más una copia del resultado. Este término sustituye al de la máscara de operación mayor cuando lo supera.

   Cada capa enmascarada aporta un `OperationCost` en `/layers/i/mask_id`, y `plan_budget` comprueba también las coordenadas de las hojas (`/masks/i`). `composition_cost` usa el mismo suelo y los mismos términos, sin el rasterizado de las hojas, que presupuesta el llamador como en ADR-018. La caja combinada es una única función pura, `moana.core.coordinates.combined_box`, que consumen `geometry` y el plan; las fórmulas de visitas y pico se repiten en `layers` y `render.budget` (el plan no importa NumPy) y una prueba las ata. Ni el plan ni `mask_dependencies`/`resolve_region` cuelgan con un `Document` construido sin validar: un ciclo o una referencia rota dan `ReferenceError` (`mask_cycle`, `unknown_mask`, `unknown_operation`) en tiempo lineal. Así, lo que admite `plan_budget` lo compone `render`. `RENDERER_VERSION` sigue en `render-v1`, porque ningún documento admitido antes cambia de píxeles.
7. **Fachada (ADR-020).**
   - `moana.schema.resolve_region(document, region_id) -> ResolvedRegion` devuelve `region_id`, `mask_id`, `mask_ids` (la máscara y sus dependencias, operandos primero y cada una una vez), `operation_ids` y `layer_ids` (capas que contienen esas operaciones, en orden del documento). Un ID desconocido es `ReferenceError` `unknown_region`. `mask_dependencies` expone el orden de evaluación.
   - `moana.api` reexporta `resolve_region` y `ResolvedRegion`, y lo añade a `AVAILABLE_FUNCTIONS`, sin añadir ningún algoritmo propio.
   - `inspect_document` añade `masks` (`MaskSummary`), `regions` (`RegionSummary`) y `mask_id` en cada capa.
   - `capabilities()` añade `collections`, `mask_types` y `planned_mask_types`. `masks`, `regions` y `mask_id` salen de lo previsto.
   - El CLI no cambia de comandos: sus objetos JSON incluyen estos campos nuevos.

## Alternativas descartadas

- **Subir a schema 1.1 ahora.** Es lo que exigirá §16 tras la primera publicación, pero antes de ella no hay lectores ni documentos publicados con 1.0 que distinguir, y abrir 1.1 duplicaría el JSON Schema versionado y el despacho por versión sin proteger a nadie. La migración de 1.0 a 1.1 sería la identidad, así que no es el argumento: la excepción se limita a este periodo y queda registrada aquí.
- **Expresiones anidadas en línea**, sin IDs por nodo. Impiden compartir subexpresiones y hacer targeting por ID, y hacen crecer la profundidad JSON, limitada a 32.
- **Reutilizar las operaciones con color como hojas de máscara.** Mezclaría geometría y pintura, y abriría la puerta a que una máscara dependiera de una capa.
- **Memorizar los nodos compartidos durante la evaluación.** La memoria crecería con el número de máscaras vivas. La reevaluación por referencia está acotada en memoria (profundidad ≤16) y su trabajo se presupuesta con el suelo por nodo, así que un DAG exponencial se rechaza antes de reservar buffers.
- **Aplicar la máscara a cada fill.** Equivale en el resultado, pero evalúa la máscara una vez por operación. §11 asocia `mask_id` a la capa.
- **Detectar ciclos en el render.** Llegaría tarde (después del plan) y dejaría `inspect_document` sin el error. La validación semántica es la frontera que conoce los punteros.
- **Mover las máscaras con el grupo.** Una región («ojo izquierdo») dejaría de ser estable en coordenadas de lienzo y dependería de la geometría local, que es justo lo que §11 quiere evitar.

## Consecuencias

- Punto de extensión para MOANA-007. Una hoja `path` se añade como modelo en la unión `MaskNode`, con sus casos en `mask_box`, `_raster_work`, `_coordinate_reach` y `_rasterize` (`assert_never` obliga a ello), y pasando `path` de `PLANNED_MASK_TYPES` a soportado. El álgebra, la resolución y el compositor no cambian.
- La edición (MOANA-018) podrá apuntar a una región por ID y rechazar el borrado de máscaras referenciadas con `mask_dependencies` y `reference_details`.
- Límites nuevos en `moana.core.limits`: `MAX_MASKS`, `MAX_MASK_OPERANDS`, `MAX_MASK_DEPTH` y `MAX_REGIONS`.
- Evidencia:
  - `tests/unit/geometry/test_geometry_algebra.py`: álgebra con fixtures de 1/8/128 píxeles, vacías, asociatividad, clipping y propiedad contra conjuntos de Python.
  - `tests/unit/layers/test_layers_masks.py`: AC1 contra el oráculo escalar, grupos transformados, máscara fuera del lienzo, coste con suelo, nodos vacíos que no evalúan operandos, DAG 64 × 15 vacío y lleno y `tracemalloc`.
  - `tests/unit/schema/test_schema_masks.py`: payloads, ciclos directos e indirectos, referencias rotas, independencia del orden y regiones.
  - `tests/unit/render/test_render_masks.py`: ejemplo calculado a mano, rechazo antes de cualquier rasterizado, oráculos de `budget-v3`, DAG anchos y profundos (vacíos al suelo, llenos rechazados), documentos sin validar con ciclos o referencias rotas y la propiedad «lo que admite `plan_budget` lo compone `render`» con máscaras.
  - `tests/unit/api/test_api_masks.py`: fachada.
