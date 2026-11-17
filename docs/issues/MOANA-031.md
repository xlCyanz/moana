# MOANA-031 — Medir rendimiento y memoria de referencia

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-031
- Aliases históricos: MOA-031
- Phase: P5
- Priority: P1
- Status: blocked
- Complexity: M (relativa, no estimación de tiempo)
- Dependencies: [MOANA-010](MOANA-010.md), [MOANA-022](MOANA-022.md), [MOANA-027](MOANA-027.md)
- Related modules: benchmarks
- Requirements: R028 ([trazabilidad](traceability.md))
- Bloqueo: Dependencias pendientes: MOANA-022, MOANA-027

## Context

No hay objetivos de rendimiento verificados antes de medir corpus real.

## Objective

Publicar latencia/memoria reproducibles y contexto de hardware.

## Scope

Crear benchmark repetible del corpus de §22 y registrar hardware, versiones, warmups, mediana, p95 y memoria.

## Out of scope

No optimización GPU/JIT/paralela antes de disponer de mediciones.

## Technical requirements

- Separar render de I/O, 5 warmups y 30 muestras; buffers y proceso identificados
- Objetivos informativos hasta runner estable; no esconder regresión con tolerancia arbitraria

## Proposed implementation

- Separar render de I/O y medir warmups/muestras de §22
- Registrar mediana/p95/pico y comparar la misma carga sin caché engañosa

## Acceptance criteria

- [ ] AC1: Reporte reproducible indica si 100 ms/2 s/256 MiB se cumplen y en qué máquina
- [ ] AC2: Casos adversos respetan presupuestos aunque incumplan objetivo de latencia

## Required tests

- [ ] T1: Benchmark estático 32 capas/500 rects y animación 16 frames
- [ ] T2: Comprobar contadores, ausencia de trabajo eliminado por caché y comparabilidad de versiones

## Expected deliverables

- Benchmarks reproducibles con warmups, muestras, mediana/p95 y memoria.
- Corpus y reporte de entorno/lock, diferenciando coste de render e I/O.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- No usar fluctuaciones de runners compartidos como gate rígido sin estabilizar entorno.

## Guía para agentes de IA

**Estado para agentes:** No empezar: estado `blocked`. Esperar a que [MOANA-010](MOANA-010.md), [MOANA-022](MOANA-022.md), [MOANA-027](MOANA-027.md) estén `done` y el catálogo marque este issue `ready`.

### 1. Preparación

- Rama: `feat/MOANA-031-medir-rendimiento-memoria` creada desde `develop` actualizado: `git switch develop && git pull --ff-only && git switch -c feat/MOANA-031-medir-rendimiento-memoria`.
- Verificar en `docs/issues/catalog.json` que este issue está `ready` y que sus dependencias ([MOANA-010](MOANA-010.md), [MOANA-022](MOANA-022.md), [MOANA-027](MOANA-027.md)) están `done`.
- Entorno: `uv sync --locked` (sin uv global: `sh scripts/bootstrap.sh` y después `sh scripts/uv.sh` en lugar de `uv`).
- Al empezar, cambiar `status` a `in_progress` en el catálogo y regenerar con `uv run python scripts/planning.py`.

### 2. Lectura obligatoria (en orden)

1. `CLAUDE.md` (Claude Code) o `AGENTS.md` (Codex) y [flujo de sesión](../guides/agent-workflow.md).
2. MOANA.md: §3 Arquitectura modular; §22 Rendimiento y optimización; §25 Definition of Done. Estas secciones son el contrato normativo; ante duda, prevalecen sobre este issue.
3. [Contratos de módulos](../architecture/module-contracts.md) para: `benchmarks`.
4. Estándares: [testing](../../docs/standards/testing.md).
5. Issues de dependencia ([MOANA-010](MOANA-010.md), [MOANA-022](MOANA-022.md), [MOANA-027](MOANA-027.md)): leer su sección Evidence para conocer las APIs ya entregadas; no reimplementarlas.
6. ADR en `docs/architecture/` que mencionen los módulos afectados.

### 3. Requisitos de MOANA.md cubiertos

| ID | Requisito | Secciones | Verificación exigida |
| --- | --- | --- | --- |
| R028 | Rendimiento y recursos medidos | §22 | Benchmark reproducible y memoria acotada |

### 4. Skills y subagentes

| Host | Skills a cargar | Revisión especializada |
| --- | --- | --- |
| Claude Code | `moana-testing`, `moana-code-review` | `moana-qa-engineer`, `moana-python-engineer` (sólo lectura; el agente principal integra) |
| Codex | `$moana-testing`, `$moana-code-review` | `moana_qa_engineer`, `moana_python_engineer` |

### 5. Archivos

- Código o documentos a crear/modificar: `tests/benchmarks/`.
- Pruebas: `tests/benchmarks/`.
- No crear módulos ni carpetas sin comportamiento real. No tocar otros módulos salvo exportaciones imprescindibles, justificadas en el PR.

### 6. Plan de pruebas

- T1: Benchmark estático 32 capas/500 rects y animación 16 frames
- T2: Comprobar contadores, ausencia de trabajo eliminado por caché y comparabilidad de versiones
- Oráculos independientes (cálculo a mano o fórmula de MOANA.md); nunca copiar la salida de la implementación como expected.
- Incluir casos negativos con el error de dominio esperado y casos borde (vacío, mínimo, máximo, fuera de rango).

### 7. Procedimiento

1. Escribir las pruebas de los criterios AC y T antes o junto con la implementación.
2. Implementar sólo **Scope**; respetar **Out of scope** y las dependencias permitidas de MOANA.md §3.
3. Validación de módulo: `uv run pytest tests/benchmarks/ -q` y `uv run mypy src/`.
4. Validación completa: `uv run python scripts/validate.py` y `uv run python scripts/check_wheel.py`.
5. Revisión: subagentes listados y skill `moana-code-review`; corregir hallazgos críticos y altos.
6. Si hay salida raster: mostrar el PNG a 1x y ampliado por vecino más cercano; si cambia un golden, presentar expected/actual/diff y justificar.

### 8. Cierre

1. En `docs/issues/catalog.json`, para este issue: `status` → `review` (o `done` tras aprobación); completar `acceptance_evidence` (AC1, AC2), `test_evidence` (T1, T2) y `evidence` con rutas concretas de tests y archivos.
2. Issues que desbloquea ([MOANA-032](MOANA-032.md)): si todas sus dependencias quedan `done`, pasarlos a `ready` con `blocking_reason: null`.
3. Ejecutar `uv run python scripts/planning.py` y `uv run python -m scripts.check_repository`.
4. Abrir PR hacia `develop` enlazando este issue de GitHub (`Closes #<número>`), con comandos ejecutados y evidencia por AC/T. El CI completo corre al integrar `develop` en `main`.
5. Commit y push sólo con autorización del usuario. No declarar CI remoto ni aprobación artística humana sin evidencia.

### 9. Prohibido en este issue

- Implementar alcance de otros issues, incluidos los que desbloquea ([MOANA-032](MOANA-032.md)).
- Actualizar goldens automáticamente, desactivar checks, editar `uv.lock` a mano o añadir dependencias sin motivo técnico registrado.
- `eval`/`exec`/`pickle`, red o estado global mutable en el núcleo; lecturas de texto sin `encoding="utf-8"`.

## Evidence

Pendiente de implementación.
