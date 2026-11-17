# Changelog

## Sin publicar

- MOANA-002: `moana.schema` con modelos Pydantic estrictos del documento 1.0, lectura acotada (bytes, profundidad, nodos, claves duplicadas, NaN), registro explícito de capacidades (`UNSUPPORTED_OPERATION`), errores agregados con `ErrorDetail` y pointer, normalización canónica y `snapshot_digest`, y JSON Schema generado en `schemas/` (ADR-011). Contrato MOANA.md 0.1.3-draft.
- MOANA-001: `moana.core` con `Point`, `Dimensions`, `Box` semiabierta (vacío como `None`), `GeometryLimits` y jerarquía de errores con códigos estables, códigos de salida, `json_pointer` y contexto inmutable picklable (ADR-010). Contrato MOANA.md 0.1.2-draft.

## Infraestructura — 2026-11-17 (sin nueva versión del paquete)

- Backlog publicado en GitHub (`scripts/github_sync.py`): 36 issues, 6 milestones por fase, labels de fase/prioridad/complejidad/estado/módulo y 95 dependencias nativas. Cada issue incluye una guía de ejecución para agentes generada por `scripts/agent_guide.py`.

- Capa Claude Code (ADR-009): `CLAUDE.md`, ocho reglas por ruta, siete envoltorios de skills, seis subagentes, hooks probados en `scripts/claude_hooks.py` y validación en el checker.

- Backlog MOANA con aliases históricos, seis estados, metadatos completos y evidencia por criterio/prueba.
- Guías, estándares, cuatro ADR adicionales, siete skills revisadas y ocho roles.
- Lectura/escritura UTF-8 explícita y regresión del fallo observado en CI Windows.
- Build mediante uv, logs/cobertura de validación y pin Python 3.12.16.
- Contratos aclarados de polígonos, snapshots de edición y proyectos atómicos; sin implementación del motor.

## 0.1.0.dev0 — 2026-11-16

- Especificación, contratos y planificación de Moana.
- Paquete mínimo tipado, entorno uv, lint, mypy, pytest y build.
- Skills locales, roles Codex, CI y validación del backlog.
- Sin implementación del motor gráfico; las APIs descritas son objetivos futuros.
