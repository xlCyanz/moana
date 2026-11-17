# Moana

Base de un motor Python de Pixel Art programático, determinista y editable, orientado a sprites de 128 × 128. **Estado: infraestructura y diseño; el motor todavía no está implementado.** El paquete expone `moana.__version__`, `moana.core` (coordenadas, cajas, límites y errores de dominio) `moana.schema` (validación estricta y normalización del documento 1.0, JSON Schema en `schemas/`) el plan de coste previo al render (`moana.render.plan_budget`) y el lienzo RGBA con adaptadores NumPy/Pillow (`moana.core.canvas`, `moana.core.pillow_adapter`). No existe aún un CLI de dibujo.

La fuente de verdad es [MOANA.md](MOANA.md). Consulta el [roadmap](docs/issues/roadmap.md), los [issues](docs/issues/README.md), las [dependencias](docs/issues/dependency-map.md) y la [trazabilidad](docs/issues/traceability.md). Pillow y NumPy son herramientas; la calidad artística requerirá algoritmos, dirección y evaluación.

## Inicio rápido

Con `uv` instalado:

```sh
uv python install 3.12.16
uv sync --locked
uv run python scripts/validate.py
```

En macOS/Linux, si no tienes uv pero sí Python >=3.9 con venv/pip:

```sh
sh scripts/bootstrap.sh
sh scripts/uv.sh run python -c 'import moana; print(moana.__version__)'
```

El bootstrap guarda uv, Python administrado y cachés dentro de `.tools/` y `.cache/`; no cambia tu PATH ni instalación global. Para esta carpeta puede usarse siempre `sh scripts/uv.sh` en lugar de `uv`. En Windows instala uv siguiendo su documentación oficial y utiliza los comandos uv anteriores.

## Desarrollo

```sh
uv run ruff check .
uv run ruff format --check .
uv run mypy src/
uv run mypy
uv run pytest
uv run python -m scripts.check_repository
uv run python scripts/planning.py --check
uv build
uv run python scripts/check_wheel.py
uv run pre-commit install
uv run pre-commit run --all-files
```

`scripts/validate.py` agrupa lock, lint, formato, tipos, estructura, tests con cobertura y build con Hatchling del lock; guarda diagnósticos en `artifacts/`. Los hooks Git se instalan por checkout. CI está configurado para Python 3.12–3.14 en Linux, macOS y Windows. El [informe actual](docs/BOOTSTRAP_REPORT.md) distingue validación local de ejecuciones observadas en GitHub.

## Organización

| Ruta | Contenido real |
| --- | --- |
| `src/moana/` | metadata mínima del paquete, `py.typed` |
| `tests/` | checks de dependencias y tooling de planificación |
| `scripts/` | bootstrap, validación y generación del backlog |
| `docs/architecture/` | límites de módulos y decisiones |
| `docs/issues/` | catálogo y especificaciones de trabajo |
| `examples/specs/` | JSON de diseño, aún no renderizable por Moana |
| `.agents/skills/` | siete skills propias del proyecto |
| `.codex/` | configuración y ocho roles de agentes locales |
| `.github/` | CI, actualización de acciones y plantillas |

Lee [CONTRIBUTING.md](CONTRIBUTING.md) y [AGENTS.md](AGENTS.md) antes de implementar. La [guía de desarrollo](docs/guides/development.md) detalla el entorno y el flujo Git. Primer issue: [MOANA-001](docs/issues/MOANA-001.md). Con Claude Code, [CLAUDE.md](CLAUDE.md) es el punto de entrada y la [auditoría de Claude Code](docs/CLAUDE_CODE.md) describe reglas, skills, subagentes y hooks. La [auditoría de entorno](docs/CODEX.md) distingue configuraciones disponibles de integraciones activas. El [reporte de inicialización](docs/INITIALIZATION_REPORT.md) conserva evidencias históricas.

La licencia de distribución queda pendiente de decisión del propietario; no se autoriza una publicación automática ni se asigna una licencia por suposición.
