# MOANA-025 — Añadir APNG y WebP lossless opcionales

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-025
- Aliases históricos: MOA-025
- Phase: P4
- Priority: P2
- Status: blocked
- Complexity: M (relativa, no estimación de tiempo)
- Dependencies: [MOANA-022](MOANA-022.md), [MOANA-011](MOANA-011.md)
- Related modules: export
- Requirements: R024 ([trazabilidad](traceability.md))
- Bloqueo: Dependencias pendientes: MOANA-022, MOANA-011

## Context

APNG/WebP dependen de capacidades del build y no justifican fallbacks ocultos.

## Objective

Exponer formatos adicionales sólo con codecs y roundtrip comprobados.

## Scope

Agregar exportadores adicionales sólo cuando el build de Pillow soporte los codecs, con capabilities públicas.

## Out of scope

No WebP lossy por defecto ni dependencia obligatoria de encoders ausentes.

## Technical requirements

- Detectar capacidad en runtime sin sustituir formatos; preservación de alfa/tiempos
- Opciones lossless explícitas y manifest con versiones de codec

## Proposed implementation

- Detectar capacidades y registrar opciones lossless
- Probar formatos disponibles y rechazar ausentes antes de crear destino

## Acceptance criteria

- [ ] AC1: Cada codec disponible pasa roundtrip RGBA y timeline
- [ ] AC2: Codec ausente produce UnsupportedOperation claro sin archivo con extensión engañosa

## Required tests

- [ ] T1: Pruebas condicionadas a capacidades con skip explicado y reporte del build
- [ ] T2: Mock de codec ausente y casos multi-frame, alfa parcial y duración

## Expected deliverables

- Adaptadores APNG/WebP lossless con detección de capacidades del codec.
- Roundtrips de timeline y errores verificables cuando una capacidad no está disponible.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- Un skip de codec no equivale a soporte probado; publicar capability matrix.

## Evidence

Pendiente de implementación.
