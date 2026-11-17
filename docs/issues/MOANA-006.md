# MOANA-006 — Rasterizar primitivas enteras y flood fill

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-006
- Aliases históricos: MOA-006
- Phase: P1
- Priority: P1
- Status: blocked
- Complexity: L (relativa, no estimación de tiempo)
- Dependencies: [MOANA-004](MOANA-004.md), [MOANA-005](MOANA-005.md)
- Related modules: geometry, layers
- Requirements: R003 ([trazabilidad](traceability.md))
- Bloqueo: Dependencias pendientes: MOANA-004, MOANA-005

## Context

Defaults de raster de bibliotecas producen diferencias de un píxel.

## Objective

Producir máscaras de primitivas que cumplan fixtures exactas del contrato.

## Scope

Implementar pixel, line, rect, ellipse, polygon y flood_fill en moana/geometry según reglas exactas de §6.

## Out of scope

No paths Bézier, AA ni trazos de grosor implícito.

## Technical requirements

- Máscaras binarias con empates y bordes normativos; no depender de defaults de ImageDraw
- Flood fill iterativo 4-conectado sobre snapshot de la capa y coste acotado; clipping consistente

## Proposed implementation

- Implementar primitivas en orden pixel/rect/line/ellipse/polygon con oráculos manuales
- Incorporar flood fill iterativo a partir de snapshot de capa recibido como entrada

## Acceptance criteria

- [ ] AC1: Invertir una línea produce la misma máscara y los extremos están incluidos
- [ ] AC2: Rectángulos, elipses y polígonos concuerdan con fixtures manuales; fill no atraviesa límites de color

## Required tests

- [ ] T1: Octantes de línea, degenerados, bordes semiabiertos y autointersecciones even-odd
- [ ] T2: Flood fill de un píxel/todo canvas, coincidencia de color, contención y rechazo por presupuesto
- [ ] T3: Bow-tie con área firmada cero pero interior even-odd no vacío; verificar máscara manual y no usar shoelace como descarte.

## Expected deliverables

- Rasterizadores enteros de primitivas y flood fill acotado.
- Máscaras manuales de bordes, degenerados, polígonos even-odd y relleno.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- Even-odd de autointersecciones no se puede descartar por área firmada cero.

## Evidence

Pendiente de implementación.
