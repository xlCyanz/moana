# MOANA-018 — Implementar batches de edición atómica

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-018
- Aliases históricos: MOA-018
- Phase: P3
- Priority: P0
- Status: blocked
- Complexity: L (relativa, no estimación de tiempo)
- Dependencies: [MOANA-002](MOANA-002.md), [MOANA-010](MOANA-010.md), [MOANA-012](MOANA-012.md), [MOANA-013](MOANA-013.md)
- Related modules: editing, api
- Requirements: R016, R038 ([trazabilidad](traceability.md))
- Bloqueo: Dependencias pendientes: MOANA-002, MOANA-010, MOANA-012, MOANA-013

## Context

Un cambio local necesita ser atómico y comprobar la revisión exacta de origen.

## Objective

Crear documentos nuevos mediante batches tipados con conflictos verificables.

## Scope

Crear moana/editing con comandos de §15, targeting por ID y revisión optimista; integrar apply_edit en fachada.

## Out of scope

No protocolo JSON Patch arbitrario ni colaboración en tiempo real.

## Technical requirements

- Validar lote completo y escena final; sin cambios parciales ni mutación del documento fuente
- Rechazar revisión vieja, capa bloqueada, borrado referenciado e IDs mutados; incrementar revisión una vez
- Exigir base_revision y base_snapshot (digest del documento) en cada batch; rechazar mismatches incluso con revisión numérica igual.

## Proposed implementation

- Resolver targets y locks, aplicar batch a una copia y validar el resultado completo
- Aceptar una sola nueva revisión y reportar IDs/dependencias/bbox afectados

## Acceptance criteria

- [ ] AC1: Recolor de body_fill modifica únicamente su referencia y la revisión preservando toda otra estructura
- [ ] AC2: Un segundo comando inválido revierte también el primero; se devuelve EditConflict para base vieja

## Required tests

- [ ] T1: Cada comando con caso válido/negativo, reorder al principio y dependencias vivas
- [ ] T2: Comparar documento original byte a byte, render antes/después y batch sin cambio visual
- [ ] T3: Dos ramas con revision=1 y contenidos distintos rechazan el batch de la otra rama mediante base_snapshot.

## Expected deliverables

- Modelos de batch y aplicación transaccional que verifica revisión y snapshot base.
- Pruebas de rollback, preservación de IDs y conflicto entre ramas con igual revisión.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- Tras undo pueden existir revisiones numéricas iguales en ramas distintas; verificar también identidad del snapshot.

## Evidence

Pendiente de implementación.
