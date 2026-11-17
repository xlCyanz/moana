# Estrategia de pruebas

En P0, `tests/test_environment.py` prueba metadata/py.typed, interoperabilidad NumPy–Pillow–PNG, la extensión nativa AggDraw y Pydantic estricto. Las pruebas de planificación ejercitan ciclos, referencias, aliases, cobertura, dependencias de estados activos y evidencia de cierre. `tests/unit/test_portability.py` simula lectura con locale cp1252 para detectar I/O que omita UTF-8. Son pruebas de infraestructura; no prueban un renderer Moana.

Al implementar, seguir el [estándar de testing](standards/testing.md) y MOANA.md §21: unit tests de píxeles/errores, Hypothesis para invariantes acotados, integración de escenas, regresión RGBA exacta, ataques de presupuesto y roundtrip de proyectos/export. [MOANA-028](issues/MOANA-028.md) crea el harness visual y [MOANA-029](issues/MOANA-029.md) amplía la matriz de determinismo.

No añadir snapshots del texto de documentación como prueba semántica. La coherencia de derivados se valida regenerándolos en memoria y los invariantes del grafo se prueban con casos corruptos. La presencia de un marker no demuestra que existan casos. Las carpetas integration/visual/fixtures se crearán con pruebas reales; no necesitan placeholders.

Comandos: `uv run pytest` y `uv run python scripts/validate.py`. El gate mide cobertura de paquete y tooling, escribe coverage.xml, junit.xml y validation.log en artifacts y construye el paquete. CI sube los diagnósticos disponibles tanto al aprobar como al fallar. No se exige un porcentaje arbitrario al paquete de una constante; el reporte debe señalar los caminos del tooling que no se han cubierto. No hay goldens ni evidencia artística en esta fase.

El smoke de wheel instala sólo el artefacto, sin dependencias, en un venv temporal para verificar metadata/py.typed. Las dependencias nativas se prueban en el entorno de desarrollo. La validación local en macOS y la simulación de locale no sustituyen una ejecución nueva en Windows/Linux; consultar el [reporte](BOOTSTRAP_REPORT.md).
