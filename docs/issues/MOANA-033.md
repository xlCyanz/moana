# MOANA-033 — Documentar flujos IA y previews editables

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-033
- Aliases históricos: MOA-033
- Phase: P5
- Priority: P1
- Status: done
- Complexity: M (relativa, no estimación de tiempo)
- Dependencies: [MOANA-012](MOANA-012.md), [MOANA-018](MOANA-018.md), [MOANA-020](MOANA-020.md), [MOANA-026](MOANA-026.md)
- Related modules: docs, api
- Requirements: R014, R034, R038 ([trazabilidad](traceability.md))
- Bloqueo: Ninguno

## Context

Las sesiones futuras no conservarán el contexto de esta conversación.

## Objective

Ofrecer un tutorial ejecutable del flujo crear/mostrar/editar con el motor real.

## Scope

Completar tutorial JSON/Python/CLI y flujo de agente desde brief hasta preview y modificación por ID usando capacidades reales.

## Out of scope

No GUI, servicio alojado, credenciales ni envío de mensajes a terceros.

## Technical requirements

- Ejemplos ejecutables con schema vigente, paths relativos autorizados y PNG 1×/4×
- Actualizar skills y capabilities tras implementar; sin proveedor IA obligatorio

## Proposed implementation

- Escribir ejemplos sobre API/CLI implementados y validar schema vigente
- Ejecutar tutorial desde wheel limpio y actualizar skills/capabilities

## Acceptance criteria

- [x] AC1: Un usuario reproduce creación, inspección y recolor con los comandos documentados
- [x] AC2: El agente conserva fuente/revisión y presenta limitaciones sin prometer generación visual inexistente

## Required tests

- [x] T1: Ejecutar snippets/tutorial en entorno wheel limpio
- [x] T2: Validar ejemplos JSON contra schema y comprobar sólo región prevista cambia salvo dependencias declaradas

## Expected deliverables

- Guía de flujos IA para crear, inspeccionar y editar documentos por IDs.
- Ejemplos ejecutables de preview/cambio localizado y recuperación de errores.

## Definition of Done

Cumplir [MOANART.md §25](../../MOANART.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- No documentar una API de diseño como importable antes de completar sus dependencias.

## Guía para agentes de IA

**Estado para agentes:** Completado; usar sólo como referencia del contrato entregado.

### 1. Preparación

- Rama: `feat/MOANA-033-documentar-flujos-ia` creada desde `develop` actualizado: `git switch develop && git pull --ff-only && git switch -c feat/MOANA-033-documentar-flujos-ia`.
- Verificar en `docs/issues/catalog.json` que este issue está `ready` y que sus dependencias ([MOANA-012](MOANA-012.md), [MOANA-018](MOANA-018.md), [MOANA-020](MOANA-020.md), [MOANA-026](MOANA-026.md)) están `done`.
- Entorno: `uv sync --locked` (sin uv global: `sh scripts/bootstrap.sh` y después `sh scripts/uv.sh` en lugar de `uv`).
- Al empezar, cambiar `status` a `in_progress` en el catálogo y regenerar con `uv run python scripts/planning.py`.

### 2. Lectura obligatoria (en orden)

1. `CLAUDE.md` (Claude Code) o `AGENTS.md` (Codex) y [flujo de sesión](../guides/agent-workflow.md).
2. MOANART.md: §1 Visión y objetivos; §3 Arquitectura modular; §13 API pública de Python; §15 Edición no destructiva; §25 Definition of Done. Estas secciones son el contrato normativo; ante duda, prevalecen sobre este issue.
3. [Contratos de módulos](../architecture/module-contracts.md) para: `docs`, `api`.
4. Estándares: [architecture](../../docs/standards/architecture.md), [python](../../docs/standards/python.md), [testing](../../docs/standards/testing.md).
5. Issues de dependencia ([MOANA-012](MOANA-012.md), [MOANA-018](MOANA-018.md), [MOANA-020](MOANA-020.md), [MOANA-026](MOANA-026.md)): leer su sección Evidence para conocer las APIs ya entregadas; no reimplementarlas.
6. ADR en `docs/architecture/` que mencionen los módulos afectados.

### 3. Requisitos de MOANART.md cubiertos

| ID | Requisito | Secciones | Verificación exigida |
| --- | --- | --- | --- |
| R014 | API Python y CLI públicas | §13 | Wheel limpio y contratos de errores/resultados |
| R034 | Codex, roles y flujos de agentes | §3, §13, §25 | Auditoría de capacidades y configuración local válida |
| R038 | Preview y modificación específica por IA | §1, §13, §15 | Tutorial render-preview-edit con IDs preservados |

### 4. Skills y subagentes

| Host | Skills a cargar | Revisión especializada |
| --- | --- | --- |
| Claude Code | `moanart-issue-planning`, `moanart-python`, `moanart-architecture`, `moanart-code-review` | `moanart-documentation`, `moanart-python-engineer`, `moanart-architect` (sólo lectura; el agente principal integra) |
| Codex | `$moanart-issue-planning`, `$moanart-python`, `$moanart-architecture`, `$moanart-code-review` | `moanart_documentation`, `moanart_python_engineer`, `moanart_architect` |

### 5. Archivos

- Código o documentos a crear/modificar: `docs/`, `src/moanart/api/`.
- Pruebas: `tests/test_repository_tools.py`, `tests/unit/api/`.
- No crear módulos ni carpetas sin comportamiento real. No tocar otros módulos salvo exportaciones imprescindibles, justificadas en el PR.

### 6. Plan de pruebas

- T1: Ejecutar snippets/tutorial en entorno wheel limpio
- T2: Validar ejemplos JSON contra schema y comprobar sólo región prevista cambia salvo dependencias declaradas
- Oráculos independientes (cálculo a mano o fórmula de MOANART.md); nunca copiar la salida de la implementación como expected.
- Incluir casos negativos con el error de dominio esperado y casos borde (vacío, mínimo, máximo, fuera de rango).

### 7. Procedimiento

1. Escribir las pruebas de los criterios AC y T antes o junto con la implementación.
2. Implementar sólo **Scope**; respetar **Out of scope** y las dependencias permitidas de MOANART.md §3.
3. Validación de módulo: `uv run pytest tests/test_repository_tools.py tests/unit/api/ -q` y `uv run mypy src/`.
4. Validación completa: `uv run python scripts/validate.py` y `uv run python scripts/check_wheel.py`.
5. Revisión: subagentes listados y skill `moanart-code-review`; corregir hallazgos críticos y altos.
6. Si hay salida raster: mostrar el PNG a 1x y ampliado por vecino más cercano; si cambia un golden, presentar expected/actual/diff y justificar.

### 8. Cierre

1. En `docs/issues/catalog.json`, para este issue: `status` → `review` (o `done` tras aprobación); completar `acceptance_evidence` (AC1, AC2), `test_evidence` (T1, T2) y `evidence` con rutas concretas de tests y archivos.
2. Issues que desbloquea ([MOANA-035](MOANA-035.md)): si todas sus dependencias quedan `done`, pasarlos a `ready` con `blocking_reason: null`.
3. Ejecutar `uv run python scripts/planning.py` y `uv run python -m scripts.check_repository`.
4. Abrir PR hacia `develop` enlazando este issue de GitHub (`Closes #<número>`), con comandos ejecutados y evidencia por AC/T. El CI completo corre al integrar `develop` en `main`.
5. Commit y push sólo con autorización del usuario. No declarar CI remoto ni aprobación artística humana sin evidencia.

### 9. Prohibido en este issue

- Implementar alcance de otros issues, incluidos los que desbloquea ([MOANA-035](MOANA-035.md)).
- Actualizar goldens automáticamente, desactivar checks, editar `uv.lock` a mano o añadir dependencias sin motivo técnico registrado.
- `eval`/`exec`/`pickle`, red o estado global mutable en el núcleo; lecturas de texto sin `encoding="utf-8"`.

## Evidence

- Guía en español docs/guides/ai-workflows.md: brief → documento JSON → moanart capabilities/validate/inspect → export 1× y --scale 4 → moanart edit (set_color por ID con base_revision y base_snapshot) → guardado explícito de edit.document (moanart edit no escribe archivos) → re-validate/re-export → diff que imprime 'bbox (5, 9, 11, 14) changed 28'; mismo flujo en Python (examples/tutorial/potion_flow.py con moanart.api, moanart.project.save_document y MoanArtError); tabla de recuperación con cinco errores reales (4 EDIT_CONFLICT stale_revision, 2 REFERENCE_ERROR unknown_target, 3 BUDGET_EXCEEDED export_dimension/export_area 2048 px, 5 EXPORT_ERROR exists, 2 usage); notas Windows (PowerShell 5.1 redirige en UTF-16).
- Ejemplos examples/tutorial/: potion.moanart.json (16×16 strict, capas bottle/liquid, región potion_liquid, máscara liquid_shape [5,9,11,14)), potion-recolor.edit.json y potion-typo.edit.json. Oráculo a mano: liquid_fill cubre 6×5 = 30 px menos los 2 de liquid_shine dibujados encima ((6,10),(6,11)) = 28 px cambiados, todos dentro de la máscara.
- Fuente única: scripts/tutorial.py parsea los bloques sh de la guía en una lista ordenada de pasos (programa, argumentos, redirección, '# exit N') con parser estricto (rechaza pipes, &&, ;, $, globs, continuaciones y etiquetas de bloque fuera de sh/json/python) y los ejecuta; el test unitario los corre con moanart.cli.main en proceso y python -I; scripts/check_wheel.py::check_tutorial ejecuta los mismos 18 pasos con el moanart instalado del wheel y el python del venv aislado y aplica check_outputs (oráculo de 28 píxeles).
- AC2/limitaciones: sección «Pautas para agentes» (conservar fuente y revisión, sin generación de imágenes, sin persistencia/proyectos/historial por CLI, GIF/APNG/WebP/spritesheets sólo en Python, los informes de calidad no son aprobación humana); punteros en .agents/skills/moanart-pixel-art y moanart-python; enlaces en examples/README.md y agent-workflow.md. Sin cambios en src/; capabilities sin cambios (sigue exacto). mypy cubre examples/.
- Revisiones de agente: documentación (comandos reales re-ejecutados, sin APIs inventadas) y Python (T1 debía ejecutar la guía y no una copia; parser estricto; pasos ordenados) con todas las correcciones aplicadas. Gate local macOS: scripts/validate.py 3686 passed con src/moanart al 100 %, check_wheel OK (tutorial 18 pasos), mypy --platform win32 OK, pre-commit OK; matriz pendiente en main; variantes PowerShell no ejecutadas.
- Aprobado por el propietario el 2026-11-17 tras revisión; PR #73 hacia develop.
- AC1: tests/unit/api/test_tutorial.py::test_guide_shell_blocks_run_as_documented (ejecuta todos los bloques sh de docs/guides/ai-workflows.md con sus códigos de salida, revisión 0→1, affected_ids ['liquid_fill'], PNG 1× 16×16 y 4× 64×64 por vecino, píxeles cambiados = oráculo, examples/ intacto) y ::test_guide_paths_and_python_excerpt_exist; scripts/check_wheel.py::check_tutorial en wheel limpio.
- AC2: Sección «Pautas para agentes» de docs/guides/ai-workflows.md; tests/unit/api/test_tutorial.py::test_documented_failures_are_atomic (stale_revision exit 4 y unknown_target exit 2 sin cambiar el documento) y ::test_python_flow_reports_moanart_errors; .agents/skills/moanart-pixel-art/SKILL.md y moanart-python/SKILL.md.
- T1: scripts/check_wheel.py::check_tutorial (venv aislado sólo con el wheel: 'Installed tutorial OK: 18 documented steps', changed_pixels 28, changed_outside_region 0, revision [0, 1]) sobre scripts/tutorial.py::run_steps/check_outputs; tests/unit/api/test_tutorial.py::test_parser_rejects_unsupported_shell, ::test_parser_reads_redirect_and_exit_code, ::test_unknown_block_language_and_wrong_exit_fail.
- T2: tests/unit/api/test_tutorial.py::test_examples_validate_against_current_schema (claves y schema_version contra schemas/moanart-document-1.0.schema.json, validate_document, batches con revisión y snapshot del documento; el schema publicado = modelo por tests/unit/schema/test_schema_roundtrip.py::test_generated_schema_matches_reviewed_golden) y ::test_recolor_changes_only_the_region_and_preserves_the_rest (sólo cambia el color de liquid_fill, IDs/capas/máscaras/regiones iguales, píxeles cambiados = oráculo a mano).
