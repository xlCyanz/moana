# MOANA-029 — Verificar determinismo entre procesos y plataformas

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-029
- Aliases históricos: MOA-029
- Phase: P2
- Priority: P1
- Status: blocked
- Complexity: M (relativa, no estimación de tiempo)
- Dependencies: [MOANA-010](MOANA-010.md), [MOANA-011](MOANA-011.md), [MOANA-028](MOANA-028.md)
- Related modules: ci, tests.integration
- Requirements: R015, R027, R035 ([trazabilidad](traceability.md))
- Bloqueo: Dependencias pendientes: MOANA-010, MOANA-011, MOANA-028

## Context

El determinismo local no demuestra igualdad entre procesos y plataformas.

## Objective

Comparar digests de fixtures enteras en la matriz de soporte.

## Scope

Ampliar CI para renderizar fixtures comunes en Python/OS soportados y comparar digests RGBA esperados.

## Out of scope

No afirmar portabilidad de backend AggDraw fuera de combinaciones realmente verificadas.

## Technical requirements

- Variar PYTHONHASHSEED y ejecutar en procesos limpios
- Registrar backend/lock y separar diferencias de codec de diferencias de píxel

## Proposed implementation

- Ejecutar subprocesses limpios variando PYTHONHASHSEED
- Agregar fixtures y registrar backend/lock/plataforma en fallos

## Acceptance criteria

- [ ] AC1: Perfil entero produce mismos digests en Linux/macOS/Windows
- [ ] AC2: CI publica evidencia útil cuando hay divergencia y no actualiza goldens automáticamente

## Required tests

- [ ] T1: Fixtures de diagonales, alpha, grupos, transparencias y clipping
- [ ] T2: Subprocesos con semillas distintas, orden de claves y export/decode frente a RGBA maestro

## Expected deliverables

- Pruebas de determinismo en procesos nuevos, seeds, caché y matriz de plataformas.
- Manifiestos/hashes RGBA y diagnóstico reproducible de divergencias.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- Identidad del perfil entero y de AggDraw son garantías separadas.

## Evidence

Pendiente de implementación.
