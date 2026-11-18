# Contratos entre módulos

Estado: **contratos previstos**, salvo `core` (con el lienzo RGBA), `schema`, `palette`, `geometry`, `layers`, `render`, `export` PNG y `api`/`cli` (implementados, ver abajo). Las firmas públicas objetivo están en [MOANA.md §13](../../MOANA.md); sus fórmulas, límites y formatos prevalecen sobre este resumen. No se añaden abstracciones base ni registros de plugins por anticipación.

## Entradas, salidas y efectos

| Módulo | Entrada y salida previstas | Responsabilidad y efectos permitidos |
| --- | --- | --- |
| `core` | Coordenadas/cajas/límites → valores tipados y errores | Contratos independientes de módulos superiores; reserva de buffers sólo tras presupuesto |
| `schema` | JSON o mapping → documento normalizado / errores con pointer | Tipos estrictos, defaults, discriminadores y schema; no dibuja ni abre paths contenidos en operaciones |
| `palette` | Colores/rampas referenciados por ID → tabla resuelta / remapeo explícito | Valida perfil y cardinalidad; no cuantiza silenciosamente |
| `geometry` | Parámetros enteros y límites → máscara binaria acotada | Rasterización, clipping y transformaciones; no conoce historial, CLI o disco |
| `layers` | Nodos ordenados, máscaras y buffers → composición RGBA | Orden, visibilidad y grupos; posee sus temporales y aplica opacidad una vez por grupo |
| `techniques` | Máscaras, rampas, patrón y semilla → operaciones/máscaras/colores derivados | Contornos, bandas y materiales editables; no elimina detalles automáticamente |
| `render` | Documento validado, frame y límites → resultado inmutable | Resuelve referencias/capacidades, estima coste y ejecuta plan; sin escritura de archivos |
| `editing` | Documento + batch tipado → documento nuevo o conflicto | Transacción completa, IDs estables y revisión; sin rasterización ni persistencia interna |
| `project` | Bytes/path autorizado + raíz de assets → documento y assets verificados | I/O confinado, hashes, historial y migración; guardado atómico |
| `animation` | Base + timeline/overrides → frames y duraciones | Evalúa cada frame contra la base; contabiliza presupuesto acumulado |
| `export` | Resultado/frames + opciones + destino autorizado → manifiesto | Codificación y escritura atómica; no llama al editor ni cambia el documento |
| `quality` | Resultado, paleta y configuración → incidencias y métricas | Diagnóstico estable y no mutante; separa reglas duras de heurísticas artísticas |
| `api` / `cli` | Solicitud del llamador → resultado, informe o código de salida | Orquesta servicios, autoriza I/O de aplicación y traduce errores; no duplica algoritmos |

## `core` (implementado en MOANA-001)

API pública en `moana.core`, sin dependencias de otros módulos Moana, NumPy ni Pillow; los adaptadores del lienzo son submódulos aparte (abajo). Decisiones en [ADR-010](decisions/ADR-010-core-contracts.md).

| Tipo | Contrato |
| --- | --- |
| `Point(x, y)` | Inmutable; `x`/`y` son `int` reales (se rechazan `bool`, float, str y escalares NumPy) con `abs ≤ 1 048 576`. Se indexa como `array[y, x]`. |
| `Dimensions(width, height)` | Cada eje en 1–2048, área ≤ 4 194 304; `Dimensions.default()` es 128 × 128. `check_pixel(point)` lanza `OutOfBoundsError` fuera del lienzo, sin wraparound de índices negativos. |
| `Box(x0, y0, x1, y1)` | Semiabierta `[x0,x1) × [y0,y1)`, nunca vacía (`x0 < x1`, `y0 < y1`). `x0`/`y0` en `±1 048 576`; `x1`/`y1` hasta `1 048 577`. Una caja 1 × 1 contiene exactamente un píxel (`Box.from_point`, válido para todo píxel). Puede quedar fuera del lienzo. |
| `Box.intersection` / `Box.clip_to` | Devuelven la caja común o **`None`** si no queda ningún píxel (incluidas cajas que sólo se tocan en un borde). Nunca se construye una caja vacía o invertida para representar «nada». |
| `MAX_LAYERS`, `MAX_OPERATIONS`, `MAX_VERTICES`, `MAX_COLORS_STRICT`, `MAX_COLORS_RGBA` | Límites de cardinalidad del documento (§20), compartidos por `schema`, `palette` y `render` (ADR-011). |
| `GeometryLimits` / `DEFAULT_GEOMETRY_LIMITS` | Máximos geométricos del contrato §5 (eje, área, coordenada), separados de su aplicación (`check_dimensions`, `check_point`, `check_box`). Sólo pueden bajar; el documento no los define. Los presupuestos elevables de §20 son `RenderLimits`, que compone este tipo. |
| `RenderLimits` / `DEFAULT_RENDER_LIMITS` | Presupuestos por solicitud de §20 (bytes de buffers con temporales, visitas de píxel, píxeles de frames, operaciones, capas) y `geometry`. Se bajan libremente; elevar un presupuesto exige `host_override=True` del anfitrión; conteos y geometría nunca superan el contrato. ADR-012. |
| `Deadline` | Comprobación cooperativa entre unidades de trabajo (`checkpoint`), `BudgetExceeded` con recurso `time`; no influye en el resultado ni interrumpe código nativo. |
| `require_int` | Validación compartida de enteros con rango; `minimum > maximum` es error de programación (`ValueError`). |
| `moana.core.ids` | Dueño único de los lenguajes léxicos: `ID_REGEX`/`ID_PATTERN` (`[a-z][a-z0-9_-]{0,63}`) y `RGBA_HEX_REGEX`/`RGBA_HEX_PATTERN` (`#RRGGBBAA`); `is_id`, `is_rgba_hex` y `check_id` aceptan sólo `str` exacto con `fullmatch`. `schema` publica estos patrones. ADR-014. |
| `MAX_RAMP_ENTRIES` | Total de miembros de rampa de una paleta (20 000); acota paletas construidas fuera del lector del esquema. |
| `MAX_GROUP_DEPTH` | Anidamiento máximo de grupos en el árbol de capas (16, §11); lo aplica `layers` y lo aplicará `schema` cuando admita grupos. |
| `errors.detail_sort_key` | Orden canónico de `ErrorDetail` (pointer con índices numéricos, código, mensaje), compartido por `schema` y `palette`. |

Errores (`moana.core.errors`): `MoanaError` (código `INTERNAL_ERROR`, salida 1) y subclases con `code` estable y `exit_code`: `ValidationError` (`VALIDATION_ERROR`, 2), `OutOfBoundsError` (`OUT_OF_BOUNDS`, 2, subclase de validación), `ReferenceError` (`REFERENCE_ERROR`, 2; distinto del builtin homónimo, importar como `errors.ReferenceError`), `UnsupportedVersion` (2), `UnsupportedOperation` (2), `BudgetExceeded` (3), `EditConflict` (4), `ExportError` (5) y `ReadError` (`READ_ERROR`, 5; ADR-020). Atributos de sólo lectura `message`, `json_pointer` (opcional, RFC 6901) y `context`. `context` es inmutable y sólo admite escalares o tuplas: nombres de campo, motivos, tipos y límites numéricos; nunca strings de entrada no confiable ni rutas. Los errores son picklables.

Lienzo (MOANA-004, [ADR-013](decisions/ADR-013-canvas-buffer.md)): adaptadores explícitos que `moana.core` no importa, para que `schema` y el plan de coste no carguen bibliotecas gráficas.

| Tipo | Contrato |
| --- | --- |
| `moana.core.canvas.Canvas` | Propietario exclusivo de un buffer `uint8` C-contiguo `(height, width, 4)`, RGBA recto, alfa cero normalizado a `(0,0,0,0)`. `blank(dimensions, *, limits)` y `from_array(array, *, limits)` (límites obligatorios) validan tipo, dtype, forma y presupuesto antes de copiar o reservar. `get_pixel`/`set_pixel` con `Point` lanzan `OutOfBoundsError` fuera del lienzo, sin wraparound. `to_array()` (copia escribible), `to_bytes()`, `copy()`, `visual_digest()` (§14). Mutable y sin hash; igualdad por tamaño y bytes; construcción directa cerrada y `copy.copy`/`deepcopy` copian el buffer. No llega a la fachada: `RenderResult` guarda bytes inmutables (ADR-013). |
| `moana.core.canvas.check_canvas_budget` | Geometría del anfitrión y `4 × A` bytes contra `RenderLimits`; `BudgetExceeded` con los mismos recursos que `plan_budget`. |
| `moana.core.pillow_adapter` | `canvas_to_pillow(canvas)` crea una imagen `RGBA` nueva; `canvas_from_pillow(image, *, limits)` acepta sólo `RGBA` de un frame ya abierto, sin conversión implícita, y copia; una imagen cerrada o truncada da `ValidationError` (`unreadable_image`). |
| `moana.core.digest.visual_digest(width, height, rgba)` | Digest visual de §14 (`sha256:` sobre ancho y alto `uint32` big-endian + RGBA), sólo biblioteca estándar; única implementación, usada por `Canvas` y `RenderResult` (ADR-018). |
| `moana.core.procedural` | `cell_unit`/`cell_choice` y `RNG_VERSION`: aleatoriedad por celda de §14, sin estado (ADR-018). |

Integración con `schema` (MOANA-002): los errores de `core` no derivan de `ValueError`, así que Pydantic no los convierte en errores de campo. `schema` valida los enteros primitivos con las constantes de `core` (`Field(ge=..., le=...)`) y expone `Point`/`Box`/`Dimensions` como propiedades de los modelos. Un error con varios problemas lleva `details: tuple[ErrorDetail, ...]` (`code`, `json_pointer`, `message`, `context`), añadido de forma compatible por ADR-011.

## `render` — orquestador (MOANA-010)

`moana.render.render(document, *, frame_id=None, limits=None, deadline=None) -> RenderResult` ejecuta validación (revalida el árbol canónico) → frame (sólo `None` en schema 1.0; otro es `ReferenceError` con `field: frame_id`) → rasterizador registrado (`RENDERABLE_OPERATION_TYPES`, si no `UnsupportedOperation`) → paleta resuelta → `plan_budget` → `LayerTree` de máscaras diferidas → `compose`. No escribe ni lee disco, no modifica el documento y no usa caché, concurrencia, reloj ni `hash()`. Decisiones en [ADR-018](decisions/ADR-018-render-pipeline.md).

| Elemento | Contrato |
| --- | --- |
| `RenderResult` | Congelado: `width`, `height`, `rgba` (`bytes` filas de arriba abajo), `digest` (§14, recalculado al construir), `warnings` (`RenderWarning(code, message, json_pointer)`; `empty_bounds` por operación cuya caja recortada está vacía), `renderer_version` y `provenance`. `pixel(x, y)` lanza `OutOfBoundsError` fuera. Sin objetos NumPy. |
| `Provenance` | Manifiesto de reproducción: ID, revisión y `snapshot_digest` del documento, schema, semilla, perfil, frame, `renderer_version` (`render-v1`), `renderer_backend` (`integer`), `estimator_version`, `rng_version`, `moana_version`; `to_mapping()` con claves ordenadas. Sin rutas, tiempos, lock ni plataforma. |
| `moana.render.budget.mask_box(operation, dimensions)` | Caja de almacenamiento de la máscara recortada (la misma que devuelve `geometry`), usada por el plan y por las máscaras diferidas. |

## `render` — plan de coste (MOANA-003, `budget-v2` en MOANA-010)

`moana.render.estimate_cost(document, *, frames)` calcula con aritmética entera, sin reservar ni recorrer píxeles, las visitas, bytes, píxeles de frames y conteos según las fórmulas de [ADR-012](decisions/ADR-012-request-budgets.md), con las visitas por operación de `budget-v2` ([ADR-018](decisions/ADR-018-render-pipeline.md): rasterizado más una pasada de pintado sobre la caja de la máscara). `plan_budget(document, limits, *, frames, deadline)` lanza `BudgetExceeded` antes de cualquier buffer, con un detalle por recurso (`resource`, `limit`, `estimated`); una solicitud en el límite se admite. `frames` (≤256) cuenta renders idénticos; una animación suma un plan por frame evaluado. `plan_budget` es la única puerta para los límites del anfitrión: el orquestador (MOANA-010) sólo crea lienzos tras `plan_budget` y les pasa los límites de la solicitud; el lienzo repite su parte (`4A`, geometría) con el mismo `BudgetExceeded` como defensa en profundidad (ADR-013). Rasterizadores y compositor trabajan por filas o tiles dentro de estas cotas, con prueba `tracemalloc`, o actualizan el estimador.

## `export` — PNG (MOANA-011)

`moana.export.export_png(frame, path, *, scale=1, overwrite=False, mode="rgba", palette=None, limits=DEFAULT_RENDER_LIMITS) -> ExportManifest` recibe cualquier `RasterFrame` (`width`, `height`, `rgba: bytes`; `RenderResult` lo cumple sin que `export` importe `render`), codifica en memoria, verifica la ida y vuelta y hace el commit atómico. Sólo depende de `core`, `palette`, NumPy, Pillow y la biblioteca estándar. Decisiones en [ADR-019](decisions/ADR-019-png-export.md).

| Elemento | Contrato |
| --- | --- |
| `encode_png` | Sin disco. `mode="rgba"` (maestro) o `"indexed"` con una `Palette` de ≤256 entradas en orden declarado, `tRNS` explícito y sin cuantización (`color_not_in_palette`). `scale` entero 1..64 nearest; `export_dimension`, `export_area` y `buffer_bytes` (24 B/px de salida) se comprueban antes de reservar. `compress_level=9`, sin chunks volátiles. Si la decodificación no coincide, `ExportError` `roundtrip_mismatch`; en indexado, `PLTE`/`tRNS` deben coincidir byte a byte (`palette_mismatch`). |
| `moana.export.atomic.commit_bytes` | Temporal hermano `O_EXCL` + `fsync`; `overwrite=False` con `os.link` (nunca reemplaza; sin enlaces duros, `no_replace_unavailable`), `overwrite=True` con `os.replace`. Ante fallo el destino conserva su contenido; `ExportError` con `reason`, nombre de archivo y `errno`, sin ruta completa. Un nombre con NUL o no codificable es `ValidationError` `invalid_name`. No crea directorios. |
| `ExportManifest` | `path`, `media_type`, `mode`, `width`, `height`, `frames`, `scale`, `master` (`scale == 1`), dimensiones de origen, `source_digest`, `pixel_digest`, `file_sha256`, `byte_size`, `warnings` (`scaled_preview`); `to_mapping()` ordenado. |

## `api` / `cli` (implementados en MOANA-012)

Fachada `moana.api` y comando `moana`: sólo componen `schema`, `render` y `export`, sin algoritmos propios. `cli` importa sólo `moana.api`, `moana.core.errors` y `moana.__version__`; ningún módulo de dominio importa `api` ni `cli`. Decisiones en [ADR-020](decisions/ADR-020-public-api-cli.md).

| Elemento | Contrato |
| --- | --- |
| `load_document(source, *, limits)` | Path autorizado por el llamador (`str`/`PathLike`), bytes o mapping → `Document` congelado. Un `str` con aspecto de JSON es `ValidationError` (`json_text`); vacío, con NUL o no codificable, `invalid_name`. Archivo regular abierto sin bloquear y lectura acotada a `max_bytes + 1`. Un fallo es `ReadError` (`not_found`, `is_directory`, `not_a_file`, `permission_denied`, `io_error`; `file_name` ≤255 y `errno`, sin ruta). |
| `render(document, *, frame_id, limits, deadline)` | Delega en `moana.render.render`; no escribe archivos. |
| `export_png(result, path, *, scale, overwrite, limits)` | PNG RGBA atómico vía `moana.export.export_png`; exige un `RenderResult`. El modo indexado sigue en `moana.export`. |
| `inspect_document(document, *, limits)` / `capabilities()` | Informes congelados con `to_mapping()`. El exceso de presupuesto se informa (`within_limits`, `exceeded`), no se lanza. Lo previsto (`PLANNED_FUNCTIONS = ("apply_edit",)`, operaciones sin rasterizador, modos futuros) va separado de lo disponible. |
| CLI `moana` | `validate`, `inspect`, `render`, `export [--scale] [--overwrite]` y `capabilities`; `edit` previsto → `UNSUPPORTED_OPERATION` (2). Un único objeto JSON por invocación; códigos = `exit_code` del error (0/2/3/4/5/1), stdout cerrado → 5, interrupción → 130 con `INTERRUPTED`; uso inválido → `VALIDATION_ERROR` (`usage`) con mensaje fijo; sin abreviaturas; sin traceback salvo `--debug`. Sólo abre los paths de sus argumentos. |

## `ci` / `tests.integration` — determinismo entre plataformas (MOANA-029)

Corpus fijo de seis casos en `tests/fixtures/determinism/` (diagonales con empate de orden, alfa, grupos aislados, transparencias, clipping con línea no diagonal y un empate exacto de `round_half_up`) con un manifiesto RGBA revisado que sale de un oráculo independiente del renderer (máscaras a mano y fórmula escalar de §11), nunca de un render. `scripts/determinism.py`:

| Subcomando | Contrato |
| --- | --- |
| `probe` | En un proceso nuevo: render, PNG RGBA en memoria, `export_png` a archivo y, en casos strict, PNG indexado; decodifica cada PNG exigiendo su modo (`RGBA`/`P`). |
| `report` | 4 `PYTHONHASHSEED` × 3 serializaciones; compara todo contra el manifiesto, registra entorno, lock y codec, y escribe expected/actual/diff al divergir. Si una sonda falla, igualmente escribe un informe `error` con la ejecución y el final de stderr. |
| `compare` | Sólo biblioteca estándar. Exige exactamente los informes esperados, sin duplicados de (sistema, Python) y con todos los sistemas pedidos; una divergencia de píxeles falla; bytes PNG distintos con el mismo codec son aviso y entre codecs distintos sólo se informan. Nunca reescribe el manifiesto. |

CI: el job `verify` ejecuta `report` y sube `artifacts/determinism/` en `diagnostics-<os>-<py>`; el job `determinism` (`needs: verify`, sólo lectura) compara los 9 informes con `--expected-platforms Darwin,Linux,Windows`. Entre plataformas se garantizan los píxeles decodificados (digest §14); los bytes PNG, sólo con el mismo codec. La matriz sólo corre en `main` (ADR-021).

## `palette` (implementado en MOANA-005)

API pública en `moana.palette`; depende sólo de `core` y no carga NumPy, Pillow ni Pydantic. Decisiones en [ADR-014](decisions/ADR-014-palette.md).

| Tipo | Contrato |
| --- | --- |
| `Rgba` | Canales `int` 0–255; `parse` sólo acepta `#RRGGBBAA` (cualquier caja) y `hex` lo devuelve en mayúsculas; `normalized()` convierte alfa 0 en `(0,0,0,0)`; `luminance` es Y lineal entera (`2126·lin[R] + 7152·lin[G] + 722·lin[B]`, tabla literal `SRGB_TO_LINEAR` × 65 535). |
| `Palette` | Valor inmutable y hashable con `id`, `profile` (`strict`/`rgba`), `colors` y `ramps`. Valida las mismas reglas que `schema` para una paleta aislada, con los mismos códigos, motivos, orden y contexto `issue_count`, y pointers relativos (`/colors/0/rgba`). `index_of`/`color`/`ramp` por ID (`ReferenceError` si falta); `ids_with_value` compara valores normalizados. `replace_color` y `duplicate_color` devuelven paletas nuevas sin renumerar. `to_mapping`/`from_mapping` usan la forma de la sección `palette` del documento normalizado; `from_mapping` acepta sólo `dict`/`list`/`str` exactos y acota longitudes antes de recorrer. |
| `PaletteWarning` | Advertencias no bloqueantes de `luminance_warnings()`: `RAMP_LUMINANCE_NOT_INCREASING` (`decreasing`, `equal`, `duplicate_value`), `RAMP_TRANSPARENT_STEP` y `RAMP_PARTIAL_ALPHA_STEP`, con pointer, `ramp_id` e IDs de color. |
| `ColorRemap` | Sustitución explícita de un paso entre IDs de la misma paleta; no encadena ni introduce colores; detalles sin pointer (`side`, `position`). |

`editing` no importa `palette` (§3): `replace_palette_color` validará con los modelos de `schema`. La conversión `schema.Palette → palette.Palette` vivirá en `render`.

## `geometry` (implementado en MOANA-006 y MOANA-008)

API pública en `moana.geometry`; depende sólo de `core` y usa NumPy internamente sin exponer arrays compartidos. `import moana.geometry` no carga Pillow ni Pydantic. Decisiones en [ADR-015](decisions/ADR-015-raster-primitives.md) y [ADR-016](decisions/ADR-016-pixel-transforms.md).

| Elemento | Contrato |
| --- | --- |
| `Mask` | Valor inmutable sin constructor público: `box` (caja de la operación recortada al lienzo, o `None`), `count`, `is_empty`, `bounds` (caja mínima), `contains(point)`, `points()` (fila a fila) y `to_array()` (copia booleana de `box`). La igualdad y el hash comparan el conjunto de píxeles: `box` y la forma de `to_array()` no forman parte de la identidad. El hash usa `hash(bytes)`, que varía por proceso, y nunca ordena ni siembra el render. `copy`/`deepcopy` devuelven el mismo objeto y `pickle` valida el estado y reconstruye los bits como sólo lectura. `Mask.empty()` es la geometría recortada por completo. |
| `rasterize_pixel`, `rasterize_line`, `rasterize_rect`, `rasterize_ellipse`, `rasterize_polygon` | Reciben `Point`/`Box`/secuencia de `Point` y `Dimensions`. Aplican las reglas de §6 con enteros de Python: Bresenham ordenado e inclusivo, caja semiabierta, inclusión del centro en la elipse (intervalo exacto por fila con `isqrt`) y even-odd por centros con umbrales enteros. Recortan sin wraparound ni error. La memoria es 1 byte por píxel de la caja recortada (el término de máscara del estimador) más temporales por fila. Un polígono exige de 3 a 4096 vértices (`ValidationError`). |
| `flood_fill(snapshot, seed, *, limits)` | Conectividad 4 e igualdad RGBA exacta sobre una copia del `Canvas` recibido, que no se modifica. Antes de copiar comprueba `flood_fill_cost` (`A` visitas, `FLOOD_FILL_BYTES_PER_PIXEL × A` bytes) y, si no cabe, lanza `BudgetExceeded`. Es un scanline iterativo, sin recursión. Una semilla fuera del lienzo da una máscara vacía: es una decisión de recorte, distinta del acceso directo de §5, que se ratificará en MOANA.md cuando el schema active `flood_fill` (en la siguiente versión del estimador; `8A`). No está activo en schema 1.0. |
| `Transform`, `transform_mask(mask, transform, dimensions)`, `transform_box(box, transform)` | Valor congelado `pivot`/`mirror`/`rotation`/`scale`/`offset` sobre índices de píxel. Orden fijo: espejo `x → −x`, cuartos de vuelta horarios `(x, y) → (−y, x)`, escala entera `k` (cada índice pasa a un bloque `k × k`) y traslación. El píxel `p` va a `k·R·(p − pivot) + pivot + offset`. Rotación fuera de {0, 90, 180, 270}, escala no entera o fuera de 1..2048 y `mirror` no booleano lanzan `ValidationError` (`arbitrary_rotation`, `out_of_range`, `not_integer`, `not_boolean`). Las máscaras se recortan al lienzo sin wraparound mediante recolección inversa (memoria: caja de salida recortada + copia del origen). Las cajas se transforman como conjuntos de píxeles. Una imagen sin píxeles visibles es `Mask.empty()`. `inverse()` sólo existe sin escala y con `pivot + offset` en rango (`not_invertible`). La igualdad es estructural. |

Aplicar una máscara a un lienzo corresponde al compositor de `layers` (MOANA-009, abajo).

## `layers` (implementado en MOANA-009)

API pública en `moana.layers`; depende de `core`, `palette` y `geometry` y usa NumPy internamente. `import moana.layers` no carga Pillow ni Pydantic. Decisiones en [ADR-017](decisions/ADR-017-layers-composition.md).

| Elemento | Contrato |
| --- | --- |
| `Fill`, `Layer`, `Group` | Valores congelados. `Fill(mask, color)` pinta una `Mask` o una `DeferredMask(box, build)` (construida al pintar, una a la vez; salirse de `box` es `RuntimeError` del llamador; ADR-018) con un `Rgba` (alfa 0 no borra). `Layer` y `Group` validan ID, nombre (UTF-8 válido, ≤4096 bytes), `visible`/`locked` booleanos, opacidad 0..255, `blend` sólo `normal`, ≤10 000 fills o ≤128 hijos. `locked` no altera el render. |
| `LayerTree(dimensions, children, profile)` | Árbol de abajo arriba validado de una vez. Rechaza IDs repetidos (`duplicate_id`), más de 16 grupos anidados (`too_deep`), más de 128 capas y grupos, máscaras fuera del lienzo (`outside_canvas`) y, en `strict`, opacidad distinta de 255 (`partial_opacity`) o fills con alfa parcial (`partial_alpha`). Los errores llevan `node_id`/`fill` y se informa del primero en orden. `walk()` recorre en profundidad, de abajo arriba. |
| `composition_cost(tree)` / `compose(tree, *, limits, deadline)` | Coste puro (visitas, bytes, capas, operaciones, profundidad) comprobado contra `RenderLimits`, incluidos los límites de geometría, antes de reservar; si no cabe, `BudgetExceeded`. Deadline antes de cada nodo y cada fill. Composición source-over entera literal de §11 por bloques de `min(4096, A // 4)` píxeles: fills en orden sobre un buffer de capa transparente, capa con su opacidad, grupos en buffer aislado con la opacidad aplicada una vez, alfa 0 normalizado. Devuelve un `Canvas` nuevo. |

## `schema` (implementado en MOANA-002)

API pública en `moana.schema`; depende sólo de `core` y Pydantic. Decisiones en [ADR-011](decisions/ADR-011-schema-v1.md).

| Elemento | Contrato |
| --- | --- |
| `validate_document(source, *, limits)` | `bytes` UTF-8 o `Mapping` → `Document` congelado. Fases: lectura acotada (`ParseLimits`: 8 MiB, profundidad 32, 20 000 nodos, sólo reducibles) → versión (`UnsupportedVersion`) → estructura y capacidades (`ValidationError` / `UnsupportedOperation`) → semántica (`ValidationError` / `ReferenceError`). Cada error lista sus problemas en `details`, ordenados por pointer (índices numéricos) y código. No acepta `str`. |
| `Document` y modelos | Pydantic `strict`, `extra='forbid'`, `frozen`, secuencias como tuplas, unión discriminada por `type` (`pixel`, `line`, `rect`, `ellipse`, `polygon`). Construir el modelo directamente sólo garantiza estructura; unicidad de IDs, referencias de color y perfil `strict` sólo los garantiza `validate_document`. |
| Capacidades | `SUPPORTED_*` y `PLANNED_*` en `moana.schema.capabilities`; lo previsto responde `UNSUPPORTED_OPERATION`, nunca se ignora. |
| `normalize_document` / `canonical_json` / `snapshot_digest` | Normalización de §14: defaults materializados, opcionales omitidos (`null` explícito rechazado; metadata vacía equivale a ausente), claves ordenadas, JSON compacto UTF-8; digest `sha256:<hex>`. |
| `document_json_schema()` | JSON Schema 2020-12 generado desde los modelos; copia revisada en `schemas/moana-document-1.0.schema.json` (`scripts/generate_schema.py --check`). |

La tabla de imports permitidos de MOANA.md §3 impide dependencias ascendentes. Si dos módulos necesitan la misma representación, se extrae un contrato mínimo a `core` cuando el caso real lo requiera; no se resuelve un ciclo con imports tardíos o un contenedor global.

## Cruces que requieren validación

1. **Bytes → modelo:** limitar bytes/profundidad, rechazar claves duplicadas y tipos inesperados. Validar estructura antes de ejecutar código nativo.
2. **Modelo → plan:** comprobar unicidad de IDs, referencias, capacidades implementadas y aciclicidad. Una operación reconocida pero no disponible falla explícitamente.
3. **Plan → buffers:** estimar memoria total, temporales y trabajo. El clipping no elimina el coste previo de segmentos largos ni autoriza reservas enormes.
4. **Buffers → resultado:** fijar forma/dtype, normalizar transparencia y eliminar aliases mutables. El consumidor no puede alterar el resultado de una llamada anterior.
5. **Resultado → archivo:** verificar opciones representables, presupuesto del export y política de sobrescritura antes del commit del archivo.

Los errores de librerías se traducen en la frontera que conoce su significado, conservando la causa para diagnóstico interno. Un `BudgetExceeded` no se presenta como entrada válida con imagen parcial. Los resultados de fallo no reutilizan buffers parcialmente escritos como si fueran completos.

## Edición, referencias y dependencias visuales

La identidad de una operación no depende de su posición en un array. `set_color` cambia una referencia; modificar el valor de un color de paleta afecta a todos sus consumidores. Borrar un nodo referenciado se rechaza. Una modificación puede invalidar una sombra o contorno dependiente: el manifiesto debe distinguir el objetivo solicitado de los consumidores afectados.

Las máscaras forman un DAG independiente de los píxeles de una capa. No se permite definir una máscara mediante el render de la propia capa. Los grupos componen hijos en un buffer aislado antes de aplicar su opacidad. Esas decisiones impiden dependencias circulares y hacen que una región siga siendo identificable aunque cambie su apariencia.

Los batches se validan completos antes de producir una revisión. Historial, revisión numérica e identidad de snapshot deben seguir el contrato de MOANA.md §15; un implementador no debe añadir reglas diferentes de conflicto dentro del CLI. El formato persistente conserva esa identidad y la procedencia de migraciones.

## API, formatos y extensiones

La fachada (`moana.api`, MOANA-012) devuelve tipos documentados y estables. Objetos de Pillow, arrays escribibles y handlers de archivos abiertos quedan internos. Aceptar `Path` en una API de aplicación no autoriza incluir rutas arbitrarias en instrucciones JSON. La configuración de límites viene del anfitrión, no de un documento no confiable.

Cada operación nueva añade modelo, capability, resolución, estimación de coste, rasterizador, fixtures y documentación. El schema MVP implementa el vocabulario soportado por su issue; mencionar una futura técnica en la especificación no implica que sus parámetros o backend ya se acepten. Las ampliaciones se versionan junto con sus modelos, y se rechazan versiones no soportadas.

Exportadores adicionales declaran capacidad real del codec. GIF necesita política de paleta/alfa/duración; PNG RGBA conserva el maestro. El manifiesto del atlas permite reconstruir frames. El proyecto editable conserva documento y assets verificados; las imágenes de preview son derivadas.

## Evidencia exigida en cada frontera

| Frontera | Evidencia mínima |
| --- | --- |
| Schema / referencias | Entrada mínima válida, extra/duplicado/tipo inválido y referencia rota |
| Recursos / buffer | Caso en el límite y rechazo previo a reservar; aliasing impedido |
| Raster / composición | Fixture de píxeles independiente, borde/clipping y alfa extremo |
| Edición / historial | Batch fallido sin mutación, conflicto, undo/redo exacto y rama de historial |
| Proyecto / export | Roundtrip semántico, destino preservado ante fallo y rutas confinadas |
| Determinismo / caché | Repetición en procesos, semillas de hash distintas y equivalencia caché on/off |

Los [estándares de arquitectura](../standards/architecture.md) fijan cuándo crear un ADR; los [estándares de testing](../standards/testing.md) detallan los oráculos y diagnósticos.
