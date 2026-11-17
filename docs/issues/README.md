# Backlog de Moana

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

36 issues locales; sus IDs no implican publicación en GitHub. Prioridad P0 = contrato/crítico, P1 = entrega principal, P2 = extensión.

| Issue | Resultado | Fase | Estado | Dependencias directas |
| --- | --- | --- | --- | --- |
| [MOA-000](MOA-000.md) | Inicializar infraestructura y planificación | P0 | done | — |
| [MOA-001](MOA-001.md) | Definir tipos, coordenadas, errores y límites | P1 | planned | MOA-000 |
| [MOA-002](MOA-002.md) | Implementar documento Pydantic y JSON Schema | P1 | planned | MOA-001 |
| [MOA-003](MOA-003.md) | Aplicar presupuesto de trabajo y recursos | P1 | planned | MOA-001, MOA-002 |
| [MOA-004](MOA-004.md) | Crear lienzo RGBA y propiedad de buffers | P1 | planned | MOA-001, MOA-003 |
| [MOA-005](MOA-005.md) | Implementar paletas y rampas | P1 | planned | MOA-001, MOA-002 |
| [MOA-006](MOA-006.md) | Rasterizar primitivas enteras y flood fill | P1 | planned | MOA-004, MOA-005 |
| [MOA-007](MOA-007.md) | Añadir adaptador de paths AggDraw | P3 | planned | MOA-006, MOA-010, MOA-028 |
| [MOA-008](MOA-008.md) | Añadir transformaciones pixel-perfect | P1 | planned | MOA-006 |
| [MOA-009](MOA-009.md) | Implementar capas, grupos y composición | P2 | planned | MOA-002, MOA-004, MOA-005, MOA-006, MOA-008 |
| [MOA-010](MOA-010.md) | Construir pipeline de render determinista | P2 | planned | MOA-002, MOA-003, MOA-006, MOA-009 |
| [MOA-011](MOA-011.md) | Exportar PNG y manifiesto de salida | P2 | planned | MOA-010 |
| [MOA-012](MOA-012.md) | Exponer API pública y CLI estático | P2 | planned | MOA-010, MOA-011 |
| [MOA-013](MOA-013.md) | Añadir máscaras y regiones semánticas | P3 | planned | MOA-009, MOA-010 |
| [MOA-014](MOA-014.md) | Crear contornos y análisis de clusters | P3 | planned | MOA-013, MOA-005 |
| [MOA-015](MOA-015.md) | Añadir bandas de sombreado e iluminación | P3 | planned | MOA-005, MOA-013 |
| [MOA-016](MOA-016.md) | Implementar dithering ordenado | P3 | planned | MOA-005, MOA-013 |
| [MOA-017](MOA-017.md) | Crear presets de materiales versionados | P3 | planned | MOA-014, MOA-015, MOA-016 |
| [MOA-018](MOA-018.md) | Implementar batches de edición atómica | P3 | planned | MOA-002, MOA-010, MOA-012, MOA-013 |
| [MOA-019](MOA-019.md) | Añadir undo/redo e historial inmutable | P3 | planned | MOA-018 |
| [MOA-020](MOA-020.md) | Persistir proyectos y assets seguros | P4 | planned | MOA-018, MOA-019, MOA-011 |
| [MOA-021](MOA-021.md) | Versionar y migrar formatos de proyecto | P4 | planned | MOA-020 |
| [MOA-022](MOA-022.md) | Implementar timeline y evaluación de frames | P4 | planned | MOA-018, MOA-019, MOA-010 |
| [MOA-023](MOA-023.md) | Exportar spritesheets y manifest reversible | P4 | planned | MOA-022, MOA-011 |
| [MOA-024](MOA-024.md) | Exportar GIF con política de pérdidas | P4 | planned | MOA-022, MOA-005, MOA-011 |
| [MOA-025](MOA-025.md) | Añadir APNG y WebP lossless opcionales | P4 | planned | MOA-022, MOA-011 |
| [MOA-026](MOA-026.md) | Crear informes de calidad gráfica | P5 | planned | MOA-014, MOA-015, MOA-022 |
| [MOA-027](MOA-027.md) | Construir corpus artístico y rúbrica humana | P5 | planned | MOA-017, MOA-022, MOA-026, MOA-028 |
| [MOA-028](MOA-028.md) | Crear harness de regresión visual | P1 | planned | MOA-004 |
| [MOA-029](MOA-029.md) | Verificar determinismo entre procesos y plataformas | P2 | planned | MOA-010, MOA-011, MOA-028 |
| [MOA-030](MOA-030.md) | Ejercitar amenazas y entradas adversarias | P5 | planned | MOA-003, MOA-020, MOA-021, MOA-022 |
| [MOA-031](MOA-031.md) | Medir rendimiento y memoria de referencia | P5 | planned | MOA-010, MOA-022, MOA-027 |
| [MOA-032](MOA-032.md) | Optimizar caché y render incremental acotados | P5 | planned | MOA-018, MOA-031 |
| [MOA-033](MOA-033.md) | Documentar flujos IA y previews editables | P5 | planned | MOA-012, MOA-018, MOA-020, MOA-026 |
| [MOA-034](MOA-034.md) | Añadir ejemplos de tiles y escenarios modulares | P5 | planned | MOA-008, MOA-016, MOA-020, MOA-023 |
| [MOA-035](MOA-035.md) | Preparar release y comprobar Definition of Done | P5 | planned | MOA-007, MOA-021, MOA-023, MOA-024, MOA-025, MOA-027, MOA-029, MOA-030, MOA-032, MOA-033, MOA-034 |
