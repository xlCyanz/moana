# MOANA-008 — Añadir transformaciones pixel-perfect

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-008
- Aliases históricos: MOA-008
- Phase: P1
- Priority: P1
- Status: blocked
- Complexity: M (relativa, no estimación de tiempo)
- Dependencies: [MOANA-006](MOANA-006.md)
- Related modules: geometry
- Requirements: R040 ([trazabilidad](traceability.md))
- Bloqueo: Dependencias pendientes: MOANA-006

## Context

El escalado o giro implícito puede alterar clusters y pivotes.

## Objective

Transformar píxeles y máscaras con reglas enteras reversibles.

## Scope

Crear traslación, espejo, giro en cuartos de vuelta y escala entera para máscaras y geometría.

## Out of scope

No interpolación suave, deformación ni rotación libre.

## Technical requirements

- Definir pivote y orden explícito; aplicar fórmula de §6 a índices
- Preservar IDs y usar nearest-neighbor; cajas resultan de píxeles transformados

## Proposed implementation

- Implementar transformaciones sobre índices y pivote/origen declarado
- Componer orden, calcular bbox resultante y recortar sólo según contrato

## Acceptance criteria

- [ ] AC1: Cuatro giros de 90 grados reconstruyen el resultado sin pérdida
- [ ] AC2: Espejo doble es identidad y una escala 2 replica cada píxel en 2×2

## Required tests

- [ ] T1: Propiedades de composición/inversas sobre máscaras no cuadradas y pivotes negativos
- [ ] T2: Clipping de objetos parcialmente fuera y rechazo de escala no entera o rotación arbitraria en strict

## Expected deliverables

- Transformaciones enteras y escala nearest-neighbor con pivote/clipping definidos.
- Fixtures de rotaciones, flips, traslaciones y propiedades inversas.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- Giro de cajas geométricas no equivale a giro de índices; probar dimensiones pares e impares.

## Evidence

Pendiente de implementación.
