# MOANA-003 — Aplicar presupuesto de trabajo y recursos

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-003
- Aliases históricos: MOA-003
- Phase: P1
- Priority: P0
- Status: blocked
- Complexity: L (relativa, no estimación de tiempo)
- Dependencies: [MOANA-001](MOANA-001.md), [MOANA-002](MOANA-002.md)
- Related modules: core, render
- Requirements: R026, R028 ([trazabilidad](traceability.md))
- Bloqueo: Dependencias pendientes: MOANA-002

## Context

Límites por operación no impiden costes acumulados o temporales enormes.

## Objective

Rechazar trabajo excesivo antes de asignar memoria o entrar a librerías nativas.

## Scope

Implementar plan de coste previo al render con límites de operaciones, buffers, visitas de píxel y frames según §20.

## Out of scope

No construir un servicio aislado ni tratar el timeout cooperativo como límite de proceso.

## Technical requirements

- Contabilizar temporales y bbox recortada, y coste de segmentos antes de clipping
- Los documentos no pueden aumentar límites; deadline cooperativo separado de límites duros del anfitrión

## Proposed implementation

- Crear estimadores por operación y acumulador de presupuesto de plan
- Introducir checkpoints cooperativos y documentar límite duro del proceso anfitrión

## Acceptance criteria

- [ ] AC1: Una solicitud que exceda cualquier límite falla antes de crear un buffer raster
- [ ] AC2: Se informa recurso, límite y coste estimado; una solicitud justo en el límite se admite

## Required tests

- [ ] T1: Instrumentar allocators falsos para comprobar ausencia de reservas al rechazar
- [ ] T2: Casos de coordenadas enormes, capas profundas, muchos frames y overflow de productos

## Expected deliverables

- Estimador de trabajo, memoria y temporales con rechazo previo a reservas.
- Pruebas de límites y diagnósticos de presupuesto por operación/documento.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- Un timeout cooperativo no interrumpe una llamada C bloqueada; nunca presentarlo como aislamiento.

## Guía para agentes de IA

**Estado para agentes:** No empezar: estado `blocked`. Esperar a que [MOANA-001](MOANA-001.md), [MOANA-002](MOANA-002.md) estén `done` y el catálogo marque este issue `ready`.

### 1. Preparación

- Rama: `feat/MOANA-003-aplicar-presupuesto-trabajo` creada desde `develop` actualizado: `git switch develop && git pull --ff-only && git switch -c feat/MOANA-003-aplicar-presupuesto-trabajo`.
- Verificar en `docs/issues/catalog.json` que este issue está `ready` y que sus dependencias ([MOANA-001](MOANA-001.md), [MOANA-002](MOANA-002.md)) están `done`.
- Entorno: `uv sync --locked` (sin uv global: `sh scripts/bootstrap.sh` y después `sh scripts/uv.sh` en lugar de `uv`).
- Al empezar, cambiar `status` a `in_progress` en el catálogo y regenerar con `uv run python scripts/planning.py`.

### 2. Lectura obligatoria (en orden)

1. `CLAUDE.md` (Claude Code) o `AGENTS.md` (Codex) y [flujo de sesión](../guides/agent-workflow.md).
2. MOANA.md: §3 Arquitectura modular; §20 Seguridad y validación; §22 Rendimiento y optimización; §25 Definition of Done. Estas secciones son el contrato normativo; ante duda, prevalecen sobre este issue.
3. [Contratos de módulos](../architecture/module-contracts.md) para: `core`, `render`.
4. Estándares: [python](../../docs/standards/python.md), [architecture](../../docs/standards/architecture.md), [testing](../../docs/standards/testing.md).
5. Issues de dependencia ([MOANA-001](MOANA-001.md), [MOANA-002](MOANA-002.md)): leer su sección Evidence para conocer las APIs ya entregadas; no reimplementarlas.
6. ADR en `docs/architecture/` que mencionen los módulos afectados.

### 3. Requisitos de MOANA.md cubiertos

| ID | Requisito | Secciones | Verificación exigida |
| --- | --- | --- | --- |
| R026 | Validación y seguridad de datos | §20 | Entradas adversarias rechazadas antes de reservar/IO |
| R028 | Rendimiento y recursos medidos | §22 | Benchmark reproducible y memoria acotada |

### 4. Skills y subagentes

| Host | Skills a cargar | Revisión especializada |
| --- | --- | --- |
| Claude Code | `moana-python`, `moana-graphics`, `moana-architecture`, `moana-code-review` | `moana-python-engineer`, `moana-architect`, `moana-graphics-engineer` (sólo lectura; el agente principal integra) |
| Codex | `$moana-python`, `$moana-graphics`, `$moana-architecture`, `$moana-code-review` | `moana_python_engineer`, `moana_architect`, `moana_graphics_engineer` |

### 5. Archivos

- Código o documentos a crear/modificar: `src/moana/core/`, `src/moana/render/`.
- Pruebas: `tests/unit/core/`, `tests/unit/render/`.
- No crear módulos ni carpetas sin comportamiento real. No tocar otros módulos salvo exportaciones imprescindibles, justificadas en el PR.

### 6. Plan de pruebas

- T1: Instrumentar allocators falsos para comprobar ausencia de reservas al rechazar
- T2: Casos de coordenadas enormes, capas profundas, muchos frames y overflow de productos
- Oráculos independientes (cálculo a mano o fórmula de MOANA.md); nunca copiar la salida de la implementación como expected.
- Incluir casos negativos con el error de dominio esperado y casos borde (vacío, mínimo, máximo, fuera de rango).

### 7. Procedimiento

1. Escribir las pruebas de los criterios AC y T antes o junto con la implementación.
2. Implementar sólo **Scope**; respetar **Out of scope** y las dependencias permitidas de MOANA.md §3.
3. Validación de módulo: `uv run pytest tests/unit/core/ tests/unit/render/ -q` y `uv run mypy src/`.
4. Validación completa: `uv run python scripts/validate.py` y `uv run python scripts/check_wheel.py`.
5. Revisión: subagentes listados y skill `moana-code-review`; corregir hallazgos críticos y altos.
6. Si hay salida raster: mostrar el PNG a 1x y ampliado por vecino más cercano; si cambia un golden, presentar expected/actual/diff y justificar.

### 8. Cierre

1. En `docs/issues/catalog.json`, para este issue: `status` → `review` (o `done` tras aprobación); completar `acceptance_evidence` (AC1, AC2), `test_evidence` (T1, T2) y `evidence` con rutas concretas de tests y archivos.
2. Issues que desbloquea ([MOANA-004](MOANA-004.md), [MOANA-010](MOANA-010.md), [MOANA-030](MOANA-030.md)): si todas sus dependencias quedan `done`, pasarlos a `ready` con `blocking_reason: null`.
3. Ejecutar `uv run python scripts/planning.py` y `uv run python -m scripts.check_repository`.
4. Abrir PR hacia `develop` enlazando este issue de GitHub (`Closes #<número>`), con comandos ejecutados y evidencia por AC/T. El CI completo corre al integrar `develop` en `main`.
5. Commit y push sólo con autorización del usuario. No declarar CI remoto ni aprobación artística humana sin evidencia.

### 9. Prohibido en este issue

- Implementar alcance de otros issues, incluidos los que desbloquea ([MOANA-004](MOANA-004.md), [MOANA-010](MOANA-010.md), [MOANA-030](MOANA-030.md)).
- Actualizar goldens automáticamente, desactivar checks, editar `uv.lock` a mano o añadir dependencias sin motivo técnico registrado.
- `eval`/`exec`/`pickle`, red o estado global mutable en el núcleo; lecturas de texto sin `encoding="utf-8"`.

## Evidence

Pendiente de implementación.
