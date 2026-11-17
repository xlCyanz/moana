# MOANA-008 — Añadir transformaciones pixel-perfect

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-008
- Aliases históricos: MOA-008
- Phase: P1
- Priority: P1
- Status: blocked
- Complexity: M (relativa, no estimación de tiempo)
- Dependencies: [MOANA-006](MOANA-006.md)
- Related modules: geometry
- Requirements: R040 ([trazabilidad](traceability.md))
- Bloqueo: Dependencias pendientes: MOANA-006

## Context

El escalado o giro implícito puede alterar clusters y pivotes.

## Objective

Transformar píxeles y máscaras con reglas enteras reversibles.

## Scope

Crear traslación, espejo, giro en cuartos de vuelta y escala entera para máscaras y geometría.

## Out of scope

No interpolación suave, deformación ni rotación libre.

## Technical requirements

- Definir pivote y orden explícito; aplicar fórmula de §6 a índices
- Preservar IDs y usar nearest-neighbor; cajas resultan de píxeles transformados

## Proposed implementation

- Implementar transformaciones sobre índices y pivote/origen declarado
- Componer orden, calcular bbox resultante y recortar sólo según contrato

## Acceptance criteria

- [ ] AC1: Cuatro giros de 90 grados reconstruyen el resultado sin pérdida
- [ ] AC2: Espejo doble es identidad y una escala 2 replica cada píxel en 2×2

## Required tests

- [ ] T1: Propiedades de composición/inversas sobre máscaras no cuadradas y pivotes negativos
- [ ] T2: Clipping de objetos parcialmente fuera y rechazo de escala no entera o rotación arbitraria en strict

## Expected deliverables

- Transformaciones enteras y escala nearest-neighbor con pivote/clipping definidos.
- Fixtures de rotaciones, flips, traslaciones y propiedades inversas.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- Giro de cajas geométricas no equivale a giro de índices; probar dimensiones pares e impares.

## Guía para agentes de IA

**Estado para agentes:** No empezar: estado `blocked`. Esperar a que [MOANA-006](MOANA-006.md) estén `done` y el catálogo marque este issue `ready`.

### 1. Preparación

- Rama: `feat/MOANA-008-anadir-transformaciones-pixel` creada desde `develop` actualizado: `git switch develop && git pull --ff-only && git switch -c feat/MOANA-008-anadir-transformaciones-pixel`.
- Verificar en `docs/issues/catalog.json` que este issue está `ready` y que sus dependencias ([MOANA-006](MOANA-006.md)) están `done`.
- Entorno: `uv sync --locked` (sin uv global: `sh scripts/bootstrap.sh` y después `sh scripts/uv.sh` en lugar de `uv`).
- Al empezar, cambiar `status` a `in_progress` en el catálogo y regenerar con `uv run python scripts/planning.py`.

### 2. Lectura obligatoria (en orden)

1. `CLAUDE.md` (Claude Code) o `AGENTS.md` (Codex) y [flujo de sesión](../guides/agent-workflow.md).
2. MOANA.md: §3 Arquitectura modular; §6 Geometría y primitivas; §25 Definition of Done. Estas secciones son el contrato normativo; ante duda, prevalecen sobre este issue.
3. [Contratos de módulos](../architecture/module-contracts.md) para: `geometry`.
4. Estándares: [python](../../docs/standards/python.md), [architecture](../../docs/standards/architecture.md), [testing](../../docs/standards/testing.md).
5. Issues de dependencia ([MOANA-006](MOANA-006.md)): leer su sección Evidence para conocer las APIs ya entregadas; no reimplementarlas.
6. ADR en `docs/architecture/` que mencionen los módulos afectados.

### 3. Requisitos de MOANA.md cubiertos

| ID | Requisito | Secciones | Verificación exigida |
| --- | --- | --- | --- |
| R040 | Transformaciones pixel-perfect | §6 | Identidades de giros/espejos y nearest-neighbor |

### 4. Skills y subagentes

| Host | Skills a cargar | Revisión especializada |
| --- | --- | --- |
| Claude Code | `moana-graphics`, `moana-code-review` | `moana-graphics-engineer`, `moana-python-engineer` (sólo lectura; el agente principal integra) |
| Codex | `$moana-graphics`, `$moana-code-review` | `moana_graphics_engineer`, `moana_python_engineer` |

### 5. Archivos

- Código o documentos a crear/modificar: `src/moana/geometry/`.
- Pruebas: `tests/unit/geometry/`.
- No crear módulos ni carpetas sin comportamiento real. No tocar otros módulos salvo exportaciones imprescindibles, justificadas en el PR.

### 6. Plan de pruebas

- T1: Propiedades de composición/inversas sobre máscaras no cuadradas y pivotes negativos
- T2: Clipping de objetos parcialmente fuera y rechazo de escala no entera o rotación arbitraria en strict
- Oráculos independientes (cálculo a mano o fórmula de MOANA.md); nunca copiar la salida de la implementación como expected.
- Incluir casos negativos con el error de dominio esperado y casos borde (vacío, mínimo, máximo, fuera de rango).

### 7. Procedimiento

1. Escribir las pruebas de los criterios AC y T antes o junto con la implementación.
2. Implementar sólo **Scope**; respetar **Out of scope** y las dependencias permitidas de MOANA.md §3.
3. Validación de módulo: `uv run pytest tests/unit/geometry/ -q` y `uv run mypy src/`.
4. Validación completa: `uv run python scripts/validate.py` y `uv run python scripts/check_wheel.py`.
5. Revisión: subagentes listados y skill `moana-code-review`; corregir hallazgos críticos y altos.
6. Si hay salida raster: mostrar el PNG a 1x y ampliado por vecino más cercano; si cambia un golden, presentar expected/actual/diff y justificar.

### 8. Cierre

1. En `docs/issues/catalog.json`, para este issue: `status` → `review` (o `done` tras aprobación); completar `acceptance_evidence` (AC1, AC2), `test_evidence` (T1, T2) y `evidence` con rutas concretas de tests y archivos.
2. Issues que desbloquea ([MOANA-009](MOANA-009.md), [MOANA-034](MOANA-034.md)): si todas sus dependencias quedan `done`, pasarlos a `ready` con `blocking_reason: null`.
3. Ejecutar `uv run python scripts/planning.py` y `uv run python -m scripts.check_repository`.
4. Abrir PR hacia `develop` enlazando este issue de GitHub (`Closes #<número>`), con comandos ejecutados y evidencia por AC/T. El CI completo corre al integrar `develop` en `main`.
5. Commit y push sólo con autorización del usuario. No declarar CI remoto ni aprobación artística humana sin evidencia.

### 9. Prohibido en este issue

- Implementar alcance de otros issues, incluidos los que desbloquea ([MOANA-009](MOANA-009.md), [MOANA-034](MOANA-034.md)).
- Actualizar goldens automáticamente, desactivar checks, editar `uv.lock` a mano o añadir dependencias sin motivo técnico registrado.
- `eval`/`exec`/`pickle`, red o estado global mutable en el núcleo; lecturas de texto sin `encoding="utf-8"`.

## Evidence

Pendiente de implementación.
