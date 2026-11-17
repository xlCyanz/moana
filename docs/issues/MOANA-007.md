# MOANA-007 — Añadir adaptador de paths AggDraw

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-007
- Aliases históricos: MOA-007
- Phase: P3
- Priority: P2
- Status: blocked
- Complexity: M (relativa, no estimación de tiempo)
- Dependencies: [MOANA-006](MOANA-006.md), [MOANA-010](MOANA-010.md), [MOANA-028](MOANA-028.md)
- Related modules: geometry, render
- Requirements: R004, R015 ([trazabilidad](traceability.md))
- Bloqueo: Dependencias pendientes: MOANA-006, MOANA-010, MOANA-028

## Context

Curvas complementarias requieren backend explícito sin diluir el contrato entero.

## Objective

Añadir paths con cobertura binaria y garantía de compatibilidad limitada.

## Scope

Agregar path M/L/Q/C/Z con punto fijo, versión de backend y binarización de cobertura; mantener separado el perfil entero.

## Out of scope

No fuentes, SVG completo ni rasterización vectorial genérica.

## Technical requirements

- Umbral >=128 a resolución nativa; comandos limitados y sin SVG externo
- Registrar aggdraw-v1 y versiones en provenance; exponer capacidad real y estimación de trabajo

## Proposed implementation

- Definir el payload de comandos fijo 1/256 en schema junto al adaptador
- Validar segmentos, rasterizar con AggDraw y aplicar threshold/documentar provenance

## Acceptance criteria

- [ ] AC1: Paths cerrados producen únicamente máscara binaria y no introducen colores por AA
- [ ] AC2: Entradas desconocidas o excesivas fallan antes del adaptador; ausencia de capacidad da error explícito

## Required tests

- [ ] T1: Fixtures de curvas pequeñas, joins, cierres y curvas fuera de lienzo
- [ ] T2: Repetición con entorno fijado y comparación backend por plataforma sin prometer equivalencia al raster entero

## Expected deliverables

- Adaptador AggDraw para paths con política explícita de muestreo y cuantización.
- Fixtures de curvas y uniones; evaluación RGBA y de errores del adaptador.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- No asumir que AggDraw comparte píxeles entre versiones o plataformas no ensayadas.

## Evidence

Pendiente de implementación.
