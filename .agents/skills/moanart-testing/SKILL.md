---
name: moanart-testing
description: Diseña y ejecuta pruebas de MoanArt para píxeles, determinismo, edición, presupuestos y packaging; úsala al verificar contratos o construir infraestructura de tests.
---

# MoanArt — Testing

Lee [TESTING.md](../../../docs/TESTING.md) y [MOANART.md](../../../MOANART.md) §§20–22. Distingue smoke del entorno de pruebas del motor aún pendiente.

- Escoge oráculos independientes: máscaras pequeñas calculadas a mano, fórmulas de composición y propiedades de inversas/inmutabilidad. No copies la salida del código como verdad.
- Prueba extremos, negativos, bool/float indebidos, aliasing, revisión obsoleta y rechazo antes de asignación cuando apliquen.
- Compara dimensiones + RGBA exacto; conserva expected/actual/diff y bbox. Nunca actualices baseline automáticamente para arreglar CI.
- Determinismo requiere procesos nuevos, PYTHONHASHSEED, caché on/off y matriz de plataforma. La igualdad de PNG comprimido es otra garantía.
- Export de animación compara timeline compuesto y duraciones efectivas, teniendo en cuenta fusiones de frames iguales del codec.
- Elige la prueba proporcional al cambio; no escribas tests que sólo repitan textos o detalles de implementación.

Ejecuta el gate común y reporta comandos/resultados reales, casos no cubiertos y por qué. La ausencia de tests visuales en P0 no es evidencia gráfica.

Elige unit para reglas locales, integration para documento→resultado→export o tooling completo, y property-based para invariantes con dominio acotado. Usa fixtures de píxeles independientes en regresión visual. Un benchmark registra CPU/OS/Python/lock, 5 warmups, 30 muestras, mediana/p95 y memoria; no mezcla I/O con render ni impone un umbral rígido sobre un runner no estabilizado. Consulta [testing](../../../docs/standards/testing.md) para cuándo usar cada nivel.
