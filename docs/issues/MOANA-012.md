# MOANA-012 — Exponer API pública y CLI estático

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-012
- Aliases históricos: MOA-012
- Phase: P2
- Priority: P1
- Status: review
- Complexity: M (relativa, no estimación de tiempo)
- Dependencies: [MOANA-010](MOANA-010.md), [MOANA-011](MOANA-011.md)
- Related modules: api, cli
- Requirements: R014, R038 ([trazabilidad](traceability.md))
- Bloqueo: Ninguno

## Context

Los agentes y programas deben usar la misma interfaz de producto.

## Objective

Ofrecer funciones tipadas y comandos estáticos con errores/capacidades reales.

## Scope

Crear moana/api y comando moana para validate/render/inspect/export estático con resultados y errores documentados.

## Out of scope

No editor interactivo, GUI ni integración con proveedor de IA.

## Technical requirements

- Fachada tipada sin objetos mutables de bibliotecas; añadir entrypoint sólo al funcionar
- CLI con códigos de §13 y paths autorizados por el llamador; capacidades visibles

## Proposed implementation

- Componer servicios en fachada y registrar entrypoint sólo cuando funcione
- Traducir errores de dominio a exit codes y probar desde wheel aislado

## Acceptance criteria

- [ ] AC1: Una instalación limpia del wheel valida un JSON y exporta un PNG de 128×128
- [ ] AC2: Help y errores distinguen capacidades disponibles, entrada inválida, presupuesto e I/O

## Required tests

- [ ] T1: Integración CLI en directorio ajeno al repo con paths con espacios
- [ ] T2: Tests de exit codes, no traceback por defecto, stdout parseable y error de operación futura

## Expected deliverables

- API pública y CLI estático documentados con contratos de retorno/error.
- Ejemplos ejecutables, pruebas de argumentos, códigos de salida e integración.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- Help o ejemplos no deben exponer operaciones aún no implementadas como disponibles.

## Guía para agentes de IA

**Estado para agentes:** En revisión: sólo correcciones de la revisión; no añadir alcance.

### 1. Preparación

- Rama: `feat/MOANA-012-exponer-api-publica` creada desde `develop` actualizado: `git switch develop && git pull --ff-only && git switch -c feat/MOANA-012-exponer-api-publica`.
- Verificar en `docs/issues/catalog.json` que este issue está `ready` y que sus dependencias ([MOANA-010](MOANA-010.md), [MOANA-011](MOANA-011.md)) están `done`.
- Entorno: `uv sync --locked` (sin uv global: `sh scripts/bootstrap.sh` y después `sh scripts/uv.sh` en lugar de `uv`).
- Al empezar, cambiar `status` a `in_progress` en el catálogo y regenerar con `uv run python scripts/planning.py`.

### 2. Lectura obligatoria (en orden)

1. `CLAUDE.md` (Claude Code) o `AGENTS.md` (Codex) y [flujo de sesión](../guides/agent-workflow.md).
2. MOANA.md: §1 Visión y objetivos; §3 Arquitectura modular; §13 API pública de Python; §15 Edición no destructiva; §25 Definition of Done. Estas secciones son el contrato normativo; ante duda, prevalecen sobre este issue.
3. [Contratos de módulos](../architecture/module-contracts.md) para: `api`, `cli`.
4. Estándares: [python](../../docs/standards/python.md), [architecture](../../docs/standards/architecture.md), [testing](../../docs/standards/testing.md), [security](../../docs/standards/security.md).
5. Issues de dependencia ([MOANA-010](MOANA-010.md), [MOANA-011](MOANA-011.md)): leer su sección Evidence para conocer las APIs ya entregadas; no reimplementarlas.
6. ADR en `docs/architecture/` que mencionen los módulos afectados.

### 3. Requisitos de MOANA.md cubiertos

| ID | Requisito | Secciones | Verificación exigida |
| --- | --- | --- | --- |
| R014 | API Python y CLI públicas | §13 | Wheel limpio y contratos de errores/resultados |
| R038 | Preview y modificación específica por IA | §1, §13, §15 | Tutorial render-preview-edit con IDs preservados |

### 4. Skills y subagentes

| Host | Skills a cargar | Revisión especializada |
| --- | --- | --- |
| Claude Code | `moana-python`, `moana-architecture`, `moana-code-review` | `moana-python-engineer`, `moana-architect` (sólo lectura; el agente principal integra) |
| Codex | `$moana-python`, `$moana-architecture`, `$moana-code-review` | `moana_python_engineer`, `moana_architect` |

### 5. Archivos

- Código o documentos a crear/modificar: `src/moana/api/`, `src/moana/cli/`.
- Pruebas: `tests/unit/api/`, `tests/unit/cli/`.
- No crear módulos ni carpetas sin comportamiento real. No tocar otros módulos salvo exportaciones imprescindibles, justificadas en el PR.

### 6. Plan de pruebas

- T1: Integración CLI en directorio ajeno al repo con paths con espacios
- T2: Tests de exit codes, no traceback por defecto, stdout parseable y error de operación futura
- Oráculos independientes (cálculo a mano o fórmula de MOANA.md); nunca copiar la salida de la implementación como expected.
- Incluir casos negativos con el error de dominio esperado y casos borde (vacío, mínimo, máximo, fuera de rango).

### 7. Procedimiento

1. Escribir las pruebas de los criterios AC y T antes o junto con la implementación.
2. Implementar sólo **Scope**; respetar **Out of scope** y las dependencias permitidas de MOANA.md §3.
3. Validación de módulo: `uv run pytest tests/unit/api/ tests/unit/cli/ -q` y `uv run mypy src/`.
4. Validación completa: `uv run python scripts/validate.py` y `uv run python scripts/check_wheel.py`.
5. Revisión: subagentes listados y skill `moana-code-review`; corregir hallazgos críticos y altos.
6. Si hay salida raster: mostrar el PNG a 1x y ampliado por vecino más cercano; si cambia un golden, presentar expected/actual/diff y justificar.

### 8. Cierre

1. En `docs/issues/catalog.json`, para este issue: `status` → `review` (o `done` tras aprobación); completar `acceptance_evidence` (AC1, AC2), `test_evidence` (T1, T2) y `evidence` con rutas concretas de tests y archivos.
2. Issues que desbloquea ([MOANA-018](MOANA-018.md), [MOANA-033](MOANA-033.md)): si todas sus dependencias quedan `done`, pasarlos a `ready` con `blocking_reason: null`.
3. Ejecutar `uv run python scripts/planning.py` y `uv run python -m scripts.check_repository`.
4. Abrir PR hacia `develop` enlazando este issue de GitHub (`Closes #<número>`), con comandos ejecutados y evidencia por AC/T. El CI completo corre al integrar `develop` en `main`.
5. Commit y push sólo con autorización del usuario. No declarar CI remoto ni aprobación artística humana sin evidencia.

### 9. Prohibido en este issue

- Implementar alcance de otros issues, incluidos los que desbloquea ([MOANA-018](MOANA-018.md), [MOANA-033](MOANA-033.md)).
- Actualizar goldens automáticamente, desactivar checks, editar `uv.lock` a mano o añadir dependencias sin motivo técnico registrado.
- `eval`/`exec`/`pickle`, red o estado global mutable en el núcleo; lecturas de texto sin `encoding="utf-8"`.

## Evidence

- src/moana/api/: fachada tipada (load_document desde path autorizado, bytes o mapping con archivo regular abierto sin bloquear y lectura acotada a max_bytes+1; render; export_png RGBA; inspect_document con presupuesto informado; capabilities con lo previsto separado) que sólo compone schema, render y export; retornos congelados sin objetos NumPy/Pillow; apply_edit no se exporta (PLANNED_FUNCTIONS).
- src/moana/cli/: comando estático moana (validate, inspect, render, export --scale/--overwrite, capabilities; edit previsto → UNSUPPORTED_OPERATION 2) con un único objeto JSON por invocación, códigos de salida del error de dominio (0/2/3/4/5/1), stdout cerrado → 5, interrupción → 130 con INTERRUPTED, errores de uso con mensaje fijo, sin abreviaturas y sin traceback salvo --debug; importa sólo moana.api, moana.core.errors y moana.__version__. Entrypoint [project.scripts] moana; uv.lock sin cambios.
- src/moana/core/errors.py: ReadError (READ_ERROR, salida 5) para lecturas fallidas, sin rutas completas; amplía ADR-010 (nota de cabecera).
- scripts/check_wheel.py: instala las dependencias de ejecución fijadas por hash desde el lock (primero offline, después en línea con aviso) y el wheel sin dependencias; ejecuta el moana instalado fuera del repo con paths con espacios, entorno sin PYTHONPATH/PYTHONHOME/VIRTUAL_ENV y timeout, y decodifica el PNG de 128×128.
- ADR-020 (docs/architecture/decisions/ADR-020-public-api-cli.md); MOANA.md 0.1.8-draft (§3 distribución, §13 fachada, firmas reales, inspect_document/capabilities, READ_ERROR, CLI y códigos; ejemplo con moana.schema.snapshot_digest); contratos de módulos, índice de ADR, overview, README, guía de desarrollo, AGENTS.md, CLAUDE.md y docstring del paquete actualizados.
- Trazabilidad: R014 cubierto; R038 cubierto en parte (render y preview desde API/CLI); la edición y el tutorial render-preview-edit quedan para MOANA-018 y MOANA-033.
- Gate: scripts/validate.py y scripts/check_wheel.py verdes; moana.api, moana.cli y moana.core.errors al 100 % de líneas y ramas; mypy también con --platform win32. Sin ejecutar en Windows real (pruebas de FIFO, dispositivo, permisos y pipe real se omiten en win32).
- Revisión: moana-architect (cambios requeridos, aplicados: ReadError en core.errors con ADR-010 ampliado, CLI sólo sobre api, errores de uso sin argv, TypeError en vez de assert, capacidades sin desapariciones, check_wheel offline primero, documentación del contrato) y moana-python-engineer (cambios requeridos, aplicados: BrokenPipe sin traceback, directorio sin permiso → READ_ERROR, JSON pasado como str, FIFO sin bloqueo, --scale estricto, entorno aislado en check_wheel, prueba real de lectura acotada, interrupción en todas las fases, sin abreviaturas, ayuda de edit, --debug tras el comando).
- AC1: scripts/check_wheel.py (check_cli: wheel limpio, moana validate y export fuera del repo, PNG 128×128 decodificado: «Installed CLI OK»); tests/unit/api/test_api_facade.py::test_export_writes_a_verified_128_png.
- AC2: tests/unit/cli/test_cli_main.py::test_help_distinguishes_available_and_planned, ::test_edit_help_says_it_is_planned, ::test_capabilities_lists_available_apart_from_planned, ::test_document_errors_map_to_exit_codes, ::test_io_errors_do_not_leak_the_full_path, ::test_export_overwrite y ::test_planned_command_is_unsupported; tests/unit/api/test_api_facade.py::test_capabilities_separate_available_from_planned y ::test_schema_only_operations_are_reported_as_planned.
- T1: tests/integration/test_cli_paths.py::test_cli_outside_the_repository_with_spaces (script instalado y python -m, paths relativos y absolutos con espacios y ñ/í), ::test_cli_failures_in_a_fresh_process y ::test_console_script_is_installed.
- T2: tests/unit/cli/test_cli_main.py::test_every_domain_error_maps_to_its_exit_code, ::test_document_errors_map_to_exit_codes, ::test_usage_errors_are_invalid_input, ::test_internal_error_hides_the_traceback_unless_debug, ::test_debug_is_accepted_after_the_command, ::test_interrupt_exits_130_with_an_interrupted_error, ::test_closed_stdout_exits_with_the_documented_code, ::test_closed_pipe_in_a_real_process y ::test_planned_command_is_unsupported (operación futura); la fixture run exige una sola línea JSON ASCII en stdout y ningún traceback.
