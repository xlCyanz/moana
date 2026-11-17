# Contribuir a Moana

1. Leer MOANA.md, escoger un issue cuyas dependencias estén completadas y acordar su alcance con la solicitud vigente.
2. Instalar `uv sync --locked` y usar una rama de trabajo. Los IDs de issues locales no son números de GitHub.
3. Añadir el módulo cuando tenga implementación real. No crear funciones vacías ni APIs que fallen con NotImplementedError como si estuvieran entregadas.
4. Documentar contratos y agregar tests con oráculos independientes. Un cambio de raster necesita fixture exacta y diff visual; un cambio sólo editorial no necesita tests nuevos.
5. Ejecutar `uv run python scripts/validate.py`. Si cambia planificación, regenerar con `scripts/planning.py`.
6. Abrir una revisión con problema, comportamiento nuevo, validación y límites; usar `.github/PULL_REQUEST_TEMPLATE.md`. Actualizar estado del issue sólo al cumplir sus criterios.

El [flujo Git](docs/guides/development.md) describe ramas y protecciones propuestas. Los IDs canónicos son MOANA-xxx; los aliases MOA-xxx conservan referencias históricas. Sigue `todo → ready → in_progress → review → done`, con `blocked` y motivo si falta una dependencia. Para cerrar, registra evidencia de cada criterio AC y prueba T según el [ciclo de vida](docs/guides/issue-lifecycle.md). No se modifican recursos remotos automáticamente.

## Convenciones

Funciones/variables snake_case, clases PascalCase, constantes UPPER_CASE. Usar tipos de colección nativos, Path para I/O, UTF-8 explícito en texto, excepciones de dominio, parámetros keyword-only cuando desambigüen. Evitar dependencias implícitas del cwd, reloj, locale, RNG global y orden de hashes. Núcleo puro cuando sea viable; I/O en bordes. Consulta los estándares de [Python](docs/standards/python.md), [testing](docs/standards/testing.md), [arquitectura](docs/standards/architecture.md), [Pixel Art](docs/standards/pixel-art.md) y [seguridad](docs/standards/security.md).

Comentarios explican decisiones y reglas de píxel. No exponer detalles internos como experiencia del usuario. No introducir porcentajes de cobertura como sustituto de pruebas relevantes; medir cobertura al crecer el motor y reforzar caminos críticos.

## Cambios de contrato y dependencias

Una incompatibilidad requiere ADR, versión adecuada y fixture de migración. Mantener schema, renderer y paquete como versiones distintas. Dependencia nueva: justificar uso, revisar origen/licencia, resolver lock con uv y ejecutar smoke de rueda. Una actualización de codec requiere comparar RGBA decodificado y tiempos de animación.

La distribución se construye con `uv build`; el gate usa `uv build --no-build-isolation` para aprovechar el backend fijado en uv.lock. `uv run python scripts/check_wheel.py` instala el wheel sin dependencias en un entorno temporal y comprueba metadata y py.typed; los smoke tests del entorno comprueban por separado las dependencias nativas.

## Hooks y automatización

`uv run pre-commit install` instala checks de Ruff y del repositorio; ejecutan el venv existente, no instalan herramientas en cada commit. El hook no reemplaza CI. `scripts/validate.py` es la entrada única de validación completa. No hay tareas recurrentes de la app creadas ni publicación automática de paquetes.

## Baselines y revisión

Goldens futuros se mantienen junto a su fuente JSON, licencia/procedencia y renderer/lock. Presentar expected/actual/diff; un revisor acepta la intención visual. No modificar referencias en CI. El corpus profesional exige revisión humana distinta de la validación matemática.

La licencia del proyecto aún no ha sido elegida. No subir assets de terceros sin permiso ni publicar una distribución antes de resolver esa decisión.
