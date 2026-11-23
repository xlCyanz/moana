# ADR-021 — Contrato de determinismo entre procesos y plataformas

Estado: aceptado · 2026-11-17 · Issue: [MOANA-029](../../issues/MOANA-029.md). Aplica [ADR-018](ADR-018-render-pipeline.md) (render y digest), [ADR-019](ADR-019-png-export.md) (PNG) y [ADR-008](ADR-008-portable-tooling.md) (matriz de CI); no sustituye ninguno. Ampliado por [ADR-041](ADR-041-rename-moanart.md): formatos `moanart-determinism-*/1`; el manifiesto revisado de píxeles no cambia.

## Contexto

MOANA.md §14 exige que el perfil entero dé los mismos bytes RGBA entre sistemas operativos y semillas de hash, y que los PNG se comparen por píxeles decodificados: la igualdad byte a byte sólo se promete con el codec fijado. MOANA-010 ya comprueba procesos nuevos con varios `PYTHONHASHSEED` en una máquina, pero nada demostraba que Linux, macOS y Windows con Python 3.12–3.14 produjeran los mismos píxeles, ni dejaba evidencia útil cuando divergen. Schema 1.0 no tiene grupos, así que el render de documentos no puede ejercitarlos.

## Decisión

1. **Corpus fijo y manifiesto RGBA revisado.** `tests/fixtures/determinism/corpus.json` contiene seis casos pequeños. Cinco son documentos 1.0:
   - `diagonals`: líneas de 45°, una línea poco inclinada y una con empate escrita al revés, que sólo da la máscara correcta si se ordenan los extremos;
   - `alpha`;
   - `transparency`;
   - `clipping`: incluye una línea no diagonal que empieza fuera del lienzo, que sólo da la máscara correcta si se traza antes de recortar;
   - `rounding`: un empate exacto en .5 de §11, donde redondear hacia arriba y redondear al par dan resultados distintos.

   El sexto, `groups`, es un árbol de `moana.layers` con grupos anidados, opacidad y una capa oculta, porque el esquema todavía no admite grupos. `expected.json` guarda para cada caso dimensiones, avisos, digest §14 y **todas las filas como `#RRGGBBAA`**. Los valores salen del oráculo independiente de `tests/integration/test_cross_platform_determinism.py`: máscaras escritas a mano según §6 y la fórmula escalar de §11. No se ejecutó el renderer para producirlos, y un test comprueba que el manifiesto coincide con el oráculo y que el digest se recalcula con `hashlib`. Ninguna herramienta reescribe el manifiesto; cambiarlo exige una revisión como la de los goldens (§21).
2. **Qué se compara.**
   - Píxeles: el digest del RGBA del render se calcula directamente. Los tres PNG (RGBA en memoria, el archivo de `export_png` con commit atómico y, en los casos `strict`, el indexado con la paleta del documento) se decodifican con Pillow. Antes se exige el modo prometido (`RGBA` en el maestro, `P` en el indexado), sin conversiones silenciosas. Todos los digests deben coincidir con el del manifiesto. Esta es la garantía entre plataformas.
   - Bytes PNG: deben ser idénticos entre todas las ejecuciones de **un mismo entorno** (mismo Pillow y zlib), y el archivo escrito debe ser igual al PNG en memoria y a su manifiesto. Entre plataformas sólo se informa: un `zlib` distinto puede comprimir de otra forma (ADR-019).
3. **Procesos nuevos.** `python -m scripts.determinism report` ejecuta la sonda en 12 intérpretes: `PYTHONHASHSEED` 0, 1, 4242 y `random`, por tres serializaciones del corpus (claves en orden, invertidas con indentación, ordenadas y compactas). Todas deben coincidir entre sí y con el manifiesto. No hay caché en el render (ADR-018), así que no se compara caché on/off.
4. **Informe por trabajo.** El informe `artifacts/determinism/determinism-report.json` registra plataforma, arquitectura, Python, versión de Moana, renderer, backend (`integer`), estimador, SHA-256 de `uv.lock`, NumPy, Pillow y zlib, sin rutas ni horas. Para cada caso divergente añade `expected.png`, `actual.png`, `diff.png` (sólo si coinciden las dimensiones), el número de píxeles distintos, la bbox y las filas reales. Si una sonda falla, el informe se escribe igualmente con estado `error`, el entorno, la semilla y la variante de la ejecución fallida y la cola de su stderr. Viaja en el artefacto `diagnostics-<os>-<python>` que ya sube cada trabajo de la matriz.
5. **Comparación entre trabajos.** El trabajo `determinism` (`needs: verify`, `if: !cancelled()`) descarga los artefactos con `actions/download-artifact` fijado por SHA y ejecuta `compare` sólo con la biblioteca estándar y los permisos de lectura del workflow. Falla en estos casos:
   - no hay exactamente 9 informes;
   - se repite un par (sistema, Python mayor.menor);
   - falta alguno de `Darwin`, `Linux` o `Windows` (`--expected-platforms`);
   - algún informe no está `ok`;
   - difieren el lock, el renderer o el backend;
   - algún digest no es el esperado.

   Los bytes PNG distintos dentro de un mismo build de codec (mismo Pillow y zlib) generan un aviso. Entre builds distintos sólo se informan. El resumen lista los artefactos encontrados, para identificar un trabajo ausente o fallido, y va a `$GITHUB_STEP_SUMMARY` y al artefacto `determinism-summary`.

## Alternativas descartadas

- **Digests grabados de un render.** Sería usar la implementación como oráculo (§21).
- **Exigir bytes PNG iguales entre sistemas operativos.** §14 y ADR-019 no lo prometen; un cambio de zlib rompería CI sin alterar ningún píxel.
- **Comparar sólo contra el manifiesto, sin trabajo agregador.** Cada trabajo ya falla solo, pero no habría una tabla común que separe las diferencias de codec de las de píxel ni detectaría informes ausentes.

## Consecuencias

- La garantía cubre el backend entero `integer` en las combinaciones de la matriz (Ubuntu, macOS y Windows con Python 3.12, 3.13 y 3.14) con el lock fijado. No dice nada de AggDraw ni de combinaciones que no se ejecuten.
- Hasta la primera ejecución remota sólo hay evidencia local (macOS arm64, Python 3.12). La parte entre plataformas se confirmará en el workflow `Quality` de `main`.
- Al añadir un caso al corpus hay que escribir su oráculo a mano y regenerar el manifiesto desde ese oráculo, nunca desde un render.
- Evidencia: `tests/integration/test_cross_platform_determinism.py`, `tests/test_repository_tools.py` (cableado del workflow) y `scripts/determinism.py`.
