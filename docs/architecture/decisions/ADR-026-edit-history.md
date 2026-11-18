# ADR-026 — Historial de edición inmutable en memoria: snapshots por digest, cursor y ramas

Estado: aceptado · 2026-11-18 · Issue: [MOANA-019](../../issues/MOANA-019.md). Amplía [ADR-024](ADR-024-atomic-edits.md) (el historial aplica cada edición con `apply_batch` sobre el documento del cursor), con dos límites nuevos, `MAX_HISTORY_SNAPSHOTS` y `MAX_HISTORY_BYTES`, en `moana.core.limits` junto a `MAX_EDIT_COMMANDS`. Aplica ADR-007 (identidad de snapshot), ADR-010 (`BudgetExceeded`, `ReferenceError`, `ValidationError`) y ADR-011 (`canonical_json`, `snapshot_digest`). No cambia la fachada ni el CLI de [ADR-020](ADR-020-public-api-cli.md). Ampliado por [ADR-029](ADR-029-project-persistence.md): `moana.project` persiste el historial (snapshots y batches canónicos por hash, entradas `{snapshot, parent, batch, redo}`) y lo reconstruye con el constructor validado tras reaplicar cada batch; la convergencia sigue rechazada (§4).

## Contexto

MOANA.md §15 fija el contrato del historial:

- los snapshots son inmutables y se identifican por digest;
- cada uno guarda el batch canónico, el digest del padre y una revisión numérica local a la rama;
- undo/redo seleccionan estados existentes;
- una edición sobre un estado anterior crea una rama lógica y descarta sólo el cursor redo activo, no los estados guardados.

El issue exige además recuperar documento y RGBA exactos, no aproximarlos, y limitar la memoria del historial. La persistencia (`history/` del proyecto, §16) es de `project` (MOANA-020). §3 limita `editing` a `core` y `schema`.

Quedaban abiertos: dónde vive el historial, qué guarda cada nodo, cómo se elige el redo, qué pasa cuando dos caminos llegan al mismo digest y cómo se acota la memoria.

## Decisión

1. **Valor congelado en `moana.editing`.** `History` es una dataclass `frozen` con `root`, `cursor`, `limits`, `snapshots` (digest → `Snapshot`, en orden de inserción), `children` (digest → hijos en orden de creación), `redo_children` (digest → hijo redo activo) y `total_bytes`. Los mapas son `MappingProxyType` de copias. Cada operación devuelve un `History` nuevo; el receptor nunca cambia, así que cualquier valor anterior sigue siendo válido. No hay estado global ni persistencia.
   - Se crea con `History.start(document, *, limits=DEFAULT_HISTORY_LIMITS)`: la raíz es el documento recibido.
   - Lectura: `current`, `document`, `snapshot(digest)`, `children_of(digest)`, `leaves()` (puntas de rama), `can_undo`, `can_redo`, `len()` e `in`.
   - El constructor público valida un historial construido a mano. Copia cada mapa en uno de sólo lectura, así que el llamante no conserva un alias mutable. Después comprueba:
     - que cada snapshot está bajo su digest y que ese digest coincide con `snapshot_digest(document)`;
     - que el tamaño es un entero no negativo;
     - que sólo la raíz no tiene padre ni batch;
     - que cada padre está guardado antes que su hijo, con la revisión anterior;
     - que `root` y `cursor` existen;
     - que `children` es exactamente el derivado de los padres;
     - que cada `redo_children[p]` es hijo de `p`;
     - que `total_bytes` es la suma de los tamaños.

     Un fallo es `ValidationError` (`invalid_history`), y superar `limits` es `BudgetExceeded`. Cuesta un digest por snapshot. `start` es la entrada normal; el constructor permite a MOANA-020 reconstruir un historial persistido. Los métodos construyen sus resultados sin revalidar, porque mantienen esas invariantes.
   - `__hash__` usa `root`, `cursor`, `total_bytes` y el número de snapshots, coherente con `==` (los mapas no son hashables).
2. **Qué guarda cada nodo.** `Snapshot(digest, document, parent, batch, affected_ids, size)`, congelado:
   - `digest`: `snapshot_digest(document)`, la única identidad y la clave del índice;
   - `document`: el `Document` congelado que devolvió `apply_batch`;
   - `parent`: digest del padre (`None` en la raíz);
   - `batch`: JSON canónico del primer batch que lo produjo (`canonical_batch`: claves ordenadas, sin espacios, UTF-8, `null` explícito). Se guarda en bytes porque `EditBatch` sólo está congelado en superficie (ADR-024 §1); `parse_edit_batch` lo vuelve a leer. La codificación es la misma que la de `canonical_json`, y una prueba fija que coinciden;
   - `affected_ids`: los de `EditResult`, para el manifiesto de `project`;
   - `size`: lo que cuenta contra el presupuesto (punto 5);
   - `revision` (propiedad): la del documento. Es local a la rama: dos ramas pueden tener la misma revisión con distinto digest, y nunca se usa como clave.
3. **Cursor y navegación.** Seleccionar no crea revisión.
   - `undo()` mueve el cursor al padre y registra el estado abandonado como redo activo del padre. En la raíz: `ValidationError` (`no_parent`).
   - `redo()` mueve el cursor a su redo activo. Sin él: `ValidationError` (`no_redo`).
   - `checkout(digest)` selecciona cualquier snapshot guardado. Un digest desconocido es `ReferenceError` (`unknown_snapshot`, sin eco del valor); un no-`str`, `TypeError`.
   - Navegar no toca `snapshots`, `children` ni `total_bytes`, y `checkout` tampoco cambia `redo_children`.
   - Se elige `ValidationError` para los límites de navegación: es una petición fuera de rango (salida 2) y no merece un código nuevo en ADR-010; `reason` la distingue.
4. **Edición y ramas.** `edit(batch, *, parse_limits)` es lo único que añade un snapshot.
   - Aplica `apply_batch(document_del_cursor, batch)`. La base del batch debe ser la del cursor: si no, `EditConflict` (`stale_revision` o `snapshot_mismatch`), igual que en ADR-024. Cualquier error se propaga sin dejar rastro.
   - El snapshot nuevo es hijo del cursor y pasa a ser su redo activo. Editar tras un undo crea así una rama y sólo sustituye ese redo; el hijo anterior y su descendencia siguen guardados y accesibles por digest.
   - Si el digest resultante ya existe con el cursor como padre, se reutiliza el nodo sin consumir presupuesto. Pasa al repetir la misma edición tras un undo, o con otro batch que dé el mismo documento. Mismo digest no implica mismo batch: el nodo conserva el `batch` y los `affected_ids` del primero.
   - Si existe con otro padre (dos ramas que convergen en el mismo documento), se rechaza con `EditConflict` (salida 4, `existing_snapshot`, con el digest en `snapshot`, que es un valor calculado). El batch es válido; lo que choca es el estado del historial. Es reintentable: `checkout(snapshot)` selecciona ese estado. Un digest tiene un único padre, y aceptar un segundo haría que `undo` devolviera un estado distinto del anterior. Permitir la convergencia exigiría separar la identidad de la entrada de historial (por ejemplo, un hash de padre + batch + digest) del almacén de documentos por contenido, y eso requiere un ADR nuevo. MOANA-020 lo tiene anotado.
   - Tras una edición no hay redo activo (`can_redo` es falso), también al reutilizar un nodo. Así el historial equivale, para edit/undo/redo, a una lista de estados con cursor que se trunca al editar; la propiedad Hypothesis lo comprueba.
5. **Presupuesto explícito sin desalojo.** `HistoryLimits(max_snapshots, max_bytes)`, con máximos `MAX_HISTORY_SNAPSHOTS` = 1024 (raíz incluida) y `MAX_HISTORY_BYTES` = 32 MiB en `moana.core.limits`. Un anfitrión puede bajarlos, nunca subirlos (`require_int`: `out_of_range`, `not_integer`).
   - `size` de un snapshot = bytes de `canonical_json(document)` más bytes del batch canónico.
     - Es una medida determinista y proporcional a lo guardado, pero **no es una cota de RAM**. `apply_batch` reconstruye y valida el documento entero, así que los snapshots no comparten objetos.
     - Con `tracemalloc`, la memoria trazada fue de unas 10–17 veces los bytes canónicos, es decir, 0,3–0,5 GiB reales con el máximo de 32 MiB. Por eso el máximo baja de 256 a 32 MiB.
     - Una prueba `slow` fija la proporcionalidad: la memoria trazada de 21 snapshots queda entre 1× y 24× `total_bytes`.
     - Un servicio que necesite una cota de RAM estricta debe aislar el proceso con límites del SO, como con el render (§20).
   - Si añadir superaría un límite, `edit` lanza `BudgetExceeded` (salida 3; `resource` = `history_snapshots` o `history_bytes`, con `limit` y `estimated`) antes de añadir. `start` aplica el límite de bytes a la raíz.
   - No se desaloja nada: un estado guardado desaparecería en silencio, y el cursor o un digest que un agente conserva dejarían de resolverse. Liberar espacio es empezar otro historial desde el documento deseado o, con MOANA-020, persistir.
   - El recuento se comprueba tras aplicar el batch: aplicar está acotado por ADR-024 y así una edición que reutiliza un nodo nunca se rechaza por presupuesto.
6. **Sin operaciones inversas.** Undo, redo y checkout devuelven el `Document` guardado (el mismo objeto). Reconstruir con inversas exigiría una inversa exacta por comando, incluidas `remove` y `replace_palette_color`, y cualquier error se acumularía en silencio. Guardar documentos congelados cuesta memoria, pero el presupuesto la acota y la igualdad es exacta por construcción.
7. **Fachada y CLI.** MOANA.md §13 no prevé el historial en la fachada ni en `capabilities()`, y el CLI no tiene estado entre invocaciones. `History` se expone en `moana.editing`; `moana.api` y `moana` no cambian. `project` (MOANA-020) lo persistirá y decidirá su exposición.

## Alternativas descartadas

- **Clave por revisión numérica:** dos ramas comparten número tras un undo; §15 y el issue lo prohíben.
- **Historial mutable con pila de undo/redo:** perder el redo al editar borraría estados que §15 obliga a conservar, y compartir el objeto entre llamadas rompería la inmutabilidad.
- **Desalojo LRU o del más antiguo:** pérdida silenciosa de estados; el issue pide un presupuesto explícito.
- **Varios padres por digest (DAG):** `undo` sería ambiguo y §15 define un único padre por snapshot.
- **Guardar el `EditBatch` como modelo:** sus mapas `geometry` y `operation` son mutables.

## Consecuencias

- `undo`/`redo` cuestan O(n) por la copia del mapa de redo (n ≤ 1024); `edit` copia los mapas y aplica el batch. Es despreciable frente a la validación de ADR-024.
- Con documentos grandes, el límite de bytes se alcanza antes que el de snapshots: sólo caben 4 versiones de un documento de 8 MiB. Un anfitrión que quiera más debe persistir (MOANA-020); subir el máximo exige otro ADR.
- MOANA-020 puede persistir cada nodo tal cual: digest, padre, batch canónico, revisión y `affected_ids`.
- MOANA.md 0.1.14-draft recoge ADR-026 en §15.
- Evidencia (`tests/unit/editing/test_editing_history.py`):
  - AC1: `test_ac1_undo_and_redo_restore_document_and_rgba` (JSON canónico y RGBA construidos a mano en cada paso, y el mismo objeto guardado);
  - AC2: `test_ac2_edit_after_undo_replaces_only_the_active_redo` y `test_ac2_undo_of_an_old_branch_reactivates_its_redo`;
  - T1: `test_t1_sequences_and_navigation_limits[1|10|100]` y `test_t1_snapshot_records_parent_batch_revision_and_size`;
  - T2:
    - fallo, ramas y checkout: `test_t2_failed_batch_adds_nothing_and_keeps_the_cursor`, `test_t2_branches_with_the_same_revision_have_distinct_digests`, `test_t2_checkout_creates_no_revision` y `test_t2_checkout_of_an_unknown_digest_is_a_reference_error`;
    - presupuesto: `test_t2_snapshot_budget_rejects_before_adding`, `test_t2_byte_budget_rejects_before_adding`, `test_t2_exact_byte_budget_accepts_and_one_byte_less_rejects`, `test_t2_a_single_snapshot_budget_rejects_every_edit` y `test_t2_traced_memory_is_proportional_to_total_bytes` (`slow`);
    - reutilización y convergencia: `test_t2_same_edit_after_undo_reuses_the_stored_snapshot`, `test_t2_reuse_keeps_the_first_batch_and_affected_ids` y `test_t2_a_digest_reached_from_another_parent_is_rejected`;
    - historial construido a mano: `test_t2_hand_built_history_is_validated`, `test_t2_hand_built_history_rejects_corruption[*]` y `test_t2_hand_built_history_types_and_budget`;
    - codificación, límites e inmutabilidad: `test_canonical_batch_uses_the_canonical_document_encoding`, `test_t2_history_limits_can_only_be_lowered[*]` y `test_t2_history_values_are_frozen`;
  - propiedades (200 ejemplos, hasta 80 acciones, con invariantes en cada paso):
    - `test_property_history_matches_a_list_and_cursor_model`: edit/undo/redo frente a una lista de estados con cursor;
    - `test_property_history_with_checkouts_matches_a_path_tree`: con checkouts aleatorios, frente a un árbol de caminos.

    Las invariantes son:
    - no se pierde ningún snapshot;
    - el número de snapshots no supera el límite;
    - `total_bytes` es la suma de los tamaños;
    - cada digest coincide con su documento;
    - cada hijo tiene la revisión del padre más 1;
    - cada redo activo es hijo de su snapshot;
    - hay `len − 1` aristas.

    Al final, el constructor validado acepta el estado alcanzado.
