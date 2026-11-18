# Roadmap

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

Se conservan las seis fases de MOANA.md para respetar las dependencias del contrato existente. Las ocho áreas temáticas de la solicitud se distribuyen entre estas fases; no se crean carpetas vacías ni se pospone schema hasta después del renderer.

Total: 36 issues; fases: {'P0': 1, 'P1': 8, 'P2': 5, 'P3': 8, 'P4': 6, 'P5': 8}.

Prioridades: P0=7, P1=25, P2=4, P3=0. Complejidad S/M/L/XL es relativa, sin promesas de calendario.

## P0 — Inicialización

Puerta de salida: Gate de infraestructura, skills y backlog válido; sin motor.

Estado: 1/1 issues completados.

- [MOANA-000](MOANA-000.md) — Inicializar infraestructura y planificación (done)

## P1 — Contratos y core

Puerta de salida: Modelos estrictos, límites y fixtures enteras exactas.

Estado: 8/8 issues completados.

- [MOANA-001](MOANA-001.md) — Definir tipos, coordenadas, errores y límites (done)
- [MOANA-002](MOANA-002.md) — Implementar documento Pydantic y JSON Schema (done)
- [MOANA-003](MOANA-003.md) — Aplicar presupuesto de trabajo y recursos (done)
- [MOANA-004](MOANA-004.md) — Crear lienzo RGBA y propiedad de buffers (done)
- [MOANA-005](MOANA-005.md) — Implementar paletas y rampas (done)
- [MOANA-006](MOANA-006.md) — Rasterizar primitivas enteras y flood fill (done)
- [MOANA-008](MOANA-008.md) — Añadir transformaciones pixel-perfect (done)
- [MOANA-028](MOANA-028.md) — Crear harness de regresión visual (done)

## P2 — Imagen estática

Puerta de salida: Render 128 x 128, PNG roundtrip y determinismo en matriz.

Estado: 5/5 issues completados.

- [MOANA-009](MOANA-009.md) — Implementar capas, grupos y composición (done)
- [MOANA-010](MOANA-010.md) — Construir pipeline de render determinista (done)
- [MOANA-011](MOANA-011.md) — Exportar PNG y manifiesto de salida (done)
- [MOANA-012](MOANA-012.md) — Exponer API pública y CLI estático (done)
- [MOANA-029](MOANA-029.md) — Verificar determinismo entre procesos y plataformas (done)

## P3 — Arte y edición

Puerta de salida: Técnicas editables y batches atómicos con historial.

Estado: 2/8 issues completados.

- [MOANA-007](MOANA-007.md) — Añadir adaptador de paths AggDraw (done)
- [MOANA-013](MOANA-013.md) — Añadir máscaras y regiones semánticas (done)
- [MOANA-014](MOANA-014.md) — Crear contornos y análisis de clusters (ready)
- [MOANA-015](MOANA-015.md) — Añadir bandas de sombreado e iluminación (ready)
- [MOANA-016](MOANA-016.md) — Implementar dithering ordenado (review)
- [MOANA-017](MOANA-017.md) — Crear presets de materiales versionados (blocked)
- [MOANA-018](MOANA-018.md) — Implementar batches de edición atómica (ready)
- [MOANA-019](MOANA-019.md) — Añadir undo/redo e historial inmutable (blocked)

## P4 — Persistencia y animación

Puerta de salida: Proyecto reversible, atlas y timeline decodificado.

Estado: 0/6 issues completados.

- [MOANA-020](MOANA-020.md) — Persistir proyectos y assets seguros (blocked)
- [MOANA-021](MOANA-021.md) — Versionar y migrar formatos de proyecto (blocked)
- [MOANA-022](MOANA-022.md) — Implementar timeline y evaluación de frames (blocked)
- [MOANA-023](MOANA-023.md) — Exportar spritesheets y manifest reversible (blocked)
- [MOANA-024](MOANA-024.md) — Exportar GIF con política de pérdidas (blocked)
- [MOANA-025](MOANA-025.md) — Añadir APNG y WebP lossless opcionales (blocked)

## P5 — Evaluación y release

Puerta de salida: Corpus revisado, seguridad, benchmarks y wheel limpio.

Estado: 0/8 issues completados.

- [MOANA-026](MOANA-026.md) — Crear informes de calidad gráfica (blocked)
- [MOANA-027](MOANA-027.md) — Construir corpus artístico y rúbrica humana (blocked)
- [MOANA-030](MOANA-030.md) — Ejercitar amenazas y entradas adversarias (blocked)
- [MOANA-031](MOANA-031.md) — Medir rendimiento y memoria de referencia (blocked)
- [MOANA-032](MOANA-032.md) — Optimizar caché y render incremental acotados (blocked)
- [MOANA-033](MOANA-033.md) — Documentar flujos IA y previews editables (blocked)
- [MOANA-034](MOANA-034.md) — Añadir ejemplos de tiles y escenarios modulares (blocked)
- [MOANA-035](MOANA-035.md) — Preparar release y comprobar Definition of Done (blocked)

## Siguiente paso

Implementar [MOANA-018](MOANA-018.md): Implementar batches de edición atómica.
