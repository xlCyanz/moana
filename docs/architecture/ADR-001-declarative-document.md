# ADR-001 — Documento declarativo e identidad estable

Estado: aceptado para implementación · 2026-11-16.

## Contexto

Una imagen plana no conserva la identidad del ojo, la capa o el arma que el usuario quiere editar. Reconstruir una imagen generada perdería partes correctas y haría imposible una revisión localizada y reproducible.

## Decisión

El documento versionado con IDs globales es fuente de verdad. Las operaciones son datos tipados; los comandos de edición producen documentos nuevos de forma atómica. El render es un derivado sin I/O. Pydantic genera JSON Schema cuando MOANA-002 exista. IDs no se reasignan al ordenar capas y los frames referencian la base mediante overrides.

## Alternativas y consecuencias

Raster como fuente primaria facilita pintar pero pierde semántica; scripts Python arbitrarios dan flexibilidad pero no son un formato seguro ni fácilmente editable. Un scene graph declarativo limita expresividad a cambio de validación, determinismo y trazabilidad. Las extensiones exigirán un contrato y migraciones explícitas. MOANA-018/019/020 prueban atomicidad, historial y roundtrip.
