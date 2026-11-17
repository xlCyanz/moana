# Moana

Base de un motor Python de Pixel Art programático, determinista y editable, orientado a sprites de 128 × 128. **Estado: infraestructura y diseño; el motor todavía no está implementado.** El paquete sólo expone `moana.__version__`. No existe aún un CLI de dibujo.

La fuente de verdad es [MOANA.md](MOANA.md). Consulta el [roadmap](docs/ROADMAP.md), los [issues](docs/issues/README.md) y la [trazabilidad](docs/TRACEABILITY.md). Pillow y NumPy son herramientas; la calidad artística requerirá algoritmos, dirección y evaluación.

## Inicio rápido

Con `uv` instalado:

```sh
uv python install 3.12
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
uv run mypy
uv run pytest
uv run python -m scripts.check_repository
uv run python scripts/planning.py --check
uv run python -m build --no-isolation
uv run pre-commit install
uv run pre-commit run --all-files
```

`scripts/validate.py` agrupa lock, lint, formato, tipos, estructura, tests y build; no modifica baselines. Los hooks Git se instalan por checkout. CI ejecuta Python 3.12–3.14 en Linux, macOS y Windows. Publicar el repositorio y ejecutar Actions remoto son pasos posteriores.

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
| `.codex/` | configuración y roles de agentes locales |
| `.github/` | CI, actualización de acciones y plantillas |

Lee [CONTRIBUTING.md](CONTRIBUTING.md) y [AGENTS.md](AGENTS.md) antes de implementar. Primer issue: [MOA-001](docs/issues/MOA-001.md). La [auditoría de entorno](docs/CODEX.md) distingue configuraciones disponibles de integraciones activas. El [reporte de inicialización](docs/INITIALIZATION_REPORT.md) recoge evidencias y limitaciones.

La licencia de distribución queda pendiente de decisión del propietario; no se autoriza una publicación automática ni se asigna una licencia por suposición.
