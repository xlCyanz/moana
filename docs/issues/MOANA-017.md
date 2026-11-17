# MOANA-017 — Crear presets de materiales versionados

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-017
- Aliases históricos: MOA-017
- Phase: P3
- Priority: P1
- Status: blocked
- Complexity: L (relativa, no estimación de tiempo)
- Dependencies: [MOANA-014](MOANA-014.md), [MOANA-015](MOANA-015.md), [MOANA-016](MOANA-016.md)
- Related modules: techniques, schema
- Requirements: R010, R005 ([trazabilidad](traceability.md))
- Bloqueo: Dependencias pendientes: MOANA-014, MOANA-015, MOANA-016

## Context

Un material repetible debe exponer parámetros y conservar paleta/IDs.

## Objective

Entregar cinco recetas de material editables con versión y procedencia.

## Scope

Crear presets editables de piel, tela, metal, madera y piedra definidos por rampas, bandas y patrones.

## Out of scope

No afirmar calidad profesional sólo por aprobar fixtures ni usar assets sin licencia.

## Technical requirements

- Semilla por operación/coordenada según §14; ningún shader ejecutable en JSON
- Parámetros con rango, fuente, versión y recetas reproducibles; registrar procedencia de ejemplos

## Proposed implementation

- Definir presets como composición de bandas, ramps y patrones existentes
- Añadir controles de rango, semillas y ejemplos propios por material

## Acceptance criteria

- [ ] AC1: Cada material puede editarse sin perder IDs ni introducir colores fuera del perfil
- [ ] AC2: Misma semilla genera igual textura y una operación nueva no altera material existente

## Required tests

- [ ] T1: Fixtures pequeñas por material con máscara y límites de densidad/escala
- [ ] T2: Pruebas de estabilidad entre frames y revisión visual a 1×/4× documentada como humana o pendiente

## Expected deliverables

- Presets de materiales versionados con parámetros y semilla local explícitos.
- Ejemplos editables, fixtures de repetibilidad y límites de cada material.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- Una receta reproducible puede seguir siendo visualmente mala; separar evaluación humana.

## Evidence

Pendiente de implementación.
