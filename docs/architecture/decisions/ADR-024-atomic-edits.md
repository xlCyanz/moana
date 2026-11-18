# ADR-024 — Batches de edición atómicos, revisión optimista y `moana edit`

Estado: aceptado · 2026-11-18 · Issue: [MOANA-018](../../issues/MOANA-018.md). Amplía [ADR-011](ADR-011-schema-v1.md) (los batches reutilizan la lectura acotada y los modelos de schema 1.0; límite `MAX_EDIT_COMMANDS` en `moana.core.limits`) y [ADR-020](ADR-020-public-api-cli.md) (`apply_edit`, `edit_document` y `load_edit_batch` pasan a la fachada y `moana edit` deja de ser un comando previsto). Aplica ADR-007 (identidad de snapshot), ADR-010 (`EditConflict`, salida 4), ADR-022 (DAG de máscaras y regiones por ID), ADR-023 (paths en punto fijo 1/256) y [ADR-025](ADR-025-ordered-dithering.md) (tabla de miembros por tipo en `moana.schema`, operación `dither`). Ampliado por [ADR-026](ADR-026-edit-history.md): `moana.editing.History` guarda en memoria las revisiones que produce `apply_batch` (snapshots por digest, cursor, ramas y presupuesto); el punto 8 sigue vigente y el manifiesto con bbox sigue siendo de MOANA-020.

## Contexto

MOANA.md §15 fija el contrato de edición:

- Un batch lleva `schema_version`, `base_revision`, `base_snapshot` y comandos tipados del catálogo: `set_color`, `set_geometry`, `translate`, `set_visibility`, `replace_palette_color`, `insert_operation`, `remove` y `reorder`.
- Se verifican ambas precondiciones y se valida todo antes de aceptar. Un fallo revierte todo y la revisión sube exactamente 1.
- Se preservan IDs y orden.
- Se rechazan el borrado con referencias vivas, la edición de capas bloqueadas y los comandos ambiguos.

§3 limita `editing` a `core` y `schema`. `EditConflict` (`EDIT_CONFLICT`, 4) ya existía en `core.errors` (ADR-010), pero nada lo producía.

§15 deja abiertos el objetivo admisible de cada comando, la forma de `geometry`, el tratamiento de errores y la interfaz del CLI.

## Decisión

1. **Módulo `moana.editing`.** Sólo usa `core`, `schema` y Pydantic; ni render, ni disco, ni `palette`.
   - `EditBatch` es un modelo Pydantic `strict`, `extra='forbid'` y `frozen`:
     - `schema_version: "1.0"`;
     - `base_revision` en `0..2^64-1`;
     - `base_snapshot` con patrón `^sha256:[0-9a-f]{64}$`;
     - `commands` con 1..`MAX_EDIT_COMMANDS` (1024) comandos discriminados por `type`.

     El congelado es superficial: `commands` es una tupla de modelos congelados, pero `geometry` e `insert_operation.operation` son mapas JSON que el editor sólo lee y vuelve a validar. Un batch vacío se rechaza (`too_short`): no tiene sentido crear una revisión sin intención.
   - `parse_edit_batch(bytes | Mapping | EditBatch, *, limits)` pasa por la misma lectura acotada que los documentos: 8 MiB, profundidad 32, 20 000 nodos, claves duplicadas y NaN. Los mensajes del lector hablan de «edit batch», con el mismo contexto. Otra `schema_version` textual es `UnsupportedVersion`. Los errores estructurales son un `ValidationError` con un detalle por problema y pointer del batch. Un `type` desconocido no se repite ni en el mensaje ni en el contexto; `expected` lista el catálogo.
   - `apply_batch(document, batch, *, limits) -> EditResult`. `EditResult` es una dataclass congelada con `document`, `base_revision`, `base_snapshot`, `snapshot`, `affected_ids` y `to_mapping()`, que devuelve el documento normalizado. `apply_edit(document, batch) -> Document` existe sólo en la fachada `moana.api`, con la firma de §13; `moana.editing` no lo exporta.
2. **Tabla de miembros por tipo.** Lo que el editor sabe de una operación o máscara sale sólo de `OPERATION_MEMBERS` y `MASK_MEMBERS`, mapas inmutables (`MappingProxyType`) de tipo a `NodeMembers(colors, masks, geometry)`:
   - `colors`: miembros con un ID de color;
   - `masks`: miembros con IDs de máscara;
   - `geometry`: miembros que `set_geometry` reemplaza y `translate` desplaza.

   Ningún código accede a `operation["color"]` ni a un miembro geométrico por nombre fijo. La prueba de exhaustividad de schema (`tests/unit/schema/test_schema_members.py`) compara las filas con los tipos de las uniones `Operation` y `MaskNode`. Así, un tipo nuevo sin fila falla en las pruebas y nunca como `KeyError` durante una edición.

   La tabla es `moana.schema.OPERATION_MEMBERS` / `MASK_MEMBERS`, de [ADR-025](ADR-025-ordered-dithering.md); `editing` no mantiene una copia. Un `dither` (`colors=("color_a", "color_b")`, `masks=("mask_id",)`, `geometry=()`) es objetivo de `remove`, `reorder` e `insert_operation`. `set_color` lo rechaza (`multiple_colors`), y `translate` y `set_geometry` también (`not_geometric`): su `origin` ancla la fase del patrón y no es geometría mientras otro ADR no lo decida. Cómo se desplaza cada forma (`GEOMETRY_SHAPES`: punto, caja, lista de puntos, comandos de path) es una regla de edición y se queda en `editing`; una prueba exige que cubra todos los miembros geométricos de la tabla.
3. **Objetivos de cada comando.** Es una decisión mínima donde §15 no precisa.
   - Los IDs son globales, así que el objetivo nunca es ambiguo.
   - Un ID inexistente es `ReferenceError` (`unknown_target`). Un ID de otra clase es `ValidationError` (`invalid_target`, con `kind` y `expected`).

   | Comando | Objetivo | Efecto |
   | --- | --- | --- |
   | `set_color(target_id, color)` | operación con exactamente un miembro de color | Cambia sólo esa referencia. Un color inexistente da `unknown_color`. Un tipo con otro número de colores da `multiple_colors` en `/commands/i/target_id`. |
   | `set_geometry(target_id, geometry)` | operación u hoja de máscara | `geometry` contiene exactamente los miembros geométricos de la fila; otro conjunto da `geometry_members`. Un tipo sin geometría (máscara combinada) da `not_geometric`. No cambia `type`, colores ni `backend`. |
   | `translate(target_id, dx, dy)` | operación u hoja de máscara | Desplaza en píxeles enteros (`\|d\| ≤ 2·1 048 576 + 1`); un path se desplaza `256·d` unidades. Si un miembro sale del rango de coordenadas, da `out_of_range` en `/commands/i`, con `member` en el contexto. Un tipo sin geometría da `not_geometric`. |
   | `set_visibility(target_id, visible)` | capa | Cambia `visible`. |
   | `replace_palette_color(target_id, rgba)` | color de paleta | Cambia el valor (en mayúsculas) y afecta a todos sus consumidores, incluidos los de capas bloqueadas (punto 4). |
   | `insert_operation(layer_id, after_id, operation)` | capa | Inserta tras `after_id` de esa capa (`null`: al principio). El ID debe ser nuevo en todo el documento y en el batch (`duplicate_id`) y no puede reutilizar uno eliminado en el mismo batch (`reused_id`). Todos sus miembros de color deben existir; las referencias a máscaras las comprueba la validación final. |
   | `remove(target_id)` | operación, capa (con sus operaciones), máscara, región, color o rampa | Rechaza referencias vivas. |
   | `reorder(target_id, after_id)` | cualquier nodo de una lista (color, rampa, capa, operación, máscara, región) | Mueve dentro del mismo contenedor; `null` lo lleva al principio. Un `after_id` de otro contenedor da `not_in_container`; uno igual al objetivo, `after_self`. |

   `after_id` es obligatorio y admite `null` explícito. La regla de §12 de omitir opcionales no aplica porque §15 lo define así.

   No hay comandos para:
   - mover un nodo entre contenedores;
   - bloquear o desbloquear capas;
   - cambiar `id`, `schema_version` o `revision`;
   - aplicar JSON Patch genérico.

   Un modelo construido sin validar con un comando desconocido da `unknown_command`. Un `KeyError`, `TypeError` o `IndexError` al aplicar un comando se envuelve como `ValidationError` (`invalid_source`) en `/commands/i`.

   Reutilizar un ID eliminado se rechaza aunque el resultado fuera válido. Así un ID nunca nombra dos nodos distintos dentro de una misma transición, y el historial de MOANA-020 puede tratar `affected_ids` como un conjunto sin ambigüedad.
4. **Capas bloqueadas.** Falla con `ValidationError` (`locked_layer`, pointer del comando) un comando cuyo objetivo es:
   - una capa con `locked: true`;
   - una de sus operaciones;
   - en `insert_operation`, la capa de destino.

   Como no existe comando de desbloqueo, una capa bloqueada sólo cambia editando el documento fuera de los batches. Reordenar otras capas a su alrededor sí se permite.

   `replace_palette_color` se permite aunque el color tenga consumidores en capas bloqueadas. Su objetivo es la paleta, no la capa, y el bloqueo protege la estructura y la geometría, no el valor de un color compartido. Bloquearlo obligaría a duplicar colores para retocar la paleta global.
5. **Atomicidad e inmutabilidad.**
   1. Se valida el batch y se comprueban las precondiciones, incluido el desbordamiento de revisión (punto 6).
   2. Cada comando se aplica, en orden, sobre una copia privada del árbol normalizado (`normalize_document`, objetos nuevos). Los nodos se localizan por ID, nunca por posición.
   3. `set_geometry` e `insert_operation` revalidan el nodo con los modelos de schema. Sus errores se reubican bajo el pointer del comando: `/commands/i/geometry/…` y `/commands/i/operation/…`.
   4. `translate` no revalida el nodo. Comprueba el rango de cada coordenada desplazada y deja el resto a la validación final.
   5. Se fija `revision = base + 1` y se valida el documento completo con `validate_document`: unicidad global, referencias de color, DAG de máscaras y regiones, perfil y límites. Si esa validación falla, el error conserva su clase y sus detalles con pointers del documento resultante y `reason: invalid_result`.

   Cualquier excepción se produce antes de construir un `Document`, así que no hay resultado parcial. El `Document` fuente está congelado y nunca se toca.
6. **Revisión optimista.**
   - Un `base_revision` distinto de la revisión actual del documento da `EditConflict` (`stale_revision`, `/base_revision`). No importa si es menor o mayor.
   - Con la misma revisión, un `base_snapshot` distinto de `snapshot_digest(document)` da `EditConflict` (`snapshot_mismatch`, `/base_snapshot`). Así dos ramas con el mismo número de revisión no aceptan el batch de la otra.
   - El contexto incluye `current_revision` y `current_snapshot`, que son valores calculados, no entrada.
   - Si la revisión actual ya es `2^64-1`, el batch se rechaza antes de aplicar ningún comando con `ValidationError` (`revision_overflow`, `/base_revision`, `maximum`).
7. **Referencias vivas.** `remove` calcula los nodos eliminados; una capa arrastra sus operaciones. Después busca referencias desde los nodos que permanecen, según la tabla del punto 2:
   - los miembros `colors` y `masks` de operaciones y máscaras;
   - los colores de rampa;
   - el `mask_id` de capas y regiones;
   - los `operation_ids` de regiones.

   Si hay alguna, da `ReferenceError` (`live_reference`, pointer del comando), con un detalle por referencia. Cada detalle lleva el pointer del documento de trabajo y ningún ID en el contexto. Reordenar no rompe nada porque todas las referencias son por ID.
8. **IDs afectados.** `affected_ids` lista sólo los objetivos, los IDs insertados y los eliminados, una vez cada uno y en orden de comandos. La caja de diferencia (bbox) y los consumidores indirectos, como las operaciones que usan un color reemplazado, no se calculan aquí porque `editing` no rasteriza. Se calcularán con el manifiesto del historial de §15 en `project` (MOANA-020).
9. **Presupuesto y coste.** `editing` no depende de `render`.
   - Los límites de cardinalidad (capas, operaciones, máscaras, nodos) se comprueban en la revalidación.
   - El presupuesto de render se aplica al renderizar el resultado, como con cualquier documento.
   - `limits` (un `ParseLimits`) acota tanto la lectura del batch como la revalidación del resultado.

   Cada comando reindexa el árbol en tiempo lineal. El peor caso medido son 1024 `translate` sobre un path de 3001 comandos: unos 2 s en un portátil, frente a decenas de segundos si `translate` revalidara el nodo en cada comando. Una prueba de humo lo acota con un umbral generoso.
10. **Imports privados de `schema`.** `editing` reutiliza, sin duplicarlos, cuatro módulos internos. Ninguno es API pública, pero los consume también `moana.api` y los reutilizará `project` (MOANA-020). La prueba de arquitectura fija exactamente esta lista: un import privado nuevo exige actualizar este ADR.

    | Módulo | Uso | Motivo |
    | --- | --- | --- |
    | `moana.schema._reader` | lectura JSON acotada del batch | Mismos límites y errores que los documentos. |
    | `moana.schema._issues` | traducción de errores de Pydantic | Mismos pointers y `reason`. |
    | `moana.schema._pointers` | escape de JSON Pointer | Mismo formato de pointer. |
    | `moana.schema.models` | `MAX_REVISION` | Mismo máximo que valida el documento. |
11. **Fachada y CLI.**
    - `moana.api` exporta:
      - `apply_edit(document, batch) -> Document`, con la firma de §13;
      - `edit_document(document, batch) -> EditResult`;
      - `load_edit_batch(source) -> EditBatch`.

      `batch` acepta `EditBatch`, bytes, un mapping o un path autorizado. El path usa la misma lectura no bloqueante y acotada que `load_document`; un fallo da `ReadError` con mensaje propio y sin ruta.

      La fachada también reexporta `EditBatch`, `EditResult`, `EditConflict`, `COMMAND_TYPES` y el alias `BatchSource`.
    - `AVAILABLE_FUNCTIONS` incorpora las tres funciones y `PLANNED_FUNCTIONS` queda vacío. `capabilities()` añade `edit_commands` con el catálogo. Ningún nombre desaparece de los listados.
    - `moana edit DOC BATCH` imprime un único objeto JSON en una línea. Incluye `edit = {affected_ids, base_revision, base_snapshot, document, document_id, revision, snapshot_digest}`, con el documento completo, y **no escribe archivos**: persistir la revisión con escritura atómica pertenece a `project` (MOANA-020). Salidas:
      - 0: éxito;
      - 2: batch o resultado inválido, o referencia rota;
      - 4: conflicto;
      - 5: lectura.

      `PLANNED_COMMANDS` queda vacío.

## Alternativas descartadas

- **JSON Patch o comandos genéricos `set(path, value)`:** permitirían cambiar `id`, `revision` o estructuras arbitrarias y harían imposible garantizar IDs estables. El issue lo excluye.
- **Mutar un `Document` con `model_copy(update=...)`:** se salta la validación de Pydantic y obliga a reconstruir a mano las invariantes de schema. El árbol normalizado más `validate_document` reutiliza el único validador.
- **Sólo revisión numérica:** tras un undo, dos ramas comparten número; §15 exige también el snapshot.
- **Escribir el documento editado desde `moana edit` (`--output`):** necesita la escritura atómica y la política de historial de `project`. El CLI imprime el documento para que el agente lo guarde.
- **Calcular la caja de diferencia en `editing`:** exigiría rasterizar, y §3 lo prohíbe.
- **Acceder a `operation["color"]` y a miembros geométricos por nombre:** fallaría con `KeyError` en cuanto schema añada un tipo con otros miembros, como el dither de MOANA-016. Lo sustituye la tabla del punto 2.

## Consecuencias

- `EDIT_CONFLICT` (4) tiene por fin un productor, y los agentes reciben pointers del batch para cada comando inválido.
- Un batch cuesta como mucho `MAX_EDIT_COMMANDS` recorridos lineales más una validación completa (punto 9).
- Si `schema` renombra uno de los cuatro módulos privados del punto 10, hay que actualizar `editing`. La prueba de arquitectura lo detecta.
- Un tipo nuevo de operación o máscara sólo necesita su fila en `moana.schema` (ADR-025) y, si tiene geometría con una forma nueva, una entrada en `GEOMETRY_SHAPES`. MOANA.md 0.1.13-draft recoge ADR-024 y ADR-025.
- Evidencia:
  - `tests/unit/editing/test_editing_apply.py`:
    - AC1: diff campo a campo del JSON normalizado;
    - AC2: rollback del primer comando, base distinta y fallo en la validación final;
    - T1: cada comando válido y negativo, hojas de máscara path, línea, polígono y elipse, reorder al principio, referencias vivas, `reused_id` y `duplicate_id`;
    - T2: documento y archivo fuente idénticos byte a byte, render antes y después, y batches sin cambio visual que suben la revisión;
    - T3: dos ramas con revisión 1;
    - propiedades Hypothesis de todo o nada y contra un oráculo mínimo;
    - límites, desbordamiento de revisión, peor caso de coste y modelos sin validar.
  - `tests/unit/editing/test_editing_members.py`: `editing` lee la tabla de `moana.schema`, `GEOMETRY_SHAPES` cubre sus miembros geométricos y las referencias desde nodos borrados no son vivas. La exhaustividad de la tabla frente a las uniones la prueba `tests/unit/schema/test_schema_members.py`.
  - `tests/unit/editing/test_editing_dither.py`: sobre `examples/specs/dither-dusk.moana.json`, `remove` de la máscara o de los colores de un dither da `live_reference`, otros borrados (incluida la capa con sus dithers) funcionan, `set_color` da `multiple_colors`, `translate` y `set_geometry` dan `not_geometric`, `insert_operation` de un dither válido funciona y con un color o una máscara inexistentes falla, y `reorder` de un dither funciona.
  - `tests/unit/editing/test_editing_batch.py` y `test_editing_architecture.py`: parsing estricto, mensajes «edit batch», errores sin eco de entrada, versión, límites, fronteras de import y lista exacta de imports privados.
  - `tests/unit/api/test_api_editing.py`, `tests/unit/cli/test_cli_edit.py` y `tests/integration/test_cli_paths.py`: fachada, lectura acotada del batch, `moana edit` con salidas 0/2/4/5, sin archivos escritos y en un proceso nuevo.
