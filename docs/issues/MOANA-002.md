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

## Evidence

Pendiente de implementación.
