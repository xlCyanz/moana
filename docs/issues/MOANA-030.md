# MOANA-030 — Ejercitar amenazas y entradas adversarias

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-030
- Aliases históricos: MOA-030
- Phase: P5
- Priority: P0
- Status: blocked
- Complexity: L (relativa, no estimación de tiempo)
- Dependencies: [MOANA-003](MOANA-003.md), [MOANA-020](MOANA-020.md), [MOANA-021](MOANA-021.md), [MOANA-022](MOANA-022.md)
- Related modules: tests.security
- Requirements: R026, R027 ([trazabilidad](traceability.md))
- Bloqueo: Dependencias pendientes: MOANA-003, MOANA-020, MOANA-021, MOANA-022

## Context

Los límites nominales pueden saltarse con combinaciones maliciosas.

## Objective

Demostrar rechazo previo a buffers/IO para las fronteras del threat model.

## Scope

Implementar suite de seguridad y propiedades de rechazo para JSON, proyectos, assets, referencias y edición.

## Out of scope

No pentest de servicios externos ni garantía de aislamiento in-process para llamadas nativas bloqueadas.

## Technical requirements

- Generadores acotados Hypothesis y corpus malicioso versionado sin payload ejecutable
- Verificar no reserva/IO previo al rechazo, preservación de destino y errores sin secretos

## Proposed implementation

- Construir corpus adversario acotado y generadores de propiedades
- Instrumentar allocation/IO y límites del proceso de tests

## Acceptance criteria

- [ ] AC1: Todas las fronteras del threat model tienen caso reproducible y mitigación ejercitada
- [ ] AC2: Solicitudes hostiles fallan bajo límites de tiempo/memoria de test y no dejan salida parcial

## Required tests

- [ ] T1: Duplicados JSON, nesting, ciclos, NaN, tamaños enormes y ZIP traversal/bomb
- [ ] T2: Monkeypatch de asignación/IO, mutación parcial de batch, decode enorme y fallo de checksum

## Expected deliverables

- Suite adversaria de documentos, assets, rutas y presupuestos del motor.
- Casos que verifican rechazo antes de asignación/efectos y resumen de amenazas cubiertas.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- Las pruebas hostiles deben ser acotadas y nunca desactivar protecciones de Pillow.

## Evidence

Pendiente de implementación.
