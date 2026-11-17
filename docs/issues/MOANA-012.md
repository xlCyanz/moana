# MOANA-012 — Exponer API pública y CLI estático

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-012
- Aliases históricos: MOA-012
- Phase: P2
- Priority: P1
- Status: blocked
- Complexity: M (relativa, no estimación de tiempo)
- Dependencies: [MOANA-010](MOANA-010.md), [MOANA-011](MOANA-011.md)
- Related modules: api, cli
- Requirements: R014, R038 ([trazabilidad](traceability.md))
- Bloqueo: Dependencias pendientes: MOANA-011

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

**Estado para agentes:** No empezar: estado `blocked`. Esperar a que [MOANA-010](MOANA-010.md), [MOANA-011](MOANA-011.md) estén `done` y el catálogo marque este issue `ready`.

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

Pendiente de implementación.
