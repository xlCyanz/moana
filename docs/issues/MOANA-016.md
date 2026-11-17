# MOANA-016 — Implementar dithering ordenado

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-016
- Aliases históricos: MOA-016
- Phase: P3
- Priority: P1
- Status: blocked
- Complexity: M (relativa, no estimación de tiempo)
- Dependencies: [MOANA-005](MOANA-005.md), [MOANA-013](MOANA-013.md)
- Related modules: techniques
- Requirements: R009 ([trazabilidad](traceability.md))
- Bloqueo: Dependencias pendientes: MOANA-005, MOANA-013

## Context

Un patrón mal anclado produce costuras y parpadeo.

## Objective

Aplicar Bayer exacto con coverage entera y fase estable.

## Scope

Añadir patrones Bayer 2×2/4×4 con coverage entera, anclaje explícito y clipping por máscara.

## Out of scope

No error diffusion ni dithering automático global.

## Technical requirements

- Tablas y módulo matemático fijados en §10; dos IDs de color
- El patrón se ancla al canvas y conserva fase entre tiles y frames salvo instrucción explícita

## Proposed implementation

- Implementar tablas normativas y módulo matemático
- Aplicar la selección A/B sobre máscara y origen compartido

## Acceptance criteria

- [ ] AC1: Coverage 0 produce sólo A y N² sólo B dentro de la máscara
- [ ] AC2: Patrones con origen negativo y traducciones múltiplo del período coinciden exactamente

## Required tests

- [ ] T1: Todos los thresholds, coberturas y posiciones del período
- [ ] T2: Máscaras no rectangulares, costuras entre tiles y repetición temporal sin parpadeo

## Expected deliverables

- Dithering ordenado con patrón/anclaje documentado y máscara de aplicación.
- Fixtures exactas de patrones, transparencia y estabilidad ante recortes.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- El módulo negativo y los overrides temporales deben tener tests propios.

## Evidence

Pendiente de implementación.
