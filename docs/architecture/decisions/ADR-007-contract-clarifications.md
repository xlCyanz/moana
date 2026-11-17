# ADR-007 — Aclaraciones previas a implementar el motor

Estado: aceptado para implementación · 2026-11-17.

## Contexto y decisiones

La auditoría de MOANA.md detectó cuatro ambigüedades que afectarían implementaciones independientes. Se corrigen ahora en la especificación 0.1.1-draft, sin añadir código gráfico:

1. **Even-odd y degeneración.** Un polígono autointersectado puede tener área algebraica cero y relleno no vacío. La cobertura se decide mediante la regla even-odd sobre centros de píxel; no se utiliza shoelace=0 como descarte. MOANA-006 exige una fixture bow-tie.
2. **Identidad al ramificar historial.** Después de undo, ramas diferentes pueden compartir revision=1. Los batches requieren base_revision y base_snapshot, digest del documento normalizado. El snapshot se identifica por digest y la revisión numérica es local a la rama. MOANA-018/019 prueban conflictos entre ramas con igual revisión.
3. **Proyecto y documento.** Un Document estricto no admite un campo assets no declarado. ProjectManifest es un sobre separado con kind, project_version, document, assets e history opcional. Los assets/snapshots son inmutables y se referencian por hash; se compromete el manifiesto al final para preservar el estado previo ante fallos. MOANA-020 cubre el roundtrip y el fallo intermedio.
4. **No sobrescritura y concurrencia.** exists seguido de replace presenta una carrera. overwrite=false requiere un commit atómico sin reemplazo o error explícito si no se puede garantizar; MOANA-011 prueba dos escritores concurrentes.

La especificación también distingue el vocabulario MVP de colecciones previstas para capacidades futuras. Un nombre de técnica en la visión no es una gramática JSON implementada; el issue que la incorpore define su payload y versión de schema.

## Alternativas y consecuencias

Un contador global de revisión requeriría un coordinador persistente; el digest permite funciones de edición puras. Mezclar manifiesto y documento obliga a todas las operaciones a conocer almacenamiento; el sobre mantiene esa frontera. Usar bytes inmutables puede dejar assets huérfanos después de un fallo; su recolección es explícita y no compromete el proyecto anterior. Rechazar filesystem sin garantía de commit es preferible a prometer atomicidad inexistente.

Los ejemplos de batch se actualizan con base_snapshot. No existe todavía una versión publicada del schema del motor; se registra el cambio de contrato y se exige su implementación posterior, sin afirmar una migración de datos reales ya probada.
