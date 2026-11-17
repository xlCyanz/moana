# Instrucciones operativas para Moana

## Propósito y fuente de verdad

Moana será un motor Python de Pixel Art determinista y editable. Lee [MOANA.md](MOANA.md), el issue asignado en [docs/issues](docs/issues/README.md) y sus dependencias antes de editar. Estado actual: infraestructura lista; el paquete sólo expone metadata. Implementa únicamente el alcance solicitado. No conviertas ejemplos de diseño en APIs existentes ni marques completado un issue sin pruebas.

Orden documental: solicitud actual del usuario → contratos de MOANA.md → ADR aplicables → criterios del issue. Si detectas una contradicción, corrige fuente y derivados dentro del alcance o informa el punto concreto. Conserva trabajo existente; no hagas commit, push, publicación ni comunicación externa implícitos.

## Organización y arquitectura

`src/moana/` contiene el paquete; `tests/`, pruebas reales; `scripts/`, herramientas del repositorio; `docs/issues/`, planificación generada desde JSON; `docs/architecture/`, contratos y ADR; `docs/standards/` y `docs/guides/`, reglas especializadas. `examples/specs/` contiene diseño futuro. `.agents/skills/` y `.codex/agents/` son instrucciones y roles distintos.

Sigue los [contratos de módulos](docs/architecture/module-contracts.md) y el [estándar de arquitectura](docs/standards/architecture.md). Dominio independiente de disco, renderer determinista, edición por IDs, exportación en el borde. No importes cli, project o export desde core. No crees módulos gráficos vacíos durante trabajo de infraestructura.

No hay AGENTS.md anidados: las reglas actuales son comunes y las diferencias de dominio se expresan mediante skills y estándares. Añadir uno sólo si un directorio necesita instrucciones propias y compatibles.

## Comandos

```sh
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run mypy src/
uv run mypy
uv run pytest
uv build
uv run python scripts/check_wheel.py
uv run python scripts/validate.py
```

Sin uv global, usa `sh scripts/bootstrap.sh` y sustituye `uv` por `sh scripts/uv.sh`. El gate incluye lock, lint, tipos, estructura, cobertura y build con el backend fijado. Los entornos, cachés y artefactos son ignorados por Git. No edites uv.lock a mano.

Backlog: editar `docs/issues/catalog.json` y `docs/requirements.json`, ejecutar `uv run python scripts/planning.py`, después `uv run python -m scripts.check_repository`; con autorización remota, reflejarlo con `uv run python scripts/github_sync.py --apply`. Cada issue incluye una «Guía para agentes de IA» con lecturas, skills, archivos, pruebas y cierre. Hook por checkout: `uv run pre-commit install`. La [guía de desarrollo](docs/guides/development.md) explica reproducción y Git.

## Código, pruebas y arte

Código en inglés; documentación y comunicación preferentemente en español. Layout src, Python >=3.12, tipos estrictos, snake_case para funciones y PascalCase para clases. Usa UTF-8 explícito al leer/escribir texto y errores de dominio en fronteras. Sigue los estándares de [Python](docs/standards/python.md) y [testing](docs/standards/testing.md). Añade pruebas de contratos y riesgos reales; un ajuste editorial no necesita tests nuevos.

Al rasterizar: RGBA uint8, origen superior izquierdo, coordenadas enteras, bbox semiabiertas, alfa cero normalizado, sin AA implícito, semilla local estable, clipping antes de reservar buffers, operaciones acotadas. Una edición conserva IDs y propiedades no afectadas. Revisión y snapshot identifican conjuntamente la base de un batch.

Calidad artística exige revisión a 1× y ampliación nearest-neighbor, silueta, clusters, paleta e iluminación. Sigue el [estándar artístico](docs/standards/pixel-art.md). No uses generación de imágenes para sustituir la edición de un sprite Moana. No cambies goldens automáticamente para hacer pasar CI: presenta expected/actual/diff y justifica el nuevo contrato.

## Seguridad y Git

Consulta [seguridad](docs/standards/security.md). No incluir secretos ni ejecutar código arbitrario de documentos/skills. Prohibidos eval/exec/pickle en documentos y acceso a red desde el núcleo. Validar rutas, tamaños y presupuestos antes de abrir assets o reservar buffers. Revisar origen, código y permisos de dependencias/skills; no instalar herramientas globales silenciosamente ni desactivar controles del entorno.

Inspecciona estado, rama, diff y remotos antes de modificar. Usa una rama de issue como `feat/MOANA-001-coordinates` desde la integración vigente. Conserva commits y cambios ajenos. No usar reset destructivo ni force push para resolver problemas ordinarios. Las protecciones y revisiones propuestas están en la guía Git; cambiar recursos remotos exige una autorización que lo incluya.

## Skills y agentes

Skills locales: `moana-architecture`, `moana-python`, `moana-pixel-art`, `moana-graphics`, `moana-testing`, `moana-issue-planning`, `moana-code-review`. Carga sólo las relevantes desde `.agents/skills/`; sus instrucciones no amplían la autorización del usuario.

Roles en `.codex/agents/`: architect, python_engineer, graphics_engineer, pixel_artist, test_engineer, documentation_writer, reviewer e issue_planner, con prefijo `moana_`. Heredan modelo y permisos. Si se solicita delegación y el host lo permite, asigna contratos y archivos separados; el agente principal integra y valida. En otro caso, utiliza los roles como guía en una sesión. No abras otros chats como sustituto sin solicitud. Sigue el [flujo de sesión](docs/guides/agent-workflow.md). Claude Code usa `CLAUDE.md`, envoltorios de estas skills en `.claude/skills/`, seis subagentes en `.claude/agents/` y hooks en `.claude/settings.json` ([auditoría](docs/CLAUDE_CODE.md)).

## Ciclo de issues y Definition of Done

IDs canónicos MOANA-xxx; aliases históricos MOA-xxx. Ciclo: `todo → ready → in_progress → review → done`; `blocked` exige motivo y condición de desbloqueo. Los estados ready, in_progress, review y done exigen dependencias completas. Prioridades P0–P3 y complejidad S/M/L/XL son independientes de las fases P0–P5. Consulta el [ciclo completo](docs/guides/issue-lifecycle.md).

DoD: alcance y criterios satisfechos, pruebas relevantes aprobadas, tipos/lint/build correctos, documentación y trazabilidad sincronizadas, diff revisado y evidencia específica de cada criterio AC y prueba T además del resumen general. El validador comprueba la presencia de evidencia; el responsable verifica su veracidad. Regenera el catálogo derivado antes del cierre.

Reporta cambios, comandos ejecutados, fallos/no comprobado y siguiente paso. Distingue smoke tests del entorno de pruebas del motor. No declares CI remoto, carga de roles, hooks de Codex o aprobación artística humana sin evidencia. Siguiente issue: [MOANA-001](docs/issues/MOANA-001.md).
