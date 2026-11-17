# Estándares de arquitectura

Estado de módulos e imports: [overview](../architecture/overview.md), [contratos](../architecture/module-contracts.md) y [MOANA.md §3](../../MOANA.md). Los módulos futuros se crean al implementar un issue, no como carpetas vacías para simular progreso.

## Decisiones y fronteras

Una decisión estructural identifica entrada, salida, propietario del estado, efectos, costes y errores. Mantener rasterización separada de almacenamiento; edición separada de rasterización; diagnóstico separado de mutación. La fachada coordina esos servicios sin duplicar sus algoritmos.

Las dependencias de imports apuntan hacia contratos estables. No resolver ciclos con import dinámico, localizadores globales o callbacks sin tipos. Una dependencia compartida se extrae a un contrato mínimo sólo cuando existen consumidores concretos. Preferir composición y funciones pequeñas; evitar clases base que no representen variación real.

Un dato persistido es declarativo, versionado y validable. Una capacidad nueva especifica modelo, límites, operación, coste, pruebas y error cuando no está disponible. Los lectores no ignoran campos futuros bajo la apariencia de compatibilidad. Las opciones que cambian resultado visual deben ser explícitas y participar en la identidad de render.

## Cuándo escribir un ADR

Crear un ADR cuando cambie un contrato observable, dirección de dependencias, formato persistente, estrategia de backend, garantía de determinismo o política de compatibilidad. Un ajuste interno sin efecto arquitectónico puede explicarse en el issue o revisión.

Cada ADR registra contexto, alternativas, decisión, consecuencias y evidencia pendiente/observada. Los ADR existentes se conservan; una decisión nueva indica cuál sustituye. No repetir íntegramente las fórmulas de MOANA.md: enlazarlas y actualizar la fuente normativa si cambian.

## Revisión de una propuesta

Evaluar al menos un recorrido concreto, por ejemplo recolor de una parte, rechazo por presupuesto o roundtrip de proyecto. Comprobar si la propuesta preserva IDs, errores, estado no afectado y formatos. Identificar migración y fixtures antes de declarar un cambio compatible. Toda optimización demuestra equivalencia y beneficio medido.

El issue que implementa la decisión incluye los entregables y pruebas; una decisión documentada no permite marcar funcionalidad como `done`. El [ciclo de issues](../guides/issue-lifecycle.md) define la evidencia de cierre.
