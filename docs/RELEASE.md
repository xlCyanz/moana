# Release candidate 0.1.0rc2

Checklist de release de MoanArt (MOANA-035, [MOANART.md §25](../MOANART.md)). Este documento prepara un candidato instalable; **no publica nada**. La publicación (PyPI, GitHub Releases, tags) es una acción separada que exige autorización explícita del propietario y no se ha ejecutado para 0.1.0rc2.

0.1.0rc2 es el renombrado completo del proyecto a MoanArt (MOANA-037, [ADR-041](architecture/decisions/ADR-041-rename-moanart.md)): distribución, paquete y comando `moanart`, formatos `moanart-*` y extensiones `.moanart`/`.moanart.json`, sin alias del nombre anterior y con los mismos documentos, digests y RGBA. 0.1.0rc1 se publicó el 2026-11-20 como prerelease de GitHub con el nombre anterior; sus proyectos se convierten con `migrate_project` y sus manifiestos de spritesheet y rúbricas con `migrate_spritesheet_manifest` y `migrate_rubric`.

Las tablas del bloque generado salen del código y de los catálogos con `uv run python scripts/release.py write`; `scripts/release.py check` (y `tests/test_repository_tools.py`) fallan si el documento queda desfasado. El resto del documento se edita a mano.

## Decisión de licencia

- Licencia: **MIT** ([LICENSE](../LICENSE)), «Copyright (c) 2026 xlCyanz and MoanArt contributors».
- Alcance: código, documentación, ejemplos (`examples/`) y corpus artístico (`examples/corpus/`, `examples/tiles/`).
- Decisión: del propietario del repositorio, en la sesión de trabajo del 2026-11-20, registrada en el PR de MOANA-035. Los registros del corpus (`provenance.licence`) y la procedencia de las fuentes de tiles la declaran con esa fecha.
- Empaquetado: `license = "MIT"` y `license-files = ["LICENSE"]` en `pyproject.toml` (PEP 639, Hatchling ≥ 1.27). Sin clasificador `License ::`, que PEP 639 prohíbe junto a una expresión de licencia.
- La licencia no es una aprobación artística: la revisión humana sigue pendiente (ver [Limitaciones](#limitaciones-y-pendientes-explícitos)).

## Tablas generadas

Los codecs APNG y WebP son opcionales: su disponibilidad depende del build de Pillow de cada instalación y se comprueba en tiempo de ejecución con `moanart.export.export_capabilities()` (o `moanart capabilities`); por eso la tabla sólo lista los formatos. «Previsto» significa no ejecutable: el validador lo rechaza con `UNSUPPORTED_OPERATION`. En la auditoría, un requisito cuenta como entregado sólo cuando todos los issues que lo cubren están `done`: estar cubierto en planning no es estar implementado. R031, R036 y R039 dependen de este issue (MOANA-035) y quedan «parcial» hasta su cierre; tras cambiar su estado en el catálogo hay que regenerar este bloque.

<!-- release:begin (generado por scripts/release.py write; no editar) -->

### Versiones

| Elemento | Versión | Fuente |
| --- | --- | --- |
| Paquete | `0.1.0rc2` | `moanart.__version__` |
| Schema de documento | `1.0` | `moanart.schema.capabilities` |
| Formato de proyecto | `1.0` | `moanart.project.manifest` |
| Renderer | `render-v1` | `moanart.render.result` |
| Estimador de presupuesto | `budget-v8` | `moanart.render.budget` |
| Reglas de calidad | `quality-v1` | `moanart.quality.config` |
| Backend vectorial | `aggdraw-v1` (AggDraw ensayado: `1.4.1`) | `moanart.geometry.paths` |
| Migraciones de documento | `1.0`; 0 migraciones registradas | `moanart.schema.DOCUMENT_MIGRATIONS` |
| Migraciones de proyecto | `1.0`; 0 migraciones registradas | `moanart.project.PROJECT_MIGRATIONS` |

### Compatibilidad declarada

| Elemento | Valor | Fuente |
| --- | --- | --- |
| Python | `>=3.12`; clasificadores `3.12`, `3.13`, `3.14` | `pyproject.toml` |
| Matriz CI: Python | `3.12`, `3.13`, `3.14` | `.github/workflows/ci.yml` |
| Matriz CI: sistemas | `ubuntu-latest`, `macos-latest`, `windows-latest` | `.github/workflows/ci.yml` |
| Dependencia de ejecución | `pillow>=12,<14` | `pyproject.toml` |
| Dependencia de ejecución | `numpy>=2.2,<3` | `pyproject.toml` |
| Dependencia de ejecución | `aggdraw>=1.3,<2` | `pyproject.toml` |
| Dependencia de ejecución | `pydantic>=2.10,<3` | `pyproject.toml` |
| Licencia | `MIT` (`LICENSE`) | `pyproject.toml` |

### Capacidades (`moanart.api.capabilities()`)

| Superficie | Implementado | Previsto (no ejecutable) |
| --- | --- | --- |
| Versiones de schema | `1.0` | — |
| Perfiles de color | `rgba`, `strict` | — |
| Operaciones | `dither`, `ellipse`, `line`, `material`, `outline`, `path`, `pixel`, `polygon`, `rect`, `selective_outline`, `shade` | `flood_fill` |
| Máscaras | `ellipse`, `intersect`, `line`, `path`, `pixel`, `polygon`, `rect`, `subtract`, `union`, `xor` | — |
| Colecciones | `animations`, `masks`, `regions` | `materials` |
| Modos de fusión | `normal` | `multiply`, `screen` |
| Campos de capa | — | `children`, `transform` |
| Funciones de `moanart.api` | `analyze_clusters`, `apply_edit`, `capabilities`, `edit_document`, `evaluate_quality`, `export_png`, `inspect_document`, `load_document`, `load_edit_batch`, `render`, `resolve_region` | — |
| Comandos de edición | `insert_operation`, `remove`, `reorder`, `replace_palette_color`, `set_color`, `set_geometry`, `set_parameters`, `set_visibility`, `translate` | — |
| Exportación desde el CLI | `png` | — |
| Exportación desde Python | `png`, `gif`, `apng` (opcional), `webp` (opcional) | — |
| Backends vectoriales | `aggdraw-v1` | — |

### Auditoría de requisitos (40; implementado: 36; implementado con pendientes: 4; parcial: 0; pendiente: 0)

| ID | Requisito | Issues (estado) | Entrega | Pendiente |
| --- | --- | --- | --- | --- |
| R001 | Visión, alcance y especificación exhaustiva | MOANA-000 (done) | implementado | — |
| R002 | Lienzo, coordenadas y buffers RGBA seguros | MOANA-001 (done), MOANA-004 (done) | implementado | — |
| R003 | Primitivas exactas, clipping y flood fill | MOANA-006 (done) | implementado | — |
| R004 | Geometría complementaria AggDraw | MOANA-007 (done) | implementado | — |
| R005 | Técnicas profesionales y calidad artística | MOANA-017 (done), MOANA-026 (done), MOANA-027 (done), MOANA-034 (done) | implementado con pendientes | revisión artística humana del corpus pendiente (ningún ejemplo es profesional) |
| R006 | Siluetas, contornos y clusters | MOANA-014 (done) | implementado | — |
| R007 | Paletas, ramps y perfiles de color | MOANA-005 (done) | implementado | — |
| R008 | Iluminación y sombreado por bandas | MOANA-015 (done) | implementado | — |
| R009 | Dithering controlado | MOANA-016 (done) | implementado | — |
| R010 | Materiales editables y reproducibles | MOANA-017 (done) | implementado | — |
| R011 | Capas, grupos y composición | MOANA-009 (done) | implementado | — |
| R012 | Máscaras y regiones semánticas | MOANA-013 (done) | implementado | — |
| R013 | JSON estricto y schema para agentes | MOANA-002 (done) | implementado | — |
| R014 | API Python y CLI públicas | MOANA-012 (done), MOANA-033 (done) | implementado | — |
| R015 | Renderizado determinista | MOANA-007 (done), MOANA-010 (done), MOANA-029 (done), MOANA-032 (done) | implementado con pendientes | matriz de CI remota verde (9 trabajos + determinismo) en `3857617`, run 44777404728; falta observarla sobre el commit candidato |
| R016 | Edición no destructiva atómica | MOANA-018 (done) | implementado | — |
| R017 | Historial y undo/redo | MOANA-019 (done) | implementado | — |
| R018 | Formato de proyectos y assets | MOANA-020 (done) | implementado | — |
| R019 | Versionado y migraciones | MOANA-021 (done) | implementado | — |
| R020 | Animaciones, duraciones y pivotes | MOANA-022 (done) | implementado | — |
| R021 | Spritesheets y manifest | MOANA-023 (done) | implementado | — |
| R022 | Exportación PNG RGBA/indexada | MOANA-011 (done) | implementado | — |
| R023 | Exportación GIF | MOANA-024 (done) | implementado | — |
| R024 | Formatos adicionales | MOANA-025 (done) | implementado | — |
| R025 | Evaluación gráfica y diagnósticos | MOANA-014 (done), MOANA-026 (done) | implementado | — |
| R026 | Validación y seguridad de datos | MOANA-001 (done), MOANA-002 (done), MOANA-003 (done), MOANA-020 (done), MOANA-030 (done) | implementado | — |
| R027 | Testing y regresión visual | MOANA-004 (done), MOANA-027 (done), MOANA-028 (done), MOANA-029 (done), MOANA-030 (done) | implementado | — |
| R028 | Rendimiento y recursos medidos | MOANA-003 (done), MOANA-031 (done), MOANA-032 (done), MOANA-036 (done) | implementado | — |
| R029 | Caché e incrementalidad | MOANA-032 (done) | implementado | — |
| R030 | Arquitectura modular y documentación | MOANA-000 (done), MOANA-001 (done), MOANA-010 (done), MOANA-037 (done) | implementado | — |
| R031 | Paquete instalable y artefactos | MOANA-000 (done), MOANA-035 (done), MOANA-037 (done) | implementado | — |
| R032 | Entorno Python y herramientas de calidad | MOANA-000 (done) | implementado | — |
| R033 | Siete skills especializadas | MOANA-000 (done), MOANA-037 (done) | implementado | — |
| R034 | Codex, roles y flujos de agentes | MOANA-000 (done), MOANA-033 (done) | implementado | — |
| R035 | Hooks y automatización CI | MOANA-000 (done), MOANA-029 (done) | implementado con pendientes | matriz de CI remota verde (9 trabajos + determinismo) en `3857617`, run 44777404728; falta observarla sobre el commit candidato |
| R036 | Issues, roadmap, dependencias y trazabilidad | MOANA-000 (done), MOANA-035 (done) | implementado | — |
| R037 | Objetos, tiles y escenarios | MOANA-034 (done) | implementado con pendientes | revisión artística humana de tiles y escena pendiente |
| R038 | Preview y modificación específica por IA | MOANA-012 (done), MOANA-018 (done), MOANA-027 (done), MOANA-033 (done) | implementado | — |
| R039 | Criterios de aceptación y Definition of Done | MOANA-000 (done), MOANA-035 (done) | implementado | — |
| R040 | Transformaciones pixel-perfect | MOANA-008 (done) | implementado | — |

<!-- release:end -->

## Evidencia de calidad archivada

| Área | Evidencia | Cómo reproducir |
| --- | --- | --- |
| Gate local | lock, Ruff, formato, mypy, estructura, tests con cobertura y build de sdist y wheel | `uv run python scripts/validate.py`; además `uv run mypy --platform win32` |
| Wheel y sdist limpios | ambos artefactos se instalan en entornos separados sin checkout: CLI, tutorial, migraciones y corpus | `uv run python scripts/check_wheel.py` |
| Trazabilidad | DAG del backlog, requisitos sin huérfanos y documentos generados al día | `uv run python scripts/planning.py --check`, `uv run python -m scripts.check_repository` |
| Corpus | registros, procedencia, digests, informes de calidad y rúbrica (5 ejemplos, revisión humana pendiente) | `uv run python scripts/corpus.py check` |
| Tiles | escena derivada al día, costuras y espejos | `uv run python scripts/tiles.py check` |
| JSON Schema | `schemas/` coincide con los modelos | `uv run python scripts/generate_schema.py --check` |
| Seguridad | suite adversaria por frontera de [SECURITY_MODEL.md](architecture/SECURITY_MODEL.md) | `uv run pytest tests/security -q` |
| Determinismo | manifiesto RGBA revisado entre procesos; comparación entre plataformas en la matriz de CI de `main` | `uv run python -m scripts.determinism report --output artifacts/determinism` |
| Rendimiento | línea base informativa de MOANART.md §22 en [tests/benchmarks/results](../tests/benchmarks/results/macos-arm64-py312.md) (regenerada con `0.1.0rc2` el 2026-11-22 sobre `develop` `dde4ff8` con el renombrado sin commit, porque el formato del informe cambió: render estático 29,7 ms, animación de 16 frames 652,7 ms, pico de proceso 61,0 MiB; todos los objetivos se cumplen) | `uv run python -m tests.benchmarks run` y `compare` |

CI remoto (matriz `ubuntu/macos/windows × Python 3.12–3.14` más comparación de determinismo, lanzada con `workflow_dispatch`). Las ejecuciones siguientes son de 0.1.0rc1; la de 0.1.0rc2 sólo se observará cuando el renombrado llegue a `main`:

- `develop` `714c2f6`: [run 44768996258](https://github.com/xlCyanz/moana/actions/runs/44768996258) **falló** (8 de 9 trabajos: portabilidad en Windows, Linux y Python 3.14; los digests de determinismo coincidían). Era la primera ejecución remota real de la matriz: hasta entonces sólo corría en `main`.
- Corrección en PR #75 ([ADR-039](architecture/decisions/ADR-039-ci-matrix-portability.md)), commit `3857617`: [run 44777404728](https://github.com/xlCyanz/moana/actions/runs/44777404728) **verde**, 9/9 trabajos y determinismo entre plataformas.
- Commit candidato de MOANA-035 `69b7ddc`: [run 44783751159](https://github.com/xlCyanz/moana/actions/runs/44783751159). Terminó **verde**: 9/9 trabajos y determinismo entre plataformas. El merge se hizo antes de que acabara, por decisión del propietario, cuando iban 5/9 trabajos verdes y 4 en curso.

## Definition of Done de la release (MOANART.md §25)

- [x] Wheel y sdist se construyen una vez y se instalan limpios en entornos separados (`scripts/check_wheel.py`).
- [x] Tutorial de [flujos IA](guides/ai-workflows.md) y corpus funcionan desde la instalación, sin checkout.
- [x] Migración probada: `migrate_document` y `migrate_project` sobre una copia, con el original intacto (también desde wheel y sdist).
- [x] Changelog con versiones de paquete, schema, renderer y estimador ([CHANGELOG.md](../CHANGELOG.md)).
- [x] Licencia decidida por el propietario y registrada (MIT).
- [x] Threat model y suite adversaria vigentes ([SECURITY_MODEL.md](architecture/SECURITY_MODEL.md), `tests/security/`).
- [x] Presupuesto de rendimiento medido (línea base informativa).
- [x] Trazabilidad y auditoría de requisitos generadas desde los catálogos.
- [ ] Matriz de CI remota verde observada para el commit candidato de 0.1.0rc2 (ver «CI remoto» arriba).
- [ ] Corpus y rúbrica revisados por una persona (pendiente; ningún ejemplo es profesional).
- [ ] Autorización explícita de publicación de 0.1.0rc2: pendiente. (El propietario autorizó el 2026-11-20 publicar `0.1.0rc1` como prerelease de GitHub, no PyPI, con la revisión artística humana pendiente declarada.)

## Limitaciones y pendientes explícitos

- **Revisión artística humana pendiente** para todo el arte generado por agentes: corpus de `examples/corpus/` (MOANA-027), tiles y escena de `examples/tiles/` (MOANA-034) y los ejemplos de técnicas de `examples/specs/` (MOANA-014 a MOANA-022: contornos, sombreado, materiales, animación). Las notas de agente no cuentan como revisión ni aprobación.
- **Publicación**: 0.1.0rc1 es la prerelease de GitHub `v0.1.0rc1` (tag sobre `main`, wheel y sdist adjuntos, con el nombre anterior); 0.1.0rc2 no está publicada. No hay paquete en PyPI: subirlo exige las credenciales del propietario. Nada en este repositorio publica automáticamente.
- **Ruptura de nombre**: quien instaló 0.1.0rc1 debe reinstalar con la distribución `moanart`; no hay import ni comando del nombre anterior. El repositorio remoto y la etiqueta del backlog en GitHub conservan el nombre anterior (ADR-041).
- **Persistencia e historial sin CLI ni fachada**: `moanart.project` (proyectos, migraciones) y `moanart.editing.History` sólo desde Python; `moanart edit` no escribe archivos.
- **Animación, spritesheets, GIF, APNG y WebP sin CLI**: sólo desde Python (`moanart.animation`, `moanart.export`). APNG/WebP dependen del codec de cada build de Pillow.
- **Capacidades previstas no ejecutables**: `flood_fill` como operación, `multiply`/`screen`, colección `materials` con contenido, `children`/`transform` en capas (ver la tabla de capacidades).
- **Calidad artística**: los informes de `moanart.quality` no puntúan ni garantizan calidad profesional; contraste entre partes, lectura de silueta y coherencia de luz no están implementados.
- **Schema 1.0** quedará cerrado con la primera publicación; después, toda ampliación de gramática sube el minor (MOANART.md §12 y §16).
- **Benchmark** informativo, medido en una sola máquina (macOS arm64); sin runner estable de referencia.

## Pasos de publicación (ejecutados el 2026-11-20 para la prerelease de GitHub de 0.1.0rc1; PyPI no; pendientes para 0.1.0rc2)

Requieren autorización explícita del propietario para esa acción concreta; preparar este candidato no la concede.

1. Rellenar «CI remoto» con la ejecución observada de la matriz de `main` para el commit candidato (enlace y resultado de los 9 trabajos más la comparación de determinismo).
2. Confirmar que `scripts/release.py check`, `scripts/validate.py` y `scripts/check_wheel.py` pasan en ese commit.
3. Decidir si se publica con la revisión artística humana pendiente (y comunicarlo así) o esperar a la revisión.
4. Crear el tag `v0.1.0rc2` sobre el commit verificado.
5. Construir los artefactos en limpio (`uv build`), comprobarlos (`scripts/check_wheel.py`) y subirlos al índice elegido con las credenciales del propietario.
6. Crear la GitHub Release del tag con la sección `0.1.0rc2` del changelog y estas limitaciones.
