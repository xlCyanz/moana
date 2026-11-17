# MOANA-024 — Exportar GIF con política de pérdidas

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-024
- Aliases históricos: MOA-024
- Phase: P4
- Priority: P1
- Status: blocked
- Complexity: L (relativa, no estimación de tiempo)
- Dependencies: [MOANA-022](MOANA-022.md), [MOANA-005](MOANA-005.md), [MOANA-011](MOANA-011.md)
- Related modules: export, animation
- Requirements: R023 ([trazabilidad](traceability.md))
- Bloqueo: Dependencias pendientes: MOANA-022, MOANA-005, MOANA-011

## Context

GIF no representa alfa parcial, colores arbitrarios ni todos los tiempos.

## Objective

Exportar una timeline equivalente con pérdidas explícitas y controladas.

## Scope

Implementar GIF con paleta compartida, transparencia, disposal y duración efectiva declarada.

## Out of scope

No cuantización silenciosa ni equiparar GIF al maestro RGBA.

## Technical requirements

- <=256 índices, reserva de transparencia y rechazo de alfa intermedio sin background explícito
- Duración múltiplo de 10 ms o redondeo solicitado; comprobar timeline tras decode

## Proposed implementation

- Preparar paleta compartida/reserva transparente y política de duración
- Codificar frames/disposal y reconstruir timeline decodificada

## Acceptance criteria

- [ ] AC1: Frames decodificados/composited y tiempos son equivalentes al objetivo bajo las opciones elegidas
- [ ] AC2: Colores o tiempos no representables generan error o informe de pérdida explícitamente aceptada

## Required tests

- [ ] T1: Paleta llena, 255 colores más transparente, alpha intermedio y disposal
- [ ] T2: Frames duplicados fusionados, loop, duraciones cortas y decode acumulado en Pillow

## Expected deliverables

- Exportador GIF con política explícita de pérdidas, paleta y duración efectiva.
- Pruebas de timeline decodificado, transparencia, límites y rechazos sin pérdida autorizada.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- Los encoders pueden fusionar frames idénticos; comparar tiempo/imagen, no sólo count.

## Evidence

Pendiente de implementación.
