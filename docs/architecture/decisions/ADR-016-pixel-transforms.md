# ADR-016 — Transformaciones pixel-perfect sobre índices de píxel

Estado: aceptado · 2026-11-17 · Issue: [MOANA-008](../../issues/MOANA-008.md). Complementa ADR-015 (máscaras de `geometry`).

## Contexto

MOANA.md §6 admite traslación entera, espejo, giros de 0/90/180/270 grados «alrededor del origen del grupo seguidas de traslación explícita» y escala entera por vecino más cercano. Fija el giro horario en coordenadas de índice como `(x, y) → (−y, x)` y exige transformar las cajas como conjuntos de píxeles, no redondeando esquinas geométricas. Girar las esquinas de una caja geométrica desplaza medio píxel las cajas de lado impar; girar índices no. Los grupos (MOANA-009) y la imagen espejo de sprites (MOANA-034) necesitan una regla única, reversible y sin coma flotante. El esquema 1.0 aún no tiene `transform`: es un campo planificado de grupo.

## Decisión

1. **Valor `Transform` en `moana.geometry`.** Es un dataclass congelado con los campos `pivot: Point`, `mirror: bool`, `rotation: int`, `scale: int` y `offset: Point`. La igualdad es estructural: dos transformaciones con la misma función y campos distintos, como una identidad con otro pivote, no son `==`. Valida en la construcción:
   - `rotation` es un `int` real en {0, 90, 180, 270}. Un valor que no es múltiplo de 90 se rechaza con `arbitrary_rotation`, un múltiplo fuera de ese conjunto con `out_of_range` y un no entero, incluido `bool` o `90.0`, con `not_integer`.
   - `scale` es un `int` real en 1..2048 (`MAX_SCALE`, el lado máximo del lienzo), con `not_integer` u `out_of_range`.
   - `mirror` es un `bool` real (`not_boolean`).
   - Un `pivot` u `offset` que no sea `Point` da `TypeError`.

   Los errores de valor son `ValidationError` con `field` y `reason`. La rotación arbitraria y la escala fraccionaria no tienen implementación en ningún perfil.
2. **Orden fijo sobre índices respecto a un píxel pivote.** Primero el espejo horizontal `x → −x`. Después `rotation/90` cuartos de vuelta horarios `(x, y) → (−y, x)` (y crece hacia abajo). Luego la escala: el índice `q` pasa a ser el bloque `[k·q, k·q + k)`. Por último el desplazamiento. El píxel `p` va al bloque cuya esquina superior izquierda es `k·R·(p − c) + c + t`.
   - El pivote es un **píxel**. Por eso, con `k = 1` y `t = 0`, el pivote queda fijo y cuatro giros o dos espejos son la identidad exacta.
   - El espejo vertical se obtiene como espejo + 180°, así que la representación de los ocho elementos del grupo diedro es única.
   - Al escalar, el bloque del pivote empieza en el pivote, de modo que la figura crece hacia la derecha y hacia abajo de él.
   - El «origen del grupo» de §6 será el `pivot` que fije el grupo (MOANA-009).
3. **Cajas como conjuntos de píxeles.** `transform_box(box, transform)` devuelve la caja de los píxeles transformados: transforma los píxeles extremos y añade el bloque de escala. Lanza `ValidationError` si la caja resultante sale del rango de coordenadas.
4. **Máscaras por recolección inversa y recortadas.** `transform_mask(mask, transform, dimensions)` calcula la caja imagen de `mask.bounds` con enteros de Python y la recorta al lienzo sin wraparound. Si no queda nada, o si todos los píxeles activos caen fuera del lienzo, devuelve `Mask.empty()`.
   - Por cada fila y columna de salida recupera el índice de origen: `q = (o − c − t) // k` con división entera por defecto, y `p = Rᵀ·q + c`, ya que `R⁻¹ = Rᵀ`.
   - Como `R` sólo permuta y cambia el signo de los ejes, cada eje de salida depende de un único eje de origen. Basta con dos vectores de índices y un `np.ix_` sobre una copia del almacenamiento de origen con una fila y una columna de ceros como relleno para los índices que caen fuera.
   - La memoria y el trabajo son la caja de salida recortada (como mucho `A`) más una única copia con relleno del almacenamiento de origen, que se llena directamente desde los bits de sólo lectura; una prueba `tracemalloc` lo comprueba. Una escala de 2048 sobre un píxel no reserva nada fuera del lienzo.
5. **Inversa sólo sin escala.** `Transform.inverse()` usa como pivote `pivot + offset`, con desplazamiento `−offset`, el espejo igual y el giro opuesto, o el mismo giro si hay espejo, porque una reflexión es su propia inversa. Si `scale ≠ 1`, o si `pivot + offset` sale del rango de coordenadas, lanza `ValidationError` (`not_invertible`, con `field` `scale` o `pivot`). La composición se expresa aplicando transformaciones en serie; no hay álgebra de composición pública hasta que un consumidor la necesite.

## Alternativas descartadas

- Girar esquinas geométricas de cajas o puntos en coma flotante: desplaza medio píxel con lados impares y depende del redondeo.
- `np.rot90`, `np.flip` y `np.kron` sobre la máscara completa: la escala reserva `k²` veces el origen antes de recortar.
- Permitir dos espejos (horizontal y vertical) además del giro: dos representaciones distintas del mismo resultado rompen la igualdad de valores.
- Rotación libre con vecino más cercano: no es reversible ni pixel-perfect y §6 la deja fuera del perfil estricto.

## Consecuencias

- Los grupos, las regiones y el espejo de animaciones usarán `Transform`. El modelo `transform` del esquema y su coste se definirán con MOANA-009/010 sin cambiar esta regla.
- `transform_mask` no está presupuestado en `budget-v1`, porque no hay operación de documento que lo active. Su cota (caja de salida recortada más el almacenamiento de origen) entrará en el estimador junto con los grupos.
- Evidencia: `tests/unit/geometry/test_geometry_transform.py`. Incluye fixtures a mano de giros, espejos, traslación y escala; un oráculo directo independiente con Hypothesis; identidades de cuatro giros y doble espejo; composición e inversas con pivotes negativos; recorte parcial y total; y rechazo de rotación arbitraria y de escala no entera.
