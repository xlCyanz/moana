# MOANA-010 — Construir pipeline de render determinista

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-010
- Aliases históricos: MOA-010
- Phase: P2
- Priority: P0
- Status: blocked
- Complexity: L (relativa, no estimación de tiempo)
- Dependencies: [MOANA-002](MOANA-002.md), [MOANA-003](MOANA-003.md), [MOANA-006](MOANA-006.md), [MOANA-009](MOANA-009.md)
- Related modules: render
- Requirements: R015, R030 ([trazabilidad](traceability.md))
- Bloqueo: Dependencias pendientes: MOANA-002, MOANA-003, MOANA-006, MOANA-009

## Context

La reproducibilidad necesita orden explícito y normalización compartida.

## Objective

Producir RenderResult sin modificar documentos ni acceder a disco.

## Scope

Implementar moana/render como orquestador validación-resolución-coste-raster-composición y RenderResult inmutable.

## Out of scope

No caché, concurrencia ni optimizaciones sin benchmark.

## Technical requirements

- Canonicalizar defaults/keys y digest dimensional RGBA según §14
- Registro explícito de operaciones; RNG por ID/coordenadas; sin reloj, hash() ni estado global

## Proposed implementation

- Resolver/costear el documento y construir plan estable
- Ejecutar operaciones y calcular digest dimensional/versiones/RNG por identidad

## Acceptance criteria

- [ ] AC1: El mismo documento produce RGBA y digest idénticos en procesos nuevos
- [ ] AC2: Añadir una operación no cambia la secuencia aleatoria de otra; render no modifica documento ni escribe archivos

## Required tests

- [ ] T1: Variar PYTHONHASHSEED, orden de claves de objeto y repetir en subprocesos
- [ ] T2: Entradas no soportadas, references inválidas, cancelación entre operaciones y límites previos al render

## Expected deliverables

- Pipeline documento→validación→presupuesto→render y RenderResult inmutable.
- Escenas de integración y manifiesto de decisiones/versiones para reproducción.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- hash(), reloj o estado global rompen reproducibilidad aunque el primer test pase.

## Evidence

Pendiente de implementación.
