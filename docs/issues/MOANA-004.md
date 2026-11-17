# MOANA-004 — Crear lienzo RGBA y propiedad de buffers

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-004
- Aliases históricos: MOA-004
- Phase: P1
- Priority: P1
- Status: blocked
- Complexity: M (relativa, no estimación de tiempo)
- Dependencies: [MOANA-001](MOANA-001.md), [MOANA-003](MOANA-003.md)
- Related modules: core
- Requirements: R002, R027 ([trazabilidad](traceability.md))
- Bloqueo: Dependencias pendientes: MOANA-001, MOANA-003

## Context

NumPy y Pillow difieren en ownership, índices y representación de datos.

## Objective

Proveer un buffer RGBA seguro con adaptadores sin alias públicos mutables.

## Scope

Crear buffer de canvas y adaptadores Pillow/NumPy con propiedad explícita, normalización de transparencia y acceso seguro.

## Out of scope

No dibujar primitivas ni componer capas.

## Technical requirements

- uint8 C-contiguo [y,x,4], alfa recto y píxel transparente negro
- Copias o vistas inmutables hacia el exterior; acumuladores amplios y límites antes de reservar

## Proposed implementation

- Reservar buffers sólo tras presupuesto y validar shape/dtype/contigüidad
- Añadir copias de frontera y normalizar transparencia al importar/exportar

## Acceptance criteria

- [ ] AC1: Leer/escribir coordenadas válidas preserva RGBA y coordenadas negativas no hacen wrap
- [ ] AC2: Una copia/export de array no puede mutar silenciosamente el canvas original

## Required tests

- [ ] T1: Fixtures 1×1 y 128×128, transparentes con RGB residual y roundtrip NumPy/Pillow
- [ ] T2: Pruebas de aliasing, dtype/shape inválidos, límite de memoria y acceso fuera de rango

## Expected deliverables

- Canvas RGBA y adaptadores con reglas de ownership/copia documentadas.
- Fixtures de canal alfa, clipping, buffers no compartidos y dimensiones extremas.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- Vistas writeable=false pueden reabrirse si el propietario se filtra; probar ownership real.

## Evidence

Pendiente de implementación.
