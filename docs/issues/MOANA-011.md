# MOANA-011 — Exportar PNG y manifiesto de salida

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-011
- Aliases históricos: MOA-011
- Phase: P2
- Priority: P1
- Status: blocked
- Complexity: M (relativa, no estimación de tiempo)
- Dependencies: [MOANA-010](MOANA-010.md)
- Related modules: export
- Requirements: R022 ([trazabilidad](traceability.md))
- Bloqueo: Dependencias pendientes: MOANA-010

## Context

Exportar no debe perder píxeles ni sobrescribir archivos por accidente.

## Objective

Escribir PNG maestro y manifiesto con roundtrip y atomicidad comprobados.

## Scope

Crear exportador PNG RGBA/indexado con escala entera y escritura atómica que no sobrescribe por defecto.

## Out of scope

No GIF ni publicar archivos en servicios externos.

## Technical requirements

- Metadata estable; indexed conserva orden y valida cardinalidad/transparencia
- ExportManifest incluye dimensiones, hash, ruta y warnings; evitar cuantización implícita

## Proposed implementation

- Separar encode en memoria del commit a filesystem
- Validar formato/indexado/escala y escribir temporal hermano antes del commit

## Acceptance criteria

- [ ] AC1: PNG decodificado es exactamente igual al RenderResult en escala 1
- [ ] AC2: Fallo de escritura deja el destino anterior intacto y no devuelve éxito parcial

## Required tests

- [ ] T1: Roundtrip RGBA e indexado, transparencia y escala nearest 1/2/4
- [ ] T2: Paleta 256/257, destino existente, permiso denegado y fallo simulado durante escritura
- [ ] T3: Carrera de dos escritores con overwrite=false: uno gana y el otro falla sin reemplazar; no usar exists+replace como exclusión.

## Expected deliverables

- Exportador PNG y manifiesto de salida con escritura atómica sin sobrescritura accidental.
- Roundtrips RGBA, pruebas de fallo de I/O y carrera entre escritores.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- Una comprobación exists seguida de replace puede sobreescribir por carrera; usar commit sin reemplazo cuando overwrite=false.

## Evidence

Pendiente de implementación.
