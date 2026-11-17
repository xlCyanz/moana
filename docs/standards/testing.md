# Estándares de testing

La [estrategia general](../TESTING.md) y [MOANA.md §21](../../MOANA.md) son la referencia. En infraestructura se verifican bibliotecas y tooling; eso no equivale a probar un renderer de Moana.

## Elegir el nivel de prueba

| Nivel | Objetivo | Casos representativos |
| --- | --- | --- |
| Unitario | Una regla observable con oráculo independiente | Caja semiabierta, empate de línea, validación de color, DAG con ciclo |
| Integración | Fronteras entre componentes | Documento→render→PNG→decode; wheel instalado fuera de `src` |
| Propiedades | Invariantes sobre entradas variadas y acotadas | Giro cuatro veces, espejo doble, normalización idempotente, no mutación |
| Regresión visual | Igualdad exacta de dimensiones y RGBA | expected/actual/diff, bbox y conteo de diferencias |
| Determinismo | Independencia de estado no declarado | Procesos nuevos, `PYTHONHASHSEED`, caché on/off, matriz de plataforma |
| Seguridad | Rechazo antes de asignación o efectos | JSON profundo, IDs duplicados, ZIP traversal, assets enormes |
| Rendimiento | Coste y recursos comparables | Corpus fijo, hardware/versiones, warmups, mediana/p95 y memoria |

Organizar unit/integration/visual/fixtures cuando haya tests o recursos reales para esas categorías. No crear carpetas vacías ni snapshots de documentación como sustituto de contratos. Un cambio editorial no exige nuevos tests; un nuevo validador necesita ejemplos que demuestren tanto aceptación como rechazo.

## Oráculos y regresiones

Las fixtures pequeñas se calculan manualmente o mediante una formulación independiente. No se copia la salida de la implementación como expected sin revisión. Para imágenes, comparar píxeles decodificados y dimensiones; bytes PNG comprimidos son otra garantía. SSIM puede apoyar inspección, pero no sustituye igualdad exacta del perfil entero.

Un fallo visual conserva fuente, expected, actual, diff, bbox y entorno. La actualización de golden requiere explicar el cambio de contrato e inspeccionar la diferencia. CI no modifica baselines ni aprueba por sí sola la intención artística. Una revisión humana se registra como tal, con responsable y observaciones; una evaluación de agente no la suplanta.

Los tests de edición comprueban estructura/IDs preservados, atomicidad y conflictos, además del PNG. Los de GIF comparan frames compuestos y timeline efectivo, pues un codec puede fusionar imágenes iguales. Los de límites instrumentan reservas/IO para detectar trabajo ejecutado antes del rechazo.

## Ejecución y resultados

`uv run pytest` ejecuta la suite; `uv run python scripts/validate.py` reúne el gate. Usar los markers configurados para seleccionar casos de seguridad, visuales o lentos cuando existan. Una selección vacía no demuestra cobertura. Reportar comando, entorno, resultado y limitaciones.

La cobertura numérica ayuda a localizar caminos sin ejercicio; el paquete inicial de una constante no necesita un umbral artificial. Incorporar al crecer el motor pruebas de ramas críticas y casos negativos, sin perseguir un porcentaje mediante pruebas que repitan la implementación.

Los benchmarks siguen MOANA.md §22 y no se mezclan con aserciones temporales inestables de PR. Fijar corpus y versiones, separar I/O y render, medir 5 warmups/30 muestras y repetir una regresión antes de atribuirla al cambio.
