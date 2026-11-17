# MOANA-001 — Definir tipos, coordenadas, errores y límites

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-001
- Aliases históricos: MOA-001
- Phase: P1
- Priority: P0
- Status: ready
- Complexity: M (relativa, no estimación de tiempo)
- Dependencies: [MOANA-000](MOANA-000.md)
- Related modules: core
- Requirements: R002, R026, R030 ([trazabilidad](traceability.md))
- Bloqueo: Ninguno

## Context

Las decisiones de coordenadas y errores condicionan todos los módulos raster.

## Objective

Proveer tipos y errores que expresen las reglas exactas de límites.

## Scope

Crear moana/core con contratos inmutables de coordenadas, cajas, dimensiones, límites y jerarquía de errores utilizada por todos los módulos.

## Out of scope

No reservar buffers ni dibujar; no crear aún modelos de documento.

## Technical requirements

- Aplicar cajas semiabiertas, enteros sin bool y top-left según MOANA.md §5
- Separar datos de límites de su aplicación; códigos de error estables sin imports de capas superiores

## Proposed implementation

- Definir tipos inmutables para Point, Box y Dimensions y errores de dominio
- Implementar intersecciones y validación con enteros Python antes de buffers

## Acceptance criteria

- [ ] AC1: Una dimensión 0, coordenada bool o bbox invertida falla con error de dominio identificable
- [ ] AC2: Cajas 1×1 y recortes vacíos tienen semántica documentada y no dependen de NumPy

## Required tests

- [ ] T1: Parametrizar extremos de rango, cajas negativas, bordes y tamaños 1/128/2048
- [ ] T2: Propiedades de intersección: conmutatividad, contención y ausencia de expansión

## Expected deliverables

- Tipos Point/Box/Dimensions, configuración de límites y jerarquía de errores en moana/core.
- Fixtures de bordes y propiedades de intersección; documentación de cajas vacías y errores.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- Los bool son subclase de int; distinguirlos y definir el resultado vacío sin bbox inválida.

## Evidence

Pendiente de implementación.
