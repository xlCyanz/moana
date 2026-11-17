# MOANA-027 — Construir corpus artístico y rúbrica humana

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-027
- Aliases históricos: MOA-027
- Phase: P5
- Priority: P1
- Status: blocked
- Complexity: L (relativa, no estimación de tiempo)
- Dependencies: [MOANA-017](MOANA-017.md), [MOANA-022](MOANA-022.md), [MOANA-026](MOANA-026.md), [MOANA-028](MOANA-028.md)
- Related modules: examples, quality
- Requirements: R005, R027, R038 ([trazabilidad](traceability.md))
- Bloqueo: Dependencias pendientes: MOANA-017, MOANA-022, MOANA-026, MOANA-028

## Context

Las técnicas requieren un corpus editable y evaluación de lectura real.

## Objective

Demostrar cinco categorías con fuentes propias y rúbrica documentada.

## Scope

Crear ejemplos propios de personaje, criatura, objeto, tile y animación con JSON, PNG, paleta, procedencia y evaluación.

## Out of scope

No inventar aprobaciones humanas ni generar ejemplos finales con un modelo visual.

## Technical requirements

- Cada ejemplo conserva fuente editable, semilla, versión de renderer y licencia/procedencia
- Mostrar 1×/4×, silueta y clusters; rúbrica de §19 con aprobación humana registrada o pendiente

## Proposed implementation

- Crear brief/JSON/semilla por ejemplo y renders reproducibles
- Registrar procedencia y revisión humana con categorías y justificación

## Acceptance criteria

- [ ] AC1: Corpus cubre cinco categorías y pasa hard checks sin ocultar warnings
- [ ] AC2: Sólo se califica profesional un ejemplo revisado por una persona con >=4 en categorías aplicables

## Required tests

- [ ] T1: Render de todo el corpus y cambio localizado por región con diff
- [ ] T2: Inspección visual documentada, estabilidad de animación y auditoría de procedencia

## Expected deliverables

- Corpus propio de personaje, criatura, objeto, tile y animación con fuentes editables.
- Previews 1×/4×, procedencia/licencia y rúbrica humana con evidencia de evaluación.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- No marcar como aprobada la calidad artística mientras falte una persona revisora.

## Evidence

Pendiente de implementación.
