# ADR-014 — Paletas por ID, lenguajes compartidos en `core` y luminancia de rampas

Estado: aceptado · 2026-11-17 · Issue: [MOANA-005](../../issues/MOANA-005.md). Complementa ADR-010 y ADR-011.

## Contexto

MOANA.md §9 define paletas con IDs estables, valores `#RRGGBBAA`, rampas ordenadas de sombra a luz con «luminancia creciente como recomendación verificable» y perfiles `strict`/`rgba`. El esquema 1.0 (ADR-011) ya valida la sección `palette` del documento, pero §3 sólo permite a `palette` depender de `core`, y `layers`, `techniques`, `quality` y `export` necesitan una paleta resuelta sin cargar Pydantic. `editing`, en cambio, sólo puede depender de `core` y `schema`.

## Decisión

1. **Paquete `moana.palette`, dependiente sólo de `core`.** `Rgba` (canales enteros, `parse` del formato canónico, `hex`, `normalized`, `luminance`), `PaletteColor`, `Ramp`, `Palette` (valor inmutable con índice de IDs), `PaletteWarning` y `ColorRemap`. No carga NumPy, Pillow ni Pydantic.
2. **Lenguajes léxicos con un único dueño en `core`.** `moana.core.ids` define `ID_REGEX`/`ID_PATTERN` y `RGBA_HEX_REGEX`/`RGBA_HEX_PATTERN`, con `is_id`, `is_rgba_hex` y `check_id`. Sólo aceptan `str` exacto, nunca subclases, y usan `fullmatch` para que un salto de línea final no pase. `schema` publica esos mismos patrones en el JSON Schema, que no cambia. `detail_sort_key` pasa a `core.errors` para que `palette` ordene sus detalles igual que `schema`.
3. **Reglas de paleta reflejadas, no importadas.** `Palette` valida lo mismo que `schema` para una paleta aislada y con los mismos códigos, motivos y puntero relativo:
   - IDs únicos entre paleta, colores y rampas (`duplicate_id` con `first`);
   - de 1 a 256 colores en `strict` (`too_many`) y de 1 a 4096 en `rgba` (`too_long`, `too_short`);
   - alfa 0 o 255 en `strict` (`partial_alpha` con `profile`);
   - rampas de al menos 2 entradas (`too_short`) sin repetidos (`duplicate_ramp_color`);
   - referencias existentes (`REFERENCE_ERROR`, `unknown_color`).
   
   Los errores siguen el formato de `schema`: detalles ordenados, precedencia de validación sobre referencia y contexto raíz `{"issue_count": n}`. Una prueba de paridad compara ambos módulos caso a caso. La unicidad de IDs en todo el documento (capas, operaciones) sigue siendo responsabilidad de `schema`.
4. **Punteros relativos.** Los detalles de `Palette` apuntan dentro del objeto paleta (`/colors/0/rgba`); quien la incrusta en un documento antepone `/palette`. `ColorRemap` no tiene forma en el documento, así que sus detalles no llevan puntero, sólo `side` y `position` en el contexto.
5. **Coste acotado en la frontera.** `Palette.from_mapping` acepta sólo la salida de `json.loads` (`dict`, `list` y `str` exactos). Antes de recorrer elementos comprueba la longitud de cada array (4096) y el total de miembros de rampa, `MAX_RAMP_ENTRIES = 20 000` en `core.limits`. Un documento validado por `schema` nunca alcanza ese total, porque su lector admite como mucho 20 000 nodos JSON. `ColorRemap` rechaza mapeos con más entradas que colores tiene la paleta antes de iterar.
6. **Luminancia lineal en enteros.** `Rgba.luminance = 2126·lin[R] + 7152·lin[G] + 722·lin[B]`, donde `lin` es una tabla literal de 256 enteros, `round(65535 · sRGB→lineal(v/255))` según IEC 61966-2-1. La tabla es literal y no se calcula con `pow` al importar, para que ninguna libm cambie un bit. L* de CIELAB es monótona en Y, así que ordenar por Y equivale a ordenar por L* sin coma flotante. Sobre valores codificados, el orden de azules y rojos saturados respecto a grises salía invertido.
7. **Advertencias, nunca rechazos.** `luminance_warnings()` produce `PaletteWarning` con puntero, `ramp_id` e IDs de color:
   - `RAMP_LUMINANCE_NOT_INCREASING`, con motivo `decreasing`, `equal` o `duplicate_value`;
   - `RAMP_TRANSPARENT_STEP`: el paso se informa y se omite al comparar el orden;
   - `RAMP_PARTIAL_ALPHA_STEP`: el valor percibido depende del fondo.
   
   La supresión por rampa estilizada corresponde a la configuración de evaluación de §19, no al esquema 1.0.
8. **Edición por valor, sin renumerar.** `replace_color` devuelve una paleta nueva con los mismos IDs, el mismo orden y las mismas rampas. `duplicate_color` añade el ID al final, sin incorporarlo a ninguna rampa. `ColorRemap` es explícito, de un solo paso (no encadena sustituciones) y cerrado sobre la paleta: nunca introduce colores que la paleta no tenga. Estos métodos sirven a `render`, `layers`, `techniques`, `quality`, `export` y `api`. **`editing` no los usa**: §3 no le permite importar `palette`, y `replace_palette_color` validará con los modelos de `schema`.

## Alternativas descartadas

- Que `palette` importe `schema`: viola §3 y carga Pydantic en el raster.
- Que `schema` importe `palette`: viola §3, porque `schema` sólo depende de `core`.
- Luma Rec. 709 sobre valores codificados: ordena mal los tonos saturados que se usan en rampas con hue shift.
- L* de CIELAB en coma flotante: introduce raíces cúbicas que no hacen falta para ordenar.
- Rechazar las rampas no monótonas: §9 permite excepciones estilizadas.

## Consecuencias

- La conversión de `schema.Palette` a `palette.Palette` vivirá en `render` (MOANA-010), que puede depender de ambos.
- Un cambio en las reglas de paleta del esquema exige actualizar `palette` y la prueba de paridad en el mismo cambio.
- Evidencia: `tests/unit/palette/` y `tests/unit/core/test_core_ids.py`.
