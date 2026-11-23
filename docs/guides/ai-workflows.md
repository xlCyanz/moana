# Flujos IA: crear, previsualizar y editar por ID

Tutorial ejecutable del flujo de [MOANART.md §1, §13 y §15](../../MOANART.md): un brief se convierte en un documento JSON editable, se valida, se inspecciona, se previsualiza a 1× y 4× y se modifica con un batch que nombra IDs, revisión y snapshot. Todo usa el motor real (`moanart.api` y el comando `moanart`); no hace falta ningún proveedor de IA, GUI, servicio alojado, credencial ni red. Un agente sigue exactamente los mismos pasos que una persona.

Los archivos del tutorial están en [examples/tutorial/](../../examples/tutorial/): [potion.moanart.json](../../examples/tutorial/potion.moanart.json) (documento), [potion-recolor.edit.json](../../examples/tutorial/potion-recolor.edit.json) (recolor por ID), [potion-typo.edit.json](../../examples/tutorial/potion-typo.edit.json) (batch erróneo para la recuperación de errores) y [potion_flow.py](../../examples/tutorial/potion_flow.py) (el mismo flujo en Python). Los bloques `sh` de esta guía son la fuente única de los comandos del tutorial: `scripts/tutorial.py` los analiza en orden (un comando por línea, `# exit N` indica el código de salida documentado) y los ejecuta tal cual, comprobando cada código de salida y, al final, los píxeles cambiados. `tests/unit/api/test_tutorial.py` los ejecuta con el entorno de desarrollo y `scripts/check_wheel.py` con el comando `moanart` y el intérprete de un entorno limpio donde sólo está instalado el wheel, así que la guía no puede divergir del motor sin que falle el gate.

## Preparación

Los comandos se ejecutan desde la raíz del repositorio y escriben sólo en `artifacts/tutorial/`, carpeta ignorada por Git. Dentro del checkout, antepón `uv run` (o `sh scripts/uv.sh run` sin uv global) a `moanart` y `python`; con el wheel instalado en un entorno activado, úsalos tal cual. Las rutas son relativas y las elige quien ejecuta: el comando abre sólo los archivos que recibe como argumento. Los bloques usan sintaxis POSIX (`mkdir -p`, comillas simples dentro de dobles); en PowerShell crea la carpeta con `New-Item -ItemType Directory -Force artifacts/tutorial` y adapta las comillas de `python -c`. Windows PowerShell 5.1 escribe la redirección `>` en UTF-16 con BOM y el paso siguiente, que lee UTF-8, falla: usa PowerShell 7 o posterior, o sustituye `> archivo` por `| Out-File -Encoding utf8NoBOM archivo` (PowerShell 7) o `| Set-Content -Encoding utf8 archivo`.

Cada invocación de `moanart` imprime un único objeto JSON en stdout con `"ok"` y `"command"`; un fallo añade `"error"` (`code`, `context`, `json_pointer`, `exit_code`) y una línea breve en stderr. Códigos de salida: 0 éxito, 2 entrada inválida o capacidad no soportada, 3 presupuesto excedido, 4 conflicto de edición, 5 E/S, 1 error interno, 130 interrumpido (Ctrl+C).

## 1. Del brief al documento

Brief de ejemplo: «una poción de 16 × 16 en un frasco de cristal con tapón de corcho; el líquido debe poder cambiar de color sin tocar el frasco».

El agente traduce el brief a operaciones con IDs estables, no a una imagen. Antes de escribir consulta lo que este build implementa realmente:

```sh
moanart capabilities
```

`capabilities.operations` y `capabilities.edit_commands` son el vocabulario disponible; lo que aparece en `planned_*` no existe todavía y no debe usarse. El documento resultante, [potion.moanart.json](../../examples/tutorial/potion.moanart.json), separa el frasco (capa `bottle`) del líquido (capa `liquid`), da a cada rectángulo un ID (`body_glass`, `liquid_fill`, `liquid_shine`…) y declara la región semántica `potion_liquid` con la máscara `liquid_shape` = `[5, 9, 11, 14)` y las operaciones del líquido. Los colores se referencian por ID de paleta; `potion_green` ya está en la paleta para el recolor posterior. Los IDs son únicos en todo el documento (una operación no puede llamarse igual que un color).

## 2. Validar e inspeccionar

```sh
moanart validate examples/tutorial/potion.moanart.json
moanart inspect examples/tutorial/potion.moanart.json
```

`validate` devuelve `revision` 0 y `snapshot_digest`, el digest SHA-256 del documento normalizado (§14) que un batch necesita como `base_snapshot`. `inspect` resume capas, operaciones con su color, máscaras, regiones y la estimación de presupuesto sin dibujar nada: es la forma de encontrar «el líquido» por ID (`document.regions[0].operation_ids`) antes de editar.

## 3. Preview 1× y 4×

```sh
mkdir -p artifacts/tutorial
moanart export examples/tutorial/potion.moanart.json artifacts/tutorial/potion-1x.png
moanart export examples/tutorial/potion.moanart.json artifacts/tutorial/potion-4x.png --scale 4
```

El PNG a 1× es el máster (`"master": true`); `--scale N` (entero 1–64) amplía por vecino más cercano y el manifiesto lo marca como preview (`"warnings": ["scaled_preview"]`). Revisa siempre ambos: el 1× para la lectura real del sprite y el 4× para clusters y contornos. `export` nunca sustituye un archivo existente salvo con `--overwrite`.

## 4. Recolor por ID

El batch [potion-recolor.edit.json](../../examples/tutorial/potion-recolor.edit.json) cambia sólo el color de la operación `liquid_fill`:

```json
{
  "schema_version": "1.0",
  "base_revision": 0,
  "base_snapshot": "sha256:50aacff270be883c2a20692d8f04c077cabdb0dcc6b01d049e5ea1654cc22430",
  "commands": [
    {"type": "set_color", "target_id": "liquid_fill", "color": "potion_green"}
  ]
}
```

`base_revision` y `base_snapshot` son exactamente los que imprimió `moanart validate`: juntos identifican la base del batch y distinguen ramas con el mismo número de revisión.

`moanart edit` aplica el batch de forma atómica e imprime la nueva revisión, su snapshot, los IDs afectados y el documento normalizado bajo `edit.document`, **pero no escribe ningún archivo**. Para conservar la nueva revisión hay que guardar ese documento explícitamente:

```sh
moanart edit examples/tutorial/potion.moanart.json examples/tutorial/potion-recolor.edit.json > artifacts/tutorial/potion-edit.json
python -c "import json, sys; from pathlib import Path; result = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8')); Path(sys.argv[2]).write_text(json.dumps(result['edit']['document'], indent=2) + '\n', encoding='utf-8')" artifacts/tutorial/potion-edit.json artifacts/tutorial/potion-r1.moanart.json
moanart validate artifacts/tutorial/potion-r1.moanart.json
moanart export artifacts/tutorial/potion-r1.moanart.json artifacts/tutorial/potion-r1-1x.png
moanart export artifacts/tutorial/potion-r1.moanart.json artifacts/tutorial/potion-r1-4x.png --scale 4
```

La salida de `edit` tiene `"revision": 1` y `"affected_ids": ["liquid_fill"]`; el documento guardado valida con revisión 1 y conserva todos los demás IDs, capas, máscaras y regiones.

## 5. Comprobar que sólo cambió la región prevista

```sh
python -c "import sys; from PIL import Image; before, after = (Image.open(path).convert('RGBA') for path in sys.argv[1:3]); changed = [(x, y) for y in range(before.height) for x in range(before.width) if before.getpixel((x, y)) != after.getpixel((x, y))]; xs, ys = [x for x, _ in changed], [y for _, y in changed]; print('bbox', (min(xs), min(ys), max(xs) + 1, max(ys) + 1), 'changed', len(changed))" artifacts/tutorial/potion-1x.png artifacts/tutorial/potion-r1-1x.png
```

Imprime `bbox (5, 9, 11, 14) changed 28`: la caja de diferencia coincide con la máscara `liquid_shape` y cambian 6 × 5 = 30 píxeles de `liquid_fill` menos los 2 de `liquid_shine`, que se dibuja encima y conserva su color. Un cambio local puede alterar dependencias declaradas (por ejemplo, un contorno o una sombra que usen esa región, §15); aquí no hay ninguna, así que ningún píxel fuera de la región cambia. `moanart edit` no calcula todavía la caja de diferencia: por eso se compara el render antes y después.

## 6. El mismo flujo en Python

```sh
python examples/tutorial/potion_flow.py artifacts/tutorial
```

[potion_flow.py](../../examples/tutorial/potion_flow.py) usa la fachada pública `moanart.api`, `moanart.project.save_document` para guardar la revisión (escritura atómica del `.moanart.json` canónico; MOANA-020) y `moanart.core.errors.MoanArtError` para informar de un error con su `code` y su `exit_code`; la caja de la región la lee del JSON fuente, que es dato. Imprime un resumen JSON (`changed_pixels` 28, `changed_outside_region` 0, `revision` [0, 1]) y sale con 1 si algún píxel fuera de la región cambió; ante un error del motor imprime `{"error": CODE, ...}` y sale con el mismo código que el CLI. Su núcleo:

```python
document = api.load_document(TUTORIAL / "potion.moanart.json")
report = api.inspect_document(document)
before = api.render(document)
api.export_png(before, output / "potion-api-1x.png", overwrite=True)
api.export_png(before, output / "potion-api-4x.png", scale=4, overwrite=True)
result = api.edit_document(document, TUTORIAL / "potion-recolor.edit.json")
after = api.render(result.document)
save_document(result.document, output / "potion-r1-api.moanart.json", overwrite=True)
```

`render` no escribe nada y devuelve bytes RGBA inmutables con digest y procedencia; `edit_document` nunca modifica el documento de entrada; `apply_edit` devuelve sólo el documento nuevo. Los errores son clases de `moanart.core.errors` con los mismos `code` y `exit_code` que el CLI.

## 7. Recuperación de errores

```sh
moanart edit artifacts/tutorial/potion-r1.moanart.json examples/tutorial/potion-recolor.edit.json  # exit 4
moanart edit examples/tutorial/potion.moanart.json examples/tutorial/potion-typo.edit.json  # exit 2
moanart export examples/specs/minimal.moanart.json artifacts/tutorial/huge.png --scale 64  # exit 3
moanart export examples/tutorial/potion.moanart.json artifacts/tutorial/potion-1x.png  # exit 5
moanart export examples/tutorial/potion.moanart.json artifacts/tutorial/bad.png --scale 65  # exit 2
```

| Salida | Error | Causa | Recuperación |
| --- | --- | --- | --- |
| 4 | `EDIT_CONFLICT` `stale_revision` | El batch se escribió para la revisión 0 y el documento ya está en la 1. Con la misma revisión y otro contenido el motivo es `snapshot_mismatch`. | Volver a ejecutar `moanart validate` sobre el documento actual, revisar el cambio con `inspect` y regenerar el batch con su `revision` y `snapshot_digest`. Nunca editar `revision` a mano ni reutilizar un snapshot ajeno. |
| 2 | `REFERENCE_ERROR` `unknown_target` en `/commands/0/target_id` | El ID `liquid_fil` no existe. | Buscar el ID correcto con `moanart inspect`. El batch es atómico: ningún comando se aplicó. |
| 3 | `BUDGET_EXCEEDED` (`export_dimension`, `export_area`, `buffer_bytes`) | 128 × 64 = 8192 px de lado supera el máximo de 2048 px por lado de una exportación (`export_dimension`) y el área máxima de 2048 × 2048 = 4 194 304 px (`export_area`); se rechaza antes de reservar memoria o escribir. | Bajar `--scale` (aquí, 16 o menos). Los recursos y límites están en `error.details[].context`. |
| 5 | `EXPORT_ERROR` `exists` | El destino ya existe. | Elegir otra ruta o pasar `--overwrite` explícitamente. |
| 2 | `VALIDATION_ERROR` `usage` | `--scale` fuera de 1–64. | Corregir el argumento; `moanart export --help` describe la sintaxis. |

## Pautas para agentes

- **Conserva la fuente y la revisión.** El documento JSON es el artefacto primario y el PNG es derivado. Guarda cada revisión aceptada (paso 4) junto con su `snapshot_digest`, y construye el siguiente batch a partir de esa revisión, no de una copia anterior ni del PNG.
- **Edita por ID, no repintando.** Localiza objetivos con `inspect` (capas, operaciones, regiones) y usa sólo los comandos de `capabilities.edit_commands`. Un batch fallido no cambia nada; corrige y vuelve a intentarlo.
- **Muestra siempre la preview 1× y la ampliada**, e informa de la diferencia antes/después (paso 5) cuando el cambio pretende ser local.
- **Presenta las limitaciones reales.** MoanArt no genera imágenes a partir de texto ni interpreta un brief: el agente escribe operaciones y el motor las rasteriza de forma determinista; no prometas una «generación visual» que no existe. `moanart edit` no escribe archivos y no hay comando CLI de persistencia, proyectos ni historial: guardar la revisión es un paso explícito (JSON de salida o `moanart.project.save_document` en Python); el historial undo/redo (`moanart.editing.History`) vive en memoria; sólo se persiste con `moanart.project.save_project` (Python), sin fachada ni CLI. El CLI exporta PNG; GIF, APNG/WebP y spritesheets sólo están en `moanart.export` (Python). La calidad artística profesional sólo la declara una revisión humana; los informes de `moanart.api.evaluate_quality` son advertencias y métricas, no aprobación.
- **No uses generación de imágenes** para sustituir la edición de un sprite MoanArt ([estándar artístico](../standards/pixel-art.md)).

Relacionado: [flujo de sesión de agentes](agent-workflow.md), [ejemplos](../../examples/README.md), [contratos de módulos](../architecture/module-contracts.md).
