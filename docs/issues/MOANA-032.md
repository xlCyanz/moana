# MOANA-032 — Optimizar caché y render incremental acotados

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-032
- Aliases históricos: MOA-032
- Phase: P5
- Priority: P2
- Status: blocked
- Complexity: L (relativa, no estimación de tiempo)
- Dependencies: [MOANA-018](MOANA-018.md), [MOANA-031](MOANA-031.md)
- Related modules: render
- Requirements: R029, R028, R015 ([trazabilidad](traceability.md))
- Bloqueo: Dependencias pendientes: MOANA-018, MOANA-031

## Context

La optimización debe conservar semántica, presupuesto e inmutabilidad.

## Objective

Reducir trabajo sólo donde exista beneficio medido sin cambiar RGBA.

## Scope

Agregar caché LRU por bytes y dirty regions únicamente donde el benchmark demuestre beneficio.

## Out of scope

No paralelismo ni optimizaciones sin mejora medible; justificar si el benchmark no aconseja caché.

## Technical requirements

- Clave incluye documento/dependencias, renderer/backend/lock y frame
- Nunca filtrar buffers mutables; invalidar dependencias transitivas y limitar temporales

## Proposed implementation

- Elegir caché/dirty regions después del benchmark y documentar decisión
- Probar invalidación transitiva, LRU por bytes y equivalencia on/off

## Acceptance criteria

- [ ] AC1: Caché on/off produce RGBA y reportes idénticos
- [ ] AC2: Una edición cambia todos sus consumidores y la caché no supera el límite configurado

## Required tests

- [ ] T1: Comparar render completo/incremental para cambios de paleta, máscara, grupo y orden
- [ ] T2: Evicción LRU, versiones distintas, mutación externa impedida y benchmark antes/después

## Expected deliverables

- Caché e invalidación incremental acotadas por snapshot, parámetros y recursos.
- Comparaciones cold/warm y caché on/off con igualdad RGBA y mediciones de coste.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- Si no hay beneficio, documentar decisión de no introducir caché y su evidencia.

## Evidence

Pendiente de implementación.
