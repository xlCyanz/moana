# ADR-006 — Identidad y ciclo de vida del backlog

Estado: aceptado · 2026-11-17. Ampliado por [ADR-041](ADR-041-rename-moanart.md): los IDs `MOANA-xxx` y `MOA-xxx` no cambian con el renombrado a MoanArt y la etiqueta remota del backlog se conserva.

## Contexto

El commit 9388c57 ya publicó 36 issues locales MOANA-000…035 y seis fases P0–P5. La solicitud nueva requiere identificadores MOANA, metadatos completos, estados operativos y rutas de planificación bajo docs/issues. Reemplazar identidades sin transición rompería referencias; duplicar el backlog produciría dos fuentes de verdad.

## Decisión

El catálogo pasa a schema_version=2 y conserva los 36 trabajos con IDs canónicos MOANA-000…035. Cada uno registra su alias MOA anterior; los archivos antiguos se generan como enlaces al único issue vigente. Las rutas anteriores de roadmap, dependencia y trazabilidad también se conservan como enlaces. Los aliases no cuentan como issues ni sirven de clave en dependencias nuevas.

Se mantienen las seis fases del contrato existente. Las ocho áreas temáticas sugeridas se cubren mediante módulos/issues dentro de esas fases: validar el schema debe anteceder al renderer y no aplazarse a una fase posterior de IA. La estructura de carpetas es una organización, no una razón para invertir dependencias.

Se admiten todo, ready, in_progress, blocked, review y done. Los estados activos requieren dependencias done. blocked exige motivo; done exige evidencia para cada criterio AC y prueba T además de evidencia general. Sólo MOANA-000 describe infraestructura ya entregada; ningún módulo gráfico se marca implementado. Prioridades P0–P3 y complejidad S/M/L/XL son independientes de las fases.

El DAG genera dependientes, niveles paralelizables, orden topológico y cadena más larga por número de issues. Ésta se identifica como ruta crítica estructural; sin estimaciones de duración no constituye un calendario.

## Alternativas y consecuencias

Mantener MOA como único nombre incumpliría el formato solicitado; crear issues nuevos duplicaría entregables. Los enlaces de compatibilidad añaden archivos pequeños con una función clara y mantienen el historial de Git. El catálogo y la generación determinista siguen siendo la fuente única. Las transiciones se revisan en el diff; el checker demuestra coherencia del estado actual y cobertura documental, no veracidad de la evidencia escrita ni autorización para ejecutar trabajo.

## Verificación

Pruebas negativas de alias duplicado, dependencia inexistente/cíclica, fase invertida, estado activo bloqueado, motivo ausente, evidencia incompleta y criterios desconocidos. Los Markdown se comparan con su generación en memoria. El estado ready calculado conduce a MOANA-001.
