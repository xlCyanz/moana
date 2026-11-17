# MOANA-034 — Añadir ejemplos de tiles y escenarios modulares

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-034
- Aliases históricos: MOA-034
- Phase: P5
- Priority: P2
- Status: blocked
- Complexity: M (relativa, no estimación de tiempo)
- Dependencies: [MOANA-008](MOANA-008.md), [MOANA-016](MOANA-016.md), [MOANA-020](MOANA-020.md), [MOANA-023](MOANA-023.md)
- Related modules: examples, geometry
- Requirements: R037, R005 ([trazabilidad](traceability.md))
- Bloqueo: Dependencias pendientes: MOANA-008, MOANA-016, MOANA-020, MOANA-023

## Context

Tiles y escenarios requieren continuidad entre elementos y edición por identidad.

## Objective

Componer escenas/props y tiles con paleta compartida sin costuras.

## Scope

Crear composiciones de tiles/props/escena con origen de patrón común, IDs semánticos y paleta compartida.

## Out of scope

No editor de mapas, física ni sistema de juego.

## Technical requirements

- Instanciar geometría existente sin crear motor de mapas separado
- Definir grid, pivotes, bordes y licencia/procedencia; asegurar textura periódica en costuras

## Proposed implementation

- Usar operaciones/transformaciones existentes con grid/origen de patrón común
- Exportar atlas y reconstruir escena para comparar píxeles

## Acceptance criteria

- [ ] AC1: Un tile repetible no presenta costuras y una escena mantiene paleta e IDs editables
- [ ] AC2: Exportar atlas y reconstruir composición reproduce los píxeles originales

## Required tests

- [ ] T1: Costuras horizontal/vertical, espejos y traslación por múltiplos de tile
- [ ] T2: Editar un prop por ID y verificar regiones; inspección de legibilidad a escala nativa

## Expected deliverables

- Ejemplos editables de tiles y escenarios modulares con composición documentada.
- Pruebas de uniones, repetibilidad, procedencia y previews de ensamblaje.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- Repetición horizontal/vertical necesita fixtures de costura y revisión a escala nativa.

## Evidence

Pendiente de implementación.
