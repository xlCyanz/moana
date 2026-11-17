# MOANA-010 — Construir pipeline de render determinista

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-010
- Aliases históricos: MOA-010
- Phase: P2
- Priority: P0
- Status: ready
- Complexity: L (relativa, no estimación de tiempo)
- Dependencies: [MOANA-002](MOANA-002.md), [MOANA-003](MOANA-003.md), [MOANA-006](MOANA-006.md), [MOANA-009](MOANA-009.md)
- Related modules: render
- Requirements: R015, R030 ([trazabilidad](traceability.md))
- Bloqueo: Ninguno

## Context

La reproducibilidad necesita orden explícito y normalización compartida.

## Objective

Producir RenderResult sin modificar documentos ni acceder a disco.

## Scope

Implementar moana/render como orquestador validación-resolución-coste-raster-composición y RenderResult inmutable.

## Out of scope

No caché, concurrencia ni optimizaciones sin benchmark.

## Technical requirements

- Canonicalizar defaults/keys y digest dimensional RGBA según §14
- Registro explícito de operaciones; RNG por ID/coordenadas; sin reloj, hash() ni estado global

## Proposed implementation

- Resolver/costear el documento y construir plan estable
- Ejecutar operaciones y calcular digest dimensional/versiones/RNG por identidad

## Acceptance criteria

- [ ] AC1: El mismo documento produce RGBA y digest idénticos en procesos nuevos
- [ ] AC2: Añadir una operación no cambia la secuencia aleatoria de otra; render no modifica documento ni escribe archivos

## Required tests

- [ ] T1: Variar PYTHONHASHSEED, orden de claves de objeto y repetir en subprocesos
- [ ] T2: Entradas no soportadas, references inválidas, cancelación entre operaciones y límites previos al render

## Expected deliverables

- Pipeline documento→validación→presupuesto→render y RenderResult inmutable.
- Escenas de integración y manifiesto de decisiones/versiones para reproducción.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- hash(), reloj o estado global rompen reproducibilidad aunque el primer test pase.

## Guía para agentes de IA

**Estado para agentes:** Listo: todas las dependencias están `done`; puede empezarse.

### 1. Preparación

- Rama: `feat/MOANA-010-construir-pipeline-render` creada desde `develop` actualizado: `git switch develop && git pull --ff-only && git switch -c feat/MOANA-010-construir-pipeline-render`.
- Verificar en `docs/issues/catalog.json` que este issue está `ready` y que sus dependencias ([MOANA-002](MOANA-002.md), [MOANA-003](MOANA-003.md), [MOANA-006](MOANA-006.md), [MOANA-009](MOANA-009.md)) están `done`.
- Entorno: `uv sync --locked` (sin uv global: `sh scripts/bootstrap.sh` y después `sh scripts/uv.sh` en lugar de `uv`).
- Al empezar, cambiar `status` a `in_progress` en el catálogo y regenerar con `uv run python scripts/planning.py`.

### 2. Lectura obligatoria (en orden)

1. `CLAUDE.md` (Claude Code) o `AGENTS.md` (Codex) y [flujo de sesión](../guides/agent-workflow.md).
2. MOANA.md: §3 Arquitectura modular; §14 Renderizado y determinismo; §25 Definition of Done. Estas secciones son el contrato normativo; ante duda, prevalecen sobre este issue.
3. [Contratos de módulos](../architecture/module-contracts.md) para: `render`.
4. Estándares: [python](../../docs/standards/python.md), [architecture](../../docs/standards/architecture.md), [testing](../../docs/standards/testing.md).
5. Issues de dependencia ([MOANA-002](MOANA-002.md), [MOANA-003](MOANA-003.md), [MOANA-006](MOANA-006.md), [MOANA-009](MOANA-009.md)): leer su sección Evidence para conocer las APIs ya entregadas; no reimplementarlas.
6. ADR en `docs/architecture/` que mencionen los módulos afectados.

### 3. Requisitos de MOANA.md cubiertos

| ID | Requisito | Secciones | Verificación exigida |
| --- | --- | --- | --- |
| R015 | Renderizado determinista | §14 | Digests RGBA en procesos/OS y semillas distintas |
| R030 | Arquitectura modular y documentación | §3 | Dependencias internas y ADR revisados |

### 4. Skills y subagentes

| Host | Skills a cargar | Revisión especializada |
| --- | --- | --- |
| Claude Code | `moana-graphics`, `moana-architecture`, `moana-code-review` | `moana-graphics-engineer`, `moana-architect` (sólo lectura; el agente principal integra) |
| Codex | `$moana-graphics`, `$moana-architecture`, `$moana-code-review` | `moana_graphics_engineer`, `moana_architect` |

### 5. Archivos

- Código o documentos a crear/modificar: `src/moana/render/`.
- Pruebas: `tests/unit/render/`.
- No crear módulos ni carpetas sin comportamiento real. No tocar otros módulos salvo exportaciones imprescindibles, justificadas en el PR.

### 6. Plan de pruebas

- T1: Variar PYTHONHASHSEED, orden de claves de objeto y repetir en subprocesos
- T2: Entradas no soportadas, references inválidas, cancelación entre operaciones y límites previos al render
- Oráculos independientes (cálculo a mano o fórmula de MOANA.md); nunca copiar la salida de la implementación como expected.
- Incluir casos negativos con el error de dominio esperado y casos borde (vacío, mínimo, máximo, fuera de rango).

### 7. Procedimiento

1. Escribir las pruebas de los criterios AC y T antes o junto con la implementación.
2. Implementar sólo **Scope**; respetar **Out of scope** y las dependencias permitidas de MOANA.md §3.
3. Validación de módulo: `uv run pytest tests/unit/render/ -q` y `uv run mypy src/`.
4. Validación completa: `uv run python scripts/validate.py` y `uv run python scripts/check_wheel.py`.
5. Revisión: subagentes listados y skill `moana-code-review`; corregir hallazgos críticos y altos.
6. Si hay salida raster: mostrar el PNG a 1x y ampliado por vecino más cercano; si cambia un golden, presentar expected/actual/diff y justificar.

### 8. Cierre

1. En `docs/issues/catalog.json`, para este issue: `status` → `review` (o `done` tras aprobación); completar `acceptance_evidence` (AC1, AC2), `test_evidence` (T1, T2) y `evidence` con rutas concretas de tests y archivos.
2. Issues que desbloquea ([MOANA-007](MOANA-007.md), [MOANA-011](MOANA-011.md), [MOANA-012](MOANA-012.md), [MOANA-013](MOANA-013.md), [MOANA-018](MOANA-018.md), [MOANA-022](MOANA-022.md), [MOANA-029](MOANA-029.md), [MOANA-031](MOANA-031.md)): si todas sus dependencias quedan `done`, pasarlos a `ready` con `blocking_reason: null`.
3. Ejecutar `uv run python scripts/planning.py` y `uv run python -m scripts.check_repository`.
4. Abrir PR hacia `develop` enlazando este issue de GitHub (`Closes #<número>`), con comandos ejecutados y evidencia por AC/T. El CI completo corre al integrar `develop` en `main`.
5. Commit y push sólo con autorización del usuario. No declarar CI remoto ni aprobación artística humana sin evidencia.

### 9. Prohibido en este issue

- Implementar alcance de otros issues, incluidos los que desbloquea ([MOANA-007](MOANA-007.md), [MOANA-011](MOANA-011.md), [MOANA-012](MOANA-012.md), [MOANA-013](MOANA-013.md), [MOANA-018](MOANA-018.md), [MOANA-022](MOANA-022.md), [MOANA-029](MOANA-029.md), [MOANA-031](MOANA-031.md)).
- Actualizar goldens automáticamente, desactivar checks, editar `uv.lock` a mano o añadir dependencias sin motivo técnico registrado.
- `eval`/`exec`/`pickle`, red o estado global mutable en el núcleo; lecturas de texto sin `encoding="utf-8"`.

## Evidence

Pendiente de implementación.
