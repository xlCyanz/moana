# Ejemplos de contrato

`specs/minimal.moana.json` y `specs/recolor.edit.json` corresponden a MOANA.md §§12–15. `minimal.moana.json` se valida con `moana.schema` (MOANA-002); la ejecución del batch se incorporará en MOANA-018. No son sprites profesionales ni una demostración del motor.

El documento base usa revision=0 y el batch cambia sólo la referencia de color de body_fill. La salida prevista conserva geometría y capas, e incrementa la revisión a 1. Los ejemplos artísticos y sus PNG se producirán en MOANA-027 y MOANA-034 con procedencia documentada.

El batch incluye `base_snapshot`, SHA-256 de la normalización de §14 del documento mínimo (arrays masks/regions/materials/animations materializados vacíos). Es un valor de contrato, no resultado de un renderer; `tests/unit/schema/test_schema_document.py` comprueba que `snapshot_digest` del modelo real lo reproduce. MOANA-018 exigirá revisión y snapshot coincidentes.
