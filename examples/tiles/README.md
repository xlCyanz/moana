# Tiles y escenarios modulares (MOANA-034)

Ejemplo editable de tiles repetibles y de una escena modular de 128 × 128 (`meadow`, un prado cruzado por un camino de tierra) compuesta por tiles y props con paleta compartida, origen de patrón común e IDs semánticos. Todo son documentos Moana 1.0 normales: no hay motor de mapas, nodo de instancia, física ni sistema de juego.

Notación: coordenadas `(x, y)` en píxeles a 1×, origen arriba a la izquierda; cajas `[x0, y0, x1, y1)` semiabiertas.

## Archivos

| Archivo | Qué es |
| --- | --- |
| [tiles/grass.moana.json](tiles/grass.moana.json), [tiles/grass-b.moana.json](tiles/grass-b.moana.json) | Dos tiles de hierba 16 × 16 con distinta disposición de manchas (dithering) y matas |
| [tiles/dirt.moana.json](tiles/dirt.moana.json), [tiles/dirt-b.moana.json](tiles/dirt-b.moana.json), [tiles/dirt-c.moana.json](tiles/dirt-c.moana.json) | Tres tiles de tierra: dos guijarros, uno, ninguno; surcos a distintas alturas |
| [tiles/grass-dirt-edge.moana.json](tiles/grass-dirt-edge.moana.json), [tiles/grass-dirt-edge-b.moana.json](tiles/grass-dirt-edge-b.moana.json) | Bordes norte del camino (hierba arriba) con dos perfiles interiores y labio oscuro `grass_0` |
| [tiles/grass-dirt-edge-s.moana.json](tiles/grass-dirt-edge-s.moana.json) | Borde sur (hierba abajo) con labio iluminado `grass_2` |
| [props/rock.moana.json](props/rock.moana.json), [props/bush.moana.json](props/bush.moana.json), [props/sign.moana.json](props/sign.moana.json) | Props 16 × 16 con fondo transparente, contorno de tinta y sombra de contacto al sureste |
| [meadow.layout.json](meadow.layout.json) | Composición: fuentes, variantes, rejilla, props, bordes, pivotes y `border_operations` |
| [meadow.moana.json](meadow.moana.json) | Escena derivada (68 capas, 807 operaciones, 637 máscaras, 75 regiones, 14 colores) |

Todas las fuentes se editan a mano, con `moana edit` o con `moana.api.apply_edit`. El generador es [`scripts/tiles.py`](../../scripts/tiles.py):

```sh
uv run python scripts/tiles.py check    # valida layouts y compara la escena versionada byte a byte
uv run python scripts/tiles.py build    # reescribe meadow.moana.json desde el layout y las fuentes
uv run python scripts/tiles.py preview  # escribe previews y atlas en artifacts/tiles/ (ignorado por Git)
```

Las fuentes (`tiles/`, `props/`) y el layout son la fuente de verdad; `meadow.moana.json` es un derivado versionado para que se pueda abrir, renderizar y editar sin el script. Si se cambia una fuente o el layout, se ejecuta `build`; `check` (y `tests/integration/test_tile_scene.py`) falla si la escena quedó desactualizada.

## Rejilla, origen de patrón y pivotes

- **Rejilla**: 8 × 8 celdas de 16 × 16; la celda `(fila r, columna c)` ocupa `[16c, 16r, 16c + 16, 16r + 16)`. Los tiles tienen pivote `(0, 0)` (esquina superior izquierda).
- **Origen de patrón común**: `(0, 0)` del lienzo (`pattern_origin`). Cada `dither` de una fuente usa `origin [0, 0]` y en la escena recibe el origen de patrón del layout: la textura pertenece al lienzo, no al tile (MOANA.md §10). Como el lado del tile (16) es múltiplo del periodo (2), dos tiles contiguos continúan el patrón sin cambio de fase. El generador rechaza un lado que no sea múltiplo del periodo (`period_mismatch`), un `origin` distinto de `[0, 0]` en la fuente (`dither_origin`) y una colocación cuyo origen no coincida con el de patrón módulo el periodo (`phase_mismatch`; por ejemplo, un `pattern_origin` impar con esta rejilla).
- **Pivote de los props**: `(8, 15)` en coordenadas de borde de píxel del frame de 16 × 16 (centro de la base; `y = 16` sería el borde bajo la última fila). En el layout, `at` es la posición del pivote en la escena; la esquina superior izquierda es `at − pivote`. Con espejo horizontal el pivote pasa a `(16 − px, py)` y con espejo vertical a `(px, 16 − py)`.
- **Props dentro del lienzo**: la caja completa de cada prop debe caber en la escena (`off_canvas` si no); así el recorte nunca se da y el atlas se reconstruye con un pegado sin recortes.

| Prop | `at` | Caja en la escena |
| --- | --- | --- |
| `prop_rock` | (104, 25) | `[96, 10, 112, 26)` |
| `prop_sign` | (43, 46) | `[35, 31, 51, 47)` |
| `prop_bush_west` | (18, 119) | `[10, 104, 26, 120)` |
| `prop_bush_east` | (108, 115) | `[100, 100, 116, 116)` |

Los props se colocaron donde no recortan las manchas de dithering del suelo: un recorte dejaba píxeles sueltos (advertencias `singleton`).

## Bordes y variantes

Cada tile declara el perfil de material de sus cuatro bordes, leído en coordenada creciente (de izquierda a derecha en `n`/`s`, de arriba abajo en `w`/`e`), con el material tomado del prefijo del ID de color (`grass_*`, `dirt_*`):

| Tile | n | e | s | w |
| --- | --- | --- | --- | --- |
| `grass`, `grass_b` | `grass*16` | `grass*16` | `grass*16` | `grass*16` |
| `dirt`, `dirt_b`, `dirt_c` | `dirt*16` | `dirt*16` | `dirt*16` | `dirt*16` |
| `edge_n`, `edge_nb` | `grass*16` | `grass*10+dirt*6` | `dirt*16` | `grass*10+dirt*6` |
| `edge_s` | `dirt*16` | `dirt*6+grass*10` | `grass*16` | `dirt*6+grass*10` |

En el interior la frontera varía: `edge_n` en tramos de 3, 5, 2 y 6 columnas, `edge_nb` en 2, 4, 4, 3 y 3 y `edge_s` en 4, 3, 5, 2 y 2, siempre en la fila 10 (6 en el sur) en las columnas 0 y 15.

Una variante es una fuente con `none`, `mirror_x` (espejo horizontal) o `mirror_y` (espejo vertical); el espejo intercambia los bordes opuestos e invierte el perfil de los otros dos. El generador exige que dos celdas vecinas presenten el mismo perfil (`edge_mismatch`), y la prueba comprueba los perfiles contra los píxeles renderizados.

| Variantes | Fuente | Transformación | Por qué se admite |
| --- | --- | --- | --- |
| `grass`, `grass_mx`, `grass_b`, `grass_b_mx` | hierba, hierba B | `none`, `mirror_x` | Las matas son simétricas en horizontal; el espejo sólo mueve las manchas |
| `dirt`, `dirt_b` | tierra, tierra B | `none` | Los guijarros tienen luz noroeste: un espejo la invertiría |
| `dirt_c`, `dirt_c_mx` | tierra C | `none`, `mirror_x` | Sin guijarros; surcos y manchas no tienen dirección de luz |
| `edge_n`, `edge_n_mx`, `edge_nb`, `edge_nb_mx` | bordes norte | `none`, `mirror_x` | La frontera llega a la fila 10 en ambos lados; el labio no depende de la izquierda o la derecha |
| `edge_s`, `edge_s_mx` | borde sur | `none`, `mirror_x` | Fuente propia: con luz desde arriba, el labio superior de la hierba se ilumina (`grass_2`), al revés que el labio oscuro del borde norte, por eso no es un `mirror_y` de `edge_n` |
| `rock`, `bush`, `sign` | props | `none` | Luz noroeste; no se reflejan |

Reglas que el generador hace cumplir:

- **Sólo se refleja lo que no tiene luz direccional**, y la textura con dithering nunca se refleja: conserva la fase del lienzo.
- **Un espejo es el espejo de los píxeles** (`mirror_asymmetry` si no): al cargar el layout, cada variante reflejada se renderiza con el dithering a cobertura completa y se compara con `numpy.flip` de la fuente. Volver a rasterizar una geometría reflejada no siempre equivale a reflejar sus píxeles: una `line` resuelve sus empates según su dirección (de `(1, 1)` a `(3, 2)` en 8 × 8, reflejada, pinta `(6, 1)`→`(6, 2)` en otro orden), así que una fuente con líneas no simétricas no se puede reflejar.
- **Los detalles no tocan el borde del tile** (`detail_on_edge`): sólo las operaciones de forma listadas en `border_operations` de la fuente (el relleno y la frontera hierba/tierra de los bordes) y el dithering pueden tocarlo. Así ni espejos ni traslaciones cortan una mata o un guijarro en una costura.
- **Presupuesto del documento** (`budget`): la escena no puede superar `MAX_LAYERS`, `MAX_OPERATIONS`, `MAX_MASKS` ni `MAX_REGIONS` de `moana.core.limits`.
- **Rutas confinadas**: las rutas de las fuentes son relativas a la carpeta del layout, sin `..` ni rutas absolutas, y tras resolver enlaces simbólicos siguen dentro de ella (`path_escape`); el tamaño se comprueba antes de leer (`too_large`: 256 KiB para el layout, 1 MiB por fuente). Layout y fuentes se validan antes de usarlos (`invalid_layout`, `invalid_source`, `duplicate_id`).

Rejilla del prado (filas de arriba abajo): tres filas de hierba que alternan las cuatro variantes de hierba sin repetir la misma variante a 32 px en ninguna fila, una fila de bordes norte, una de las tres tierras, una de bordes sur y dos de hierba.

## Paleta

Una sola paleta `palette_meadow` (perfil `strict`, 14 colores, todos usados en la escena), idéntica en todas las fuentes (el generador falla con `palette_mismatch` si no): `ink`; rampas `grass_ramp` (`grass_0`–`grass_3`), `dirt_ramp` (`dirt_0`–`dirt_3`) y `stone_ramp` (`stone_0` `#4A465E` frío a `stone_3` `#D8D6CF` cálido, con desplazamiento de matiz); y `berry` (`#E8705A`) para las bayas. Luz noroeste en todos los props.

## IDs y edición por ID

Cada colocación es una capa con el ID de la instancia: `tile_r{fila}_c{columna}` (64 capas, en orden de filas) y después `prop_rock`, `prop_sign`, `prop_bush_west` y `prop_bush_east`. Las operaciones, máscaras y regiones de la fuente se copian con el prefijo `<instancia>-`: `tile_r3_c2-lip_1`, `prop_sign-board_face`, región `prop_sign-board`, región `prop_bush_west-berries`.

Regiones semánticas por fuente: `texture` en los tiles; `pebbles` en las tierras con guijarros; `rock` en la roca; `foliage` y `berries` en el arbusto; `board` y `post` en el cartel.

Recolorear sólo el tablero del cartel (batch sobre la revisión 0; `base_snapshot` se obtiene con `moana.api.snapshot_digest`):

```json
{"schema_version": "1.0", "base_revision": 0, "base_snapshot": "sha256:…",
 "commands": [{"type": "set_color", "target_id": "prop_sign-board_face", "color": "dirt_1"}]}
```

Mover un prop es trasladar sus operaciones geométricas y sus máscaras hoja (`translate` con el mismo `dx`, `dy`); el contorno sigue a su máscara. Un cambio hecho así en `meadow.moana.json` es válido, pero `scripts/tiles.py check` lo marcará como desactualizado respecto del layout: para que sea permanente se cambia `at` en el layout (o la fuente) y se ejecuta `build`.

## Atlas

`scripts/tiles.py preview` exporta un atlas con `moana.export.export_spritesheet` (MOANA-023): un frame de 16 × 16 por variante (17), en el orden del layout, 5 columnas, con el pivote de la variante y `duration_ms` 100 (el manifiesto exige una duración; los tiles son estáticos). Cada frame es la variante sola con su caja en `(0, 0)` y el dithering con el origen de patrón del layout; como toda celda empieza en ese origen módulo el periodo, el frame tiene la fase de cualquier colocación, también con otro `pattern_origin` (la prueba usa `(16, 0)`, `(2, 2)` y `(−4, 6)`). Para reconstruir la escena: copiar el frame de cada celda en `[16c, 16r)` y pegar los props, en el orden del layout, en `at − pivote` con alfa binaria. La prueba lo hace y obtiene exactamente los píxeles de la escena.

## Calidad, previews y revisión

`moana.api.evaluate_quality` con la configuración por defecto (`quality-v1`) da, para la escena, cada fuente y cada variante: hard checks superados, ninguna advertencia, ningún singleton y ninguna supresión. Previews de revisión (no versionadas): `artifacts/tiles/meadow/meadow-1x.png`, `meadow-4x.png`, `variant-<id>-3x3-8x.png` y el atlas.

Periodicidad medida (porcentaje de píxeles iguales a su vecino desplazado 32 px en horizontal; el relleno uniforme ya da un mínimo alto): hierba de las filas 0–47, 66 % (81 % con un solo tile de hierba); camino de las filas 64–79, 81 % (93 % antes); hierba de las filas 96–127, 65 % (84 % antes).

**Revisión artística humana: PENDIENTE.** Las notas siguientes son de un agente de IA y no cuentan como revisión ni aprobación: a 1× y a 4×/8× por vecino más cercano, la repetición 3 × 3 de cada variante no muestra costuras; el camino lee bien a 1× y sus bordes ya no repiten la misma muesca cada 16 px; la hierba sigue dejando ver un ritmo de matas en áreas grandes; el arbusto, con base `grass_2`, banda de sombra `grass_0` y bayas más claras, se separa ahora de la hierba; el cartel lleva una flecha con punta diagonal.

## Procedencia y licencia

Creado por un agente de IA de programación (Claude Code), bajo la dirección del usuario del repositorio, con operaciones de Moana escritas en los documentos JSON; sin modelo de imagen, sin calcar arte externo y sin assets de terceros. Los scripts auxiliares que usó el agente para escribir las fuentes no se versionan; `scripts/tiles.py` sólo deriva la escena, el atlas y las previews.

Licencia: **PENDIENTE**. La decide el propietario del repositorio (como en el [corpus](../corpus/README.md)); hasta entonces no se asigna ninguna.

## Pruebas

`tests/integration/test_tile_scene.py`: costuras horizontales y verticales como extensión periódica (`np.tile`) y por material en el render de cada fuente, traslación por múltiplos del tile, fase del dithering por la fórmula de Bayer en coordenadas del lienzo (escena y frames reflejados), espejos contra `np.flip` (tiles y props, horizontal y vertical), perfiles de borde contra los píxeles, rechazo de layouts y fuentes inválidos (rutas, tamaño, tipos, IDs duplicados, espejo asimétrico, detalle en el borde, presupuesto, fase, props fuera del lienzo), edición de un prop por ID limitada a su región o a sus cajas, legibilidad a 1× y 4×, paleta e IDs de la escena y reconstrucción desde el atlas con varios orígenes de patrón.
