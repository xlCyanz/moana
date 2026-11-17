# MOANA-006 — Rasterizar primitivas enteras y flood fill

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-006
- Aliases históricos: MOA-006
- Phase: P1
- Priority: P1
- Status: blocked
- Complexity: L (relativa, no estimación de tiempo)
- Dependencies: [MOANA-004](MOANA-004.md), [MOANA-005](MOANA-005.md)
- Related modules: geometry, layers
- Requirements: R003 ([trazabilidad](traceability.md))
- Bloqueo: Dependencias pendientes: MOANA-004, MOANA-005

## Context

Defaults de raster de bibliotecas producen diferencias de un píxel.

## Objective

Producir máscaras de primitivas que cumplan fixtures exactas del contrato.

## Scope

Implementar pixel, line, rect, ellipse, polygon y flood_fill en moana/geometry según reglas exactas de §6.

## Out of scope

No paths Bézier, AA ni trazos de grosor implícito.

## Technical requirements

- Máscaras binarias con empates y bordes normativos; no depender de defaults de ImageDraw
- Flood fill iterativo 4-conectado sobre snapshot de la capa y coste acotado; clipping consistente

## Proposed implementation

- Implementar primitivas en orden pixel/rect/line/ellipse/polygon con oráculos manuales
- Incorporar flood fill iterativo a partir de snapshot de capa recibido como entrada

## Acceptance criteria

- [ ] AC1: Invertir una línea produce la misma máscara y los extremos están incluidos
- [ ] AC2: Rectángulos, elipses y polígonos concuerdan con fixtures manuales; fill no atraviesa límites de color

## Required tests

- [ ] T1: Octantes de línea, degenerados, bordes semiabiertos y autointersecciones even-odd
- [ ] T2: Flood fill de un píxel/todo canvas, coincidencia de color, contención y rechazo por presupuesto
- [ ] T3: Bow-tie con área firmada cero pero interior even-odd no vacío; verificar máscara manual y no usar shoelace como descarte.

## Expected deliverables

- Rasterizadores enteros de primitivas y flood fill acotado.
- Máscaras manuales de bordes, degenerados, polígonos even-odd y relleno.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- Even-odd de autointersecciones no se puede descartar por área firmada cero.

## Guía para agentes de IA

**Estado para agentes:** No empezar: estado `blocked`. Esperar a que [MOANA-004](MOANA-004.md), [MOANA-005](MOANA-005.md) estén `done` y el catálogo marque este issue `ready`.

### 1. Preparación

- Rama: `feat/MOANA-006-rasterizar-primitivas-enteras` creada desde `develop` actualizado: `git switch develop && git pull --ff-only && git switch -c feat/MOANA-006-rasterizar-primitivas-enteras`.
- Verificar en `docs/issues/catalog.json` que este issue está `ready` y que sus dependencias ([MOANA-004](MOANA-004.md), [MOANA-005](MOANA-005.md)) están `done`.
- Entorno: `uv sync --locked` (sin uv global: `sh scripts/bootstrap.sh` y después `sh scripts/uv.sh` en lugar de `uv`).
- Al empezar, cambiar `status` a `in_progress` en el catálogo y regenerar con `uv run python scripts/planning.py`.

### 2. Lectura obligatoria (en orden)

1. `CLAUDE.md` (Claude Code) o `AGENTS.md` (Codex) y [flujo de sesión](../guides/agent-workflow.md).
2. MOANA.md: §3 Arquitectura modular; §6 Geometría y primitivas; §25 Definition of Done. Estas secciones son el contrato normativo; ante duda, prevalecen sobre este issue.
3. [Contratos de módulos](../architecture/module-contracts.md) para: `geometry`, `layers`.
4. Estándares: [python](../../docs/standards/python.md), [architecture](../../docs/standards/architecture.md), [testing](../../docs/standards/testing.md).
5. Issues de dependencia ([MOANA-004](MOANA-004.md), [MOANA-005](MOANA-005.md)): leer su sección Evidence para conocer las APIs ya entregadas; no reimplementarlas.
6. ADR en `docs/architecture/` que mencionen los módulos afectados.

### 3. Requisitos de MOANA.md cubiertos

| ID | Requisito | Secciones | Verificación exigida |
| --- | --- | --- | --- |
| R003 | Primitivas exactas, clipping y flood fill | §6 | Oráculos de píxel por primitiva y casos degenerados |

### 4. Skills y subagentes

| Host | Skills a cargar | Revisión especializada |
| --- | --- | --- |
| Claude Code | `moana-graphics`, `moana-code-review` | `moana-graphics-engineer`, `moana-python-engineer`, `moana-architect` (sólo lectura; el agente principal integra) |
| Codex | `$moana-graphics`, `$moana-code-review` | `moana_graphics_engineer`, `moana_python_engineer`, `moana_architect` |

### 5. Archivos

- Código o documentos a crear/modificar: `src/moana/geometry/`, `src/moana/layers/`.
- Pruebas: `tests/unit/geometry/`, `tests/unit/layers/`.
- No crear módulos ni carpetas sin comportamiento real. No tocar otros módulos salvo exportaciones imprescindibles, justificadas en el PR.

### 6. Plan de pruebas

- T1: Octantes de línea, degenerados, bordes semiabiertos y autointersecciones even-odd
- T2: Flood fill de un píxel/todo canvas, coincidencia de color, contención y rechazo por presupuesto
- T3: Bow-tie con área firmada cero pero interior even-odd no vacío; verificar máscara manual y no usar shoelace como descarte.
- Oráculos independientes (cálculo a mano o fórmula de MOANA.md); nunca copiar la salida de la implementación como expected.
- Incluir casos negativos con el error de dominio esperado y casos borde (vacío, mínimo, máximo, fuera de rango).

### 7. Procedimiento

1. Escribir las pruebas de los criterios AC y T antes o junto con la implementación.
2. Implementar sólo **Scope**; respetar **Out of scope** y las dependencias permitidas de MOANA.md §3.
3. Validación de módulo: `uv run pytest tests/unit/geometry/ tests/unit/layers/ -q` y `uv run mypy src/`.
4. Validación completa: `uv run python scripts/validate.py` y `uv run python scripts/check_wheel.py`.
5. Revisión: subagentes listados y skill `moana-code-review`; corregir hallazgos críticos y altos.
6. Si hay salida raster: mostrar el PNG a 1x y ampliado por vecino más cercano; si cambia un golden, presentar expected/actual/diff y justificar.

### 8. Cierre

1. En `docs/issues/catalog.json`, para este issue: `status` → `review` (o `done` tras aprobación); completar `acceptance_evidence` (AC1, AC2), `test_evidence` (T1, T2, T3) y `evidence` con rutas concretas de tests y archivos.
2. Issues que desbloquea ([MOANA-007](MOANA-007.md), [MOANA-008](MOANA-008.md), [MOANA-009](MOANA-009.md), [MOANA-010](MOANA-010.md)): si todas sus dependencias quedan `done`, pasarlos a `ready` con `blocking_reason: null`.
3. Ejecutar `uv run python scripts/planning.py` y `uv run python -m scripts.check_repository`.
4. Abrir PR hacia `develop` enlazando este issue de GitHub (`Closes #<número>`), con comandos ejecutados y evidencia por AC/T. El CI completo corre al integrar `develop` en `main`.
5. Commit y push sólo con autorización del usuario. No declarar CI remoto ni aprobación artística humana sin evidencia.

### 9. Prohibido en este issue

- Implementar alcance de otros issues, incluidos los que desbloquea ([MOANA-007](MOANA-007.md), [MOANA-008](MOANA-008.md), [MOANA-009](MOANA-009.md), [MOANA-010](MOANA-010.md)).
- Actualizar goldens automáticamente, desactivar checks, editar `uv.lock` a mano o añadir dependencias sin motivo técnico registrado.
- `eval`/`exec`/`pickle`, red o estado global mutable en el núcleo; lecturas de texto sin `encoding="utf-8"`.

## Evidence

Pendiente de implementación.
