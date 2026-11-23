# Artefactos de 0.1.0rc1 para las migraciones del renombrado (MOANA-037)

`rc1/` contiene bytes escritos por el código del tag `v0.1.0rc1`, antes del renombrado a MoanArt (ADR-041), y son el oráculo independiente de `tests/unit/project/test_project_rename.py` y de las pruebas `t3` de spritesheet y rúbrica. No se regeneran ni se editan.

- `project/`: proyecto directorio con un asset PNG y un historial con una rama (tres snapshots, dos batches), guardado con `save_project` de 0.1.0rc1 a partir de `examples/specs/minimal`.
- `project.zip`: el mismo proyecto guardado con `save_project_archive` de 0.1.0rc1 (el cargador no mira la extensión).
- `sheet.png` y `sheet.json`: spritesheet de tres frames de 2 × 2 escrito por `encode_spritesheet` de 0.1.0rc1.
- `frog.corpus.json`: ficha del corpus de 0.1.0rc1 con su rúbrica.
