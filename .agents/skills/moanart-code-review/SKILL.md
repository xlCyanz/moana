---
name: moanart-code-review
description: Revisa cambios de MoanArt buscando defectos de corrección, tipos, complejidad, imagen, seguridad y compatibilidad. Úsala para una revisión solicitada o antes de integrar un módulo.
---

# MoanArt — Code Review

Lee el diff, el issue completo y [MOANART.md](../../../MOANART.md) aplicable. Revisa sin modificar archivos salvo que también se soliciten correcciones; no conviertas una revisión en una reescritura fuera de alcance.

- Sigue entrada → validación → coste → raster → export. Busca referencias sin resolver, coerciones inesperadas y reservas o bucles costosos anteriores al presupuesto.
- Comprueba tipo/shape/dtype y ownership de arrays, casts injustificados y `Any` que oculte un contrato. La anotación de un array no garantiza su forma en ejecución.
- Examina complejidad en tamaño de canvas, operaciones, vértices, capas y frames, incluidos temporales y copias. Una vectorización puede aumentar memoria aunque reduzca tiempo.
- Para imagen, revisa off-by-one, empates, clipping, overflow de uint8, alfa, orden de composición, nearest-neighbor y semilla estable. Contrasta fixture con especificación, no con apariencia solamente.
- Para edición, revisa atomicidad, revisión base, IDs preservados, capas bloqueadas, referencias vivas e historial. En I/O, confinamiento de rutas, límites de decode/ZIP, no sobreescritura implícita y escritura atómica.
- Busca regresiones de API/schema/capabilities y dependencias circulares. Evalúa si la abstracción reduce una duplicación real y si los nombres/errores permiten mantener el módulo.
- Para cada hallazgo, explica escenario reproducible, ubicación, consecuencia y prueba que detectaría el fallo. Prioriza defectos accionables; Ruff ya cubre estilo mecánico.

Entrega hallazgos por severidad y evidencia de las verificaciones realizadas. Si no hay hallazgos, informa alcance y límites. No inventes ejecución de CI, aprobación artística humana o tests que no corriste; consulta la [guía de desarrollo](../../../docs/guides/development.md) para el gate.

En tooling portable comprueba UTF-8 explícito al leer/escribir catálogos y documentación, incluyendo tests bajo un locale distinto.
