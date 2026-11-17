# MOANA-014 — Crear contornos y análisis de clusters

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-014
- Aliases históricos: MOA-014
- Phase: P3
- Priority: P1
- Status: blocked
- Complexity: L (relativa, no estimación de tiempo)
- Dependencies: [MOANA-013](MOANA-013.md), [MOANA-005](MOANA-005.md)
- Related modules: techniques, quality
- Requirements: R006, R025 ([trazabilidad](traceability.md))
- Bloqueo: Dependencias pendientes: MOANA-013, MOANA-005

## Context

Los contornos y clusters deben admitir excepciones artísticas locales.

## Objective

Generar outlines editables y diagnósticos de componentes sin limpieza automática.

## Scope

Implementar morfología binaria para outlines y análisis conectado de clusters con salida editable y diagnósticos.

## Out of scope

No clasificar intención artística como error matemático ni borrar detalles automáticamente.

## Technical requirements

- Vecindad Chebyshev para contornos y conectividad 4/8 explícita para clusters
- Advertencias por singleton y escalones con supresión por región; no limpieza destructiva automática

## Proposed implementation

- Implementar dilatación/erosión acotada y análisis 4/8 conectado
- Representar resultado como operaciones y advertencias con bbox/región

## Acceptance criteria

- [ ] AC1: Contornos internos/externos respetan ancho, huecos y clipping
- [ ] AC2: Un brillo aislado puede conservarse mediante excepción; el análisis no cambia el documento

## Required tests

- [ ] T1: Máscaras con huecos, contactos de esquina, diagonal y borde de canvas
- [ ] T2: Componentes conocidos, outline de ancho 1/2 y operación editable que reproduce la máscara

## Expected deliverables

- Operaciones de contorno y análisis de clusters con conectividad explícita.
- Máscaras de referencia para bordes/huecos/diagonales y ejemplos ampliados.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- No eliminar ojos o partículas por ser singletons; las métricas no inferirán intención.

## Evidence

Pendiente de implementación.
