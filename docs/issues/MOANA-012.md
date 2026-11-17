# MOANA-012 — Exponer API pública y CLI estático

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-012
- Aliases históricos: MOA-012
- Phase: P2
- Priority: P1
- Status: blocked
- Complexity: M (relativa, no estimación de tiempo)
- Dependencies: [MOANA-010](MOANA-010.md), [MOANA-011](MOANA-011.md)
- Related modules: api, cli
- Requirements: R014, R038 ([trazabilidad](traceability.md))
- Bloqueo: Dependencias pendientes: MOANA-010, MOANA-011

## Context

Los agentes y programas deben usar la misma interfaz de producto.

## Objective

Ofrecer funciones tipadas y comandos estáticos con errores/capacidades reales.

## Scope

Crear moana/api y comando moana para validate/render/inspect/export estático con resultados y errores documentados.

## Out of scope

No editor interactivo, GUI ni integración con proveedor de IA.

## Technical requirements

- Fachada tipada sin objetos mutables de bibliotecas; añadir entrypoint sólo al funcionar
- CLI con códigos de §13 y paths autorizados por el llamador; capacidades visibles

## Proposed implementation

- Componer servicios en fachada y registrar entrypoint sólo cuando funcione
- Traducir errores de dominio a exit codes y probar desde wheel aislado

## Acceptance criteria

- [ ] AC1: Una instalación limpia del wheel valida un JSON y exporta un PNG de 128×128
- [ ] AC2: Help y errores distinguen capacidades disponibles, entrada inválida, presupuesto e I/O

## Required tests

- [ ] T1: Integración CLI en directorio ajeno al repo con paths con espacios
- [ ] T2: Tests de exit codes, no traceback por defecto, stdout parseable y error de operación futura

## Expected deliverables

- API pública y CLI estático documentados con contratos de retorno/error.
- Ejemplos ejecutables, pruebas de argumentos, códigos de salida e integración.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- Help o ejemplos no deben exponer operaciones aún no implementadas como disponibles.

## Evidence

Pendiente de implementación.
