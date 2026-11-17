# Contratos entre módulos

Estado: **contratos previstos**, salvo `core` y `schema` (implementados, ver abajo). Las firmas públicas objetivo están en [MOANA.md §13](../../MOANA.md); sus fórmulas, límites y formatos prevalecen sobre este resumen. No se añaden abstracciones base ni registros de plugins por anticipación.

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

API pública en `moana.core`, sin dependencias de otros módulos Moana, NumPy ni Pillow. Decisiones en [ADR-010](decisions/ADR-010-core-contracts.md).

| Tipo | Contrato |
| --- | --- |
| `Point(x, y)` | Inmutable; `x`/`y` son `int` reales (se rechazan `bool`, float, str y escalares NumPy) con `abs ≤ 1 048 576`. Se indexa como `array[y, x]`. |
| `Dimensions(width, height)` | Cada eje en 1–2048, área ≤ 4 194 304; `Dimensions.default()` es 128 × 128. `check_pixel(point)` lanza `OutOfBoundsError` fuera del lienzo, sin wraparound de índices negativos. |
| `Box(x0, y0, x1, y1)` | Semiabierta `[x0,x1) × [y0,y1)`, nunca vacía (`x0 < x1`, `y0 < y1`). `x0`/`y0` en `±1 048 576`; `x1`/`y1` hasta `1 048 577`. Una caja 1 × 1 contiene exactamente un píxel (`Box.from_point`, válido para todo píxel). Puede quedar fuera del lienzo. |
| `Box.intersection` / `Box.clip_to` | Devuelven la caja común o **`None`** si no queda ningún píxel (incluidas cajas que sólo se tocan en un borde). Nunca se construye una caja vacía o invertida para representar «nada». |
| `MAX_LAYERS`, `MAX_OPERATIONS`, `MAX_VERTICES`, `MAX_COLORS_STRICT`, `MAX_COLORS_RGBA` | Límites de cardinalidad del documento (§20), compartidos por `schema`, `palette` y `render` (ADR-011). |
| `GeometryLimits` / `DEFAULT_GEOMETRY_LIMITS` | Máximos geométricos del contrato §5 (eje, área, coordenada), separados de su aplicación (`check_dimensions`, `check_point`, `check_box`). Sólo pueden bajar; el documento no los define. Los presupuestos elevables de §20 serán `RenderLimits` (MOANA-003), que compone este tipo. |
| `require_int` | Validación compartida de enteros con rango; `minimum > maximum` es error de programación (`ValueError`). |

Errores (`moana.core.errors`): `MoanaError` (código `INTERNAL_ERROR`, salida 1) y subclases con `code` estable y `exit_code`: `ValidationError` (`VALIDATION_ERROR`, 2), `OutOfBoundsError` (`OUT_OF_BOUNDS`, 2, subclase de validación), `ReferenceError` (`REFERENCE_ERROR`, 2; distinto del builtin homónimo, importar como `errors.ReferenceError`), `UnsupportedVersion` (2), `UnsupportedOperation` (2), `BudgetExceeded` (3), `EditConflict` (4), `ExportError` (5). Atributos de sólo lectura `message`, `json_pointer` (opcional, RFC 6901) y `context`. `context` es inmutable y sólo admite escalares o tuplas: nombres de campo, motivos, tipos y límites numéricos; nunca strings de entrada no confiable ni rutas. Los errores son picklables.

Integración con `schema` (MOANA-002): los errores de `core` no derivan de `ValueError`, así que Pydantic no los convierte en errores de campo. `schema` valida los enteros primitivos con las constantes de `core` (`Field(ge=..., le=...)`) y expone `Point`/`Box`/`Dimensions` como propiedades de los modelos. Un error con varios problemas lleva `details: tuple[ErrorDetail, ...]` (`code`, `json_pointer`, `message`, `context`), añadido de forma compatible por ADR-011.

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

La fachada futura devuelve tipos documentados y estables. Objetos de Pillow, arrays escribibles y handlers de archivos abiertos quedan internos. Aceptar `Path` en una API de aplicación no autoriza incluir rutas arbitrarias en instrucciones JSON. La configuración de límites viene del anfitrión, no de un documento no confiable.

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
