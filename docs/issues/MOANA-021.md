# MOANA-021 — Versionar y migrar formatos de proyecto

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-021
- Aliases históricos: MOA-021
- Phase: P4
- Priority: P1
- Status: blocked
- Complexity: M (relativa, no estimación de tiempo)
- Dependencies: [MOANA-020](MOANA-020.md)
- Related modules: project, schema
- Requirements: R019 ([trazabilidad](traceability.md))
- Bloqueo: Dependencias pendientes: MOANA-020

## Context

La evolución de datos no debe corromper originales ni aceptar versiones desconocidas.

## Objective

Migrar versiones soportadas mediante transformaciones puras y copia preservada.

## Scope

Implementar registro explícito de versiones de schema y migraciones puras con copia original preservada.

## Out of scope

No prometer compatibilidad con formatos que no tengan contrato de migración registrado.

## Technical requirements

- Distinguir versión paquete/schema/renderer y rechazar futuras desconocidas
- Migración offline sin I/O interno; metadata de procedencia y backup gestionados por proyecto

## Proposed implementation

- Registrar rutas explícitas origen/destino y fixtures de versiones reales
- Probar migración y guardado por separado; mantener backup antes de commit

## Acceptance criteria

- [ ] AC1: Una fixture de versión anterior migra a v1 conservando semántica y render
- [ ] AC2: Abrir un archivo no lo sobrescribe ni aplica migración destructiva silenciosa

## Required tests

- [ ] T1: Fixtures de migración, migración repetida/idempotencia del destino y versión futura
- [ ] T2: Simular fallo intermedio y comprobar que el original permanece intacto

## Expected deliverables

- Registro explícito de versiones/migraciones y política de incompatibilidad.
- Fixtures de formatos soportados, errores de versiones futuras y migración preservando IDs.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- No inventar un formato histórico publicado; una fixture de prueba debe identificarse como tal.

## Evidence

Pendiente de implementación.
