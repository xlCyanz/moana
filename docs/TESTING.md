# Estrategia de pruebas

En P0, `tests/test_environment.py` prueba metadata/py.typed, interoperabilidad NumPy–Pillow–PNG, la extensión nativa AggDraw y Pydantic estricto. Las pruebas del tooling ejercitan ciclos, referencias y cobertura del backlog. Son smoke tests de infraestructura, no un renderer de Moana.

Al implementar: unit tests de píxeles y errores, Hypothesis sobre dimensiones/transformaciones e inmutabilidad, integración de escenas, regresión RGBA exacta, ataques de presupuesto y roundtrip de proyectos/export. MOANA.md §21 fija las reglas; MOA-028 crea el harness visual y MOA-029 amplía la matriz de determinismo.

No añadir snapshots del texto de documentación como prueba semántica. La coherencia de archivos derivados se valida regenerándolos en memoria, y los invariantes del grafo se prueban con casos corruptos. No exigir un porcentaje de coverage arbitrario al paquete de una sola constante.

Comandos: `uv run pytest`, `uv run pytest -m security`, `uv run python scripts/validate.py`. Markers sin casos todavía no demuestran cobertura de producto. CI almacena `artifacts/` sólo cuando haya diagnóstico producido por una prueba; no fabrica imágenes de regresión en P0.
