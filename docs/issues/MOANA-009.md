# MOANA-009 — Implementar capas, grupos y composición

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-009
- Aliases históricos: MOA-009
- Phase: P2
- Priority: P1
- Status: blocked
- Complexity: L (relativa, no estimación de tiempo)
- Dependencies: [MOANA-002](MOANA-002.md), [MOANA-004](MOANA-004.md), [MOANA-005](MOANA-005.md), [MOANA-006](MOANA-006.md), [MOANA-008](MOANA-008.md)
- Related modules: layers
- Requirements: R011 ([trazabilidad](traceability.md))
- Bloqueo: Dependencias pendientes: MOANA-002, MOANA-004, MOANA-005, MOANA-006, MOANA-008

## Context

La composición define la relación entre colores, visibilidad y grupos aislados.

## Objective

Componer capas ordenadas usando una sola fórmula entera source-over.

## Scope

Crear árbol ordenado de capas/grupos, visibilidad, bloqueo y composición normal source-over entera.

## Out of scope

No multiply/screen ni máscaras semánticas todavía.

## Technical requirements

- Orden abajo-arriba; buffer aislado por grupo y opacidad aplicada una vez
- Fórmula de redondeo §11, normalización alpha cero y límite de profundidad

## Proposed implementation

- Crear árbol de capas/grupos con ownership de buffer
- Componer hijos y aplicar opacidad del grupo una sola vez

## Acceptance criteria

- [ ] AC1: Composición de fixture semitransparente coincide con cálculo entero independiente
- [ ] AC2: Cambiar orden/visibilidad produce diferencia prevista; grupos no aplican opacidad por hijo

## Required tests

- [ ] T1: Casos alpha 0/1/127/255 y normalización RGB en transparente
- [ ] T2: Grupos anidados, profundidad límite, capa invisible y strict que rechaza opacidad intermedia

## Expected deliverables

- Árbol de capas/grupos y composición RGBA con opacidad de grupo aplicada una vez.
- Fixtures de orden, visibilidad, alfa parcial y aislamiento de grupos.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- La opacidad por hijo cambia la imagen; el bloqueo afecta edición, no render.

## Evidence

Pendiente de implementación.
