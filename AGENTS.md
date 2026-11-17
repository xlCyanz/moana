# Instrucciones operativas para Moana

## Alcance y verdad del proyecto

Lee `MOANA.md`, el issue asignado en `docs/issues/` y sus dependencias antes de editar. El estado actual es P0: infraestructura lista; no hay motor gráfico. En una tarea futura implementa sólo el módulo solicitado. No conviertas ejemplos de diseño en APIs existentes ni marques completado un issue sin pruebas.

Orden documental: solicitud actual del usuario → contratos de `MOANA.md` → ADR aplicables → criterios del issue. Si detectas contradicción técnica, corrige la fuente y sus derivados dentro del alcance o informa el punto concreto. Conserva trabajo existente y no hagas commits, publicación, push ni comunicación externa implícitos.

## Comandos

- Instalar: `uv sync --locked`; sin uv global usar `sh scripts/bootstrap.sh` y `sh scripts/uv.sh`.
- Verificación completa: `uv run python scripts/validate.py`.
- Checks rápidos: `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`.
- Tests: `uv run pytest`; añade sólo los que prueben contratos o riesgos reales.
- Backlog: editar `docs/issues/catalog.json` / `docs/requirements.json`, ejecutar `uv run python scripts/planning.py`, después `uv run python -m scripts.check_repository`.
- Hook Git: `uv run pre-commit install`; no requiere configuración global.

Los entornos y cachés son ignorados por Git. No edites `uv.lock` manualmente; usa uv y revisa la resolución. Si la red o una ruta protegida requieren escalación, utiliza el mecanismo del entorno y comunica el bloqueo real. No desactives seguridad, revisiones ni controles administrados.

## Ingeniería y arte

Código en inglés; documentación y comunicación preferentemente en español. Layout `src`, Python >=3.12, tipos estrictos. No importes `cli`, `project` o `export` desde el núcleo. No añadas funcionalidad gráfica al paquete hasta trabajar un issue de implementación.

Al rasterizar: RGBA uint8, origen superior izquierdo, coordenadas enteras, bbox semiabiertas, alfa cero normalizado, sin AA implícito, semilla local estable, clipping antes de reservar buffers, operaciones acotadas. Una edición debe conservar IDs, documentos y propiedades no afectadas. Prohibidos eval/exec/pickle en documentos y acceso a red desde el núcleo.

Calidad artística exige revisión a 1× y ampliación nearest-neighbor, silueta, clusters, paleta e iluminación. No uses un generador de imágenes para sustituir la edición de un sprite de Moana. No cambies goldens automáticamente para hacer pasar CI; explica y presenta la diferencia cuando el contrato visual cambie.

## Skills y agentes

Skills locales: `moana-python`, `moana-graphics`, `moana-pixel-art`, `moana-architecture`, `moana-testing`, `moana-review`, `moana-planning`. Carga sólo las relevantes. Sus rutas están bajo `.agents/skills/` y sus instrucciones no amplían la autorización del usuario.

Roles en `.codex/agents/`: architect, python_engineer, graphics_engineer, pixel_artist, test_engineer, reviewer e issue_planner, con prefijo `moana_`. Heredan modelo y permisos; no presuponen conexión a servicios. Si se solicita trabajo delegado y el host lo permite, asigna alcance/archivos separados y reúne evidencia; en caso contrario usa los mismos roles como guía en una sola sesión. El agente principal verifica el resultado integrado. No lances sesiones nuevas como sustituto de subagentes sin que el usuario lo solicite.

## Cierre de trabajo

Cumple DoD de `MOANA.md` y criterios del issue. Reporta cambios, pruebas ejecutadas, fallos/no comprobado y siguiente paso. Distingue validaciones del entorno de pruebas del motor. Mantén sincronizados catálogo, requisitos, roadmap y documentación generada. No declares CI remoto, activación de hooks de Codex o aprobación artística humana sin observar evidencia.
