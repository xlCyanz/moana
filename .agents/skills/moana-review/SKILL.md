---
name: moana-review
description: Revisa cambios de Moana buscando errores de píxel, estado, seguridad, compatibilidad y pruebas insuficientes. Úsala para revisión solicitada o antes de integrar un módulo.
---

# Moana — Code Review

Lee el diff, el issue y [MOANA.md](../../../MOANA.md) aplicable. Trata la revisión como análisis; no modifiques archivos salvo que también se solicite corregir.

- Sigue entrada → validación → coste → raster → export; busca reservas antes del presupuesto y referencias sin resolver.
- Revisa off-by-one, reglas de borde, uint8 overflow, alfa, alias de arrays y semilla/orden global.
- Para edición, comprueba atomicidad, revisión base, capas bloqueadas, referencias vivas e historial inmutable.
- En I/O, comprueba confinamiento de paths, límites de decode/ZIP, escritura atómica y no sobreescritura implícita.
- Contrasta golden y contrato; una imagen agradable no valida determinismo. Comprueba que el test detectaría el fallo señalado.
- Reporta sólo hallazgos accionables con ubicación, escenario y consecuencia. Diferencia defectos de sugerencias y no repitas estilo cubierto por Ruff.

Si no hay hallazgos, dilo con el alcance revisado y pruebas observadas. No inventes resultados, aprobaciones humanas ni ejecución de CI.
