# ADR-040 — Índice incremental de nodos en la edición por batches

Estado: aceptado · 2026-11-20 · Issue: [MOANA-036](../../issues/MOANA-036.md). Amplía [ADR-024](ADR-024-atomic-edits.md) (punto 9: coste por comando de un batch) y [ADR-039](ADR-039-ci-matrix-portability.md) (punto 5: la prueba del peor caso de edición cuenta pasos caros). Aplica [ADR-032](ADR-032-animation-timeline.md) (cada frame se evalúa contra la base con `apply_commands`, dos veces por animación) y las mediciones de [ADR-038](ADR-038-layer-buffer-cache.md). No cambia el formato de batch, la semántica de los comandos, los códigos de error, los punteros, el orden de `affected_ids`, el schema, el renderer (`render-v1`), el estimador (`budget-v8`), la fachada ni el CLI.

## Contexto

Antes de este ADR cada comando de `apply_batch` y `apply_commands` llamaba a `index_nodes(work.tree)`, que recorre el árbol de trabajo entero para localizar los IDs. Un batch costaba así O(comandos × nodos). ADR-038 midió que esa reconstrucción suponía ≈ 50 % de `apply_commands`, y que la evaluación de frames, que ocurre dos veces por animación (admisión y render), era ≈ 42 % de la animación de 16 frames del benchmark de MOANA-031. La prueba de ADR-039 fijaba exactamente un `index_nodes` por comando.

MOANA.md §22 pide medir antes y después de optimizar. El issue exige resultados, errores y atomicidad idénticos, incluida la regla de que la primera declaración gana ante IDs duplicados.

## Decisión

1. **Índice de trabajo privado por batch.** `moana.editing._tree.WorkingIndex` vive en `_Work` junto al árbol y los IDs retirados. Se construye una sola vez, en la **primera consulta**, recorriendo el árbol con el mismo generador que `index_nodes` (`_members`, que ahora delega las operaciones y sus items en `_operation_nodes`). Que la construcción sea perezosa conserva el error de un origen sin validar (`invalid_source` en el puntero del primer comando que consulta el índice, igual que antes) y que un batch cuyo único comando no es del catálogo no indexe nada.
2. **Actualización por los comandos estructurales**, siempre después de cambiar el árbol:
   - `insert_operation` → `inserted(operation, siblings, layer)`: la operación y sus items (bandas de `shade` y `material`, tramos de `selective_outline`).
   - `remove` → `removed(ids)`: exactamente los IDs que el comando ya retira (el objetivo; las operaciones e items de una capa; los items de una operación). Ningún otro tipo removible contiene IDs.
   - `set_geometry` y `set_parameters` (sustituyen el objeto del nodo por el validado) → `replaced(node, value)`: la entrada del nodo y, si es una operación, las de sus items, que son objetos y listas nuevos con los mismos IDs.
   - `reorder` → `reordered()`: no cambia nada mientras los IDs sean únicos, porque una entrada guarda la lista que contiene el nodo y la posición se calcula al usarla.
   - `set_color`, `translate`, `set_visibility` y `replace_palette_color` mutan valores en su sitio y no tocan el índice.
3. **Duplicados.** Al construir se cuenta si algún ID está repetido (sólo un origen sin validar puede tenerlo; ningún comando lo introduce: `insert_operation` comprueba sus IDs contra el índice, y `set_geometry`/`set_parameters` no cambian IDs). Con duplicados, cada actualización estructural reconstruye el índice entero, porque borrar o mover la primera declaración puede dar el ID a otro nodo. Así la regla «la primera declaración gana» se cumple por construcción en los dos casos.
4. **Pertenencia a la paleta.** `set_color` e `insert_operation` comprobaban el color construyendo el conjunto de IDs de la paleta en cada comando. Ahora `is_color` consulta el índice (un ID único es color si y sólo si su entrada es de clase `color`); con duplicados vuelve a recorrer la paleta.
5. **Atomicidad.** El índice es local al batch, como el árbol de trabajo: si un comando falla, la excepción descarta `_Work` entero y el documento fuente (congelado) nunca cambia. No hace falta deshacer nada. Ningún comando actualiza el índice antes de terminar sus comprobaciones. Una actualización nunca lanza `KeyError`, que el editor traduce a `invalid_source`: si `removed` no encuentra un ID (índice desincronizado) falla con un error interno (`AssertionError`) en lugar de disfrazarse de origen mal formado.
6. **Coste resultante.** Una construcción O(nodos) por batch y búsquedas O(1) por comando; una actualización cuesta O(1) por ID más los items de la operación. La cota O(1) es del índice, no del comando: siguen recorriendo nodos, como antes, la posición en el contenedor (`Node.position`, O(hermanos): `set_geometry`, `set_parameters`, `insert_operation`, `remove`, `reorder`) y la búsqueda de referencias vivas de `remove` (`live_references`, O(nodos): el árbol entero). Con IDs duplicados (sólo un origen sin validar) cada cambio estructural reconstruye el índice entero, O(nodos). `translate`, `set_color`, `set_visibility` y `replace_palette_color` no recorren nada.
7. **`index_nodes` se conserva** como función de referencia: la usan las pruebas como oráculo y define qué es un índice correcto.

## Pruebas

- `tests/unit/editing/test_editing_index.py`:
  - Propiedad Hypothesis (1000 ejemplos, `derandomize=True`) sobre todos los documentos de `examples/` (specs, corpus, `tiles/meadow`, tutorial) con batches de 1 a 10 comandos de los nueve tipos, buena parte fallidos a mitad de batch: tras cada comando, falle o no, cada entrada del índice es idéntica (clase e identidad del objeto, de su lista y de su capa) a la de `index_nodes` recalculado. El resultado (documento canónico, revisión, snapshots, `affected_ids`) o el error (tipo, código, mensaje, puntero, contexto y detalles) es el mismo que con `RebuildingIndex`, una reimplementación en la prueba de las consultas anteriores a este ADR.
  - Un caso explícito por actualización estructural que debe aplicarse (inserción con items, borrado de una operación con items y de una capa, reorder, sustitución de una operación con items y de una máscara), seguido de un comando que falla.
  - Árboles con IDs duplicados (reorder que cambia qué declaración gana, borrado de la primera, inserción duplicada) frente a la misma referencia.
  - Equivalencia de los batches publicados (`examples/**/*.edit.json`, con el RGBA del resultado) y de todas las timelines (`bouncing-slime`, `adventurer-walk` y la animación del benchmark: documentos evaluados, RGBA y digest de cada frame), más un override que falla a mitad de frame.
- `tests/unit/editing/test_editing_apply.py::test_worst_case_translate_batch_stays_linear`: con 256 y 1024 `translate` sobre un path de 3001 comandos, exactamente una construcción del índice, tantos nodos indexados como objetos con `id` del documento (contados aparte), una consulta por comando, ninguna revalidación de nodo y una sola `validate_document`.

## Medición (benchmark de MOANA-031, macOS arm64, CPython 3.12, mediana de 30 muestras tras 5 warmups)

`python -m tests.benchmarks run` sobre `eb0d177` sin cambios y con este cambio; `compare` sin avisos de comparabilidad:

| Caso | Fase | Antes | Después | Cambio |
| --- | --- | ---: | ---: | ---: |
| `animation` (16 frames) | render | 874,9 ms | 658,8 ms | −24,7 % |
| `animation` | render_frame | 30,4 ms | 30,9 ms | +1,6 % |
| `corpus/adventurer-walk` | render | 72,6 ms | 46,4 ms | −36,2 % |
| `static` | render | 30,6 ms | 29,9 ms | −2,3 % |

`render_frame` y `static` no usan el editor: su variación es ruido. El pico RSS bajó también en casos sin edición (`static` 61,1 → 54,3 MiB) porque bajó el RSS de arranque (57,8 → 51,0 MiB); el pico de `tracemalloc` es el mismo (4,2 MiB en `animation`), así que la memoria no cambia de forma atribuible. La línea base versionada de `tests/benchmarks/results/` no se regenera en este cambio.

## Opciones descartadas

- **Mantener posiciones en el índice**: haría O(1) también la posición en el contenedor, pero cada inserción, borrado o reorder desplaza las posiciones de los hermanos, que habría que renumerar. Esos comandos no están en la ruta caliente (las animaciones sólo usan `set_visibility`, `translate` y `set_color`).
- **Índice compartido entre batches o documentos**: un índice cacheado entre llamadas tendría que invalidarse con cada documento nuevo; está fuera del alcance del issue.
- **Reconstruir sólo tras los comandos estructurales**: más simple, pero deja los batches de `remove`/`insert_operation` en O(comandos × nodos) y no aporta nada frente a la actualización local con IDs únicos.
- **Omitir la revalidación final**: es la otra mitad del coste de `apply_commands` (ADR-038), pero es el contrato de atomicidad de ADR-024.

## Consecuencias

- Un comando nuevo que añada, borre, mueva o sustituya nodos debe llamar a la actualización del índice correspondiente; la propiedad de `test_editing_index.py` lo detecta si genera ese comando.
- La revalidación del resultado es ahora el coste dominante de `apply_commands`.
