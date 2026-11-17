# MOANA-009 — Implementar capas, grupos y composición

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-009
- Aliases históricos: MOA-009
- Phase: P2
- Priority: P1
- Status: blocked
- Complexity: L (relativa, no estimación de tiempo)
- Dependencies: [MOANA-002](MOANA-002.md), [MOANA-004](MOANA-004.md), [MOANA-005](MOANA-005.md), [MOANA-006](MOANA-006.md), [MOANA-008](MOANA-008.md)
- Related modules: layers
- Requirements: R011 ([trazabilidad](traceability.md))
- Bloqueo: Dependencias pendientes: MOANA-006, MOANA-008

## Context

La composición define la relación entre colores, visibilidad y grupos aislados.

## Objective

Componer capas ordenadas usando una sola fórmula entera source-over.

## Scope

Crear árbol ordenado de capas/grupos, visibilidad, bloqueo y composición normal source-over entera.

## Out of scope

No multiply/screen ni máscaras semánticas todavía.

## Technical requirements

- Orden abajo-arriba; buffer aislado por grupo y opacidad aplicada una vez
- Fórmula de redondeo §11, normalización alpha cero y límite de profundidad

## Proposed implementation

- Crear árbol de capas/grupos con ownership de buffer
- Componer hijos y aplicar opacidad del grupo una sola vez

## Acceptance criteria

- [ ] AC1: Composición de fixture semitransparente coincide con cálculo entero independiente
- [ ] AC2: Cambiar orden/visibilidad produce diferencia prevista; grupos no aplican opacidad por hijo

## Required tests

- [ ] T1: Casos alpha 0/1/127/255 y normalización RGB en transparente
- [ ] T2: Grupos anidados, profundidad límite, capa invisible y strict que rechaza opacidad intermedia

## Expected deliverables

- Árbol de capas/grupos y composición RGBA con opacidad de grupo aplicada una vez.
- Fixtures de orden, visibilidad, alfa parcial y aislamiento de grupos.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- La opacidad por hijo cambia la imagen; el bloqueo afecta edición, no render.

## Guía para agentes de IA

**Estado para agentes:** No empezar: estado `blocked`. Esperar a que [MOANA-002](MOANA-002.md), [MOANA-004](MOANA-004.md), [MOANA-005](MOANA-005.md), [MOANA-006](MOANA-006.md), [MOANA-008](MOANA-008.md) estén `done` y el catálogo marque este issue `ready`.

### 1. Preparación

- Rama: `feat/MOANA-009-implementar-capas-grupos` creada desde `develop` actualizado: `git switch develop && git pull --ff-only && git switch -c feat/MOANA-009-implementar-capas-grupos`.
- Verificar en `docs/issues/catalog.json` que este issue está `ready` y que sus dependencias ([MOANA-002](MOANA-002.md), [MOANA-004](MOANA-004.md), [MOANA-005](MOANA-005.md), [MOANA-006](MOANA-006.md), [MOANA-008](MOANA-008.md)) están `done`.
- Entorno: `uv sync --locked` (sin uv global: `sh scripts/bootstrap.sh` y después `sh scripts/uv.sh` en lugar de `uv`).
- Al empezar, cambiar `status` a `in_progress` en el catálogo y regenerar con `uv run python scripts/planning.py`.

### 2. Lectura obligatoria (en orden)

1. `CLAUDE.md` (Claude Code) o `AGENTS.md` (Codex) y [flujo de sesión](../guides/agent-workflow.md).
2. MOANA.md: §3 Arquitectura modular; §11 Capas, máscaras y regiones; §25 Definition of Done. Estas secciones son el contrato normativo; ante duda, prevalecen sobre este issue.
3. [Contratos de módulos](../architecture/module-contracts.md) para: `layers`.
4. Estándares: [python](../../docs/standards/python.md), [architecture](../../docs/standards/architecture.md), [testing](../../docs/standards/testing.md).
5. Issues de dependencia ([MOANA-002](MOANA-002.md), [MOANA-004](MOANA-004.md), [MOANA-005](MOANA-005.md), [MOANA-006](MOANA-006.md), [MOANA-008](MOANA-008.md)): leer su sección Evidence para conocer las APIs ya entregadas; no reimplementarlas.
6. ADR en `docs/architecture/` que mencionen los módulos afectados.

### 3. Requisitos de MOANA.md cubiertos

| ID | Requisito | Secciones | Verificación exigida |
| --- | --- | --- | --- |
| R011 | Capas, grupos y composición | §11 | Source-over entero y orden/opacidad de grupos |

### 4. Skills y subagentes

| Host | Skills a cargar | Revisión especializada |
| --- | --- | --- |
| Claude Code | `moana-graphics`, `moana-code-review` | `moana-graphics-engineer`, `moana-architect` (sólo lectura; el agente principal integra) |
| Codex | `$moana-graphics`, `$moana-code-review` | `moana_graphics_engineer`, `moana_architect` |

### 5. Archivos

- Código o documentos a crear/modificar: `src/moana/layers/`.
- Pruebas: `tests/unit/layers/`.
- No crear módulos ni carpetas sin comportamiento real. No tocar otros módulos salvo exportaciones imprescindibles, justificadas en el PR.

### 6. Plan de pruebas

- T1: Casos alpha 0/1/127/255 y normalización RGB en transparente
- T2: Grupos anidados, profundidad límite, capa invisible y strict que rechaza opacidad intermedia
- Oráculos independientes (cálculo a mano o fórmula de MOANA.md); nunca copiar la salida de la implementación como expected.
- Incluir casos negativos con el error de dominio esperado y casos borde (vacío, mínimo, máximo, fuera de rango).

### 7. Procedimiento

1. Escribir las pruebas de los criterios AC y T antes o junto con la implementación.
2. Implementar sólo **Scope**; respetar **Out of scope** y las dependencias permitidas de MOANA.md §3.
3. Validación de módulo: `uv run pytest tests/unit/layers/ -q` y `uv run mypy src/`.
4. Validación completa: `uv run python scripts/validate.py` y `uv run python scripts/check_wheel.py`.
5. Revisión: subagentes listados y skill `moana-code-review`; corregir hallazgos críticos y altos.
6. Si hay salida raster: mostrar el PNG a 1x y ampliado por vecino más cercano; si cambia un golden, presentar expected/actual/diff y justificar.

### 8. Cierre

1. En `docs/issues/catalog.json`, para este issue: `status` → `review` (o `done` tras aprobación); completar `acceptance_evidence` (AC1, AC2), `test_evidence` (T1, T2) y `evidence` con rutas concretas de tests y archivos.
2. Issues que desbloquea ([MOANA-010](MOANA-010.md), [MOANA-013](MOANA-013.md)): si todas sus dependencias quedan `done`, pasarlos a `ready` con `blocking_reason: null`.
3. Ejecutar `uv run python scripts/planning.py` y `uv run python -m scripts.check_repository`.
4. Abrir PR hacia `develop` enlazando este issue de GitHub (`Closes #<número>`), con comandos ejecutados y evidencia por AC/T. El CI completo corre al integrar `develop` en `main`.
5. Commit y push sólo con autorización del usuario. No declarar CI remoto ni aprobación artística humana sin evidencia.

### 9. Prohibido en este issue

- Implementar alcance de otros issues, incluidos los que desbloquea ([MOANA-010](MOANA-010.md), [MOANA-013](MOANA-013.md)).
- Actualizar goldens automáticamente, desactivar checks, editar `uv.lock` a mano o añadir dependencias sin motivo técnico registrado.
- `eval`/`exec`/`pickle`, red o estado global mutable en el núcleo; lecturas de texto sin `encoding="utf-8"`.

## Evidence

Pendiente de implementación.
