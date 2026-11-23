# Ejemplos de contrato

`specs/minimal.moanart.json` y `specs/recolor.edit.json` corresponden a MOANART.md §§12–15. `minimal.moanart.json` se valida con `moanart.schema` (MOANA-002); `recolor.edit.json` se aplica con `moanart.api.apply_edit` o `moanart edit` (MOANA-018, ADR-024). No son sprites profesionales ni una demostración del motor.

El documento base usa revision=0 y el batch cambia sólo la referencia de color de body_fill. La salida prevista conserva geometría y capas, e incrementa la revisión a 1. El corpus artístico de MOANA-027 (personaje, criatura, objeto, tile y ciclo animado, con procedencia, previews y rúbrica humana pendiente) está en [corpus/](corpus/README.md).

El batch incluye `base_snapshot`, SHA-256 de la normalización de §14 del documento mínimo (arrays masks/regions/materials/animations materializados vacíos). Es un valor de contrato, no resultado de un renderer; `tests/unit/schema/test_schema_document.py` comprueba que `snapshot_digest` del modelo real lo reproduce. MOANA-018 exige revisión y snapshot coincidentes.

## Tutorial de flujos IA

[tutorial/](tutorial/) contiene una poción de 16 × 16 (`potion.moanart.json`, con la región `potion_liquid`), el batch `potion-recolor.edit.json` que recolorea sólo `liquid_fill` (revisión 0 y su `base_snapshot`), el batch erróneo `potion-typo.edit.json` para practicar la recuperación de errores y `potion_flow.py`, el mismo flujo con `moanart.api`. La [guía de flujos IA](../docs/guides/ai-workflows.md) los recorre con `moanart validate`, `inspect`, `export` (1× y 4×) y `edit` (MOANA-033); `scripts/tutorial.py` analiza los bloques `sh` de la guía y los ejecuta en orden comprobando cada código de salida y que sólo cambian los 28 píxeles previstos: `tests/unit/api/test_tutorial.py` lo hace con el entorno de desarrollo y `scripts/check_wheel.py` con el `moanart` y el intérprete de un entorno limpio con sólo el wheel instalado. Las salidas se escriben en `artifacts/tutorial/` (ignorada por Git).

## Tiles y escenarios modulares

[tiles/](tiles/README.md) contiene tiles de 16 × 16 (dos de hierba, tres de tierra y tres bordes hierba/tierra) y props (roca, arbusto y cartel) con una paleta compartida, y `meadow.layout.json`, que los compone en la escena de 128 × 128 `meadow.moanart.json`: una capa por instancia (`tile_r{fila}_c{columna}`, `prop_sign`...) con IDs prefijados, espejos pixel-perfect de `moanart.geometry` y el dithering anclado al origen de patrón común `(0, 0)` (MOANA-034). `scripts/tiles.py` deriva la escena (`build`), comprueba que la versionada está al día (`check`) y escribe previews y el atlas en `artifacts/tiles/` (`preview`). Licencia: MIT ([LICENSE](../LICENSE), decisión del propietario del 2026-11-20). Revisión artística humana: pendiente.

## Escritorio isométrico

[desk/](desk/README.md) contiene un escritorio isométrico de 512 × 512 (tablero, pata, faldón con cajón y cajonera con tres cajones) y su historial de edición: la revisión 0 con sombras tramadas, dos batches que las sustituyen por bandas sólidas escalonadas (`remove`, `insert_operation`, `set_color`, `replace_palette_color` y `set_geometry`) y la revisión 2 resultante con su preview a 1×. `tests/integration/test_desk_example.py` reproduce el historial y compara la preview con el render. Licencia: MIT. Revisión artística humana: pendiente.
