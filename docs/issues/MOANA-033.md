# MOANA-033 — Documentar flujos IA y previews editables

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-033
- Aliases históricos: MOA-033
- Phase: P5
- Priority: P1
- Status: blocked
- Complexity: M (relativa, no estimación de tiempo)
- Dependencies: [MOANA-012](MOANA-012.md), [MOANA-018](MOANA-018.md), [MOANA-020](MOANA-020.md), [MOANA-026](MOANA-026.md)
- Related modules: docs, api
- Requirements: R014, R034, R038 ([trazabilidad](traceability.md))
- Bloqueo: Dependencias pendientes: MOANA-012, MOANA-018, MOANA-020, MOANA-026

## Context

Las sesiones futuras no conservarán el contexto de esta conversación.

## Objective

Ofrecer un tutorial ejecutable del flujo crear/mostrar/editar con el motor real.

## Scope

Completar tutorial JSON/Python/CLI y flujo de agente desde brief hasta preview y modificación por ID usando capacidades reales.

## Out of scope

No GUI, servicio alojado, credenciales ni envío de mensajes a terceros.

## Technical requirements

- Ejemplos ejecutables con schema vigente, paths relativos autorizados y PNG 1×/4×
- Actualizar skills y capabilities tras implementar; sin proveedor IA obligatorio

## Proposed implementation

- Escribir ejemplos sobre API/CLI implementados y validar schema vigente
- Ejecutar tutorial desde wheel limpio y actualizar skills/capabilities

## Acceptance criteria

- [ ] AC1: Un usuario reproduce creación, inspección y recolor con los comandos documentados
- [ ] AC2: El agente conserva fuente/revisión y presenta limitaciones sin prometer generación visual inexistente

## Required tests

- [ ] T1: Ejecutar snippets/tutorial en entorno wheel limpio
- [ ] T2: Validar ejemplos JSON contra schema y comprobar sólo región prevista cambia salvo dependencias declaradas

## Expected deliverables

- Guía de flujos IA para crear, inspeccionar y editar documentos por IDs.
- Ejemplos ejecutables de preview/cambio localizado y recuperación de errores.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- No documentar una API de diseño como importable antes de completar sus dependencias.

## Evidence

Pendiente de implementación.
