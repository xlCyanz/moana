# Ejemplos de contrato

`specs/minimal.moana.json` y `specs/recolor.edit.json` corresponden a MOANA.md §§12–15. `minimal.moana.json` se valida con `moana.schema` (MOANA-002); `recolor.edit.json` se aplica con `moana.api.apply_edit` o `moana edit` (MOANA-018, ADR-024). No son sprites profesionales ni una demostración del motor.

El documento base usa revision=0 y el batch cambia sólo la referencia de color de body_fill. La salida prevista conserva geometría y capas, e incrementa la revisión a 1. El corpus artístico de MOANA-027 (personaje, criatura, objeto, tile y ciclo animado, con procedencia, previews y rúbrica humana pendiente) está en [corpus/](corpus/README.md); MOANA-034 añadirá más ejemplos.

El batch incluye `base_snapshot`, SHA-256 de la normalización de §14 del documento mínimo (arrays masks/regions/materials/animations materializados vacíos). Es un valor de contrato, no resultado de un renderer; `tests/unit/schema/test_schema_document.py` comprueba que `snapshot_digest` del modelo real lo reproduce. MOANA-018 exige revisión y snapshot coincidentes.

## Tutorial de flujos IA

[tutorial/](tutorial/) contiene una poción de 16 × 16 (`potion.moana.json`, con la región `potion_liquid`), el batch `potion-recolor.edit.json` que recolorea sólo `liquid_fill` (revisión 0 y su `base_snapshot`), el batch erróneo `potion-typo.edit.json` para practicar la recuperación de errores y `potion_flow.py`, el mismo flujo con `moana.api`. La [guía de flujos IA](../docs/guides/ai-workflows.md) los recorre con `moana validate`, `inspect`, `export` (1× y 4×) y `edit` (MOANA-033); `scripts/tutorial.py` analiza los bloques `sh` de la guía y los ejecuta en orden comprobando cada código de salida y que sólo cambian los 28 píxeles previstos: `tests/unit/api/test_tutorial.py` lo hace con el entorno de desarrollo y `scripts/check_wheel.py` con el `moana` y el intérprete de un entorno limpio con sólo el wheel instalado. Las salidas se escriben en `artifacts/tutorial/` (ignorada por Git).
