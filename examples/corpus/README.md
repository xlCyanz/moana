# Corpus artístico de MoanArt (MOANA-027)

Primer corpus de MOANART.md §19: cinco ejemplos propios, uno por categoría, con fuente editable, procedencia, previews e informe de calidad. El formato y las reglas están en [ADR-037](../../docs/architecture/decisions/ADR-037-art-corpus-rubric.md).

**Rúbrica: los cinco ejemplos están pendientes de revisión humana y ninguno es «profesional».** Las puntuaciones y notas marcadas como de agente, aquí y en los registros, son la opinión de un agente de IA: no cuentan como revisión humana ni como aprobación.

Notación: coordenadas `(x, y)` sobre la imagen a 1×, con origen arriba a la izquierda; cajas `[x0, y0, x1, y1)` semiabiertas.

## Ejemplos

| Ejemplo | Categoría | Lienzo | Colores (usados/declarados) | Técnicas | Hard checks | Advertencias | Rúbrica |
| --- | --- | --- | --- | --- | --- | --- | --- |
| [adventurer](adventurer/adventurer.moanart.json) | personaje | 24 × 32 | 17/17 | rectángulos por parte, contorno 4-conexo de tinta, sombras y luces manuales, 8 regiones | superados | ninguna | pendiente de revisión humana |
| [frog](frog/frog.moanart.json) | criatura | 32 × 27 | 9/9 | elipses, `shade` por bandas, `selective_outline`, pliegues y brillos manuales | superados | ninguna | pendiente de revisión humana |
| [chest](chest/chest.moanart.json) | objeto | 32 × 28 | 11/13 | material `wood` v1 (densidad 15), biseles por tabla, `shade` plano y por bandas, `selective_outline` | superados | ninguna | pendiente de revisión humana |
| [stone-tile](stone-tile/stone-tile.moanart.json) | tile | 16 × 16 | 5/5 | rectángulos; sillares partidos en el borde para repetir sin costura | superados | ninguna | pendiente de revisión humana |
| [adventurer-walk](adventurer-walk/adventurer-walk.moanart.json) | animación | 24 × 32, 6 frames | 17/17 | timeline `walk` con overrides `translate`, bucle infinito, 6 × 120 ms | superados (también en cada frame) | ninguna (sin `temporal_flicker`, tampoco en la costura del bucle) | pendiente de revisión humana |

El cofre declara 13 colores y usa 11: `wood_4` y `metal_0` son extremos de rampa que conservan los índices del sombreado (`ambient` y desplazamientos) y quedan disponibles para editar la luz.

Advertencias: el informe por defecto de `moanart.api.evaluate_quality` (reglas `quality-v1`) no da ninguna advertencia para estos ejemplos y no se usa ninguna supresión (`suppressions: []` en cada registro). Si una edición futura produce advertencias, se anotan por regla en `quality.warnings` del registro y en esta tabla; la prueba exige que coincidan con el informe real. Las reglas artísticas de `quality-v1` sólo analizan la imagen fija; para la animación, `tests/integration/test_art_corpus.py` comprueba además que ningún frame tenga singletons.

Tile: un tile único siempre se repite de forma visible en áreas grandes. Este rompe el periodo de 8 filas con un sillar corto en la tercera hilada y un musgo de 3 px, pero para suelos o muros extensos hacen falta variantes.

Contornos: la aventurera usa un anillo 4-conexo de rectángulos de tinta y la rana y el cofre usan `selective_outline`. La mezcla es deliberada. `outline` y `selective_outline` dilatan con vecindad Chebyshev (8 vecinos), y en los escalones de la cabeza, las manos y los pies de un sprite de 24 × 32 eso crea esquinas dobles de tinta. Sobre las elipses de la rana y el rectángulo redondeado del cofre ese defecto no aparece, y el contorno selectivo aporta el tramo claro del lado iluminado. La aventurera simula ese tramo con luces internas en los bordes izquierdos.

## Previews

Cada carpeta tiene `previews/` con PNG RGBA versionados, que `tests/visual/test_corpus_previews.py` compara píxel a píxel:

| Ejemplo | 1× | 4× | Silueta | Clusters |
| --- | --- | --- | --- | --- |
| adventurer | [1×](adventurer/previews/adventurer-1x.png) | [4×](adventurer/previews/adventurer-4x.png) | [silueta](adventurer/previews/adventurer-silhouette-4x.png) | [clusters](adventurer/previews/adventurer-clusters-4x.png) |
| frog | [1×](frog/previews/frog-1x.png) | [4×](frog/previews/frog-4x.png) | [silueta](frog/previews/frog-silhouette-4x.png) | [clusters](frog/previews/frog-clusters-4x.png) |
| chest | [1×](chest/previews/chest-1x.png) | [4×](chest/previews/chest-4x.png) | [silueta](chest/previews/chest-silhouette-4x.png) | [clusters](chest/previews/chest-clusters-4x.png) |
| stone-tile | [1×](stone-tile/previews/stone-tile-1x.png) | [4×](stone-tile/previews/stone-tile-4x.png) | [silueta](stone-tile/previews/stone-tile-silhouette-4x.png) | [clusters](stone-tile/previews/stone-tile-clusters-4x.png) |
| adventurer-walk | [tira 1×](adventurer-walk/previews/adventurer-walk-1x.png) | [tira 4×](adventurer-walk/previews/adventurer-walk-4x.png) | [silueta](adventurer-walk/previews/adventurer-walk-silhouette-4x.png) | [clusters](adventurer-walk/previews/adventurer-walk-clusters-4x.png) |

El tile añade [la repetición 3 × 3 a 4×](stone-tile/previews/stone-tile-tiled-3x3-4x.png). La silueta pinta en negro todo píxel con alfa > 0. La vista de clusters colorea cada cluster 8-conexo de igual color (sin repetir color entre vecinos cuando la tabla lo permite) y marca los singletons en magenta. La animación se muestra como una tira horizontal de frames en orden.

## Registro de cada ejemplo

`<slug>.corpus.json` (`moanart-corpus-entry/1`) contiene:

- `brief`: tema, tamaño, intención de paleta, luz y restricciones.
- `provenance`: autor, `authored_by: "ai_agent"`, método, fecha 2026-11-19, licencia, `third_party_assets: []`, semilla, `renderer_version`, `estimator_version` y `vector_backend`.
- `render`: digest y, en la animación, digests por frame.
- `quality`: informe por defecto (hard checks, advertencias por regla, digest del informe y supresiones).
- `agent_inspection`: dos pasadas de inspección a 1× y a 8× por vecino más cercano, marcadas como de agente.
- `rubric`.

Procedencia: cada ejemplo lo creó un agente de IA de programación, bajo la dirección del usuario del repositorio, mediante operaciones de MoanArt (formas, máscaras, regiones, paleta y técnicas del motor) escritas en el documento JSON. No se usó ningún modelo de imagen, no se calcó arte externo y no hay assets de terceros. El archivo `<slug>.moanart.json` es la única fuente: los scripts auxiliares que usó el agente para escribirlo no se versionan, y cualquier cambio se hace sobre el documento (a mano, con `moanart edit` o con `moanart.api.apply_edit`).

Licencia: **MIT** ([LICENSE](../../LICENSE)), decidida por el propietario del repositorio el 2026-11-20 para código, documentación, ejemplos y corpus; cada registro la declara en `provenance.licence`. La revisión artística humana sigue **PENDIENTE**: la licencia no aprueba el arte.

Cada fuente declara regiones semánticas para editar una parte sin tocar las demás; por ejemplo `hair`, `eyes`, `shirt` y `boots` en la aventurera; `skin`, `belly` y `eyes` en la rana; `wood`, `metal` y `lock` en el cofre; `bricks` y `moss` en el tile. La prueba de integración recolorea la camisa con un batch y comprueba que sólo cambian píxeles de la región `shirt`.

## Cómo registra una persona su revisión

1. Revisar cada categoría aplicable a 1× y ampliada (previews `1x` y `4x`, además de silueta y clusters): `legibility`, `silhouette`, `clusters`, `palette`, `light_material` y, sólo en la animación, `temporal_continuity`.
2. En `rubric` del registro, poner cada categoría como `{"status": "reviewed", "score": <1–5>, "justification": "<motivo>"}`. Una revisión humana puntúa todas las categorías aplicables.
3. Ejecutar `uv run python scripts/corpus.py facts` y copiar el `render_fingerprint` del ejemplo revisado.
4. Rellenar `"human_review": {"reviewer": "<nombre o usuario>", "reviewer_kind": "human", "date": "AAAA-MM-DD", "render_fingerprint": "sha256:…"}`. La valoración del agente (`agent_assessment`) puede quedarse o borrarse; nunca cuenta.
5. Poner `"professional": true` sólo si todas las puntuaciones son ≥ 4 y los hard checks pasan; en otro caso, `false`.
6. En `tests/integration/test_art_corpus.py`, ajustar en el mismo cambio la prueba `test_real_corpus_is_pending_until_reviewed`, que documenta el estado inicial (ningún ejemplo revisado ni profesional): quitar el ejemplo revisado de su comprobación. La prueba `test_real_records_satisfy_the_rubric_invariant` no se toca; exige la regla profesional en cualquier estado.
7. Validar con `uv run python scripts/corpus.py check` (sale con código 1 y explica el motivo, por ejemplo `not_professional` con `cause: low_score`) y con `uv run pytest tests/integration/test_art_corpus.py tests/visual/test_corpus_previews.py`.

## Cómo se cambia el arte de un ejemplo

1. Editar `<slug>.moanart.json` y revisar el resultado a 1× y ampliado.
2. Ejecutar `uv run python scripts/corpus.py facts` y copiar en el registro `render.digest`, `render.frame_digests` (animación), los campos de `quality` y las versiones de `provenance` que hayan cambiado.
3. Ejecutar `uv run pytest tests/integration/test_art_corpus.py`: `test_corpus_renders_to_its_pinned_digests` compara el render con los digests del registro, así que no hay digests duplicados en la prueba. Si se tocó la camisa de la aventurera, revisar también las cajas literales del oráculo de `test_localized_shirt_recolour_stays_inside_the_shirt_region`.
4. Regenerar las previews con el flujo local del harness: `MOANART_UPDATE_GOLDENS=1 uv run pytest tests/visual/test_corpus_previews.py -k <slug>` (falla a propósito; nunca en CI). Después, ejecutar la prueba otra vez sin la variable.
5. Revisar `artifacts/visual/corpus__<slug>__<vista>/` (expected, actual y diff) y mostrar expected/actual/diff en el PR.
6. Añadir una pasada a `agent_inspection.passes` si la hizo un agente.
7. Si el ejemplo tenía revisión humana, `scripts/corpus.py check` falla con «the art changed after the human review; review it again», porque su `render_fingerprint` ya no coincide. Una persona debe revisarlo de nuevo (pasos 1–7 de la sección anterior); no basta con copiar la huella nueva.

## Notas de inspección del agente (no son revisión humana)

Valoración orientativa de un agente de IA, de 1 a 5, recogida también en `agent_assessment` de cada registro. Entre paréntesis, la valoración anterior a la segunda pasada:

| Ejemplo | Legibilidad | Silueta | Clusters | Paleta | Luz/material | Continuidad | Observación principal |
| --- | --- | --- | --- | --- | --- | --- | --- |
| adventurer | 4 | 4 (3) | 4 | 4 | 3 | — | Piernas separadas, mandíbula y manos redondeadas; los brazos siguen siendo rectos y la mayoría de partes tiene un solo paso de sombra. |
| frog | 4 | 4 | 4 | 4 | 4 (3) | — | Media luna iluminada, brillos y pliegues dan volumen; el vientre sigue casi plano. |
| chest | 4 | 4 | 4 (3) | 4 | 4 | — | Vetas escasas y biseles por tabla; ya no compiten con las juntas. |
| stone-tile | 4 | 3 | 4 | 4 | 4 | — | Repite sin costuras; un tile único se repite de forma visible en áreas grandes. |
| adventurer-walk | 4 | 4 (3) | 4 | 4 | 3 | 3 | Seis frames con bajada y talón levantado; las rodillas no se flexionan y el movimiento sigue siendo rígido. |

Detalle de cada pasada en `agent_inspection.passes`:

- **Primera pasada.** La aventurera perdió dos píxeles dorados aislados en las botas y una sombra de barbilla que parecía barba. La rana ganó patas y dejó de tocar el borde con el vientre. El cofre recibió una sombra plana sobre la madera para quitar dos singletons de las vetas. En el tile se movieron dos desgastes que dejaban píxeles sueltos. En la caminata se cerró un hueco transparente entre cinturón y pantalón.
- **Segunda pasada** (tras la revisión de pixel art). Se separaron las piernas de la aventurera (tinta en `[11, 21, 13, 27)`), se estrechó la mandíbula y se redondearon las manos. La rana recibió pliegues simétricos, brillos en los abultamientos y una base de vientre (`belly_floor`). El cofre bajó la densidad de vetas a 15 y ganó biseles. El tile redujo el musgo a 3 px y partió la segunda hilada. La caminata pasó a 6 frames de 120 ms.

Algunas correcciones propuestas se adaptaron porque creaban singletons o duplicaban el contorno; cada registro explica la adaptación.
