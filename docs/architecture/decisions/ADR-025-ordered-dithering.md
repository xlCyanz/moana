# ADR-025 — Dithering ordenado Bayer con cobertura entera, anclaje explícito y `budget-v5`

Estado: aceptado · 2026-11-18 · Issue: [MOANA-016](../../issues/MOANA-016.md). Amplía [ADR-011](ADR-011-schema-v1.md) y [ADR-022](ADR-022-masks-regions.md) (operación `dither` en schema 1.0, con `mask_id` en el DAG de referencias, y tabla de miembros por tipo), [ADR-012](ADR-012-request-budgets.md) (el recurso `operations` compara fills rasterizados), [ADR-015](ADR-015-raster-primitives.md) (selección periódica en `geometry`), [ADR-017](ADR-017-layers-composition.md) (`evaluate_mask` público en `layers`), [ADR-018](ADR-018-render-pipeline.md) (dos fills diferidos por `dither` y estimador `budget-v5`) y [ADR-020](ADR-020-public-api-cli.md) (`dither` disponible en `capabilities()` y resumido en `inspect_document`). Aplica ADR-012 (presupuestos), ADR-014 (paleta) y ADR-021 (determinismo). Consumido por [ADR-024](ADR-024-atomic-edits.md): la edición recorre la tabla de miembros (un `dither` da `multiple_colors` en `set_color` y `not_geometric` en `translate`/`set_geometry`).

## Contexto

MOANA.md §10 fija el contrato normativo del dithering ordenado inicial:

- matrices Bayer 2×2 `[[0,2],[3,1]]` y 4×4 `[[0,8,2,10],[12,4,14,6],[3,11,1,9],[15,7,13,5]]`;
- `coverage` entera entre 0 y N², con color B si `threshold < coverage` y A en caso contrario;
- origen de patrón explícito `(ox, oy)` en el lienzo, con módulo matemático también en coordenadas negativas;
- recorte por máscara antes de escribir, y la misma fase entre tiles y frames salvo instrucción del autor.

§10 añade que el ruido y el dithering se aplican a regiones elegidas, no a toda la imagen por defecto. El issue deja fuera la difusión de error y el dithering automático global.

Un patrón mal anclado produce costuras y parpadeo. Si el umbral dependiera de la caja de cada operación, de un `%` truncado (C) o del orden de recorrido, dos tiles contiguos con el mismo origen no encajarían y una traslación de la caja cambiaría la fase. Hacía falta además decidir dónde vive el dithering (§3: `techniques` depende de `core`, `geometry` y `palette`), cómo entra en el documento y cuánto cuesta.

## Decisión

1. **Regla normativa (la de §10, sin cambios).** Para una matriz `M` de lado `N` ∈ {2, 4} anclada en `origin = (ox, oy)`, el píxel `(x, y)` tiene umbral `t(x, y) = M[(y − oy) mod N][(x − ox) mod N]`: la fila sale de `y` y la columna de `x`. `mod` es el módulo matemático, con resultado en `[0, N)` también para operandos negativos (el `%` de Python y `numpy.remainder` sobre enteros). Con cobertura `c` ∈ `0..N²`, el píxel toma B si `t < c` y A en otro caso. Cada valor de umbral aparece una vez por período, así que cada período `N × N` tiene exactamente `c` celdas B: `c = 0` es todo A y `c = N²`, todo B.
2. **`moana.geometry.select_periodic(mask, cells, origin)` (geometría genérica).** Recibe una tabla rectangular de booleanos de 1 a 64 celdas por eje (`CellTable`) que tesela el lienzo con su celda `(0, 0)` en `origin`, y devuelve los píxeles de `mask` que selecciona. Trabaja sólo sobre la caja de almacenamiento de la máscara, que ya está recortada al lienzo: el resultado tiene esa misma caja o es vacío. Los índices de fila y columna son vectores `int64` con módulo matemático y la selección se hace con dos `take` (sin la iteración con búfer del indexado avanzado), así que el pico es `área + 8·(ancho + alto) + filas_de_tabla·ancho` bytes (`PATTERN_INDEX_BYTES` = 8). Una tabla mal formada es `ValidationError` con `field: cells` y `reason` `not_sequence`, `not_boolean`, `bad_size` o `not_rectangular`. Vive en `geometry` porque es la única pieza que construye `Mask` (su constructor está cerrado), y porque una teselación periódica anclada no es exclusiva del dithering.
3. **`moana.techniques` (módulo nuevo, sólo dithering ordenado).** Importa `core` y `geometry`. No hay stubs de contornos, clusters ni sombreado.
   - `BAYER_2X2`, `BAYER_4X4` y `bayer_matrix(size)` exponen las tablas literales de §10, indexadas `[fila][columna]`. `DITHER_SIZES = (2, 4)`.
   - `DITHER_SIZES` y `PATTERN_INDEX_BYTES` se definen una sola vez en `moana.core.dither`, un módulo de sólo datos sin dependencias, como `core.vector_path`. Los consumen `schema` (gramática de `size`), `techniques`, `geometry` y el plan de coste, que no importa NumPy; no hay copias.
   - `OrderedDither(size, coverage, origin)` es inmutable. Un `size` distinto de 2 o 4 da `unsupported_size`, y un `bool` o un float, `not_integer`. `coverage` debe estar en `0..size²` (`out_of_range`, `not_integer`). `origin` es un `Point` cualquiera, también negativo o fuera del lienzo. `threshold(point)` y `part(point)` son el oráculo escalar.
   - `dither_cells(dither, part)` devuelve un período de la parte `"a"` o `"b"`. `dither_mask(mask, dither, part)` y `split_dither(mask, dither)` dividen una máscara en sus partes A y B, que son disjuntas, suman la máscara y nunca contienen píxeles exteriores. Una parte desconocida es `unknown_part`.
4. **Operación `dither` en schema 1.0.** El payload es `{id, type: "dither", size, coverage, origin, color_a, color_b, mask_id}`. Todos los miembros son obligatorios:
   - `size` es un entero estricto 2 o 4. Un `bool`, un float o un string dan `int_type`; otro entero, `unsupported_size`.
   - `coverage` es un entero estricto `0..size²`. La cota depende de `size` y se comprueba en el modelo, con el puntero en `…/coverage` (`less_than_equal`, `le = size²`).
   - `origin = [ox, oy]` usa coordenadas de píxel (±1 048 576). Es obligatorio porque §10 exige un anclaje explícito: no hay origen implícito en la caja ni en el lienzo.
   - `color_a` y `color_b` son IDs de la paleta. Una referencia inexistente es `REFERENCE_ERROR` `unknown_color` en el miembro.
   - `mask_id` es la máscara de recorte. Es obligatorio porque §10 reserva el dithering a regiones elegidas. Entra en el DAG de referencias de ADR-022: un ID que no nombra una máscara (por ejemplo, una capa o una operación) es `unknown_mask` en `…/operations/j/mask_id`.

   Ejemplo validado: `examples/specs/dither-dusk.moana.json`.

   ```json
   {"id": "dune_dither", "type": "dither", "size": 2, "coverage": 2, "origin": [0, -1],
    "color_a": "sand", "color_b": "sand_shadow", "mask_id": "dune_shade"}
   ```

   **Amplía 1.0 sin subir la versión, con la misma excepción previa a la primera publicación de ADR-022 y ADR-023.** No hay tags, paquete publicado ni documentos de terceros, y la especificación es `-draft`. 1.0 sigue abierta hasta la primera publicación; después, toda ampliación de gramática sube el minor (§12 y §16). La ampliación es compatible: ningún documento válido antes cambia de validez, forma canónica ni `snapshot_digest`, porque antes `dither` era un `type` desconocido y se rechazaba. Un lector anterior lo rechaza con `VALIDATION_ERROR` (`union_tag_invalid`), que es explícito, nunca lo ignora. `dither` no figuraba en `PLANNED_OPERATION_TYPES`; pasa directamente a `SUPPORTED_OPERATION_TYPES`. `schemas/moana-document-1.0.schema.json` se regenera.
5. **Render.** `dither` entra en `RENDERABLE_OPERATION_TYPES`. El plan traduce cada operación a **dos fills diferidos**, A y luego B, declarados sobre la caja de resultado de su máscara (`mask_estimates(document)[mask_id].box`). Cada fill, al construirse, evalúa la máscara con `moana.layers.evaluate_mask`, la misma evaluación que una máscara de capa, sin memo y con deadline por nodo, y conserva su parte con `dither_mask`. El orden de los fills no cambia ningún píxel porque las partes son disjuntas, y nada fuera de la máscara recibe pintura, aunque el color sea transparente. Una máscara cuya caja recortada es vacía produce el aviso `empty_bounds` y no construye nada. `_plan_masks` incluye ya las máscaras que referencian las operaciones `dither`, de modo que una máscara compartida con una capa reutiliza el mismo nodo. `RENDERER_VERSION` sigue en `render-v1`: ningún documento admitido antes cambia de píxeles.
6. **`budget-v5` (`ESTIMATOR_VERSION`).** Un documento sin `dither` cuesta exactamente lo mismo que con `budget-v4`. Para una operación `dither` de lado `N` cuya máscara tiene la estimación `M` (caja de resultado `Bm`):
   - **Visitas.** `2·(M.pixel_visits + 4·área(Bm))`: por cada fill, la evaluación expandida de la máscara y cuatro pasadas sobre `Bm` (recogida, AND, comprobación de vacío y pintado). Si `Bm` es vacía, sólo cuenta `2·M.pixel_visits`, que es una cota superior, porque el render no construye nada.
   - **Bytes.** `M.buffer_bytes + área(Bm) + 8·(ancho(Bm) + alto(Bm)) + N·ancho(Bm) + DITHER_FIXED_BYTES` (4096). Es decir, el pico de evaluación, la copia seleccionada, los índices `int64`, una fila de caja por fila de la tabla y la sobrecarga fija de la tabla. Entra en el término de la mayor máscara de operación.
   - **Fills.** El compositor recibe dos fills por `dither`, y tanto `LayerTree` como la comprobación propia de `compose` cuentan fills. Por eso el recurso `operations` de `plan_budget` cuenta **fills rasterizados** (`fill_count`: 1 por operación y 2 por `dither`). `CostEstimate` y `BudgetReport` (de `inspect_document`) separan los dos conteos: `operations` cuenta las operaciones del documento y `fills`, los fills rasterizados. Una entrada `operations` de `exceeded` (y el detalle de `BudgetExceeded`) lleva `estimated = fills`, el valor que se comparó con `RenderLimits.max_operations`. Por ejemplo, `dither-dusk` tiene 8 operaciones, 4 de ellas `dither`, y 12 fills: con `max_operations = 8` el informe da `operations = 8`, `fills = 12` y `exceeded.estimated = 12`. Un documento de 10 000 operaciones con algún `dither` es válido, pero excede el presupuesto de operaciones.
   - **Coordenadas.** El `origin` de un `dither` se comprueba contra `GeometryLimits.max_coordinate` (`coordinate`, en el puntero de la operación).

   Lo que admite `plan_budget` lo compone `render`, con una prueba de propiedad con límites exactos y otra de memoria con `tracemalloc`. El plan sigue sin importar NumPy ni `techniques`: las fórmulas se duplican como aritmética pura en `render.budget`.
7. **Fachada (ADR-020).** `capabilities()` lista `dither` como disponible. `inspect_document` resume una operación `dither` con su color A en `OperationSummary.color`, sin cambiar la forma de las operaciones del informe, y `BudgetReport` añade `fills`. El CLI no cambia de comandos.
8. **Tabla de miembros por tipo (`moana.schema.members`).** Es un módulo de sólo datos. `NodeMembers(colors, masks, geometry)` nombra, para cada literal `type`, los miembros reales del modelo que guardan colores de paleta, referencias a máscaras y geometría. `OPERATION_MEMBERS` y `MASK_MEMBERS` son `MappingProxyType` de sólo lectura con una fila por tipo de las uniones `Operation` y `MaskNode`:
   - las primitivas tienen `colors=("color",)`, y como geometría `at`, `start`/`end`, `box`, `points` o `commands`;
   - las hojas de máscara tienen la misma geometría, sin colores;
   - las combinaciones tienen `masks=("masks",)`;
   - `dither` tiene `colors=("color_a", "color_b")`, `masks=("mask_id",)` y `geometry=()`.

   `origin` no se trata como geometría: si una edición debe moverlo con la operación lo decidirá un ADR futuro. `validate_document` (referencias de color), `reference_details` (`mask_id` de operaciones) e `inspect_document` (color principal) recorren la tabla en lugar de comprobar clases, y la edición (MOANA-018) la usará igual. Una prueba exige que las claves sean exactamente los literales de las uniones (introspección con `typing.get_args`), que cada miembro exista en su modelo y que ningún miembro de color o de máscara quede fuera de la tabla.

## Alternativas descartadas

- **Anclar el patrón a la caja de la operación o de la máscara.** Moverla cambiaría la fase y dos tiles contiguos tendrían una costura. §10 exige un origen explícito en el lienzo.
- **`origin` opcional con `[0, 0]` por defecto.** Sería cómodo, pero un anclaje implícito es justo lo que §10 prohíbe. Hacerlo obligatorio vuelve visible la decisión del autor en cada operación.
- **Recortar por la máscara de la capa en vez de por `mask_id` propio.** Obligaría a crear una capa por cada zona dithered y mezclaría dos usos de la máscara de capa. `mask_id` en la operación usa las mismas máscaras semánticas de MOANA-013. Una capa con máscara puede además recortar el resultado.
- **Un único fill bicolor en `layers`.** Ampliar `Fill` con una segunda máscara y un segundo color complicaría el contrato del compositor (validación, coste, pintado) por una sola técnica. Dos fills diferidos reutilizan el compositor sin cambios. Su coste es reevaluar la máscara dos veces, presupuestado, y contar fills en el recurso `operations`.
- **Memorizar la máscara entre los dos fills.** Mantendría viva una máscara más entre fills y rompería la regla de una máscara construida a la vez de ADR-018.
- **Indexado avanzado `table[np.ix_(rows, cols)]`.** Es correcto, pero NumPy reserva búferes de iteración de ~128 KiB, invisibles en la fórmula. Dos `take` dan el mismo resultado con memoria acotada por la caja.
- **Difusión de error o dithering global automático.** Quedan fuera del issue y de §10, que habla de regiones elegidas.

## Consecuencias

- `techniques` existe con un único submódulo real (`dither`). Contornos, clusters, sombreado y materiales se añadirán en sus issues (MOANA-017 y siguientes) sin stubs previos.
- La animación (P4) deberá conservar el `origin` entre frames salvo un override explícito del autor. El render ya no introduce ninguna dependencia del frame, la semilla ni el hash.
- La edición (MOANA-018) debe tratar `dither` como una operación con dos colores (`color_a`, `color_b`) y una referencia de máscara (`mask_id`), leyendo `OPERATION_MEMBERS`. `set_color` sobre ella necesita un contrato explícito, y borrar una máscara referenciada por un `dither` debe rechazarse como con `mask_id` de capa.
- **Limitación conocida de la fachada:** `inspect_document` sólo muestra el color A de un `dither` (`OperationSummary.color`). Queda como seguimiento exponer todos los colores de la fila de `OPERATION_MEMBERS` sin romper la forma del informe.
- **Riesgo heredado de MOANA-013 (coste por nodo de máscara):** el suelo de 1 visita por nodo evaluado subestima el tiempo real, unos 7 µs por nodo, en DAG anchos y profundos. Cada `dither` reevalúa su máscara dos veces y un documento puede tener hasta 10 000 operaciones (como mucho 5000 `dither` caben en el recurso `operations`), así que un DAG caro puede evaluarse miles de veces. Los límites siguen siendo el total de `pixel_visits` y el `Deadline` cooperativo, que se comprueba antes de cada nodo. Un `budget-v6` con un coste de nodo mayor, calibrado por medición, queda como seguimiento.
- Evidencia:
  - `tests/unit/techniques/test_techniques_dither.py`: T1 con todas las coberturas, umbrales y posiciones del período para 2×2 y 4×4 contra las matrices literales, y conteo exacto de B por período; AC1 con elipse, polígono y combinación; AC2 con orígenes negativos y traslaciones por múltiplos del período; costuras entre tiles; repetición; propiedad Hypothesis contra el oráculo; casos negativos; arquitectura.
  - `tests/unit/geometry/test_geometry_pattern.py`: módulo matemático con orígenes negativos, recorte por máscara, tablas inválidas y `tracemalloc`.
  - `tests/unit/schema/test_schema_members.py`: exhaustividad de `OPERATION_MEMBERS`/`MASK_MEMBERS` frente a las uniones y existencia de cada miembro.
  - `tests/unit/schema/test_schema_dither.py`: payload, JSON Schema, casos negativos (cobertura, tamaño, `bool`/float, colores y máscara inexistentes) y digest de documentos anteriores.
  - `tests/unit/render/test_render_dither.py`: AC1/T1/AC2/T2 a nivel de documento, oráculo de `budget-v5` a mano, conteo de fills, `origin` contra límites, documentos sin validar, memoria, la propiedad «admite ⇒ renderiza» y `operations`/`fills`/`exceeded.estimated` sobre el ejemplo.
  - `tests/integration/test_dither_determinism.py`: el cielo del ejemplo coincide con las bandas Bayer 4×4 calculadas a mano, la duna con la fase 2×2 de `origin [0, -1]` (que difiere de `[0, 0]` en cada píxel comprobado) y el render es idéntico en procesos nuevos con distintos `PYTHONHASHSEED` y en renders repetidos.
