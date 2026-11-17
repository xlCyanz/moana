# MOANA-026 — Crear informes de calidad gráfica

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-026
- Aliases históricos: MOA-026
- Phase: P5
- Priority: P1
- Status: blocked
- Complexity: L (relativa, no estimación de tiempo)
- Dependencies: [MOANA-014](MOANA-014.md), [MOANA-015](MOANA-015.md), [MOANA-022](MOANA-022.md)
- Related modules: quality
- Requirements: R025, R005 ([trazabilidad](traceability.md))
- Bloqueo: Dependencias pendientes: MOANA-014, MOANA-015, MOANA-022

## Context

Heurísticas artísticas y errores de contrato tienen distinta severidad.

## Objective

Producir informes reproducibles y accionables sin modificar el sprite.

## Scope

Crear moana/quality para hard checks, heurísticas configurables, métricas y diagnósticos por región.

## Out of scope

No puntaje automático que garantice calidad profesional ni revisión humana ficticia.

## Technical requirements

- Informe ordenado con rule_id, severidad, bbox, explicación y evidencia; no modifica render
- Separar conformidad matemática de advertencias artísticas y permitir supresiones localizadas

## Proposed implementation

- Implementar hard checks primero y métricas sobre fixtures sintéticas
- Añadir heurísticas/supresiones y orden estable por regla/región/posición

## Acceptance criteria

- [ ] AC1: Un color fuera de paleta strict se detecta como fallo y un singleton como advertencia
- [ ] AC2: Informe se reproduce idéntico y supresión de un ojo no oculta errores de otra región

## Required tests

- [ ] T1: Corpus sintético con defectos conocidos y versiones corregidas
- [ ] T2: Tests de no mutación, orden estable, regiones superpuestas y estabilidad temporal

## Expected deliverables

- Reporte estructurado de calidad con hard checks y warnings identificables.
- Fixtures positivas/negativas por regla y separación entre métricas y juicio artístico.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- Un score no debe presentarse como garantía profesional ni como aprobación humana.

## Evidence

Pendiente de implementación.
