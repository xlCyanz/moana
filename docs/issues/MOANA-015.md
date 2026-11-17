# MOANA-015 — Añadir bandas de sombreado e iluminación

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-015
- Aliases históricos: MOA-015
- Phase: P3
- Priority: P1
- Status: blocked
- Complexity: M (relativa, no estimación de tiempo)
- Dependencies: [MOANA-005](MOANA-005.md), [MOANA-013](MOANA-013.md)
- Related modules: techniques, palette
- Requirements: R008 ([trazabilidad](traceability.md))
- Bloqueo: Dependencias pendientes: MOANA-005, MOANA-013

## Context

La iluminación estilizada depende de rampas y máscaras authored.

## Objective

Seleccionar tonos de forma explícita y consistente al editar sombras.

## Scope

Agregar luces discretas, máscaras de bandas y selección de índices de rampa para volúmenes estilizados.

## Out of scope

No sombreado 3D físico ni multiplicación RGB que cree colores ocultos.

## Technical requirements

- Prioridad por orden de bandas y clamp de pasos a la rampa
- Sin normales inferidas: luz recibe regiones/mapas authored; selective outline consume la misma información

## Proposed implementation

- Registrar luz discreta y bandas ordenadas
- Resolver rampas, prioridad de solapamiento y clamp sin inventar normales

## Acceptance criteria

- [ ] AC1: Solapamientos toman la última banda y todos los colores pertenecen a la rampa
- [ ] AC2: Modificar una máscara de sombra conserva geometría/IDs y da un diff localizado documentado

## Required tests

- [ ] T1: Bandas vacías, solapamientos, clamp y cambios de orientación
- [ ] T2: Fixtures manuales con rampa de 3/5 tonos y píxeles de frontera

## Expected deliverables

- Operaciones de bandas y sombreado que conservan rampas y máscaras editables.
- Fixtures de orientación, número de tonos, clipping y evaluación visual de iluminación.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- La estética de una rampa puede contradecir luminancia monótona; emitir advertencia configurable.

## Evidence

Pendiente de implementación.
