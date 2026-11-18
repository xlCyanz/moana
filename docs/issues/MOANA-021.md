# MOANA-021 — Versionar y migrar formatos de proyecto

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-021
- Aliases históricos: MOA-021
- Phase: P4
- Priority: P1
- Status: ready
- Complexity: M (relativa, no estimación de tiempo)
- Dependencies: [MOANA-020](MOANA-020.md)
- Related modules: project, schema
- Requirements: R019 ([trazabilidad](traceability.md))
- Bloqueo: Ninguno

## Context

La evolución de datos no debe corromper originales ni aceptar versiones desconocidas.

## Objective

Migrar versiones soportadas mediante transformaciones puras y copia preservada.

## Scope

Implementar registro explícito de versiones de schema y migraciones puras con copia original preservada.

## Out of scope

No prometer compatibilidad con formatos que no tengan contrato de migración registrado.

## Technical requirements

- Distinguir versión paquete/schema/renderer y rechazar futuras desconocidas
- Migración offline sin I/O interno; metadata de procedencia y backup gestionados por proyecto

## Proposed implementation

- Registrar rutas explícitas origen/destino y fixtures de versiones reales
- Probar migración y guardado por separado; mantener backup antes de commit

## Acceptance criteria

- [ ] AC1: Una fixture de versión anterior migra a v1 conservando semántica y render
- [ ] AC2: Abrir un archivo no lo sobrescribe ni aplica migración destructiva silenciosa

## Required tests

- [ ] T1: Fixtures de migración, migración repetida/idempotencia del destino y versión futura
- [ ] T2: Simular fallo intermedio y comprobar que el original permanece intacto

## Expected deliverables

- Registro explícito de versiones/migraciones y política de incompatibilidad.
- Fixtures de formatos soportados, errores de versiones futuras y migración preservando IDs.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- No inventar un formato histórico publicado; una fixture de prueba debe identificarse como tal.

## Guía para agentes de IA

**Estado para agentes:** Listo: todas las dependencias están `done`; puede empezarse.

### 1. Preparación

- Rama: `feat/MOANA-021-versionar-migrar-formatos` creada desde `develop` actualizado: `git switch develop && git pull --ff-only && git switch -c feat/MOANA-021-versionar-migrar-formatos`.
- Verificar en `docs/issues/catalog.json` que este issue está `ready` y que sus dependencias ([MOANA-020](MOANA-020.md)) están `done`.
- Entorno: `uv sync --locked` (sin uv global: `sh scripts/bootstrap.sh` y después `sh scripts/uv.sh` en lugar de `uv`).
- Al empezar, cambiar `status` a `in_progress` en el catálogo y regenerar con `uv run python scripts/planning.py`.

### 2. Lectura obligatoria (en orden)

1. `CLAUDE.md` (Claude Code) o `AGENTS.md` (Codex) y [flujo de sesión](../guides/agent-workflow.md).
2. MOANA.md: §3 Arquitectura modular; §16 Formato de proyectos; §25 Definition of Done. Estas secciones son el contrato normativo; ante duda, prevalecen sobre este issue.
3. [Contratos de módulos](../architecture/module-contracts.md) para: `project`, `schema`.
4. Estándares: [python](../../docs/standards/python.md), [architecture](../../docs/standards/architecture.md), [testing](../../docs/standards/testing.md), [security](../../docs/standards/security.md).
5. Issues de dependencia ([MOANA-020](MOANA-020.md)): leer su sección Evidence para conocer las APIs ya entregadas; no reimplementarlas.
6. ADR en `docs/architecture/` que mencionen los módulos afectados.

### 3. Requisitos de MOANA.md cubiertos

| ID | Requisito | Secciones | Verificación exigida |
| --- | --- | --- | --- |
| R019 | Versionado y migraciones | §16 | Fixtures entre versiones y original preservado |

### 4. Skills y subagentes

| Host | Skills a cargar | Revisión especializada |
| --- | --- | --- |
| Claude Code | `moana-python`, `moana-architecture`, `moana-code-review` | `moana-python-engineer`, `moana-architect` (sólo lectura; el agente principal integra) |
| Codex | `$moana-python`, `$moana-architecture`, `$moana-code-review` | `moana_python_engineer`, `moana_architect` |

### 5. Archivos

- Código o documentos a crear/modificar: `src/moana/project/`, `src/moana/schema/`.
- Pruebas: `tests/unit/project/`, `tests/unit/schema/`.
- No crear módulos ni carpetas sin comportamiento real. No tocar otros módulos salvo exportaciones imprescindibles, justificadas en el PR.

### 6. Plan de pruebas

- T1: Fixtures de migración, migración repetida/idempotencia del destino y versión futura
- T2: Simular fallo intermedio y comprobar que el original permanece intacto
- Oráculos independientes (cálculo a mano o fórmula de MOANA.md); nunca copiar la salida de la implementación como expected.
- Incluir casos negativos con el error de dominio esperado y casos borde (vacío, mínimo, máximo, fuera de rango).

### 7. Procedimiento

1. Escribir las pruebas de los criterios AC y T antes o junto con la implementación.
2. Implementar sólo **Scope**; respetar **Out of scope** y las dependencias permitidas de MOANA.md §3.
3. Validación de módulo: `uv run pytest tests/unit/project/ tests/unit/schema/ -q` y `uv run mypy src/`.
4. Validación completa: `uv run python scripts/validate.py` y `uv run python scripts/check_wheel.py`.
5. Revisión: subagentes listados y skill `moana-code-review`; corregir hallazgos críticos y altos.
6. Si hay salida raster: mostrar el PNG a 1x y ampliado por vecino más cercano; si cambia un golden, presentar expected/actual/diff y justificar.

### 8. Cierre

1. En `docs/issues/catalog.json`, para este issue: `status` → `review` (o `done` tras aprobación); completar `acceptance_evidence` (AC1, AC2), `test_evidence` (T1, T2) y `evidence` con rutas concretas de tests y archivos.
2. Issues que desbloquea ([MOANA-030](MOANA-030.md), [MOANA-035](MOANA-035.md)): si todas sus dependencias quedan `done`, pasarlos a `ready` con `blocking_reason: null`.
3. Ejecutar `uv run python scripts/planning.py` y `uv run python -m scripts.check_repository`.
4. Abrir PR hacia `develop` enlazando este issue de GitHub (`Closes #<número>`), con comandos ejecutados y evidencia por AC/T. El CI completo corre al integrar `develop` en `main`.
5. Commit y push sólo con autorización del usuario. No declarar CI remoto ni aprobación artística humana sin evidencia.

### 9. Prohibido en este issue

- Implementar alcance de otros issues, incluidos los que desbloquea ([MOANA-030](MOANA-030.md), [MOANA-035](MOANA-035.md)).
- Actualizar goldens automáticamente, desactivar checks, editar `uv.lock` a mano o añadir dependencias sin motivo técnico registrado.
- `eval`/`exec`/`pickle`, red o estado global mutable en el núcleo; lecturas de texto sin `encoding="utf-8"`.

## Evidence

Pendiente de implementación.
