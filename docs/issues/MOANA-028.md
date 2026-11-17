# MOANA-028 — Crear harness de regresión visual

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-028
- Aliases históricos: MOA-028
- Phase: P1
- Priority: P1
- Status: blocked
- Complexity: M (relativa, no estimación de tiempo)
- Dependencies: [MOANA-004](MOANA-004.md)
- Related modules: tests.visual
- Requirements: R027 ([trazabilidad](traceability.md))
- Bloqueo: Dependencias pendientes: MOANA-004

## Context

Comparar bytes PNG confunde codecs con diferencias de píxel.

## Objective

Construir diagnósticos exactos de regresión sin actualizar baselines en CI.

## Scope

Crear utilidades de tests para comparar buffers exactos y producir expected/actual/diff con manifiesto cuando fallan.

## Out of scope

No SSIM como criterio de aprobación ni corpus artístico completo.

## Technical requirements

- Oráculos pequeños independientes y digest dimensional; no depender de render aún
- Actualizar goldens mediante acción explícita revisada; CI no escribe baseline

## Proposed implementation

- Crear comparador de dimensiones/RGBA y diferencias por bbox/conteo
- Guardar expected/actual/diff y metadata sólo al fallar

## Acceptance criteria

- [ ] AC1: Una diferencia de un píxel falla y genera bbox/conteo correctos
- [ ] AC2: Una imagen idéntica pasa aunque los bytes comprimidos del PNG sean diferentes

## Required tests

- [ ] T1: Tests del harness con píxel cambiado, dimensiones distintas y alfa cero
- [ ] T2: Archivos de diagnóstico válidos y baseline intacto tras fallo; manejo de ruta con espacios

## Expected deliverables

- Harness visual de comparación RGBA exacta con expected/actual/diff y bbox.
- Fixtures independientes y procedimiento revisable para aceptar cambios de baseline.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- El harness no puede usar el renderer como oráculo de sus propias pruebas.

## Evidence

Pendiente de implementación.
