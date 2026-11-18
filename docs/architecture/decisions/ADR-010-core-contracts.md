# ADR-010 — Contratos de `core`: cajas, límites geométricos y errores

Estado: aceptado · 2026-11-17 · Issue: [MOANA-001](../../issues/MOANA-001.md). Ampliado por [ADR-020](ADR-020-public-api-cli.md): `ReadError` (`READ_ERROR`, salida 5) para lecturas de documento fallidas. Ampliado por [ADR-029](ADR-029-project-persistence.md): `project` reutiliza `ExportError` (escrituras de proyecto) y `ReadError` sin códigos nuevos.

## Contexto

MOANA-001 crea el primer módulo real. MOANA.md §5 fija coordenadas, cajas semiabiertas y dimensiones, y §13 enumera los errores públicos, pero deja abiertos detalles observables que todos los módulos posteriores consumirán. La revisión de arquitectura detectó que el borde excluido de una caja no podía representarse para el píxel máximo, y que faltaban decisiones sobre `json_pointer`, presupuestos y códigos.

## Decisión

1. **Rango de cajas.** El rango absoluto `±1 048 576` de §5 se aplica a coordenadas de píxel (`Point`, `x0`, `y0`). El borde excluido (`x1`, `y1`) puede valer hasta `1 048 577`, de modo que todo píxel válido tiene caja 1 × 1.
2. **Vacío como ausencia.** `Box` nunca es vacía (`x0 < x1`, `y0 < y1`); intersección y recorte devuelven `None` cuando no queda ningún píxel, incluidas las cajas que sólo se tocan. Alternativa descartada: permitir cajas vacías, que obligaría a cada consumidor a comprobar `area == 0` y admitiría cajas invertidas.
3. **Límites geométricos frente a presupuestos.** `GeometryLimits` contiene los máximos del formato (eje, área, coordenada) y sólo puede bajarlos. Los presupuestos de §20, que el anfitrión puede elevar explícitamente, serán `RenderLimits` (MOANA-003), que **compone** `GeometryLimits`. Se nombró `GeometryLimits` antes de tener consumidores para evitar confusión con `RenderLimits`.
4. **Errores.** `MoanaError` lleva `code` estable, `exit_code` de §13, `json_pointer` opcional (§12) y `context` inmutable con valores escalares o tuplas. Son picklables para procesos aislados (§20). Códigos: `INTERNAL_ERROR` (1), `VALIDATION_ERROR` (2), `OUT_OF_BOUNDS` (2), `REFERENCE_ERROR` (2), `UNSUPPORTED_VERSION` (2), `UNSUPPORTED_OPERATION` (2), `BUDGET_EXCEEDED` (3), `EDIT_CONFLICT` (4), `EXPORT_ERROR` (5). `OutOfBoundsError` se añade como subclase de `ValidationError` para el acceso a píxel fuera del lienzo de §5. El exit code vive en la clase para que la CLI no mantenga una tabla paralela.
5. **Integración con Pydantic.** Los errores de `core` no derivan de `ValueError`. `schema` (MOANA-002) valida enteros primitivos con las constantes de `core` y construye los tipos de `core` tras la validación sintáctica, conservando el `json_pointer`. La agregación de varios errores de documento es una ampliación aditiva de MOANA-002.
6. **Nombre `ReferenceError`.** Se mantiene el nombre de §13 aunque coincide con un builtin; se recomienda importarlo como `errors.ReferenceError`.

## Consecuencias

- MOANA.md §5 y §13 se aclaran sin cambiar semántica previa.
- Otros errores de I/O con salida 5 (por ejemplo, lectura de proyectos en MOANA-020) se añadirán como subclases nuevas.
- Evidencia: `tests/unit/core/` (oráculos de conjuntos de píxeles, extremos del rango, pickle de errores y aislamiento de imports).
