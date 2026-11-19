# MOANA-032 — Optimizar caché y render incremental acotados

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-032
- Aliases históricos: MOA-032
- Phase: P5
- Priority: P2
- Status: ready
- Complexity: L (relativa, no estimación de tiempo)
- Dependencies: [MOANA-018](MOANA-018.md), [MOANA-031](MOANA-031.md)
- Related modules: render
- Requirements: R029, R028, R015 ([trazabilidad](traceability.md))
- Bloqueo: Ninguno

## Context

La optimización debe conservar semántica, presupuesto e inmutabilidad.

## Objective

Reducir trabajo sólo donde exista beneficio medido sin cambiar RGBA.

## Scope

Agregar caché LRU por bytes y dirty regions únicamente donde el benchmark demuestre beneficio.

## Out of scope

No paralelismo ni optimizaciones sin mejora medible; justificar si el benchmark no aconseja caché.

## Technical requirements

- Clave incluye documento/dependencias, renderer/backend/lock y frame
- Nunca filtrar buffers mutables; invalidar dependencias transitivas y limitar temporales

## Proposed implementation

- Elegir caché/dirty regions después del benchmark y documentar decisión
- Probar invalidación transitiva, LRU por bytes y equivalencia on/off

## Acceptance criteria

- [ ] AC1: Caché on/off produce RGBA y reportes idénticos
- [ ] AC2: Una edición cambia todos sus consumidores y la caché no supera el límite configurado

## Required tests

- [ ] T1: Comparar render completo/incremental para cambios de paleta, máscara, grupo y orden
- [ ] T2: Evicción LRU, versiones distintas, mutación externa impedida y benchmark antes/después

## Expected deliverables

- Caché e invalidación incremental acotadas por snapshot, parámetros y recursos.
- Comparaciones cold/warm y caché on/off con igualdad RGBA y mediciones de coste.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- Si no hay beneficio, documentar decisión de no introducir caché y su evidencia.

## Guía para agentes de IA

**Estado para agentes:** Listo: todas las dependencias están `done`; puede empezarse.

### 1. Preparación

- Rama: `feat/MOANA-032-optimizar-cache-render` creada desde `develop` actualizado: `git switch develop && git pull --ff-only && git switch -c feat/MOANA-032-optimizar-cache-render`.
- Verificar en `docs/issues/catalog.json` que este issue está `ready` y que sus dependencias ([MOANA-018](MOANA-018.md), [MOANA-031](MOANA-031.md)) están `done`.
- Entorno: `uv sync --locked` (sin uv global: `sh scripts/bootstrap.sh` y después `sh scripts/uv.sh` en lugar de `uv`).
- Al empezar, cambiar `status` a `in_progress` en el catálogo y regenerar con `uv run python scripts/planning.py`.

### 2. Lectura obligatoria (en orden)

1. `CLAUDE.md` (Claude Code) o `AGENTS.md` (Codex) y [flujo de sesión](../guides/agent-workflow.md).
2. MOANA.md: §3 Arquitectura modular; §14 Renderizado y determinismo; §22 Rendimiento y optimización; §25 Definition of Done. Estas secciones son el contrato normativo; ante duda, prevalecen sobre este issue.
3. [Contratos de módulos](../architecture/module-contracts.md) para: `render`.
4. Estándares: [python](../../docs/standards/python.md), [architecture](../../docs/standards/architecture.md), [testing](../../docs/standards/testing.md).
5. Issues de dependencia ([MOANA-018](MOANA-018.md), [MOANA-031](MOANA-031.md)): leer su sección Evidence para conocer las APIs ya entregadas; no reimplementarlas.
6. ADR en `docs/architecture/` que mencionen los módulos afectados.

### 3. Requisitos de MOANA.md cubiertos

| ID | Requisito | Secciones | Verificación exigida |
| --- | --- | --- | --- |
| R029 | Caché e incrementalidad | §22 | Equivalencia caché on/off y límites LRU |
| R028 | Rendimiento y recursos medidos | §22 | Benchmark reproducible y memoria acotada |
| R015 | Renderizado determinista | §14 | Digests RGBA en procesos/OS y semillas distintas |

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

- T1: Comparar render completo/incremental para cambios de paleta, máscara, grupo y orden
- T2: Evicción LRU, versiones distintas, mutación externa impedida y benchmark antes/después
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
