# Backlog de Moana

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

36 issues únicos; los aliases MOA-xxx conservan enlaces previos y no incrementan el total. Los IDs no son números de issues GitHub.

Prioridades: P0 fundamento/bloqueante; P1 funcionalidad central; P2 avanzada; P3 mejora opcional. No se inventan mejoras opcionales sólo para llenar P3.

[Roadmap](roadmap.md) · [Dependencias](dependency-map.md) · [Trazabilidad](traceability.md) · [Ciclo de vida](../guides/issue-lifecycle.md).

Estados: {'blocked': 2, 'done': 30, 'ready': 4}.

| Issue | Resultado | Fase | Prioridad | Estado | Dependencias directas |
| --- | --- | --- | --- | --- | --- |
| [MOANA-000](MOANA-000.md) | Inicializar infraestructura y planificación | P0 | P0 | done | — |
| [MOANA-001](MOANA-001.md) | Definir tipos, coordenadas, errores y límites | P1 | P0 | done | MOANA-000 |
| [MOANA-002](MOANA-002.md) | Implementar documento Pydantic y JSON Schema | P1 | P0 | done | MOANA-001 |
| [MOANA-003](MOANA-003.md) | Aplicar presupuesto de trabajo y recursos | P1 | P0 | done | MOANA-001, MOANA-002 |
| [MOANA-004](MOANA-004.md) | Crear lienzo RGBA y propiedad de buffers | P1 | P1 | done | MOANA-001, MOANA-003 |
| [MOANA-005](MOANA-005.md) | Implementar paletas y rampas | P1 | P1 | done | MOANA-001, MOANA-002 |
| [MOANA-006](MOANA-006.md) | Rasterizar primitivas enteras y flood fill | P1 | P1 | done | MOANA-004, MOANA-005 |
| [MOANA-007](MOANA-007.md) | Añadir adaptador de paths AggDraw | P3 | P2 | done | MOANA-006, MOANA-010, MOANA-028 |
| [MOANA-008](MOANA-008.md) | Añadir transformaciones pixel-perfect | P1 | P1 | done | MOANA-006 |
| [MOANA-009](MOANA-009.md) | Implementar capas, grupos y composición | P2 | P1 | done | MOANA-002, MOANA-004, MOANA-005, MOANA-006, MOANA-008 |
| [MOANA-010](MOANA-010.md) | Construir pipeline de render determinista | P2 | P0 | done | MOANA-002, MOANA-003, MOANA-006, MOANA-009 |
| [MOANA-011](MOANA-011.md) | Exportar PNG y manifiesto de salida | P2 | P1 | done | MOANA-010 |
| [MOANA-012](MOANA-012.md) | Exponer API pública y CLI estático | P2 | P1 | done | MOANA-010, MOANA-011 |
| [MOANA-013](MOANA-013.md) | Añadir máscaras y regiones semánticas | P3 | P1 | done | MOANA-009, MOANA-010 |
| [MOANA-014](MOANA-014.md) | Crear contornos y análisis de clusters | P3 | P1 | done | MOANA-013, MOANA-005 |
| [MOANA-015](MOANA-015.md) | Añadir bandas de sombreado e iluminación | P3 | P1 | done | MOANA-005, MOANA-013 |
| [MOANA-016](MOANA-016.md) | Implementar dithering ordenado | P3 | P1 | done | MOANA-005, MOANA-013 |
| [MOANA-017](MOANA-017.md) | Crear presets de materiales versionados | P3 | P1 | done | MOANA-014, MOANA-015, MOANA-016 |
| [MOANA-018](MOANA-018.md) | Implementar batches de edición atómica | P3 | P0 | done | MOANA-002, MOANA-010, MOANA-012, MOANA-013 |
| [MOANA-019](MOANA-019.md) | Añadir undo/redo e historial inmutable | P3 | P1 | done | MOANA-018 |
| [MOANA-020](MOANA-020.md) | Persistir proyectos y assets seguros | P4 | P1 | done | MOANA-018, MOANA-019, MOANA-011 |
| [MOANA-021](MOANA-021.md) | Versionar y migrar formatos de proyecto | P4 | P1 | done | MOANA-020 |
| [MOANA-022](MOANA-022.md) | Implementar timeline y evaluación de frames | P4 | P1 | done | MOANA-018, MOANA-019, MOANA-010 |
| [MOANA-023](MOANA-023.md) | Exportar spritesheets y manifest reversible | P4 | P1 | done | MOANA-022, MOANA-011 |
| [MOANA-024](MOANA-024.md) | Exportar GIF con política de pérdidas | P4 | P1 | done | MOANA-022, MOANA-005, MOANA-011 |
| [MOANA-025](MOANA-025.md) | Añadir APNG y WebP lossless opcionales | P4 | P2 | done | MOANA-022, MOANA-011 |
| [MOANA-026](MOANA-026.md) | Crear informes de calidad gráfica | P5 | P1 | done | MOANA-014, MOANA-015, MOANA-022 |
| [MOANA-027](MOANA-027.md) | Construir corpus artístico y rúbrica humana | P5 | P1 | done | MOANA-017, MOANA-022, MOANA-026, MOANA-028 |
| [MOANA-028](MOANA-028.md) | Crear harness de regresión visual | P1 | P1 | done | MOANA-004 |
| [MOANA-029](MOANA-029.md) | Verificar determinismo entre procesos y plataformas | P2 | P1 | done | MOANA-010, MOANA-011, MOANA-028 |
| [MOANA-030](MOANA-030.md) | Ejercitar amenazas y entradas adversarias | P5 | P0 | ready | MOANA-003, MOANA-020, MOANA-021, MOANA-022 |
| [MOANA-031](MOANA-031.md) | Medir rendimiento y memoria de referencia | P5 | P1 | ready | MOANA-010, MOANA-022, MOANA-027 |
| [MOANA-032](MOANA-032.md) | Optimizar caché y render incremental acotados | P5 | P2 | blocked | MOANA-018, MOANA-031 |
| [MOANA-033](MOANA-033.md) | Documentar flujos IA y previews editables | P5 | P1 | ready | MOANA-012, MOANA-018, MOANA-020, MOANA-026 |
| [MOANA-034](MOANA-034.md) | Añadir ejemplos de tiles y escenarios modulares | P5 | P2 | ready | MOANA-008, MOANA-016, MOANA-020, MOANA-023 |
| [MOANA-035](MOANA-035.md) | Preparar release y comprobar Definition of Done | P5 | P1 | blocked | MOANA-007, MOANA-021, MOANA-023, MOANA-024, MOANA-025, MOANA-027, MOANA-029, MOANA-030, MOANA-032, MOANA-033, MOANA-034 |
