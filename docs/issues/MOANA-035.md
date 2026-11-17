# MOANA-035 — Preparar release y comprobar Definition of Done

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-035
- Aliases históricos: MOA-035
- Phase: P5
- Priority: P1
- Status: blocked
- Complexity: L (relativa, no estimación de tiempo)
- Dependencies: [MOANA-007](MOANA-007.md), [MOANA-021](MOANA-021.md), [MOANA-023](MOANA-023.md), [MOANA-024](MOANA-024.md), [MOANA-025](MOANA-025.md), [MOANA-027](MOANA-027.md), [MOANA-029](MOANA-029.md), [MOANA-030](MOANA-030.md), [MOANA-032](MOANA-032.md), [MOANA-033](MOANA-033.md), [MOANA-034](MOANA-034.md)
- Related modules: release, docs
- Requirements: R031, R039, R036 ([trazabilidad](traceability.md))
- Bloqueo: Dependencias pendientes: MOANA-007, MOANA-021, MOANA-023, MOANA-024, MOANA-025, MOANA-027, MOANA-029, MOANA-030, MOANA-032, MOANA-033, MOANA-034

## Context

Una release necesita evidencias de alcance, compatibilidad y licencia además de un wheel.

## Objective

Preparar un candidato instalable con DoD y pendientes explícitos.

## Scope

Preparar release candidate con wheel/sdist, changelog, matriz de compatibilidad, evidencia de QA y decisión de licencia.

## Out of scope

No publicar en PyPI/GitHub ni declarar CI remoto verde sin ejecutarlo y sin autorización de publicación.

## Technical requirements

- Auditar todos los requisitos y evidencias sin confundir cobertura de planning con implementación
- Versiones paquete/schema/renderer, migraciones y capacidades documentadas; publicación separada

## Proposed implementation

- Auditar requisitos/evidencias y generar matriz de capacidades
- Probar wheel/sdist, tutorial, migraciones y dejar publicación como acción autorizada separada

## Acceptance criteria

- [ ] AC1: Wheel y sdist se instalan limpios y tutorial/corpus funcionan sin checkout
- [ ] AC2: DoD completa, licencia decidida por propietario y limitaciones/artistic review pendientes explícitas antes de publicar

## Required tests

- [ ] T1: Instalación desde ambos artefactos, smoke CLI y migraciones en entorno limpio
- [ ] T2: Revisión final de traceability, CI remoto real, corpus, seguridad y benchmark archivados

## Expected deliverables

- Checklist de release con decisión de licencia, compatibilidad y documentación pública.
- Wheel/sdist auditados, instalación limpia y evidencia de todos los gates de entrega.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- No declarar CI remoto de cambios locales ni licencia decidida sin evidencia del propietario.

## Evidence

Pendiente de implementación.
