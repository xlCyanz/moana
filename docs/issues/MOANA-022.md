# MOANA-022 — Implementar timeline y evaluación de frames

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-022
- Aliases históricos: MOA-022
- Phase: P4
- Priority: P1
- Status: blocked
- Complexity: L (relativa, no estimación de tiempo)
- Dependencies: [MOANA-018](MOANA-018.md), [MOANA-019](MOANA-019.md), [MOANA-010](MOANA-010.md)
- Related modules: animation, schema
- Requirements: R020 ([trazabilidad](traceability.md))
- Bloqueo: Dependencias pendientes: MOANA-018, MOANA-019, MOANA-010

## Context

Evaluar frames incrementalmente introduce dependencia del orden y deriva temporal.

## Objective

Evaluar cada frame contra la misma base con tiempos/pivotes verificables.

## Scope

Crear animaciones con duración, loops, pivote común y overrides evaluados siempre contra la base.

## Out of scope

No tweening implícito, rigging ni interpolación aprendida.

## Technical requirements

- Validar IDs y presupuestos acumulados antes de export; frames no heredan cambios del anterior
- Estabilidad de semilla por defecto y variación temporal sólo explícita

## Proposed implementation

- Definir timeline y overrides limitados sin revision persistente
- Presupuestar todos los frames y evaluar cada uno independientemente

## Acceptance criteria

- [ ] AC1: Cambiar el orden de evaluación de frames no cambia ninguno de sus resultados
- [ ] AC2: Duraciones y pivotes se preservan y un override inválido impide el render parcial de la solicitud

## Required tests

- [ ] T1: Frame único, 256 frames, límite de duración/área y loops
- [ ] T2: Overrides de geometría/color/visibilidad y textura estable entre frames

## Expected deliverables

- Timeline con evaluación de frames/overrides y reglas de duración/composición.
- Fixtures de límites temporales, estabilidad de IDs y determinismo por frame.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- Un bucle infinito de playback no autoriza un render infinito; exportar secuencia finita.

## Evidence

Pendiente de implementación.
