# MOANA-003 — Aplicar presupuesto de trabajo y recursos

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-003
- Aliases históricos: MOA-003
- Phase: P1
- Priority: P0
- Status: blocked
- Complexity: L (relativa, no estimación de tiempo)
- Dependencies: [MOANA-001](MOANA-001.md), [MOANA-002](MOANA-002.md)
- Related modules: core, render
- Requirements: R026, R028 ([trazabilidad](traceability.md))
- Bloqueo: Dependencias pendientes: MOANA-001, MOANA-002

## Context

Límites por operación no impiden costes acumulados o temporales enormes.

## Objective

Rechazar trabajo excesivo antes de asignar memoria o entrar a librerías nativas.

## Scope

Implementar plan de coste previo al render con límites de operaciones, buffers, visitas de píxel y frames según §20.

## Out of scope

No construir un servicio aislado ni tratar el timeout cooperativo como límite de proceso.

## Technical requirements

- Contabilizar temporales y bbox recortada, y coste de segmentos antes de clipping
- Los documentos no pueden aumentar límites; deadline cooperativo separado de límites duros del anfitrión

## Proposed implementation

- Crear estimadores por operación y acumulador de presupuesto de plan
- Introducir checkpoints cooperativos y documentar límite duro del proceso anfitrión

## Acceptance criteria

- [ ] AC1: Una solicitud que exceda cualquier límite falla antes de crear un buffer raster
- [ ] AC2: Se informa recurso, límite y coste estimado; una solicitud justo en el límite se admite

## Required tests

- [ ] T1: Instrumentar allocators falsos para comprobar ausencia de reservas al rechazar
- [ ] T2: Casos de coordenadas enormes, capas profundas, muchos frames y overflow de productos

## Expected deliverables

- Estimador de trabajo, memoria y temporales con rechazo previo a reservas.
- Pruebas de límites y diagnósticos de presupuesto por operación/documento.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- Un timeout cooperativo no interrumpe una llamada C bloqueada; nunca presentarlo como aislamiento.

## Evidence

Pendiente de implementación.
