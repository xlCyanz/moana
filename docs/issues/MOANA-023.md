# MOANA-023 — Exportar spritesheets y manifest reversible

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-023
- Aliases históricos: MOA-023
- Phase: P4
- Priority: P1
- Status: blocked
- Complexity: M (relativa, no estimación de tiempo)
- Dependencies: [MOANA-022](MOANA-022.md), [MOANA-011](MOANA-011.md)
- Related modules: export, animation
- Requirements: R021 ([trazabilidad](traceability.md))
- Bloqueo: Dependencias pendientes: MOANA-022, MOANA-011

## Context

Un atlas sin manifest íntegro pierde pivotes, duración o tamaño fuente.

## Objective

Exportar un grid reversible que reconstruya exactamente sus frames.

## Scope

Crear atlas grid con margen/padding, manifiesto de frames, pivotes y tiempos; reconstrucción comprobable.

## Out of scope

No packing heurístico compacto hasta tener contrato de desempate independiente.

## Technical requirements

- Orden de frames estable, sin rotación/trim implícito y dimensiones presupuestadas
- Manifest versionado con rect, source_size, trim_offset, duration y digest

## Proposed implementation

- Calcular layout desde columnas/margen/padding y presupuesto
- Serializar manifest versionado y verificar recortes contra originales

## Acceptance criteria

- [ ] AC1: Recortar atlas por manifest reconstruye RGBA exacto de cada frame
- [ ] AC2: Export idéntico con misma configuración y ningún frame solapa padding o sale del sheet

## Required tests

- [ ] T1: Columnas 1/N, último renglón incompleto, margen/padding y canvas no cuadrado
- [ ] T2: Atlas excesivo, manifest corrupto y roundtrip recortes/tiempos

## Expected deliverables

- Exportador de spritesheets y manifiesto reversible con pivotes/duraciones.
- Reconstrucción exacta de frames desde atlas y pruebas de packing/límites.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- Confundir rect xywh con bbox semiabierta causa offsets; especificar ambos claramente.

## Evidence

Pendiente de implementación.
