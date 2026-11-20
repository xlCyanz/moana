# Moana — instrucciones para Claude Code

Moana es un motor Python determinista de Pixel Art (128 × 128 de referencia) controlable por agentes. **Estado: P0 completado; `moana.core` (MOANA-001), `moana.schema` (MOANA-002) y plan de coste (MOANA-003), lienzo RGBA (MOANA-004), paletas (MOANA-005), primitivas raster con flood fill (MOANA-006), transformaciones pixel-perfect (MOANA-008) capas/composición (MOANA-009) y orquestador de render (MOANA-010) y exportación PNG (MOANA-011) y API pública con CLI estático `moana` (MOANA-012) y máscaras/regiones semánticas (MOANA-013) y paths AggDraw `aggdraw-v1` (MOANA-007) y dithering ordenado Bayer `moana.techniques` (MOANA-016) y contornos `outline` con morfología Chebyshev y análisis de clusters con excepciones por región `moana.api.analyze_clusters` (MOANA-014) y sombreado por bandas con luz discreta `shade` (`moana.techniques.shading`; MOANA-015) y presets de materiales versionados con contorno selectivo (`moana.core.materials`, `moana.techniques.materials`, operaciones `material`/`selective_outline`, comando `set_parameters`, `budget-v8`; MOANA-017) y edición atómica por batches `moana.editing` con `apply_edit`/`moana edit` (MOANA-018) e historial undo/redo en memoria `moana.editing.History` (MOANA-019) y timeline de animación con frames evaluados contra la base y render en streaming con presupuesto acumulado (`moana.animation`, `moana.api.render(frame_id=…)`; MOANA-022, sin CLI) y exportación de spritesheets en grid con manifiesto versionado reversible (`moana.export.export_spritesheet`/`slice_spritesheet`; MOANA-023) y GIF con paleta compartida, transparencia reservada, disposal y política explícita de pérdidas verificada al decodificar (`moana.export.export_gif`; MOANA-024) y APNG/WebP lossless opcionales con capacidades de codec comprobadas en tiempo de ejecución (`moana.export.export_apng`/`export_webp`/`export_capabilities`; MOANA-025) e informes de calidad gráfica con hard checks, advertencias artísticas configurables, métricas y supresiones por región sin puntuación agregada (`moana.quality`, `moana.api.evaluate_quality`; MOANA-026) y corpus artístico de referencia con rúbrica de revisión humana (`examples/corpus/`, `moana.quality.parse_rubric`, `scripts/corpus.py`; MOANA-027, revisión humana pendiente) implementados; harness visual (MOANA-028) y verificación de determinismo entre procesos y plataformas (MOANA-029); suite adversaria `tests/security/` con rechazo antes de reservar memoria o tocar disco en cada frontera del modelo de amenazas (MOANA-030); benchmark informativo de §22 `python -m tests.benchmarks` con línea base versionada (MOANA-031); caché opcional de buffers de capa LRU acotada por bytes `moana.render.RenderCache` con invalidación por digest de dependencias (MOANA-032); persistencia confinada y atómica de proyectos, assets e historial `moana.project` (directorio, `.moana` ZIP y `.moana.json`; MOANA-020) y migraciones explícitas de formato con registro inmutable (sólo 1.0), `migrate_document` puro y `migrate_project` que conserva el original (MOANA-021) implementadas sin fachada ni CLI: `moana edit` sigue sin escribir archivos; guía ejecutable de flujos IA crear/inspeccionar/previsualizar/editar por ID ([ai-workflows](docs/guides/ai-workflows.md), `examples/tutorial/`, verificada en wheel limpio por `scripts/tutorial.py`; MOANA-033) y tiles repetibles y escena modular 128×128 con paleta compartida, IDs por instancia y atlas reversible generados desde fuentes por `scripts/tiles.py` (`examples/tiles/`; MOANA-034, revisión humana y licencia pendientes).** El siguiente issue `ready` está en el [roadmap](docs/issues/roadmap.md).

Las reglas operativas comunes a todos los agentes viven en `AGENTS.md` y se importan aquí; no se duplican:

@AGENTS.md

## Específico de Claude Code

- Fuente de verdad del producto: [MOANA.md](MOANA.md). Léelo por secciones según el issue; no conviertas ejemplos de diseño en APIs.
- Arquitectura y fronteras: [overview](docs/architecture/overview.md), [contratos de módulos](docs/architecture/module-contracts.md), ADR en `docs/architecture/`.
- Flujo de sesión obligatorio: [agent-workflow](docs/guides/agent-workflow.md). Inventario y límites de la configuración: [CLAUDE_CODE.md](docs/CLAUDE_CODE.md).
- Reglas por ruta en `.claude/rules/` (se cargan al tocar archivos coincidentes). Estándares completos en `docs/standards/`.
- Skills: `.claude/skills/moana-*` son envoltorios descubribles de las fuentes canónicas en `.agents/skills/`. Edita la fuente canónica; el checker exige que nombre y descripción coincidan.
- Subagentes en `.claude/agents/`: `moana-architect`, `moana-python-engineer`, `moana-graphics-engineer`, `moana-pixel-artist`, `moana-qa-engineer`, `moana-documentation`. Sólo los de documentación editan; el resto revisa e informa. El agente principal integra y ejecuta el gate.
- Hooks (`.claude/settings.json`): tras editar `.py` se ejecuta Ruff sobre ese archivo; antes de Bash se bloquean force push, reset duro, `--no-verify` y borrados recursivos fuera de artefactos; no se edita `uv.lock` ni `.env`.

## Niveles de validación

| Nivel | Cuándo | Comando |
| --- | --- | --- |
| Rápida | Automática tras cada edición `.py` | hook Ruff del archivo |
| Módulo | Al terminar una unidad | `uv run pytest tests/unit -q` o el archivo afectado; `uv run mypy src/` |
| Completa | Antes de declarar un issue en review/done | `uv run python scripts/validate.py` y `uv run python scripts/check_wheel.py` |
| Pre-commit | Al hacer commit (si se pidió) | `uv run pre-commit run --all-files` |

Sin uv global: `sh scripts/uv.sh` en lugar de `uv`. No ejecutes la suite completa tras cada cambio pequeño.

## Definition of Done (resumen)

Criterios AC y pruebas T del issue con evidencia por ID, gate completo verde, docs/trazabilidad/catálogo regenerados (`uv run python scripts/planning.py`), diff revisado, estado del issue actualizado en `docs/issues/catalog.json`. Detalle: MOANA.md §25 y [ciclo de vida](docs/guides/issue-lifecycle.md). No hagas commit, push ni cambios remotos sin autorización explícita.
