# MOANA-028 — Crear harness de regresión visual

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-028
- Aliases históricos: MOA-028
- Phase: P1
- Priority: P1
- Status: blocked
- Complexity: M (relativa, no estimación de tiempo)
- Dependencies: [MOANA-004](MOANA-004.md)
- Related modules: tests.visual
- Requirements: R027 ([trazabilidad](traceability.md))
- Bloqueo: Dependencias pendientes: MOANA-004

## Context

Comparar bytes PNG confunde codecs con diferencias de píxel.

## Objective

Construir diagnósticos exactos de regresión sin actualizar baselines en CI.

## Scope

Crear utilidades de tests para comparar buffers exactos y producir expected/actual/diff con manifiesto cuando fallan.

## Out of scope

No SSIM como criterio de aprobación ni corpus artístico completo.

## Technical requirements

- Oráculos pequeños independientes y digest dimensional; no depender de render aún
- Actualizar goldens mediante acción explícita revisada; CI no escribe baseline

## Proposed implementation

- Crear comparador de dimensiones/RGBA y diferencias por bbox/conteo
- Guardar expected/actual/diff y metadata sólo al fallar

## Acceptance criteria

- [ ] AC1: Una diferencia de un píxel falla y genera bbox/conteo correctos
- [ ] AC2: Una imagen idéntica pasa aunque los bytes comprimidos del PNG sean diferentes

## Required tests

- [ ] T1: Tests del harness con píxel cambiado, dimensiones distintas y alfa cero
- [ ] T2: Archivos de diagnóstico válidos y baseline intacto tras fallo; manejo de ruta con espacios

## Expected deliverables

- Harness visual de comparación RGBA exacta con expected/actual/diff y bbox.
- Fixtures independientes y procedimiento revisable para aceptar cambios de baseline.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- El harness no puede usar el renderer como oráculo de sus propias pruebas.

## Guía para agentes de IA

**Estado para agentes:** No empezar: estado `blocked`. Esperar a que [MOANA-004](MOANA-004.md) estén `done` y el catálogo marque este issue `ready`.

### 1. Preparación

- Rama: `feat/MOANA-028-crear-harness-regresion` creada desde `develop` actualizado: `git switch develop && git pull --ff-only && git switch -c feat/MOANA-028-crear-harness-regresion`.
- Verificar en `docs/issues/catalog.json` que este issue está `ready` y que sus dependencias ([MOANA-004](MOANA-004.md)) están `done`.
- Entorno: `uv sync --locked` (sin uv global: `sh scripts/bootstrap.sh` y después `sh scripts/uv.sh` en lugar de `uv`).
- Al empezar, cambiar `status` a `in_progress` en el catálogo y regenerar con `uv run python scripts/planning.py`.

### 2. Lectura obligatoria (en orden)

1. `CLAUDE.md` (Claude Code) o `AGENTS.md` (Codex) y [flujo de sesión](../guides/agent-workflow.md).
2. MOANA.md: §3 Arquitectura modular; §21 Testing y regresiones visuales; §25 Definition of Done. Estas secciones son el contrato normativo; ante duda, prevalecen sobre este issue.
3. [Contratos de módulos](../architecture/module-contracts.md) para: `tests.visual`.
4. Estándares: [testing](../../docs/standards/testing.md), [pixel-art](../../docs/standards/pixel-art.md).
5. Issues de dependencia ([MOANA-004](MOANA-004.md)): leer su sección Evidence para conocer las APIs ya entregadas; no reimplementarlas.
6. ADR en `docs/architecture/` que mencionen los módulos afectados.

### 3. Requisitos de MOANA.md cubiertos

| ID | Requisito | Secciones | Verificación exigida |
| --- | --- | --- | --- |
| R027 | Testing y regresión visual | §21 | Unit/property/integration y diffs exactos |

### 4. Skills y subagentes

| Host | Skills a cargar | Revisión especializada |
| --- | --- | --- |
| Claude Code | `moana-testing`, `moana-code-review` | `moana-qa-engineer` (sólo lectura; el agente principal integra) |
| Codex | `$moana-testing`, `$moana-code-review` | `moana_qa_engineer` |

### 5. Archivos

- Código o documentos a crear/modificar: `tests/visual/`.
- Pruebas: `tests/visual/`.
- No crear módulos ni carpetas sin comportamiento real. No tocar otros módulos salvo exportaciones imprescindibles, justificadas en el PR.

### 6. Plan de pruebas

- T1: Tests del harness con píxel cambiado, dimensiones distintas y alfa cero
- T2: Archivos de diagnóstico válidos y baseline intacto tras fallo; manejo de ruta con espacios
- Oráculos independientes (cálculo a mano o fórmula de MOANA.md); nunca copiar la salida de la implementación como expected.
- Incluir casos negativos con el error de dominio esperado y casos borde (vacío, mínimo, máximo, fuera de rango).

### 7. Procedimiento

1. Escribir las pruebas de los criterios AC y T antes o junto con la implementación.
2. Implementar sólo **Scope**; respetar **Out of scope** y las dependencias permitidas de MOANA.md §3.
3. Validación de módulo: `uv run pytest tests/visual/ -q` y `uv run mypy src/`.
4. Validación completa: `uv run python scripts/validate.py` y `uv run python scripts/check_wheel.py`.
5. Revisión: subagentes listados y skill `moana-code-review`; corregir hallazgos críticos y altos.
6. Si hay salida raster: mostrar el PNG a 1x y ampliado por vecino más cercano; si cambia un golden, presentar expected/actual/diff y justificar.

### 8. Cierre

1. En `docs/issues/catalog.json`, para este issue: `status` → `review` (o `done` tras aprobación); completar `acceptance_evidence` (AC1, AC2), `test_evidence` (T1, T2) y `evidence` con rutas concretas de tests y archivos.
2. Issues que desbloquea ([MOANA-007](MOANA-007.md), [MOANA-027](MOANA-027.md), [MOANA-029](MOANA-029.md)): si todas sus dependencias quedan `done`, pasarlos a `ready` con `blocking_reason: null`.
3. Ejecutar `uv run python scripts/planning.py` y `uv run python -m scripts.check_repository`.
4. Abrir PR hacia `develop` enlazando este issue de GitHub (`Closes #<número>`), con comandos ejecutados y evidencia por AC/T. El CI completo corre al integrar `develop` en `main`.
5. Commit y push sólo con autorización del usuario. No declarar CI remoto ni aprobación artística humana sin evidencia.

### 9. Prohibido en este issue

- Implementar alcance de otros issues, incluidos los que desbloquea ([MOANA-007](MOANA-007.md), [MOANA-027](MOANA-027.md), [MOANA-029](MOANA-029.md)).
- Actualizar goldens automáticamente, desactivar checks, editar `uv.lock` a mano o añadir dependencias sin motivo técnico registrado.
- `eval`/`exec`/`pickle`, red o estado global mutable en el núcleo; lecturas de texto sin `encoding="utf-8"`.

## Evidence

Pendiente de implementación.
