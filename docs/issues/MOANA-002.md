# MOANA-002 — Implementar documento Pydantic y JSON Schema

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-002
- Aliases históricos: MOA-002
- Phase: P1
- Priority: P0
- Status: done
- Complexity: L (relativa, no estimación de tiempo)
- Dependencies: [MOANA-001](MOANA-001.md)
- Related modules: schema, core
- Requirements: R013, R026 ([trazabilidad](traceability.md))
- Bloqueo: Ninguno

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

- [x] AC1: El JSON mínimo normaliza de forma idempotente y produce schema versionado reproducible
- [x] AC2: IDs duplicados, colores inexistentes, bool como entero y campos extra se rechazan con pointer y código

## Required tests

- [x] T1: Tabla de entradas válidas/inválidas y equivalencia mapping/bytes
- [x] T2: Roundtrip modelo-JSON-modelo, fuzz acotado de profundidad y golden del schema con revisión de compatibilidad

## Expected deliverables

- Modelos Pydantic estrictos del documento MVP y JSON Schema generado con versión explícita.
- Fixtures válidas/inválidas, errores con JSON pointer y roundtrip normalizado.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- Un esquema demasiado permisivo oculta instrucciones desconocidas; uno anticipado sin gramática inventa soporte.

## Guía para agentes de IA

**Estado para agentes:** Completado; usar sólo como referencia del contrato entregado.

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

- Implementación: src/moana/schema/{__init__,capabilities,models,document,_reader,_issues,_pointers}.py; ErrorDetail y MoanaError.details aditivos en core.errors; límites de cardinalidad §20 en core.limits; decisión ADR-011; MOANA.md 0.1.3-draft.
- JSON Schema generado: schemas/moana-document-1.0.schema.json (scripts/generate_schema.py --check).
- uv run python scripts/validate.py: lock, ruff, format, mypy estricto, check_repository, pytest y build verdes; moana.schema con 100 % de ramas cubiertas.
- uv run python scripts/check_wheel.py: wheel aislado incluye moana/schema.
- Revisión por subagentes moana-python-engineer y moana-architect: corregidos TypeError con blend no hashable, puntero del discriminador, orden numérico de duplicados, nombres largos fuera de punteros, límites movidos a core, metadata vacía como ausente, grupos como capacidad prevista, módulos internos privados y ADR ajustado.
- Aprobado por el propietario el 2026-11-17 tras revisión; PR #40 hacia develop.
- AC1: tests/unit/schema/test_schema_document.py::test_minimal_example_normalises_to_published_snapshot (digest igual al base_snapshot de examples/specs/recolor.edit.json; normalizar dos veces es idempotente), ::test_normalisation_materialises_section_12_defaults; test_schema_roundtrip.py::test_schema_is_reproducible_and_versioned y ::test_generated_schema_matches_reviewed_golden ($id moana-document-1.0, generación reproducible igual al archivo versionado).
- AC2: test_schema_document.py::test_invalid_table_reports_code_pointer_and_reason: casos duplicate_operation_id e id_shared_by_color_and_layer (VALIDATION_ERROR, duplicate_id), unknown_color/layer_id_used_as_color/unknown_ramp_color (REFERENCE_ERROR, unknown_color), bool_as_integer/bool_in_box (int_type), extra_root_member/extra_operation_member (extra_forbidden), cada uno con json_pointer exacto, desde mapping y bytes.
- T1: test_schema_document.py: tabla VALID (8 casos) y INVALID (43 casos con code, pointer y reason esperados) ejecutada desde mapping y desde bytes con resultados y errores idénticos; test_schema_reader.py: límites de bytes/profundidad/nodos inclusivos, claves duplicadas con pointer, NaN/Infinity, BOM, UTF-8 inválido, escaneo lineal ante strings hostiles y equivalencia de profundidad mapping/bytes.
- T2: test_schema_roundtrip.py: roundtrip modelo→JSON canónico→modelo con Hypothesis (150 documentos), fuzz acotado de profundidad (200 árboles JSON arbitrarios con límite 1–12, sólo errores Moana), golden del JSON Schema con mensaje de revisión de compatibilidad y comprobación de miembros del ejemplo mínimo frente al schema publicado.
