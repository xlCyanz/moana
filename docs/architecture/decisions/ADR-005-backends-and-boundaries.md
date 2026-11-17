# ADR-005 — Backends gráficos y fronteras declarativas

Estado: aceptado para implementación · Fecha: 2026-11-16.

## Contexto

La especificación exige operaciones deterministas, edición de partes identificables y exportación a formatos comunes. Las bibliotecas ya declaradas resuelven necesidades diferentes; tratarlas como un motor artístico completo ocultaría las reglas de píxel y dificultaría evaluar cambios. Se necesita justificar su colaboración sin introducir una capa genérica de plugins antes de tener casos reales.

## Decisión

Pillow es el backend principal para interoperabilidad de imágenes, buffers y codificación. Sus defaults de dibujo no reemplazan las reglas normativas de geometría y composición. NumPy se utiliza para matrices y operaciones vectorizadas cuando el contrato de dtype, overflow y propiedad del buffer está probado. AggDraw queda en un adaptador de paths opcional desde el punto de vista funcional, con umbral y versión de backend explícitos; no define la garantía del raster entero.

Pydantic valida instrucciones declarativas y genera el schema correspondiente a las capacidades implementadas. La validación de estructura, referencias y recursos precede a la rasterización. El documento con IDs, capas y regiones es fuente editable; las imágenes son resultados derivados. No se incorporan llamadas a modelos de generación de imágenes al núcleo porque no forman parte del contrato de ejecución determinista y no conservan por sí mismas la identidad de cada parte.

Se usan adaptadores pequeños dentro de los módulos existentes. No se crea una interfaz universal de renderer, un framework de shaders o un sistema de carga de código desde documentos. Una sustitución futura de backend deberá demostrar equivalencia del contrato o identificarse como capacidad con garantía diferente.

## Alternativas consideradas

| Alternativa | Motivo para no adoptarla como base |
| --- | --- |
| Delegar todos los píxeles a defaults de Pillow/AggDraw | No expresa de forma suficiente empates, bordes, AA y redondeo que Moana debe fijar |
| Usar sólo arrays NumPy y escribir codecs propios | Añade trabajo de formatos sin mejorar el objetivo inicial |
| Guardar scripts Python en el proyecto | Pierde una frontera segura de datos y dificulta edición por ID, costes y migración |
| Regenerar la imagen con un modelo tras cada cambio | No ofrece el contrato local y reproducible de edición requerido |
| Abstracción extensible para cualquier backend desde P0 | Introduce complejidad sin implementaciones ni benchmarks que la justifiquen |

## Consecuencias y verificación

Las dependencias se mantienen fijadas en el lock y los adaptadores no exponen sus objetos mutables en la API. La tipificación incompleta de una dependencia se limita a su frontera, no se propaga como `Any` por el dominio. Las versiones de codecs forman parte de la evidencia de exports.

MOANA-004 verifica buffers e interoperabilidad; MOANA-006, primitivas exactas; MOANA-007, el adaptador AggDraw; MOANA-010, determinismo; MOANA-011, PNG roundtrip; MOANA-018, edición atómica. La calidad artística se verifica con el corpus y revisión humana de MOANA-027, no con la presencia de estas bibliotecas.

Esta decisión complementa [ADR-001](../ADR-001-declarative-document.md), [ADR-002](../ADR-002-pixel-contract.md) y [ADR-003](../ADR-003-toolchain.md). No cambia sus garantías ni afirma que el motor ya exista.
