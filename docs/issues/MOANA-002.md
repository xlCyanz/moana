# MOANA-002 — Implementar documento Pydantic y JSON Schema

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-002
- Aliases históricos: MOA-002
- Phase: P1
- Priority: P0
- Status: blocked
- Complexity: L (relativa, no estimación de tiempo)
- Dependencies: [MOANA-001](MOANA-001.md)
- Related modules: schema, core
- Requirements: R013, R026 ([trazabilidad](traceability.md))
- Bloqueo: Dependencias pendientes: MOANA-001

## Context

La IA necesita entradas predecibles y errores localizables sin ejecutar código.

## Objective

Validar y normalizar el MVP generando un JSON Schema a partir de una sola fuente.

## Scope

Crear moana/schema, modelos v1 para el MVP y el registro explícito de capacidades; generar schema y validar el ejemplo mínimo.

## Out of scope

No rasterizar ni implementar anticipadamente todas las técnicas futuras; ampliar modelos junto a sus issues.

## Technical requirements

- Modo strict y extra forbid, IDs globales, discriminadores, defaults canónicos y rechazo de claves duplicadas en bytes
- Distinguir parseo, referencias y operación no soportada; limitar bytes/profundidad antes de parsear completamente

## Proposed implementation

- Separar lectura acotada de bytes, modelos sintácticos y resolución semántica
- Registrar capacidades del MVP y documentar extensiones mediante versiones explícitas

## Acceptance criteria

- [ ] AC1: El JSON mínimo normaliza de forma idempotente y produce schema versionado reproducible
- [ ] AC2: IDs duplicados, colores inexistentes, bool como entero y campos extra se rechazan con pointer y código

## Required tests

- [ ] T1: Tabla de entradas válidas/inválidas y equivalencia mapping/bytes
- [ ] T2: Roundtrip modelo-JSON-modelo, fuzz acotado de profundidad y golden del schema con revisión de compatibilidad

## Expected deliverables

- Modelos Pydantic estrictos del documento MVP y JSON Schema generado con versión explícita.
- Fixtures válidas/inválidas, errores con JSON pointer y roundtrip normalizado.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- Un esquema demasiado permisivo oculta instrucciones desconocidas; uno anticipado sin gramática inventa soporte.

## Guía para agentes de IA

**Estado para agentes:** No empezar: estado `blocked`. Esperar a que [MOANA-001](MOANA-001.md) estén `done` y el catálogo marque este issue `ready`.

### 1. Preparación

- Rama: `feat/MOANA-002-implementar-documento-pydantic` creada desde `develop` actualizado: `git switch develop && git pull --ff-only && git switch -c feat/MOANA-002-implementar-documento-pydantic`.
- Verificar en `docs/issues/catalog.json` que este issue está `ready` y que sus dependencias ([MOANA-001](MOANA-001.md)) están `done`.
- Entorno: `uv sync --locked` (sin uv global: `sh scripts/bootstrap.sh` y después `sh scripts/uv.sh` en lugar de `uv`).
- Al empezar, cambiar `status` a `in_progress` en el catálogo y regenerar con `uv run python scripts/planning.py`.

### 2. Lectura obligatoria (en orden)

1. `CLAUDE.md` (Claude Code) o `AGENTS.md` (Codex) y [flujo de sesión](../guides/agent-workflow.md).
2. MOANA.md: §3 Arquitectura modular; §12 Especificaciones JSON para agentes de IA; §20 Seguridad y validación; §25 Definition of Done. Estas secciones son el contrato normativo; ante duda, prevalecen sobre este issue.
3. [Contratos de módulos](../architecture/module-contracts.md) para: `schema`, `core`.
4. Estándares: [python](../../docs/standards/python.md), [architecture](../../docs/standards/architecture.md), [testing](../../docs/standards/testing.md), [security](../../docs/standards/security.md).
5. Issues de dependencia ([MOANA-001](MOANA-001.md)): leer su sección Evidence para conocer las APIs ya entregadas; no reimplementarlas.
6. ADR en `docs/architecture/` que mencionen los módulos afectados.

### 3. Requisitos de MOANA.md cubiertos

| ID | Requisito | Secciones | Verificación exigida |
| --- | --- | --- | --- |
| R013 | JSON estricto y schema para agentes | §12 | Pydantic, JSON Schema y corpus inválido |
| R026 | Validación y seguridad de datos | §20 | Entradas adversarias rechazadas antes de reservar/IO |

### 4. Skills y subagentes

| Host | Skills a cargar | Revisión especializada |
| --- | --- | --- |
| Claude Code | `moana-python`, `moana-architecture`, `moana-graphics`, `moana-code-review` | `moana-python-engineer`, `moana-architect` (sólo lectura; el agente principal integra) |
| Codex | `$moana-python`, `$moana-architecture`, `$moana-graphics`, `$moana-code-review` | `moana_python_engineer`, `moana_architect` |

### 5. Archivos

- Código o documentos a crear/modificar: `src/moana/schema/`, `src/moana/core/`.
- Pruebas: `tests/unit/schema/`, `tests/unit/core/`.
- No crear módulos ni carpetas sin comportamiento real. No tocar otros módulos salvo exportaciones imprescindibles, justificadas en el PR.

### 6. Plan de pruebas

- T1: Tabla de entradas válidas/inválidas y equivalencia mapping/bytes
- T2: Roundtrip modelo-JSON-modelo, fuzz acotado de profundidad y golden del schema con revisión de compatibilidad
- Oráculos independientes (cálculo a mano o fórmula de MOANA.md); nunca copiar la salida de la implementación como expected.
- Incluir casos negativos con el error de dominio esperado y casos borde (vacío, mínimo, máximo, fuera de rango).

### 7. Procedimiento

1. Escribir las pruebas de los criterios AC y T antes o junto con la implementación.
2. Implementar sólo **Scope**; respetar **Out of scope** y las dependencias permitidas de MOANA.md §3.
3. Validación de módulo: `uv run pytest tests/unit/schema/ tests/unit/core/ -q` y `uv run mypy src/`.
4. Validación completa: `uv run python scripts/validate.py` y `uv run python scripts/check_wheel.py`.
5. Revisión: subagentes listados y skill `moana-code-review`; corregir hallazgos críticos y altos.
6. Si hay salida raster: mostrar el PNG a 1x y ampliado por vecino más cercano; si cambia un golden, presentar expected/actual/diff y justificar.

### 8. Cierre

1. En `docs/issues/catalog.json`, para este issue: `status` → `review` (o `done` tras aprobación); completar `acceptance_evidence` (AC1, AC2), `test_evidence` (T1, T2) y `evidence` con rutas concretas de tests y archivos.
2. Issues que desbloquea ([MOANA-003](MOANA-003.md), [MOANA-005](MOANA-005.md), [MOANA-009](MOANA-009.md), [MOANA-010](MOANA-010.md), [MOANA-018](MOANA-018.md)): si todas sus dependencias quedan `done`, pasarlos a `ready` con `blocking_reason: null`.
3. Ejecutar `uv run python scripts/planning.py` y `uv run python -m scripts.check_repository`.
4. Abrir PR hacia `develop` enlazando este issue de GitHub (`Closes #<número>`), con comandos ejecutados y evidencia por AC/T. El CI completo corre al integrar `develop` en `main`.
5. Commit y push sólo con autorización del usuario. No declarar CI remoto ni aprobación artística humana sin evidencia.

### 9. Prohibido en este issue

- Implementar alcance de otros issues, incluidos los que desbloquea ([MOANA-003](MOANA-003.md), [MOANA-005](MOANA-005.md), [MOANA-009](MOANA-009.md), [MOANA-010](MOANA-010.md), [MOANA-018](MOANA-018.md)).
- Actualizar goldens automáticamente, desactivar checks, editar `uv.lock` a mano o añadir dependencias sin motivo técnico registrado.
- `eval`/`exec`/`pickle`, red o estado global mutable en el núcleo; lecturas de texto sin `encoding="utf-8"`.

## Evidence

Pendiente de implementación.
