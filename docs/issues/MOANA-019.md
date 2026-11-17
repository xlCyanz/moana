# MOANA-019 — Añadir undo/redo e historial inmutable

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-019
- Aliases históricos: MOA-019
- Phase: P3
- Priority: P1
- Status: blocked
- Complexity: L (relativa, no estimación de tiempo)
- Dependencies: [MOANA-018](MOANA-018.md)
- Related modules: editing
- Requirements: R017 ([trazabilidad](traceability.md))
- Bloqueo: Dependencias pendientes: MOANA-018

## Context

Undo/redo debe recuperar el documento y sus píxeles, no aproximarlos.

## Objective

Mantener snapshots persistentes y ramas sin pérdida silenciosa de estados.

## Scope

Crear snapshots con digest, comandos canónicos y cursor de historial; permitir undo/redo y nueva rama después de undo.

## Out of scope

No persistir todavía un contenedor de proyecto ni fusionar ramas automáticamente.

## Technical requirements

- No reconstruir estados con operaciones inversas aproximadas
- Limitar memoria/historial y separar selección de revisión de la edición que crea nueva revisión
- Identidad del snapshot por digest; número revision local a cada rama, nunca usado como clave global.

## Proposed implementation

- Indexar snapshots por digest y guardar padre/batch con cursor separado
- Implementar navegación y nueva rama con presupuesto explícito

## Acceptance criteria

- [ ] AC1: Undo y redo recuperan documento y RGBA exactos
- [ ] AC2: Editar después de undo invalida sólo redo activo sin eliminar estados ya persistidos

## Required tests

- [ ] T1: Secuencias de 1/10/100 ediciones y navegación a límites
- [ ] T2: Fallo de batch no agrega snapshot; ramas, revisiones y budget de historial

## Expected deliverables

- Historial inmutable con undo/redo y relación entre snapshots mediante digest.
- Fixtures de ramificación, invalidez de redo y restauración exacta del documento.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- No usar el número de revisión como identidad global del historial.

## Evidence

Pendiente de implementación.
