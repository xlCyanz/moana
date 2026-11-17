# MOANA-013 — Añadir máscaras y regiones semánticas

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-013
- Aliases históricos: MOA-013
- Phase: P3
- Priority: P1
- Status: blocked
- Complexity: L (relativa, no estimación de tiempo)
- Dependencies: [MOANA-009](MOANA-009.md), [MOANA-010](MOANA-010.md)
- Related modules: layers, schema
- Requirements: R012 ([trazabilidad](traceability.md))
- Bloqueo: Dependencias pendientes: MOANA-010

## Context

La edición por región necesita identidad semántica independiente del PNG.

## Objective

Resolver máscaras DAG y regiones estables para clipping y targeting.

## Scope

Implementar nodos de máscaras binarias y union/intersect/subtract/xor; asociar regiones semánticas a IDs y geometría.

## Out of scope

No inferencia automática de regiones desde un PNG.

## Technical requirements

- Resolver referencias en DAG sin depender del color raster de capas
- Máscaras en coordenadas de canvas; bbox y caché potencial dependen de los nodos fuente

## Proposed implementation

- Definir modelos de máscaras/regiones y booleanas con coordenadas de canvas
- Resolver dependencias antes de render y aplicar clipping al destino

## Acceptance criteria

- [ ] AC1: Una operación enmascarada no modifica píxeles fuera de su máscara
- [ ] AC2: Regiones permiten resolver ojo izquierdo por ID; ciclos y referencias rotas se rechazan antes de render

## Required tests

- [ ] T1: Álgebra de conjuntos en fixtures 1/8/128 píxeles y máscaras vacías
- [ ] T2: Ciclos directos/indirectos, máscara fuera del canvas y grupos transformados

## Expected deliverables

- Modelos y resolución de máscaras/regiones semánticas por IDs estables.
- Fixtures de referencias, ciclos, clipping y selección de una región editable.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- Un grupo transformado requiere semántica clara de máscara en canvas frente a geometría local.

## Guía para agentes de IA

**Estado para agentes:** No empezar: estado `blocked`. Esperar a que [MOANA-009](MOANA-009.md), [MOANA-010](MOANA-010.md) estén `done` y el catálogo marque este issue `ready`.

### 1. Preparación

- Rama: `feat/MOANA-013-anadir-mascaras-regiones` creada desde `develop` actualizado: `git switch develop && git pull --ff-only && git switch -c feat/MOANA-013-anadir-mascaras-regiones`.
- Verificar en `docs/issues/catalog.json` que este issue está `ready` y que sus dependencias ([MOANA-009](MOANA-009.md), [MOANA-010](MOANA-010.md)) están `done`.
- Entorno: `uv sync --locked` (sin uv global: `sh scripts/bootstrap.sh` y después `sh scripts/uv.sh` en lugar de `uv`).
- Al empezar, cambiar `status` a `in_progress` en el catálogo y regenerar con `uv run python scripts/planning.py`.

### 2. Lectura obligatoria (en orden)

1. `CLAUDE.md` (Claude Code) o `AGENTS.md` (Codex) y [flujo de sesión](../guides/agent-workflow.md).
2. MOANA.md: §3 Arquitectura modular; §11 Capas, máscaras y regiones; §25 Definition of Done. Estas secciones son el contrato normativo; ante duda, prevalecen sobre este issue.
3. [Contratos de módulos](../architecture/module-contracts.md) para: `layers`, `schema`.
4. Estándares: [python](../../docs/standards/python.md), [architecture](../../docs/standards/architecture.md), [testing](../../docs/standards/testing.md), [security](../../docs/standards/security.md).
5. Issues de dependencia ([MOANA-009](MOANA-009.md), [MOANA-010](MOANA-010.md)): leer su sección Evidence para conocer las APIs ya entregadas; no reimplementarlas.
6. ADR en `docs/architecture/` que mencionen los módulos afectados.

### 3. Requisitos de MOANA.md cubiertos

| ID | Requisito | Secciones | Verificación exigida |
| --- | --- | --- | --- |
| R012 | Máscaras y regiones semánticas | §11 | DAG, álgebra de máscaras y targeting por ID |

### 4. Skills y subagentes

| Host | Skills a cargar | Revisión especializada |
| --- | --- | --- |
| Claude Code | `moana-graphics`, `moana-python`, `moana-architecture`, `moana-code-review` | `moana-graphics-engineer`, `moana-architect`, `moana-python-engineer` (sólo lectura; el agente principal integra) |
| Codex | `$moana-graphics`, `$moana-python`, `$moana-architecture`, `$moana-code-review` | `moana_graphics_engineer`, `moana_architect`, `moana_python_engineer` |

### 5. Archivos

- Código o documentos a crear/modificar: `src/moana/layers/`, `src/moana/schema/`.
- Pruebas: `tests/unit/layers/`, `tests/unit/schema/`.
- No crear módulos ni carpetas sin comportamiento real. No tocar otros módulos salvo exportaciones imprescindibles, justificadas en el PR.

### 6. Plan de pruebas

- T1: Álgebra de conjuntos en fixtures 1/8/128 píxeles y máscaras vacías
- T2: Ciclos directos/indirectos, máscara fuera del canvas y grupos transformados
- Oráculos independientes (cálculo a mano o fórmula de MOANA.md); nunca copiar la salida de la implementación como expected.
- Incluir casos negativos con el error de dominio esperado y casos borde (vacío, mínimo, máximo, fuera de rango).

### 7. Procedimiento

1. Escribir las pruebas de los criterios AC y T antes o junto con la implementación.
2. Implementar sólo **Scope**; respetar **Out of scope** y las dependencias permitidas de MOANA.md §3.
3. Validación de módulo: `uv run pytest tests/unit/layers/ tests/unit/schema/ -q` y `uv run mypy src/`.
4. Validación completa: `uv run python scripts/validate.py` y `uv run python scripts/check_wheel.py`.
5. Revisión: subagentes listados y skill `moana-code-review`; corregir hallazgos críticos y altos.
6. Si hay salida raster: mostrar el PNG a 1x y ampliado por vecino más cercano; si cambia un golden, presentar expected/actual/diff y justificar.

### 8. Cierre

1. En `docs/issues/catalog.json`, para este issue: `status` → `review` (o `done` tras aprobación); completar `acceptance_evidence` (AC1, AC2), `test_evidence` (T1, T2) y `evidence` con rutas concretas de tests y archivos.
2. Issues que desbloquea ([MOANA-014](MOANA-014.md), [MOANA-015](MOANA-015.md), [MOANA-016](MOANA-016.md), [MOANA-018](MOANA-018.md)): si todas sus dependencias quedan `done`, pasarlos a `ready` con `blocking_reason: null`.
3. Ejecutar `uv run python scripts/planning.py` y `uv run python -m scripts.check_repository`.
4. Abrir PR hacia `develop` enlazando este issue de GitHub (`Closes #<número>`), con comandos ejecutados y evidencia por AC/T. El CI completo corre al integrar `develop` en `main`.
5. Commit y push sólo con autorización del usuario. No declarar CI remoto ni aprobación artística humana sin evidencia.

### 9. Prohibido en este issue

- Implementar alcance de otros issues, incluidos los que desbloquea ([MOANA-014](MOANA-014.md), [MOANA-015](MOANA-015.md), [MOANA-016](MOANA-016.md), [MOANA-018](MOANA-018.md)).
- Actualizar goldens automáticamente, desactivar checks, editar `uv.lock` a mano o añadir dependencias sin motivo técnico registrado.
- `eval`/`exec`/`pickle`, red o estado global mutable en el núcleo; lecturas de texto sin `encoding="utf-8"`.

## Evidence

Pendiente de implementación.
