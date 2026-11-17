# Changelog

## Sin publicar

- MOANA-005: `moana.palette` con `Rgba` canónico `#RRGGBBAA`, `Palette` inmutable por IDs con perfiles `strict`/`rgba` (mismas reglas, códigos y orden de errores que el esquema), edición sin renumerar, `ColorRemap` explícito y advertencias de rampa por luminancia lineal entera (tabla sRGB literal); `moana.core.ids` como dueño de los lenguajes de ID y color, `detail_sort_key` en `core.errors` y `MAX_RAMP_ENTRIES` (ADR-014). Contrato MOANA.md 0.1.6-draft.
- MOANA-004: `moana.core.canvas.Canvas`, lienzo RGBA `uint8` propietario de su buffer (copias en ambos sentidos, alfa cero normalizado, acceso por píxel sin wraparound, `visual_digest`), presupuesto comprobado antes de reservar y adaptador `moana.core.pillow_adapter` sólo para imágenes `RGBA` de un frame; `import moana.core` sigue sin cargar NumPy ni Pillow (ADR-013). Contrato MOANA.md 0.1.5-draft.
- MOANA-003: `RenderLimits` y `Deadline` cooperativo en `moana.core`; `moana.render.estimate_cost`/`plan_budget` con el estimador `budget-v1` que rechaza con `BudgetExceeded` (recurso, límite y estimación por detalle) antes de reservar buffers (ADR-012). Contrato MOANA.md 0.1.4-draft.
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
