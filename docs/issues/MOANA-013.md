# MOANA-013 — Añadir máscaras y regiones semánticas

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-013
- Aliases históricos: MOA-013
- Phase: P3
- Priority: P1
- Status: blocked
- Complexity: L (relativa, no estimación de tiempo)
- Dependencies: [MOANA-009](MOANA-009.md), [MOANA-010](MOANA-010.md)
- Related modules: layers, schema
- Requirements: R012 ([trazabilidad](traceability.md))
- Bloqueo: Dependencias pendientes: MOANA-009, MOANA-010

## Context

La edición por región necesita identidad semántica independiente del PNG.

## Objective

Resolver máscaras DAG y regiones estables para clipping y targeting.

## Scope

Implementar nodos de máscaras binarias y union/intersect/subtract/xor; asociar regiones semánticas a IDs y geometría.

## Out of scope

No inferencia automática de regiones desde un PNG.

## Technical requirements

- Resolver referencias en DAG sin depender del color raster de capas
- Máscaras en coordenadas de canvas; bbox y caché potencial dependen de los nodos fuente

## Proposed implementation

- Definir modelos de máscaras/regiones y booleanas con coordenadas de canvas
- Resolver dependencias antes de render y aplicar clipping al destino

## Acceptance criteria

- [ ] AC1: Una operación enmascarada no modifica píxeles fuera de su máscara
- [ ] AC2: Regiones permiten resolver ojo izquierdo por ID; ciclos y referencias rotas se rechazan antes de render

## Required tests

- [ ] T1: Álgebra de conjuntos en fixtures 1/8/128 píxeles y máscaras vacías
- [ ] T2: Ciclos directos/indirectos, máscara fuera del canvas y grupos transformados

## Expected deliverables

- Modelos y resolución de máscaras/regiones semánticas por IDs estables.
- Fixtures de referencias, ciclos, clipping y selección de una región editable.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- Un grupo transformado requiere semántica clara de máscara en canvas frente a geometría local.

## Evidence

Pendiente de implementación.
