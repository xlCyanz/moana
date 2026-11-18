# Moana

Base de un motor Python de Pixel Art programático, determinista y editable, orientado a sprites de 128 × 128. **Estado: motor raster en construcción; render determinista de documentos 1.0 y exportación PNG disponibles desde Python (`moana.api`) y desde el comando estático `moana` (validate/inspect/render/export/capabilities).** El paquete expone `moana.__version__`, `moana.core` (coordenadas, cajas, límites y errores de dominio) `moana.schema` (validación estricta y normalización del documento 1.0, JSON Schema en `schemas/`) el render determinista con su plan de coste (`moana.render.render`, `moana.render.plan_budget`) y el lienzo RGBA con adaptadores NumPy/Pillow (`moana.core.canvas`, `moana.core.pillow_adapter`), paletas/rampas por ID (`moana.palette`) y máscaras raster enteras de primitivas, flood fill y transformaciones pixel-perfect (`moana.geometry`), paths M/L/Q/C/Z con el backend AggDraw `aggdraw-v1` y garantía limitada a versiones ensayadas (`moana.geometry.paths`), dithering ordenado Bayer 2×2/4×4 (`moana.techniques`, operación `dither`), contornos interiores/exteriores editables (operación `outline`) y análisis de clusters (singletons, escalones irregulares) con excepciones por región que nunca modifica el documento (`moana.api.analyze_clusters`), sombreado por bandas (operación `shade`: luz discreta, `facing` authored por banda, índice de rampa recortado y la última banda gana), presets de materiales versionados v1 skin/cloth/metal/wood/stone con textura por celdas determinista (operación `material`, `moana.core.materials`) y contorno selectivo por luz (operación `selective_outline`); el resto de técnicas sigue previsto y composición de capas y grupos source-over entera con máscaras semánticas y regiones por ID (`moana.layers`, `resolve_region`) y exportación PNG RGBA o indexada con escritura atómica y manifiesto (`moana.export.export_png`). La edición atómica por batches (`moana.editing`, `moana.api.apply_edit`, `moana edit DOC BATCH`) está disponible: revisión optimista con `base_revision` + `base_snapshot`, rollback total y sin escribir archivos; el historial undo/redo en memoria (`moana.editing.History`, ramas identificadas por digest) también; la persistencia de proyectos (`moana.project`: manifiesto separado del documento, assets e historial en rutas inmutables por hash, ZIP inspeccionado sin extraer y escritura atómica) está disponible sin fachada ni CLI, con migraciones explícitas de formato que nunca se aplican al leer y conservan el original (`moana.project.migrate_project`); animación y control de calidad siguen previstos.

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
| `examples/specs/` | JSON de diseño; `minimal.moana.json` se renderiza con `moana.render.render` |
| `.agents/skills/` | siete skills propias del proyecto |
| `.codex/` | configuración y ocho roles de agentes locales |
| `.github/` | CI, actualización de acciones y plantillas |

Lee [CONTRIBUTING.md](CONTRIBUTING.md) y [AGENTS.md](AGENTS.md) antes de implementar. La [guía de desarrollo](docs/guides/development.md) detalla el entorno y el flujo Git. Primer issue: [MOANA-001](docs/issues/MOANA-001.md). Con Claude Code, [CLAUDE.md](CLAUDE.md) es el punto de entrada y la [auditoría de Claude Code](docs/CLAUDE_CODE.md) describe reglas, skills, subagentes y hooks. La [auditoría de entorno](docs/CODEX.md) distingue configuraciones disponibles de integraciones activas. El [reporte de inicialización](docs/INITIALIZATION_REPORT.md) conserva evidencias históricas.

La licencia de distribución queda pendiente de decisión del propietario; no se autoriza una publicación automática ni se asigna una licencia por suposición.
