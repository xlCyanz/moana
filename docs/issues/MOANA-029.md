# MOANA-029 — Verificar determinismo entre procesos y plataformas

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-029
- Aliases históricos: MOA-029
- Phase: P2
- Priority: P1
- Status: blocked
- Complexity: M (relativa, no estimación de tiempo)
- Dependencies: [MOANA-010](MOANA-010.md), [MOANA-011](MOANA-011.md), [MOANA-028](MOANA-028.md)
- Related modules: ci, tests.integration
- Requirements: R015, R027, R035 ([trazabilidad](traceability.md))
- Bloqueo: Dependencias pendientes: MOANA-010, MOANA-011, MOANA-028

## Context

El determinismo local no demuestra igualdad entre procesos y plataformas.

## Objective

Comparar digests de fixtures enteras en la matriz de soporte.

## Scope

Ampliar CI para renderizar fixtures comunes en Python/OS soportados y comparar digests RGBA esperados.

## Out of scope

No afirmar portabilidad de backend AggDraw fuera de combinaciones realmente verificadas.

## Technical requirements

- Variar PYTHONHASHSEED y ejecutar en procesos limpios
- Registrar backend/lock y separar diferencias de codec de diferencias de píxel

## Proposed implementation

- Ejecutar subprocesses limpios variando PYTHONHASHSEED
- Agregar fixtures y registrar backend/lock/plataforma en fallos

## Acceptance criteria

- [ ] AC1: Perfil entero produce mismos digests en Linux/macOS/Windows
- [ ] AC2: CI publica evidencia útil cuando hay divergencia y no actualiza goldens automáticamente

## Required tests

- [ ] T1: Fixtures de diagonales, alpha, grupos, transparencias y clipping
- [ ] T2: Subprocesos con semillas distintas, orden de claves y export/decode frente a RGBA maestro

## Expected deliverables

- Pruebas de determinismo en procesos nuevos, seeds, caché y matriz de plataformas.
- Manifiestos/hashes RGBA y diagnóstico reproducible de divergencias.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- Identidad del perfil entero y de AggDraw son garantías separadas.

## Guía para agentes de IA

**Estado para agentes:** No empezar: estado `blocked`. Esperar a que [MOANA-010](MOANA-010.md), [MOANA-011](MOANA-011.md), [MOANA-028](MOANA-028.md) estén `done` y el catálogo marque este issue `ready`.

### 1. Preparación

- Rama: `feat/MOANA-029-verificar-determinismo-entre` creada desde `develop` actualizado: `git switch develop && git pull --ff-only && git switch -c feat/MOANA-029-verificar-determinismo-entre`.
- Verificar en `docs/issues/catalog.json` que este issue está `ready` y que sus dependencias ([MOANA-010](MOANA-010.md), [MOANA-011](MOANA-011.md), [MOANA-028](MOANA-028.md)) están `done`.
- Entorno: `uv sync --locked` (sin uv global: `sh scripts/bootstrap.sh` y después `sh scripts/uv.sh` en lugar de `uv`).
- Al empezar, cambiar `status` a `in_progress` en el catálogo y regenerar con `uv run python scripts/planning.py`.

### 2. Lectura obligatoria (en orden)

1. `CLAUDE.md` (Claude Code) o `AGENTS.md` (Codex) y [flujo de sesión](../guides/agent-workflow.md).
2. MOANA.md: §3 Arquitectura modular; §14 Renderizado y determinismo; §21 Testing y regresiones visuales; §25 Definition of Done. Estas secciones son el contrato normativo; ante duda, prevalecen sobre este issue.
3. [Contratos de módulos](../architecture/module-contracts.md) para: `ci`, `tests.integration`.
4. Estándares: [testing](../../docs/standards/testing.md), [security](../../docs/standards/security.md).
5. Issues de dependencia ([MOANA-010](MOANA-010.md), [MOANA-011](MOANA-011.md), [MOANA-028](MOANA-028.md)): leer su sección Evidence para conocer las APIs ya entregadas; no reimplementarlas.
6. ADR en `docs/architecture/` que mencionen los módulos afectados.

### 3. Requisitos de MOANA.md cubiertos

| ID | Requisito | Secciones | Verificación exigida |
| --- | --- | --- | --- |
| R015 | Renderizado determinista | §14 | Digests RGBA en procesos/OS y semillas distintas |
| R027 | Testing y regresión visual | §21 | Unit/property/integration y diffs exactos |
| R035 | Hooks y automatización CI | §21, §25 | pre-commit y workflow en matriz sin publicación |

### 4. Skills y subagentes

| Host | Skills a cargar | Revisión especializada |
| --- | --- | --- |
| Claude Code | `moana-testing`, `moana-code-review` | `moana-qa-engineer` (sólo lectura; el agente principal integra) |
| Codex | `$moana-testing`, `$moana-code-review` | `moana_qa_engineer` |

### 5. Archivos

- Código o documentos a crear/modificar: `.github/workflows/`, `tests/integration/`.
- Pruebas: `tests/test_repository_tools.py`, `tests/integration/`.
- No crear módulos ni carpetas sin comportamiento real. No tocar otros módulos salvo exportaciones imprescindibles, justificadas en el PR.

### 6. Plan de pruebas

- T1: Fixtures de diagonales, alpha, grupos, transparencias y clipping
- T2: Subprocesos con semillas distintas, orden de claves y export/decode frente a RGBA maestro
- Oráculos independientes (cálculo a mano o fórmula de MOANA.md); nunca copiar la salida de la implementación como expected.
- Incluir casos negativos con el error de dominio esperado y casos borde (vacío, mínimo, máximo, fuera de rango).

### 7. Procedimiento

1. Escribir las pruebas de los criterios AC y T antes o junto con la implementación.
2. Implementar sólo **Scope**; respetar **Out of scope** y las dependencias permitidas de MOANA.md §3.
3. Validación de módulo: `uv run pytest tests/test_repository_tools.py tests/integration/ -q` y `uv run mypy src/`.
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
