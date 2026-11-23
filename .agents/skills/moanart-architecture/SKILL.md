---
name: moanart-architecture
description: Resuelve arquitectura, límites de módulos, formatos y compatibilidad de MoanArt. Úsala para decisiones estructurales o cambios de contrato, no para cada ajuste local de código.
---

# MoanArt — Architecture

Lee [arquitectura y ADR](../../../docs/architecture/README.md), [MOANART.md](../../../MOANART.md) y los issues dependientes.

- Identifica datos, propietario de estado, efectos y dirección de imports. Mantén render puro respecto a disco y editor independiente del raster.
- Evalúa la decisión con un caso concreto: edición de un ojo, cambio de paleta, rechazo de un documento excesivo o roundtrip de proyecto.
- Si cambia una garantía, escribe ADR con contexto, decisión, alternativas, consecuencias y prueba que la respalda; actualiza la fuente de verdad.
- Separa versiones de schema, renderer y distribución. Un formato desconocido requiere rechazo o migración explícita, no tolerancia silenciosa.
- Diseña contrato de capacidad/error antes de prometer un backend o export. No construyas extensiones dinámicas ejecutables desde JSON.
- Mantén el DAG de módulos y de issues acíclico. No añadas framework, servicio o GUI para resolver una necesidad local.

Entrega un contrato implementable, los issues afectados y la verificación requerida. Respeta el alcance actual del usuario.

Antes de diseñar una API, identifica su consumidor y errores públicos; conserva compatibilidad de schema/renderer/paquete por separado. Compara dependencias nuevas con los límites de imports y ownership de [module-contracts](../../../docs/architecture/module-contracts.md). No ocultes un ciclo mediante imports tardíos.
