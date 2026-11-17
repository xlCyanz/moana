# MOANA-020 — Persistir proyectos y assets seguros

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-020
- Aliases históricos: MOA-020
- Phase: P4
- Priority: P1
- Status: blocked
- Complexity: L (relativa, no estimación de tiempo)
- Dependencies: [MOANA-018](MOANA-018.md), [MOANA-019](MOANA-019.md), [MOANA-011](MOANA-011.md)
- Related modules: project
- Requirements: R018, R026 ([trazabilidad](traceability.md))
- Bloqueo: Dependencias pendientes: MOANA-018, MOANA-019, MOANA-011

## Context

Los assets y archivos de proyecto atraviesan una frontera de datos no confiables.

## Objective

Guardar/cargar documentos y assets de forma confinada, íntegra y atómica.

## Scope

Crear formato .moana.json, proyecto directorio y contenedor ZIP opcional con assets declarados, hashes y escritura atómica.

## Out of scope

No soporte PSD/Aseprite ni assets remotos o ejecutables.

## Technical requirements

- Confinar rutas y rechazar symlinks, duplicados y traversal antes de extracción
- Limitar entradas, expansión/ratio, bytes y decode Pillow; guardar temporal y conservar destino al fallar
- Modelar ProjectManifest separado de Document y persistir assets/snapshots bajo rutas inmutables por hash antes del commit del manifiesto.

## Proposed implementation

- Definir manifiesto separado del documento y almacenamiento content-addressed de assets
- Inspeccionar ZIP/paths/tamaños antes de escribir y comprometer manifiesto al final

## Acceptance criteria

- [ ] AC1: Guardar/cargar preserva IDs, revisiones, historial y RGBA
- [ ] AC2: Un asset con checksum incorrecto o ruta maliciosa no escribe fuera de la raíz ni carga parcialmente

## Required tests

- [ ] T1: Roundtrip proyecto geométrico y con PNG; fallo simulado de disco
- [ ] T2: ZIP con ../, rutas absolutas, symlink, nombres en colisión, ratio excesivo y bomba de imagen
- [ ] T3: Fallo después de escribir nuevos assets conserva manifiesto y assets previos; el envelope rechaza campos extra sin alterar el schema de Document.

## Expected deliverables

- ProjectManifest, persistencia de assets verificados y guardado con commit final atómico.
- Roundtrips, rechazo de rutas/archivos peligrosos y fallos durante la escritura.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- Guardar el mismo asset path in-place antes del manifiesto rompe atomicidad; versiones inmutables necesarias.

## Evidence

Pendiente de implementación.
