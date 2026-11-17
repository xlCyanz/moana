# MOANA-005 — Implementar paletas y rampas

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-005
- Aliases históricos: MOA-005
- Phase: P1
- Priority: P1
- Status: blocked
- Complexity: M (relativa, no estimación de tiempo)
- Dependencies: [MOANA-001](MOANA-001.md), [MOANA-002](MOANA-002.md)
- Related modules: palette, schema
- Requirements: R007 ([trazabilidad](traceability.md))
- Bloqueo: Dependencias pendientes: MOANA-001, MOANA-002

## Context

Una paleta por referencia permite recolor coherente y edición local intencional.

## Objective

Mantener colores y rampas con IDs estables y perfiles explícitos.

## Scope

Crear moana/palette con IDs de color, canonicalización RGBA, ramps y validación de perfiles strict/rgba.

## Out of scope

No cuantización automática ni iluminación.

## Technical requirements

- Referencias por ID y formato canónico #RRGGBBAA; orden explícito de ramps
- Validar alfa y cardinalidad por perfil; cambios de color no renumeran consumidores

## Proposed implementation

- Crear índice de IDs y canonicalización RGBA
- Validar rampas/perfiles y separar advertencias de luminancia de rechazos

## Acceptance criteria

- [ ] AC1: Paleta strict rechaza alfa intermedio y referencias de rampa inexistentes
- [ ] AC2: Serializar y cargar preserva orden, valores e identidad; advertencia de luminancia no bloquea estilos válidos

## Required tests

- [ ] T1: Casos de colores duplicados por valor pero IDs diferentes y IDs duplicados inválidos
- [ ] T2: Pruebas de límites 256/4096, transparencia y remapeo explícito sin colores ocultos

## Expected deliverables

- Modelos y resolución de paletas/rampas por ID, con remapeo explícito.
- Fixtures de cardinalidad, perfil de color, referencias y estabilidad de índices.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- La transparencia normalizada puede cambiar RGB residual; definirla antes de comparar pertenencia.

## Evidence

Pendiente de implementación.
