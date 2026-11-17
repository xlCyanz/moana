# MOANA-031 — Medir rendimiento y memoria de referencia

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-031
- Aliases históricos: MOA-031
- Phase: P5
- Priority: P1
- Status: blocked
- Complexity: M (relativa, no estimación de tiempo)
- Dependencies: [MOANA-010](MOANA-010.md), [MOANA-022](MOANA-022.md), [MOANA-027](MOANA-027.md)
- Related modules: benchmarks
- Requirements: R028 ([trazabilidad](traceability.md))
- Bloqueo: Dependencias pendientes: MOANA-010, MOANA-022, MOANA-027

## Context

No hay objetivos de rendimiento verificados antes de medir corpus real.

## Objective

Publicar latencia/memoria reproducibles y contexto de hardware.

## Scope

Crear benchmark repetible del corpus de §22 y registrar hardware, versiones, warmups, mediana, p95 y memoria.

## Out of scope

No optimización GPU/JIT/paralela antes de disponer de mediciones.

## Technical requirements

- Separar render de I/O, 5 warmups y 30 muestras; buffers y proceso identificados
- Objetivos informativos hasta runner estable; no esconder regresión con tolerancia arbitraria

## Proposed implementation

- Separar render de I/O y medir warmups/muestras de §22
- Registrar mediana/p95/pico y comparar la misma carga sin caché engañosa

## Acceptance criteria

- [ ] AC1: Reporte reproducible indica si 100 ms/2 s/256 MiB se cumplen y en qué máquina
- [ ] AC2: Casos adversos respetan presupuestos aunque incumplan objetivo de latencia

## Required tests

- [ ] T1: Benchmark estático 32 capas/500 rects y animación 16 frames
- [ ] T2: Comprobar contadores, ausencia de trabajo eliminado por caché y comparabilidad de versiones

## Expected deliverables

- Benchmarks reproducibles con warmups, muestras, mediana/p95 y memoria.
- Corpus y reporte de entorno/lock, diferenciando coste de render e I/O.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- No usar fluctuaciones de runners compartidos como gate rígido sin estabilizar entorno.

## Evidence

Pendiente de implementación.
