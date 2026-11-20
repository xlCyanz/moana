# ADR-023 — Paths de punto fijo con el backend `aggdraw-v1` y `budget-v4`

Estado: aceptado · 2026-11-18 · Issue: [MOANA-007](../../issues/MOANA-007.md). Amplía [ADR-005](ADR-005-backends-and-boundaries.md) (concreta el adaptador AggDraw), [ADR-011](ADR-011-schema-v1.md) y [ADR-022](ADR-022-masks-regions.md) (operación `path` y hoja de máscara `path` en schema 1.0), [ADR-015](ADR-015-raster-primitives.md) (nuevo rasterizador en `geometry`), [ADR-018](ADR-018-render-pipeline.md) (estimador `budget-v4` y procedencia del backend) y [ADR-020](ADR-020-public-api-cli.md) (`backends` en `capabilities()`). Aplica ADR-012 (presupuestos), ADR-013 (adaptadores) y ADR-021 (determinismo).

## Contexto

MOANA.md §6 prevé `path` con comandos M/L/Q/C/Z en punto fijo 1/256, sin SVG, fuentes ni recursos externos. AggDraw calcula la cobertura a escala nativa, se binariza con umbral >=128 y se normaliza a 0/255. El resultado se etiqueta `aggdraw-v1` y sólo es reproducible con las versiones y plataformas ensayadas; no equivale al backend entero. Hasta ahora `path` era una capacidad prevista: el schema respondía `UNSUPPORTED_OPERATION` tanto a la operación como a la hoja de máscara (`PLANNED_OPERATION_TYPES`, `PLANNED_MASK_TYPES`).

Al ensayar AggDraw 1.4.1 se observaron cuatro hechos que condicionan el diseño:

- **Regla de relleno.** Usa *nonzero*: el centro de un pentagrama queda relleno y un subpath interior con la orientación opuesta abre un agujero.
- **Contorno engordado.** Engorda cada subpath en torno a 1/4 de píxel según su orientación, con picos de hasta ~1 px en ángulos agudos, antes de calcular la cobertura. Un cuadrado entero deja 63/255 en los píxeles vecinos; una franja de 1/4 px cubre 127/255 de su fila y una de 1/2 px, 190/255. Un path de área nula no pinta nada.
- **Acumulación por winding.** La cobertura de subpaths superpuestos se acumula con su winding: copias apiladas de una astilla o de una franja fina suman cobertura hasta cruzar el umbral, y regiones de winding opuesto se restan aunque cada una, sola, cubriría el píxel.
- **Recorte.** Recorta cada segmento contra el buffer, y el trabajo no depende de lo lejos que llegue el path. Como redondea las intersecciones a su rejilla de 1/256, un path recortado puede diferir en algún píxel de umbral del mismo path en un lienzo mayor.
- **Celdas.** AGG guarda como mucho 4 194 304 celdas de cobertura y descarta las demás **sin avisar**. Un peine de 2000 dientes en 2048×2048 sale incompleto.

Además, `import aggdraw` carga Pillow.

## Decisión

1. **Payload (schema 1.0).**
   - Operación: `{"id", "type": "path", "backend": "aggdraw-v1", "color", "commands"}`.
   - Hoja de máscara: el mismo objeto sin `color`.
   - `backend` es obligatorio y hoy sólo admite `"aggdraw-v1"` (`SUPPORTED_PATH_BACKENDS`): el documento declara el contrato con el que se pintó.
   - `commands` es un array de 2 a 4096 comandos (`MAX_PATH_COMMANDS`). Cada comando es un array: `["M", x, y]`, `["L", x, y]`, `["Q", x1, y1, x, y]`, `["C", x1, y1, x2, y2, x, y]` o `["Z"]`.
   - Las coordenadas son enteros JSON en unidades de 1/256 px, dentro de ±1 048 576 × 256. Se rechazan `bool`, floats y strings.
   - Orden: el primer comando es `M`; todo subpath (de un `M` al siguiente o al final) tiene al menos un comando de dibujo (`L`/`Q`/`C`); detrás de `Z` sólo puede ir `M`.
   - Un subpath sin `Z` se cierra implícitamente y rellena lo mismo que con `Z`: un path es un contorno relleno, nunca un trazo.

   La gramática vive en `moana.core.vector_path` (`parse_path` → `FixedPath`). `PathCommand` y `FixedPath` se revalidan al construirse (letra, aridad, rango, orden, número de comandos y segmentos; `segments` se deriva y no se pasa), así que un valor construido a mano es tan seguro para el adaptador como uno analizado. La comparten:
   - el schema: cada `PathOperation`/`PathMask` analiza sus comandos **una sola vez** al construirse (`model_post_init`) y guarda el `FixedPath` en un atributo privado; `.path` lo reutiliza mientras `commands` sea la misma tupla;
   - el plan de coste, sin NumPy;
   - el adaptador.

   Los errores son `VALIDATION_ERROR` con puntero y motivo:
   - en el puntero del comando (`.../commands/{index}`): `path_command_invalid`, `int_type`, `missing`/`too_long` (aridad), `less_than_equal`/`greater_than_equal` y también los de orden y segmentos (`path_start`, `empty_subpath`, `command_after_close`, `too_many_segments`, con `index` en el contexto);
   - en `.../commands`: `too_short`/`too_long` (número de comandos).

   El lector JSON limita cada documento a 20 000 nodos; un comando `M`/`L` ocupa 4, así que 4096 comandos sólo son alcanzables con paths casi enteramente de `M`/`L`.

   **Amplía 1.0 sin subir la versión**, con la misma excepción previa a la primera publicación que ADR-022 (MOANA.md §12 y §16): no hay tags ni paquete publicado y la especificación es `-draft`. Todo documento válido antes sigue siéndolo, con la misma forma canónica y el mismo `snapshot_digest`. Un lector anterior rechaza `path` con `UNSUPPORTED_OPERATION` y no lo ignora. El JSON Schema se regenera, y `path` pasa de previsto a soportado en `SUPPORTED_OPERATION_TYPES` y `SUPPORTED_MASK_SHAPES`. `PLANNED_MASK_TYPES` queda vacío.
2. **Aplanado en `core`, nunca en el backend.**
   - Una curva con segunda diferencia `D` (norma Manhattan de `P0 − 2P1 + P2` y, en cúbicas, el máximo con `P1 − 2P2 + P3`) se divide en `n` pasos uniformes de `t`.
   - `n` es el menor entero con `64 n² ≥ D` (cuadráticas) o `64 n² ≥ 3D` (cúbicas), acotado a `1..64` (`MAX_PATH_CURVE_SEGMENTS`). Por debajo de ese tope, el error de cuerda es ≤ 1/16 px.
   - Cada punto es el racional de Bernstein exacto, redondeado a la unidad con empates al par. Así el aplanado es invariante ante traslaciones de píxeles enteros y simetrías respecto a bordes de píxel.
   - Segmentos = segmentos aplanados + una arista de cierre por subpath, como mucho 65 536 (`MAX_PATH_SEGMENTS`).

   AggDraw sólo recibe `moveto`/`lineto`/`close` con coordenadas `v/256`. Son diádicas exactas y caen sobre su rejilla de subpíxel sin redondeo.
3. **Adaptador (`moana.geometry.paths`).**
   - `rasterize_path(FixedPath, Dimensions) -> Mask`.
   - Caja de almacenamiento: la caja de píxeles de todos los puntos (`[floor(min/256), ceil(max/256))`) recortada al lienzo. Un path plano sobre un borde de píxel no tiene caja; si la caja recortada queda vacía, devuelve una máscara vacía sin llamar al backend.
   - AggDraw rellena con antialias en un buffer privado de 8 bits: la caja más 1 px de margen, a escala nativa.
   - **Regla nonzero.** La máscara es «cobertura `>= 128` ∩ caja de los puntos de control» (recortada al lienzo); el resto queda fuera. Es ese recorte del buffer a la caja, no el backend, lo que deja fuera los píxeles exteriores a la caja: el margen sí recibe el engorde. Como la caja es del path entero, el efecto no es local: un subpath lejano agranda la caja y puede dejar entrar píxeles de umbral junto a otro subpath.
   - Ningún nivel de cobertura sobrevive: la operación pinta su color de paleta a través de la máscara, como las demás primitivas, sin AA ni colores intermedios.
   - `aggdraw` se importa perezosamente con `importlib`: `import moana.geometry` y `import moana.render.budget` no lo cargan. Ningún objeto de AggDraw o Pillow sale del módulo; la superficie usada está tipada con `Protocol`.
4. **Garantía limitada.**
   - Para **un único subpath simple** (sin autointersecciones ni agujeros), un píxel cuyo cuadrado está entero dentro del contorno pertenece a la máscara.
   - Los rectángulos alineados a píxeles enteros coinciden exactamente con `rect`.
   - **No hay garantía de exclusión.** Por el engorde orientado, los picos de ~1 px en ángulos agudos y la acumulación por winding, un píxel lejos del contorno puede entrar. Las pruebas comprueban que los ejemplos convexos quedan dentro del cuadrado engordado 1/2 px, pero eso es una caracterización de 1.4.1, no un contrato.
   - Contraejemplos de AggDraw 1.4.1, caracterizados en las pruebas (coordenadas en px):
     - (A) Exterior `[0,7)×[0,3)` horario con agujeros `[1,3)×[1,2)` y `[4,6)×[1,2)` antihorarios: el píxel de pared (3,1) tiene cobertura 127 y queda **fuera**.
     - (B) `M 1,3 L 7,3 L 7,9 L 1,9 L 1,3 L 1,2 L 7,2 L 7,1 L 1,1 Z`: la franja de winding −1 (fila 1) queda **fuera** entera.
     - (C) Tres copias de la astilla `M 3453,2944 L 2941,2943 L 2941,2945 Z` (unidades 1/256) más el cuadrado `[20,21)×[11,12)`: el píxel (14,11) entra **dentro** sin que su cuadrado engordado 1/2 px toque el contorno.
     - (D) Cuatro copias de una franja de 1/8 px sobre el borde entre dos filas llenan **las dos filas**; una sola no pinta nada.
   - Fuera de esos casos, el resultado es el del backend ensayado: no se presenta como equivalente al polígono entero (que usa centros de píxel y even-odd).
   - Un path dentro del lienzo no depende del tamaño del lienzo; uno que lo cruza puede diferir en píxeles de umbral cercanos a los segmentos recortados.
   - Que las coordenadas sean diádicas exactas no hace el contorno engordado independiente de la FPU: la reproducibilidad se promete sólo con las versiones de `TESTED_AGGDRAW_VERSIONS` (`1.4.1`) y en las plataformas donde se ha ensayado.
5. **Capacidad explícita.**
   - `path_backend()` comprueba en cada llamada, sin caché ni estado global, que `aggdraw` se importa (cualquier excepción del import cuenta), que expone `Draw`, `Path` y `Brush` y que su versión está ensayada. Devuelve `PathBackend` con `name`, `available`, `version`, `pillow_version` (de `importlib.metadata`) y `reason` (`missing`, `import_failed`, `incompatible` o `untested_version`).
   - Es una capacidad **de ejecución**: el schema acepta `path` siempre, haya backend o no. `render` consulta el backend antes del presupuesto si el documento contiene algún `path`, también en capas ocultas o máscaras sin usar. Sin backend válido responde `UNSUPPORTED_OPERATION` (`backend_unavailable`, `backend`, `cause`, `tested_versions` y `version` si se conoce) en `/…/backend`, nunca un `ImportError`. El adaptador repite la comprobación para llamadas directas con el mismo constructor (`backend_unavailable_error`), así que el contexto es idéntico. Un fallo del backend al dibujar (`ValueError`, `MemoryError`, `OSError`) se envuelve en `MoanaError` (`backend_failure`).
   - `capabilities()` añade `backends` (`BackendSummary`). Sin backend, `path` pasa a `planned_operations` y `planned_mask_types`: no desaparece. El CLI lo hereda en `moana capabilities`.
6. **Procedencia.** `Provenance` añade `vector_backend` (`"aggdraw-v1"` o `None`) y `vector_backend_versions` (`"aggdraw==1.4.1"` y `"pillow==…"`, porque AggDraw carga Pillow; `()` sin paths). Son claves aditivas presentes en **todos** los renders: sin paths, `to_mapping()` da `vector_backend: null` y `vector_backend_versions: []`. `renderer_backend` sigue siendo `integer`: describe el perfil de las primitivas. `RENDERER_VERSION` sigue en `render-v1`, porque ningún documento admitido antes cambia de píxeles.
7. **`budget-v4`.** Un documento sin paths cuesta exactamente lo mismo que con `budget-v3`. Para un path con `S` segmentos y caja recortada `B` (buffer `B'` = `B` + margen):
   - **Visitas de raster:** `S` siempre (aplanado, sin recortar), más, si `B` no es vacía, `cells + 3·área(B')` (limpieza, barrido de cobertura y umbral). La operación suma además su pasada de pintado sobre `B`, como las demás. Una hoja `path` usa la misma fórmula dentro del coste de máscaras de ADR-022.
   - **Cota de celdas:** `cells = min(2·L + 3S, 3S·(ancho(B') + alto(B') + 1))`, con `L` la longitud Manhattan en píxeles de los polígonos de control y cierres. Un Bézier no varía más que sus puntos de control, y cada segmento recortado se parte como mucho en tres trozos.
   - **Bytes:** `área(B) + 2·área(B') + 24·cells + 256·comandos + 128 KiB` (`PATH_BACKEND_FIXED_BYTES`: AGG reserva en el heap de C unos 79 KB por path aunque mida 1 px). Las fórmulas viven en `moana.core.vector_path` (`path_raster_visits`, `path_raster_bytes`, `path_buffer_box`, `PATH_BUFFER_MARGIN`) y las comparten el plan, `inspect_document` y el adaptador.
   - **Límite de motor:** un path con `cells > 2 097 152` (`MAX_PATH_CELLS`, la mitad de la capacidad de AGG; el factor 2 cubre también las celdas de las uniones del contorno engordado) se rechaza con `BUDGET_EXCEEDED` (`resource: path_cells`) en `plan_budget` y en el adaptador; `inspect_document` lo **informa** en `exceeded`. Ningún `RenderLimits` lo eleva.
   - **Coordenadas:** `plan_budget` comprueba el alcance de un path (`ceil(|v|/256)`) contra `GeometryLimits`.

   Lo que admite `plan_budget` lo rasteriza `render`, y la memoria trazada queda por debajo de la estimación. La evidencia de `tracemalloc` sólo cubre la memoria de Python: la memoria nativa de AGG no la ve, y su término fijo se apoya en una medición del heap de C en macOS.

## Alternativas descartadas

- **Aplanar con `curveto` de AggDraw.** El número de segmentos dependería de la escala de aproximación interna de AGG y de su versión: el coste no sería calculable sin el backend y la garantía sería más débil.
- **Recortar en Python (Sutherland–Hodgman) antes de AggDraw.** Redondear las intersecciones introduce las mismas diferencias de umbral que el recorte de AGG, y además cuesta `O(S)` por arista de recorte en Python.
- **Compensar el engorde de 1/4 px desplazando el contorno.** Exigiría offsets de polígonos con uniones y vértices agudos; sería otra geometría, no la de AggDraw. Se documenta y se ensaya.
- **Muestreo por centros o supermuestreo.** §6 fija cobertura a escala nativa y umbral; el perfil entero ya existe para quien quiera centros de píxel.
- **Hacer `backend` opcional con valor por defecto.** Ocultaría en el documento el contrato con el que se pintaron sus píxeles.
- **Añadir casos `aggdraw-v1` al corpus de ADR-021.** Su manifiesto sale de un oráculo independiente del renderer, y para AggDraw no lo hay; mezclar ambos rebajaría la garantía `integer`. La evidencia del backend vive en pruebas propias.

## Consecuencias

- `moana.core.limits` añade `MAX_PATH_COMMANDS`, `MAX_PATH_SEGMENTS`, `MAX_PATH_CURVE_SEGMENTS` y `MAX_PATH_CELLS`. `moana.core.vector_path` es aritmética pura: no importa NumPy.
- Cambiar AggDraw de versión exige ensayarla y añadirla a `TESTED_AGGDRAW_VERSIONS`. Hasta entonces, `path` sale como previsto y los documentos con paths fallan explícitamente.
- Evidencia entre plataformas del backend (T2): local macOS; matriz pendiente en `main`. No se presenta como completa.
- Evidencia:
  - `tests/unit/core/test_core_vector_path.py`: gramática, motivos e índices, regla de pasos, puntos de Bernstein con empates al par, cajas, alcance y cota de celdas.
  - `tests/unit/geometry/test_geometry_paths.py`: AC1; oráculos geométricos exactos (dentro, y la caracterización de fuera); igualdad con `rect` y con `polygon` donde el contrato lo garantiza; casco convexo de curvas; simetría; nonzero; cierres; recorte parcial y total; paths degenerados; traslaciones; contraejemplos A–D y efecto no local de la caja; backend ausente, roto, incompatible o no ensayado; fallos del backend; límite de celdas.
  - `tests/unit/schema/test_schema_paths.py`: AC2 en el schema.
  - `tests/unit/render/test_render_paths.py`: AC1 y AC2 en el render, oráculo de `budget-v4`, «admite ⇒ renderiza» con Hypothesis y `tracemalloc`.
  - `tests/unit/api/test_api_paths.py`: capacidades y CLI.
  - `tests/integration/test_path_determinism.py`: T2, con procesos nuevos y varios `PYTHONHASHSEED`, e igualdad con `rect` en rectángulos enteros.
  - Ejemplo: `examples/specs/path-sail.moana.json`.
