# ADR-003 — src layout, uv y controles comunes

Estado: aceptado · 2026-11-16.

## Contexto

Se necesita preparar un repo vacío que futuros agentes puedan ejecutar sin inferir dependencias ni confundir import local con wheel instalable.

## Decisión

Distribución `moana-pixel-engine`, import `moana`, src layout, Python >=3.12, uv.lock real y Hatchling. Lock en control de versiones; entorno/cachés fuera de Git. Ruff, mypy estricto, pytest y validación de documentación componen el gate. CI usa el mismo script y prueba wheel aislado. Un bootstrap local instala herramientas sin modificar el sistema.

## Alternativas y consecuencias

requirements.txt solo no fija todo el flujo de proyecto; múltiples gestores amplían mantenimiento. uv añade una herramienta externa, fijada por `.uv-version`. El nombre de distribución es local: no se afirma disponibilidad en PyPI. Licencia/publicación se resuelven antes del release.
