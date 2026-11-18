# Changelog

## Sin publicar

- MOANA-029: verificación de determinismo entre procesos y plataformas: corpus fijo con manifiesto RGBA de un oráculo independiente (`tests/fixtures/determinism/`), `scripts/determinism.py` (probe/report/compare) y job de CI que compara los informes de la matriz; divergencias de píxel fallan y diferencias de codec PNG sólo se informan (ADR-021).
- MOANA-011: exportación PNG `moana.export.export_png` (RGBA maestro o indexado con la paleta declarada, sin cuantización, escala nearest 1..64 como preview, verificación de ida y vuelta en memoria) con commit atómico sin sobrescritura (`os.link`) o con reemplazo explícito (`os.replace`) y `ExportManifest` con hashes y avisos (ADR-019).
- MOANA-010: orquestador de render determinista `moana.render.render` (validación → frame → rasterizadores registrados → paleta → presupuesto → plan → composición) con `RenderResult` inmutable y `Provenance` de reproducción; máscaras diferidas en `moana.layers` (`DeferredMask`), estimador `budget-v2` (pasada de pintado), RNG por celda en `moana.core.procedural` y digest visual único en `moana.core.digest` (ADR-018). Contrato MOANA.md 0.1.7-draft.
- MOANA-009: capas, grupos y composición en `moana.layers` (`Fill`, `Layer`, `Group`, `LayerTree`, `compose`, `composition_cost`): source-over entera literal de §11 con `round_half_up` y alfa 0 normalizado, grupos aislados con opacidad aplicada una vez, nodos ocultos sin coste, profundidad ≤16, perfil strict y presupuesto comprobado antes de reservar buffers (ADR-017).
- MOANA-008: transformaciones pixel-perfect en `moana.geometry` (`Transform`, `transform_mask`, `transform_box`): espejo, giros 0/90/180/270 sobre índices `(x, y) → (−y, x)` alrededor de un píxel pivote, escala entera nearest-neighbor y traslación explícita; máscaras recortadas sin wraparound por recolección inversa, cajas como conjuntos de píxeles y rechazo de rotación arbitraria o escala no entera (ADR-016).
- MOANA-028: harness de regresión visual exacta en `tests/visual/`: comparación RGBA con alfa cero normalizado, conteo y bbox de diferencias, diagnósticos expected/actual/diff con manifiesto JSON al fallar, y actualización de goldens sólo explícita con `MOANA_UPDATE_GOLDENS=1` (rechazada en CI).
- MOANA-006: `moana.geometry` con máscaras enteras inmutables de pixel/line/rect/ellipse/polygon según §6 (sin shoelace ni defaults de ImageDraw) y flood fill 4-conectado sobre snapshot, acotado por presupuesto antes de copiar (ADR-015).
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
