# MOANA — Especificación técnica

Versión del contrato: **0.1.7-draft** · Fecha: **2026-11-17** · Estado: especificación inicial para implementación; motor todavía no implementado.

Este archivo es la fuente de verdad del producto. «DEBE» expresa una condición verificable; «DEBERÍA», una recomendación artística o de diseño. Los contratos aquí descritos son objetivos futuros, no APIs disponibles en el paquete inicial. Los cambios de contrato requieren actualizar este documento, los ejemplos, los issues y una decisión de arquitectura cuando afecten compatibilidad. El catálogo de requisitos y su trazabilidad vive en `docs/requirements.json` y `docs/issues/traceability.md`.

## 1. Visión y objetivos

Moana será una biblioteca Python de dibujo programático de Pixel Art: un agente describe una escena estructurada, Python la valida y rasteriza, y el usuario puede pedir «cambia el color de la capa», «mueve el ojo izquierdo» o «suaviza esa silueta» sin reconstruir el resto del sprite mediante un modelo de generación de imágenes. El tamaño de referencia es 128 × 128; la resolución no determina por sí sola el estilo.

**Pillow y NumPy proporcionan las herramientas gráficas, pero no garantizan por sí mismos una calidad artística profesional.** La calidad dependerá de las instrucciones, los algoritmos, las técnicas de Pixel Art y los sistemas de evaluación implementados. Ningún puntaje automático sustituye la revisión visual del usuario o artista.

Objetivos: precisión de píxel, siluetas legibles, clusters intencionales, paletas coherentes, edición local explicable, capas recuperables, animaciones consistentes y resultados reproducibles. El agente debe poder mostrar el PNG resultante a escala nativa y ampliado mediante vecino más cercano, conservar el documento fuente y aplicar una revisión específica con un diff identificable.

## 2. Alcance funcional y no funcional

El producto cubre personajes, criaturas, objetos, tiles, escenarios y animaciones 2D. La primera entrega funcional cubrirá documentos estáticos con primitivas, paletas, capas, render RGBA y exportación PNG. Las entregas siguientes agregan máscaras, técnicas artísticas, edición persistente y animación. Una integración con IA consume el mismo contrato público que un programa Python; el núcleo no necesita un proveedor de IA ni acceso de red.

Fuera del alcance inicial: GUI de pintura, modelos generativos visuales, rasterización 3D, fotorealismo, fuentes del sistema, plugins ejecutables dentro de documentos, descarga automática de recursos, PSD/Aseprite de ida y vuelta y interpolación de movimiento aprendida. No se implementará el motor en la inicialización del repositorio.

Requisitos no funcionales: Python >=3.12; instalación como paquete; operaciones sin estado global mutable; entrada no confiable validada antes de reservar buffers; errores tipados; resultados verificables; documentación en español e identificadores de código en inglés. Se comprueba inicialmente Python 3.12–3.14 en CI; las versiones posteriores permitidas por metadata requieren ampliar esa matriz para declarar soporte verificado.

## 3. Arquitectura modular

Flujo obligatorio: `entrada → validación sintáctica → resolución de referencias → presupuesto → plan de render → máscaras/primitivas → composición → evaluación → exportación`. La edición transforma el documento validado y vuelve a entrar por esa misma ruta.

| Módulo futuro | Responsabilidad | Dependencias internas permitidas |
| --- | --- | --- |
| `core` | coordenadas, límites, errores, buffers y contratos | ninguna |
| `schema` | modelos Pydantic, discriminadores y JSON Schema | core |
| `palette` | colores, ramps, remapeos e índices | core |
| `geometry` | máscaras de primitivas y transformaciones | core |
| `layers` | árbol ordenado, máscaras y composición | core, palette, geometry |
| `techniques` | contornos, clusters, dithering y materiales | core, geometry, palette |
| `render` | resolución, plan, caché y ejecución determinista | core, schema, palette, geometry, layers, techniques |
| `editing` | comandos transaccionales e historial | core, schema |
| `project` | lectura/escritura, assets, migraciones | core, schema, editing |
| `animation` | timeline y evaluación de frames | core, schema, editing, render |
| `export` | PNG/GIF/WebP/APNG/spritesheets y manifiestos | core, palette; recibe resultados, no llama al editor |
| `quality` | métricas, incidencias y visualizaciones de diagnóstico | core, palette |
| `api` / `cli` | fachada y composición de servicios | módulos anteriores |

El orquestador combina render y quality; el rasterizador no depende del CLI, del almacenamiento ni del evaluador. Pillow, NumPy y AggDraw quedan detrás de adaptadores internos. Los contratos de dominio no exponen objetos mutables de esas bibliotecas. No se crean módulos vacíos simulando funcionalidad: se incorporan al comenzar su issue. La distribución inicial sólo expone versión y metadata.

## 4. Stack tecnológico

Python 3.12+ es el lenguaje; Pillow provee buffers/intercambio y codificadores; NumPy, arrays y operaciones vectorizadas; AggDraw, un adaptador de trazados complementarios; Pydantic v2, validación estricta y generación de esquema. `uv` gestiona intérprete, entorno y lock real. Hatchling construye wheel/sdist. pytest y coverage verifican comportamiento; Hypothesis aporta propiedades; Ruff verifica estilo y formato; mypy aplica tipado estricto. PyYAML sólo forma parte del tooling de desarrollo para verificar skills y manifiestos.

`pyproject.toml` declara rangos compatibles y `uv.lock` fija las resoluciones concretas con hashes. CI sincroniza con `uv sync --locked`; las actualizaciones de dependencias generan cambios revisables del lock y regresiones. No se declara reproducibilidad de bytes entre versiones arbitrarias de codificadores. AggDraw puede carecer de stubs: su excepción de mypy se limita al import, y su adaptador tendrá superficie tipada y pruebas propias.

## 5. Motor de lienzo y píxeles

El origen es la esquina superior izquierda; x crece a la derecha y y hacia abajo. Un píxel se indexa `(x, y)` y se almacena `array[y, x, channel]`. El array canónico es C-contiguo, `uint8`, forma `(height, width, 4)`, RGBA recto (no premultiplicado). Color de trabajo sRGB codificado; la composición normativa usa esos valores enteros, sin conversión implícita a luz lineal. El color de todo píxel con alfa cero se normaliza a `(0,0,0,0)`.

Dimensiones válidas: 1–2048 por eje, con límite adicional de área de 4 194 304 píxeles. Predeterminado 128 × 128. Las coordenadas son enteros reales del JSON (no booleanos, strings ni floats); rango absoluto <=1 048 576. Una caja es `[x0,y0,x1,y1)`; exige x0<x1 e y0<y1. El rango absoluto se aplica a coordenadas de píxel; el borde excluido de una caja puede llegar a 1 048 577 para que todo píxel válido tenga caja 1 × 1. Una intersección o recorte sin píxeles es ausencia de caja, no una caja vacía (ADR-010). La geometría puede quedar fuera del lienzo: se recorta sin wraparound ni error, después de presupuestar su complejidad. Acceso directo a un píxel fuera del lienzo produce error de límites; no hereda índices negativos de NumPy.

Las vistas públicas son inmutables o copias; el propietario del buffer controla la vida útil. El lienzo y sus adaptadores NumPy/Pillow son submódulos de `core` que su paquete no importa; sólo intercambian copias e imágenes `RGBA` de un frame, sin convertir modos implícitamente (ADR-013). Se usan acumuladores uint32/int64 antes de multiplicar para evitar overflow. Escalado de preview sólo por factores enteros >=1 mediante vecino más cercano; el archivo de trabajo conserva la resolución original.

## 6. Geometría y primitivas

Cada operación tiene `id`, `type` discriminador y parámetros explícitos. La primera familia incluye `pixel`, `line`, `rect`, `ellipse`, `polygon`; luego `path`, `flood_fill` y transformaciones. Las primitivas generan máscaras binarias, no colores intermedios por antialias automático.

| Operación | Parámetros específicos | Regla raster |
| --- | --- | --- |
| pixel | `at: [x,y]`, `color` | exactamente un píxel |
| line | `start`, `end`, `color` | Bresenham entero inclusivo en ambos extremos |
| rect | `box`, `color` | caja semiabierta, rellena |
| ellipse | `box`, `color` | inclusión del centro del píxel en elipse |
| polygon | `points` (>=3), `color` | even-odd, centros de píxeles, sin AA |
| path | `commands`, `color`, `backend` | trazado cerrado por adaptador, contrato de backend |
| flood_fill | `at`, `color`, `connectivity: 4` | igualdad RGBA exacta sobre copia del estado anterior de la capa |

Para `line`, ordenar lexicográficamente los extremos antes del Bresenham simétrico: dx=abs(x1-x0), dy=-abs(y1-y0), err=dx+dy; calcular e2=2*err antes de cada paso; avanzar x si e2>=dy y avanzar y si e2<=dx. Esto fija empates y la simetría al invertir extremos. Grosor inicial: 1 píxel; los trazos gruesos se derivan de dilatación explícita, no de opciones variables de Pillow.

Para `ellipse`, w=x1-x0, h=y1-y0, A=2*x+1-x0-x1 y B=2*y+1-y0-y1; incluir si A²*h²+B²*w²<=w²*h². Usar enteros Python para esta evaluación o demostrar que el tipo elegido no desborda. Para `polygon`, descartar aristas horizontales en el cálculo de cruces; activar cada arista en `min(y0,y1)<=py<max(y0,y1)`, py=y+1/2; incluir un centro cuando el número de intersecciones estrictamente a su derecha sea impar. Las comparaciones se hacen con racionales/enteros. Se permiten autointersecciones bajo even-odd; vértices repetidos consecutivos se normalizan y una máscara es vacía sólo cuando no contiene centros de píxel en el interior even-odd. No se descarta un polígono por área algebraica (shoelace) cero: una figura autointersectada tipo bow-tie puede tener relleno válido aunque sus áreas firmadas se cancelen.

`path` acepta M/L/Q/C/Z en coordenadas de punto fijo 1/256, sin SVG, fuentes ni recursos externos. El adaptador AggDraw genera cobertura a escala nativa, umbral >=128, y normaliza a 0/255. Se etiqueta `aggdraw-v1`: reproducibilidad sólo con versiones/plataformas ensayadas; no se presenta como equivalente al backend entero. No es necesario para completar el MVP. Flood fill utiliza cola iterativa acotada, nunca recursión Python.

Transformaciones pixel-perfect: traslación entera, espejo y rotaciones 0/90/180/270 alrededor del origen del grupo seguidas de traslación explícita. En coordenadas de índice, el giro horario de un punto respecto al origen es `(-y,x)`. Las cajas se transforman como conjuntos de píxeles, no redondeando esquinas geométricas. Escala entera de nearest-neighbor; rotación arbitraria queda fuera del perfil estricto.

## 7. Técnicas profesionales de Pixel Art

El flujo artístico comienza con brief (lectura, pose, focal point, material, luz, tamaño), thumbnail/silueta, clusters grandes, rampas, volúmenes, detalles y limpieza. La resolución objetivo manda la cantidad de detalle. Mantener familias de pendientes coherentes, transiciones deliberadas y espacio negativo legible; no aplicar blur, suavizado de imagen ni ruido genérico como «mejora».

Los presets artísticos son parámetros versionados y editables, no promesas de calidad. Su evaluación muestra imagen a 1× y 4×, paleta, silueta, mapa de clusters y alertas. El antialias manual interior puede usar colores de la rampa en píxeles elegidos explícitamente; nunca introduce cobertura fraccional oculta. Las excepciones de estilo (dientes, brillos aislados, píxeles sueltos) deben poder justificarse y silenciarse por región.

## 8. Siluetas, contornos y pixel clusters

Silueta = máscara de alfa>0 del resultado o región elegida. Componentes 4-conectados son el análisis predeterminado; 8-conectividad es una opción explícita para diagonales. Contorno exterior de ancho n: `dilate(mask,n)-mask`; interior: `mask-erode(mask,n)`, con vecindad Chebyshev 3×3 y repeticiones enteras. Las máscaras se calculan en coordenadas de lienzo, con exterior transparente. Selective outlining escoge colores desde una rampa y una máscara de luz declarada, conservando IDs de la operación.

Cluster = componente conectado de píxeles del mismo color (o del mismo índice de rampa si se solicita). El informe detecta componentes de 1 píxel, discontinuidades de borde y cambios abruptos de escalones en pendientes; esos hallazgos son advertencias artísticas, no fallos universales. La limpieza propone una operación editable; nunca borra automáticamente ojos o partículas. Las pruebas usan fixtures con diagonales, huecos, contactos de esquina y contornos pegados al límite.

## 9. Paletas, color e iluminación

Una paleta tiene ID estable, colores con IDs únicos y valores `#RRGGBBAA` en mayúsculas. `#RRGGBB` no es formato canónico. Las operaciones referencian IDs de color, no copias del valor. Las rampas son listas ordenadas de IDs de sombra a luz; la luminancia creciente es una recomendación verificable, con excepción documentable para rampas estilizadas. La luminancia verificable es Y lineal entera: `2126·lin[R] + 7152·lin[G] + 722·lin[B]` con la tabla sRGB→lineal de 256 enteros escalada a 65 535 (ADR-014); un paso que no crece, un paso transparente o uno semitransparente produce advertencia, nunca rechazo. Cambiar un color modifica todos sus consumidores; duplicarlo permite una edición local independiente.

Perfil `strict`: alfa de colores {0,255}, capas con opacidad 255 y composición normal; el resultado usa sólo colores de la paleta más transparente. Perfil `rgba`: admite alfa 0–255 y composición, puede generar colores adicionales y lo declara en el reporte. No se cuantiza implícitamente. La exportación indexada rechaza exceso de colores salvo que el usuario pida un remapeo explícito y reciba su informe de error.

Luz artística: dirección discreta de ocho orientaciones o frontal, altura discreta 0–3, intensidad en pasos de rampa y luz ambiental en pasos. Las regiones/materiales referencian esa configuración. No se calculan normales 3D inexistentes: la profundidad/normal o las bandas de sombreado deben ser suministradas por máscaras o mapas validados. La política de hue shift pertenece a una rampa authored, evitando inventar colores mediante multiplicaciones RGB.

## 10. Sombreado, dithering y materiales

Sombreado base: selección de índice de rampa mediante bandas de máscara con prioridades explícitas; en solapamientos gana la última banda listada. Clamp al rango de la rampa. Cada banda conserva ID y máscara editables. Pillow shading y luz contradictoria se señalan como revisiones humanas, sin clasificadores pretendidamente infalibles.

Dithering ordenado inicial: Bayer 2×2 `[[0,2],[3,1]]` o 4×4 `[[0,8,2,10],[12,4,14,6],[3,11,1,9],[15,7,13,5]]`. Parámetro entero `coverage` entre 0 y N²; escoger color B si threshold<coverage, A en caso contrario. Origen de patrón explícito `(ox,oy)` en lienzo; usar módulo matemático también en coordenadas negativas. Recortar por máscara antes de escribir. No cambiar fase entre tiles o frames salvo instrucción del autor.

Materiales iniciales: piel, tela, metal, madera y piedra, definidos por rampa, bandas, densidad, escala y patrón; no por shaders arbitrarios. Textura aleatoria usa coordenadas y semilla según §14, nunca el RNG global. Cada preset incluye ejemplos propios, licencia/procedencia, rango de parámetros y pruebas de bordes, paleta, reproducibilidad y estabilidad temporal. Ruido y dithering se aplican a regiones elegidas; no a toda la imagen por defecto.

## 11. Capas, máscaras y regiones

`layers` es una lista ordenada de abajo arriba. Una capa tiene ID global, nombre descriptivo, visible, locked, opacity, blend, opcional mask_id y operaciones ordenadas. Los grupos son nodos con lista de hijos, transform y opacidad; profundidad máxima 16. `locked` impide comandos de edición normales y no altera render. Grupos se componen en buffer aislado; la opacidad se aplica una vez al resultado del grupo.

Las máscaras son nodos con ID, geometría binaria y combinaciones union/intersect/subtract/xor; no pueden depender del render de una capa. Las referencias forman un DAG: se rechazan ciclos y referencias inexistentes antes de ejecutar. Región = ID semántico, mask_id y lista opcional de IDs de operaciones; permite «ojo izquierdo» sin inferir coordenadas desde el PNG. Los IDs no dependen del orden de arrays.

Composición normal source-over sobre RGBA recto. Tras aplicar máscara y opacidad, `sa=round_half_up(alpha*opacity/255)`. Sea `D=sa*255+da*(255-sa)`: alfa final `round_half_up(D/255)`; canal final, si D>0, `round_half_up((sc*sa*255+dc*da*(255-sa))/D)`; si D=0, todo cero. `round_half_up(n/d)=(2*n+d)//(2*d)` para enteros no negativos. El resultado se normaliza por alfa cero. Primera versión sólo blend `normal`; multiply/screen serían extensión con contrato y fixtures propios.

## 12. Especificaciones JSON para agentes de IA

Documento UTF-8, objeto raíz, sin claves duplicadas, comentarios, NaN/Infinity ni coerciones. Los modelos Pydantic futuros usan `strict=True`, `extra='forbid'` y unions discriminadas. Validación de sintaxis se separa de referencias, capacidades y costes. Errores incluyen `code`, `json_pointer`, `message`, `context` sin datos sensibles; ordenados por pointer y código. Un documento puede ser estructuralmente válido y referirse a una capacidad aún no implementada: responder `UNSUPPORTED_OPERATION`, nunca ignorarla.

Campos raíz de v1: `schema_version` ("1.0"), `id`, `revision` (entero >=0), `seed` (0..2^64-1), `canvas`, `palette`, `layers`; opcionales `masks`, `regions`, `materials`, `animations`, `metadata`. Defaults materializados en normalización: seed=0, revision=0, canvas.profile="strict", capas visible=true, locked=false, opacity=255, blend="normal", arrays opcionales vacíos. `metadata` sólo admite title, description, author, tags y provenance; strings <=4096 bytes, tags <=32. IDs `[a-z][a-z0-9_-]{0,63}`, únicos en todo el documento incluyendo colores, operaciones y frames. Los nombres humanos no sirven como claves.

Ejemplo mínimo normativo del primer hito (diseño, no ejecución disponible):

```json
{
  "schema_version": "1.0",
  "id": "sprite_demo",
  "revision": 0,
  "seed": 42,
  "canvas": {"width": 128, "height": 128, "profile": "strict"},
  "palette": {
    "id": "palette_main",
    "colors": [
      {"id": "ink", "rgba": "#182338FF"},
      {"id": "cloth", "rgba": "#36AFA5FF"}
    ],
    "ramps": []
  },
  "layers": [
    {
      "id": "body",
      "name": "Cuerpo",
      "visible": true,
      "locked": false,
      "opacity": 255,
      "blend": "normal",
      "operations": [
        {"id": "body_fill", "type": "rect", "box": [40, 32, 88, 104], "color": "cloth"}
      ]
    }
  ]
}
```

El JSON Schema se genera desde Pydantic (`moana.schema`, MOANA-002) y se versiona en `schemas/moana-document-1.0.schema.json`; no se mantiene un segundo validador de producto a mano. `examples/specs/minimal.moana.json` se valida con el modelo real. Precisiones de 1.0 (ADR-011): `revision` en 0..2^64-1; los miembros opcionales se omiten y `null` explícito se rechaza; `metadata` vacía equivale a ausente; rampa = `{id, colors}` con 2–4096 IDs de color distintos; el ID del documento y el de la paleta entran en la unicidad global; `name` de capa ≤4096 bytes; perfil `strict` exige alfa 00/FF, opacidad 255 y ≤256 colores. Un error que agrupa varios problemas los lista en `details`. La gramática de schema 1.0 corresponde al MVP implementado por MOANA-002: primitivas estáticas, paleta y capas simples; las colecciones de capacidades futuras sólo se aceptan vacías hasta definir sus modelos. Grupos, máscaras, materiales, paths y animaciones requieren ampliar explícitamente el schema y documentar payloads junto al issue correspondiente, sin anunciar una gramática ejecutable que aún no existe. La extensión futura de operaciones exige registrar modelo, resolución, coste, raster, pruebas y documentación; no se admiten imports dinámicos desde JSON.

## 13. API pública de Python

Fachada objetivo para v0.1; aún no implementada:

```python
from moana.api import load_document, render, export_png, apply_edit

document = load_document("hero.moana.json")
result = render(document, frame_id=None, limits=None)
export_png(result, "hero.png", scale=1)
edited = apply_edit(
    document,
    {
        "schema_version": "1.0",
        "base_revision": document.revision,
        "base_snapshot": document.snapshot_digest,
        "commands": [{"type": "set_color", "target_id": "body_fill", "color": "ink"}],
    },
)
```

`load_document(path|bytes|mapping) -> Document` valida y normaliza; paths sólo desde la capa de confianza de la API, no desde operaciones JSON. `render(Document, *, frame_id: str|None, limits: RenderLimits|None) -> RenderResult` no escribe archivos ni modifica el documento; ya existe como `moana.render.render` (MOANA-010, ADR-018), que acepta además `deadline: Deadline|None` cooperativo, mientras la fachada `moana.api` sigue siendo futura. `RenderResult` contiene width, height, RGBA inmutable, digest, warnings, renderer_version y provenance. `apply_edit(Document, EditBatch|mapping) -> Document` devuelve una revisión nueva. `export_png(RenderResult, path, *, scale=1, overwrite=False) -> ExportManifest` realiza escritura atómica; ya existe como `moana.export.export_png` (MOANA-011, ADR-019), que acepta además `mode` (`rgba`/`indexed`), `palette` y `limits`.

Errores públicos (`moana.core.errors`, implementados en MOANA-001): `MoanaError` y subclases `ValidationError` (con `OutOfBoundsError` para acceso a píxel fuera del lienzo), `ReferenceError`, `BudgetExceeded`, `UnsupportedVersion`, `UnsupportedOperation`, `EditConflict`, `ExportError`. Cada clase declara `code` estable y el código de salida de la CLI; los códigos están en ADR-010. No se exponen tracebacks internos en el CLI por defecto. CLI objetivo: `moana validate`, `render`, `edit`, `inspect`, `export`; códigos 0 éxito, 2 entrada inválida, 3 presupuesto, 4 conflicto, 5 I/O, 1 fallo interno. La inicialización no registra un comando que prometa renderizar.

## 14. Renderizado y determinismo

Mismo documento normalizado + versión de renderer + lock + parámetros produce los mismos bytes RGBA. El perfil entero debe producir igualdad RGBA entre OS soportados y distintas semillas de hash de Python. Orden de capas/operaciones viene de arrays; no se usa orden de sets, concurrencia, locale, reloj ni hash() como semilla. Los paths de archivos y timestamps no forman parte de la identidad visual.

Normalización canónica: materializar defaults, ordenar claves de objetos, preservar arrays, JSON UTF-8 sin espacios, ensure_ascii=false, sin floats. Color canónico mayúsculo. Digest visual = SHA-256 de width y height como uint32 big-endian concatenados con RGBA row-major. Digest del documento incluye toda la representación canónica; la clave de caché agrega versión de renderer, backend, lock digest y frame. La revisión cambia el documento aunque la imagen no cambie.

Aleatoriedad procedural por celda: SHA-256 de la codificación JSON canónica del array `[seed, operation_id, x, y, channel, algorithm_version]`; obtener u como primeros 8 bytes big-endian; mapear a rango n con `u*n//2^64`. No es criptografía del producto; es una secuencia determinista cuyo algoritmo se versiona. Añadir una operación no cambia la textura de otra. Frame sólo entra en la semilla cuando el efecto declara variación temporal.

Cachés son optimización: activadas/desactivadas deben dar igualdad exacta. No hay procesamiento paralelo hasta demostrar orden y memoria acotados. PNG/GIF pueden diferir en bytes comprimidos entre versiones; la garantía base compara píxeles decodificados y metadata semántica. Igualdad byte a byte de un export sólo se garantiza en un entorno de codec fijado, sin metadata volátil.

## 15. Edición no destructiva

El documento es el artefacto editable primario; el PNG es derivado. Un batch contiene `schema_version`, `base_revision`, `base_snapshot` y comandos tipados. `base_snapshot` es `sha256:` seguido del digest hexadecimal del documento normalizado de origen (§14), expuesto por la futura propiedad `Document.snapshot_digest`; no se serializa esa propiedad dentro del propio documento. Se verifican ambas precondiciones para distinguir ramas con el mismo número de revisión. Catálogo inicial: `set_color(target_id,color)`, `set_geometry(target_id,geometry)`, `translate(target_id,dx,dy)`, `set_visibility(target_id,visible)`, `replace_palette_color(target_id,rgba)`, `insert_operation(layer_id,after_id|null,operation)`, `remove(target_id)`, `reorder(target_id,after_id|null)`. `after_id=null` inserta al principio del contenedor. Sólo se reordena dentro del mismo contenedor; traslado entre capas será comando explícito posterior.

Una revisión o un digest de snapshot que no coincide con el documento actual produce EditConflict. Validar todos los comandos y la escena resultante antes de aceptar; un fallo revierte todo. No se admiten cambios directos de id, schema_version ni revision. Rechazar borrado con referencias vivas, edición de capa bloqueada y comandos ambiguos. Batch exitoso incrementa revision exactamente en 1, incluso si el resultado visual no cambia. Se preservan IDs existentes, bytes fuente de assets y orden de nodos no afectados.

Historial: snapshots inmutables identificados por digest, con batch canónico, digest del padre y revisión numérica local a la rama; undo/redo selecciona estados existentes, mientras un nuevo edit sobre estado anterior crea rama lógica y descarta sólo el cursor redo activo, no los archivos guardados. Un cambio local puede modificar sombra/contorno dependiente; el manifiesto indica IDs afectados y bbox de diferencia, evitando prometer que ninguna dependencia cambia. Se informa el diff antes/después y se conserva el archivo anterior al guardar con sobreescritura explícita.

## 16. Formato de proyectos

Formato base `.moana.json` autocontenido para geometría. Proyecto con assets: directorio con `project.moana.json`, `assets/`, `history/` opcional y `previews/` derivado. `project.moana.json` es un sobre ProjectManifest separado de Document: `{kind: "moana-project", project_version: "1.0", document: Document, assets: [AssetRef], history: []}`. `history` es opcional y vacío por defecto; el resto de campos es obligatorio. El lector distingue el sobre por `kind` y aplica su modelo propio con extra=forbid; no agrega `assets` como campo desconocido de Document. Cada AssetRef declara id, path POSIX relativa, mime, byte_length y sha256; los IDs de assets son únicos en el sobre y no colisionan con IDs del documento. Únicos assets iniciales: PNG RGBA decodificado; no Python, pickle, fuentes, SVG externo ni URL. `save_project` escribe a temporal hermano, fsync cuando sea viable y reemplaza atómicamente; los assets se verifican antes del commit del manifiesto. Assets y snapshots se guardan bajo rutas inmutables derivadas del hash; actualizar el proyecto nunca reemplaza sus bytes antes del commit del nuevo manifiesto. Los assets sobrantes tras un fallo son huérfanos recuperables, no corrupción del proyecto previo; su recolección es una acción explícita posterior.

Contenedor `.moana` ZIP opcional usa esas mismas rutas; se inspecciona antes de extracción: no rutas absolutas, `..`, symlinks, duplicados, nombres normalizados en colisión ni ratios de expansión excesivos. Máximo 256 entradas, 64 MiB comprimidos, 256 MiB descomprimidos, ratio 100:1 por entrada y total. Prohibir resolver enlaces fuera de la raíz. Los perfiles en memoria conservan límites aunque no se use ZIP.

Separar schema_version de versión del paquete y renderer. Minor de schema sólo añade campos con defaults compatibles; el lector estricto soporta versiones explícitas, no «tolera» versiones nuevas. Migraciones son funciones puras probadas por fixture, preservan copia original y registran versión de origen; no migrar destructivamente al abrir. Guardar/cargar debe preservar semántica, IDs y resultado.

## 17. Animaciones y spritesheets

Animación tiene ID, frames ordenados, loop_count (0 infinito), canvas y paleta compartidos. Un frame tiene ID, duration_ms entero 1–60 000 y una lista de overrides tipados sobre IDs base; cada frame se evalúa sobre el documento base, nunca sobre el resultado del anterior. Los overrides no contienen base_revision ni cambian la revisión persistente. MVP de animación: visibilidad, geometría y color; sin tween implícito. Un pivote entero común evita jitter; los desplazamientos artísticos son explícitos. Máximo 256 frames y 16 777 216 píxeles de frame acumulados por export.

Spritesheet inicial: grid uniforme en orden de frames, columnas declaradas, padding>=0, margin>=0; cada frame mantiene canvas sin trim por defecto. Manifest JSON versionado incluye frame_id, rect `[x,y,w,h]`, duration_ms, pivot, source_size, trim_offset y digest. Packing compacto será opcional con tie-break por frame_id y nunca rotará sprites implícitamente. Exportar spritesheet y recortar según manifest reconstruye exactamente cada frame.

Se revisan siluetas, volumen, paleta, contacto con suelo y fase de dithering a lo largo de la secuencia. Un onion skin es sólo preview, no altera salida. Tests cubren loop, frame único, overrides inválidos, duraciones máximas, overflow de sheet y reconstrucción de atlas.

## 18. Exportación PNG, GIF y formatos adicionales

PNG RGBA es formato maestro: transparente normalizado, escala entera opcional, compresión fijada y metadata de procedencia separada o estable. PNG indexado usa orden declarado de paleta y transparencia explícita, <=256 entradas; sin cuantización silenciosa. PNG conserva píxeles al decodificarse.

GIF admite paleta compartida <=256, alfa binario y transparencia reservada; si hay alfa intermedio exigir background de aplanado o rechazar. Duración debe ser múltiplo de 10 ms; por defecto rechazar pérdidas, con modo de redondeo explícito que devuelve duraciones efectivas. Exportar frames completos con disposal configurado, comprobar composición decodificada y preservación de tiempo; duplicados que el encoder fusione se verifican por timeline equivalente. Reservar el índice transparente reduce a 255 colores opacos.

WebP lossless y APNG son entregas posteriores, condicionadas a capacidad real del build de Pillow y pruebas roundtrip. Si un encoder no existe, UnsupportedOperation; no fallback oculto. Atlas PNG+JSON es el intercambio adicional prioritario. La creación de archivos es atómica y por defecto no sobrescribe. `overwrite=False` requiere un commit sin reemplazo atómico en el filesystem de destino; un exists() seguido de replace() no es suficiente por la carrera entre procesos. Si esa garantía no está disponible, fallar explícitamente; con overwrite=True puede usarse reemplazo atómico de temporal hermano. Cada export devuelve path, media_type, dimensiones, frames, hashes y advertencias. No se confunde un preview escalado con el sprite maestro.

## 19. Control de calidad gráfico

Hard checks: dimensiones correctas, alfa normalizado, paleta estricta, referencias válidas, ausencia de píxeles fuera de máscara y reproducibilidad. Soft checks: clusters aislados, bordes accidentados, contraste entre partes, lectura de silueta, exceso de colores, ruido, coherencia de luz y estabilidad temporal. No convertir heurísticas artísticas en rechazos silenciosos.

Cada incidencia contiene rule_id, severity, bbox, region_id opcional, explicación y evidencia; orden estable por regla, región, y,x. Parámetros y supresiones por región quedan en configuración de evaluación, no modifican la imagen. Métricas numéricas: colores distintos, área opaca, componentes, proporción de singletons, bbox, diferencia por frame y porcentaje de píxeles cambiados.

Rúbrica humana: legibilidad a 1×, silueta, clusters, paleta, luz/material y continuidad temporal; escala 1–5 con justificación. Objetivo para ejemplos de referencia: >=4 por categoría relevante y ningún hard check fallido, evaluado por una persona y documentado; no se atribuye una aprobación humana a un agente. El primer corpus incluye personaje, criatura, objeto, tile y ciclo animado, con fuente editable y derechos claros.

## 20. Seguridad y validación

Documentos son datos, nunca código: prohibidos eval/exec, pickle, import dinámico, shell, acceso de red y paths libres en operaciones. Parsing JSON limita bytes antes de cargar (8 MiB), profundidad (32), número total de nodos (20 000), operaciones (10 000), capas/grupos (128), vértices por operación (4096) y colores (256 strict; 4096 rgba). Validar dimensiones y productos antes de crear arrays. Fallar en la fase de presupuesto, no después de una asignación enorme.

Presupuesto por solicitud predeterminado: 256 MiB de buffers estimados incluyendo temporales/cache, 100 000 000 visitas estimadas de píxel y 16 777 216 píxeles acumulados de frames. Coste de operación = bbox recortada × pasadas, salvo líneas/paths, cuyo coste incluye segmentos/pasos antes del clipping; flood fill <=área, morfología incluye vecindad y radio. El límite de op count no sustituye el límite de trabajo. El estimador implementado (`budget-v2`, ADR-012 y ADR-018: visitas = raster + una pasada de pintado sobre la caja recortada) suma también limpieza, composición y copia de cada frame, el acumulador de composición y la mayor máscara temporal; elevar un presupuesto exige `RenderLimits(host_override=True)`. API puede bajar límites; elevarlos requiere configuración explícita de la aplicación anfitriona, nunca el documento no confiable. Deadline cooperativo entre operaciones es defensa adicional; un servicio expuesto usa proceso aislado y límites del SO para detener una llamada nativa larga.

Imports Pillow verifican dimensiones, límites de descompresión, modo/frames y perfil antes de decode completo; no desactivar globalmente sus protecciones. Assets sólo bajo raíz resuelta y con digest coincidente. Los errores no filtran rutas sensibles. El threat model incluye agotamiento de memoria/CPU, zip slip/bombs, referencias cíclicas, contenido desconocido y comandos de edición inválidos. Secretos y credenciales no se guardan en documentos ni repositorio.

## 21. Testing y regresiones visuales

Pirámide: unit tests de reglas exactas; propiedades de inmutabilidad, límites e idempotencia de normalización; integración documento→render→export→decode; seguridad con entradas hostiles; corpus visual y revisión artística. Fixtures pequeñas permiten verificar píxeles manualmente, no copiar la salida de la implementación como oráculo.

Golden maestro compara RGBA y dimensiones exactamente. Fallo genera expected/actual/diff PNG, bbox, conteo, digest y manifest de entorno. Un render estándar no tiene tolerancia perceptual; SSIM y métricas perceptuales sólo complementan revisión de cambios deliberados. Actualizar baseline requiere fuente del cambio, diferencia visible y aprobación del responsable de revisión; no ejecutar actualización automática en CI ni esconder regresiones aceptando todo.

Determinismo: procesos nuevos, PYTHONHASHSEED diferente, caché on/off y matriz macOS/Linux/Windows con Python soportado. Integración comprueba instalación de wheel fuera de `src`, recursos incluidos y paquete tipado. Markers previstos `visual`, `slow`, `security`, `benchmark`; ausencia inicial de goldens no se presenta como QA del motor. Inicialización valida sólo tooling, dependencias y planificación.

## 22. Rendimiento y optimización

Objetivos iniciales a medir, no resultados actuales: sprite 128×128 con 32 capas/500 rects en <=100 ms mediana de render caliente; 16 frames de igual complejidad <=2 s; pico de memoria del proceso <=256 MiB para ese corpus. Máquina de referencia se registra con CPU, OS, Python, lock y commit. Medir 5 warmups y 30 muestras con mediana/p95, sin I/O en el tramo de render. Presupuesto obligatorio de seguridad sigue vigente aunque el objetivo de latencia no se alcance.

Medir antes de vectorizar. Recortar máscaras a bbox, reutilizar buffers internos sin alias público, renderizar frames en streaming, caché LRU limitada por bytes y invalidación por digest de dependencias. Evitar arrays de tamaño lienzo por cada operación cuando no se necesiten. No añadir GPU, multiprocessing ni JIT sin benchmark que justifique complejidad y demuestre determinismo. CI de PR detecta cambios funcionales; benchmarks son informativos hasta estabilizar runner y umbrales relativos (regresión >20% investigada con repetición controlada).

## 23. Roadmap por fases

| Fase | Resultado de salida | Puerta de salida |
| --- | --- | --- |
| P0 — inicialización | especificación, paquete mínimo, skills, CI, backlog | validación de infraestructura verde |
| P1 — contratos/core | modelos, límites, paleta, canvas, geometría entera | fixtures exactas y entradas inválidas |
| P2 — imagen estática | capas, compositor, render, PNG y fachada | documento de 128×128 reproducible en CI |
| P3 — arte y edición | máscaras, regiones, contornos, ramps, materiales, batches e historial | modificación local sin pérdida de editabilidad |
| P4 — persistencia/animación | proyectos, migraciones, timeline, GIF y atlas | roundtrip, frames y tiempos correctos |
| P5 — evaluación/release | corpus, diagnóstico, seguridad, rendimiento y documentación | DoD y release candidate validado |

`docs/issues/roadmap.md` fija issues y gates; `docs/issues/dependency-map.md` muestra el DAG derivado de `docs/issues/catalog.json`. P0 es el único alcance de esta ejecución. No hay fechas prometidas ni fases marcadas completas antes de disponer de evidencia. El siguiente módulo es MOANA-001: tipos, errores, límites y coordenadas; MOANA-002 implementa el contrato estructurado sobre esa base.

## 24. Criterios de aceptación

La trazabilidad debe asignar a cada requisito un issue, una prueba/evidencia y fase. MVP estático aceptable: instalar wheel limpio, validar JSON, render de primitivas con paleta/capas, igualdad determinista RGBA, exportar PNG que decodifique igual y rechazar entradas que excedan presupuesto. No afirmar calidad profesional por pasar tests de rasterización.

Producto completo aceptable: además, regiones semánticas y ediciones atómicas; guardar/cargar sin cambios de píxel; undo/redo; corpus artístico revisado; animaciones con tiempos y pivotes consistentes; atlas reversible; GIF con pérdidas explícitas; informes de QA accionables; límites de recursos probados; benchmarks publicados; CI de plataforma; guía de agentes y compatibilidad versionadas. Cada issue añade ejemplos observables específicos; ninguno se cierra con sólo «funciona».

Inicialización aceptable: MOANA.md cubre las 25 secciones; package importable sin engine; lock resuelto realmente; venv y herramientas instaladas; lint/typing/tests/build/checks verdes; siete skills validadas; instrucciones operativas; backlog completo sin ciclos ni requisitos huérfanos; integraciones y capacidades distinguen instalado, configurado y pendiente.

## 25. Definition of Done

Para cada módulo: alcance del issue cumplido, contrato público documentado, tipos completos, errores/presupuestos cubiertos, sin globales mutables, pruebas positivas y negativas significativas, determinismo comprobado, revisión de diffs/goldens cuando aplique, `uv run python scripts/validate.py` verde, docs/ejemplos/trazabilidad actualizados y limitaciones comunicadas. Dependencias nuevas tienen razón técnica y lock revisado.

Para release: todo lo anterior, wheel/sdist instalables, matriz de CI verde, corpus y rúbrica revisados, migración probada, threat model actualizado, presupuesto de rendimiento medido y changelog con versiones de schema/renderer. Publicación de paquetes, creación de repos remoto o envío de issues a terceros son pasos separados de esta preparación; no se inventa que ocurrieron. La licencia de distribución se decidirá con el propietario antes de publicar; los ejemplos creados deberán registrar procedencia.
