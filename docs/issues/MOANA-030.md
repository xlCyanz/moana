# MOANA-030 — Ejercitar amenazas y entradas adversarias

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-030
- Aliases históricos: MOA-030
- Phase: P5
- Priority: P0
- Status: blocked
- Complexity: L (relativa, no estimación de tiempo)
- Dependencies: [MOANA-003](MOANA-003.md), [MOANA-020](MOANA-020.md), [MOANA-021](MOANA-021.md), [MOANA-022](MOANA-022.md)
- Related modules: tests.security
- Requirements: R026, R027 ([trazabilidad](traceability.md))
- Bloqueo: Dependencias pendientes: MOANA-022

## Context

Los límites nominales pueden saltarse con combinaciones maliciosas.

## Objective

Demostrar rechazo previo a buffers/IO para las fronteras del threat model.

## Scope

Implementar suite de seguridad y propiedades de rechazo para JSON, proyectos, assets, referencias y edición.

## Out of scope

No pentest de servicios externos ni garantía de aislamiento in-process para llamadas nativas bloqueadas.

## Technical requirements

- Generadores acotados Hypothesis y corpus malicioso versionado sin payload ejecutable
- Verificar no reserva/IO previo al rechazo, preservación de destino y errores sin secretos

## Proposed implementation

- Construir corpus adversario acotado y generadores de propiedades
- Instrumentar allocation/IO y límites del proceso de tests

## Acceptance criteria

- [ ] AC1: Todas las fronteras del threat model tienen caso reproducible y mitigación ejercitada
- [ ] AC2: Solicitudes hostiles fallan bajo límites de tiempo/memoria de test y no dejan salida parcial

## Required tests

- [ ] T1: Duplicados JSON, nesting, ciclos, NaN, tamaños enormes y ZIP traversal/bomb
- [ ] T2: Monkeypatch de asignación/IO, mutación parcial de batch, decode enorme y fallo de checksum

## Expected deliverables

- Suite adversaria de documentos, assets, rutas y presupuestos del motor.
- Casos que verifican rechazo antes de asignación/efectos y resumen de amenazas cubiertas.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- Las pruebas hostiles deben ser acotadas y nunca desactivar protecciones de Pillow.

## Guía para agentes de IA

**Estado para agentes:** No empezar: estado `blocked`. Esperar a que [MOANA-003](MOANA-003.md), [MOANA-020](MOANA-020.md), [MOANA-021](MOANA-021.md), [MOANA-022](MOANA-022.md) estén `done` y el catálogo marque este issue `ready`.

### 1. Preparación

- Rama: `feat/MOANA-030-ejercitar-amenazas-entradas` creada desde `develop` actualizado: `git switch develop && git pull --ff-only && git switch -c feat/MOANA-030-ejercitar-amenazas-entradas`.
- Verificar en `docs/issues/catalog.json` que este issue está `ready` y que sus dependencias ([MOANA-003](MOANA-003.md), [MOANA-020](MOANA-020.md), [MOANA-021](MOANA-021.md), [MOANA-022](MOANA-022.md)) están `done`.
- Entorno: `uv sync --locked` (sin uv global: `sh scripts/bootstrap.sh` y después `sh scripts/uv.sh` en lugar de `uv`).
- Al empezar, cambiar `status` a `in_progress` en el catálogo y regenerar con `uv run python scripts/planning.py`.

### 2. Lectura obligatoria (en orden)

1. `CLAUDE.md` (Claude Code) o `AGENTS.md` (Codex) y [flujo de sesión](../guides/agent-workflow.md).
2. MOANA.md: §3 Arquitectura modular; §20 Seguridad y validación; §21 Testing y regresiones visuales; §25 Definition of Done. Estas secciones son el contrato normativo; ante duda, prevalecen sobre este issue.
3. [Contratos de módulos](../architecture/module-contracts.md) para: `tests.security`.
4. Estándares: [testing](../../docs/standards/testing.md), [security](../../docs/standards/security.md).
5. Issues de dependencia ([MOANA-003](MOANA-003.md), [MOANA-020](MOANA-020.md), [MOANA-021](MOANA-021.md), [MOANA-022](MOANA-022.md)): leer su sección Evidence para conocer las APIs ya entregadas; no reimplementarlas.
6. ADR en `docs/architecture/` que mencionen los módulos afectados.

### 3. Requisitos de MOANA.md cubiertos

| ID | Requisito | Secciones | Verificación exigida |
| --- | --- | --- | --- |
| R026 | Validación y seguridad de datos | §20 | Entradas adversarias rechazadas antes de reservar/IO |
| R027 | Testing y regresión visual | §21 | Unit/property/integration y diffs exactos |

### 4. Skills y subagentes

| Host | Skills a cargar | Revisión especializada |
| --- | --- | --- |
| Claude Code | `moana-testing`, `moana-code-review` | `moana-qa-engineer` (sólo lectura; el agente principal integra) |
| Codex | `$moana-testing`, `$moana-code-review` | `moana_qa_engineer` |

### 5. Archivos

- Código o documentos a crear/modificar: `tests/security/`.
- Pruebas: `tests/security/`.
- No crear módulos ni carpetas sin comportamiento real. No tocar otros módulos salvo exportaciones imprescindibles, justificadas en el PR.

### 6. Plan de pruebas

- T1: Duplicados JSON, nesting, ciclos, NaN, tamaños enormes y ZIP traversal/bomb
- T2: Monkeypatch de asignación/IO, mutación parcial de batch, decode enorme y fallo de checksum
- Oráculos independientes (cálculo a mano o fórmula de MOANA.md); nunca copiar la salida de la implementación como expected.
- Incluir casos negativos con el error de dominio esperado y casos borde (vacío, mínimo, máximo, fuera de rango).

### 7. Procedimiento

1. Escribir las pruebas de los criterios AC y T antes o junto con la implementación.
2. Implementar sólo **Scope**; respetar **Out of scope** y las dependencias permitidas de MOANA.md §3.
3. Validación de módulo: `uv run pytest tests/security/ -q` y `uv run mypy src/`.
4. Validación completa: `uv run python scripts/validate.py` y `uv run python scripts/check_wheel.py`.
5. Revisión: subagentes listados y skill `moana-code-review`; corregir hallazgos críticos y altos.
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

Pendiente de implementación.
