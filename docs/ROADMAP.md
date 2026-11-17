# Roadmap

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

Sin fechas estimadas; gates basados en evidencia.

## P0 — Inicialización

Puerta de salida: Gate de infraestructura, skills y backlog válido; sin motor.

Estado: 1/1 issues completados.

- [MOA-000](issues/MOA-000.md) — Inicializar infraestructura y planificación

## P1 — Contratos y core

Puerta de salida: Modelos estrictos, límites y fixtures enteras exactas.

Estado: 0/8 issues completados.

- [MOA-001](issues/MOA-001.md) — Definir tipos, coordenadas, errores y límites
- [MOA-002](issues/MOA-002.md) — Implementar documento Pydantic y JSON Schema
- [MOA-003](issues/MOA-003.md) — Aplicar presupuesto de trabajo y recursos
- [MOA-004](issues/MOA-004.md) — Crear lienzo RGBA y propiedad de buffers
- [MOA-005](issues/MOA-005.md) — Implementar paletas y rampas
- [MOA-006](issues/MOA-006.md) — Rasterizar primitivas enteras y flood fill
- [MOA-008](issues/MOA-008.md) — Añadir transformaciones pixel-perfect
- [MOA-028](issues/MOA-028.md) — Crear harness de regresión visual

## P2 — Imagen estática

Puerta de salida: Render 128 x 128, PNG roundtrip y determinismo en matriz.

Estado: 0/5 issues completados.

- [MOA-009](issues/MOA-009.md) — Implementar capas, grupos y composición
- [MOA-010](issues/MOA-010.md) — Construir pipeline de render determinista
- [MOA-011](issues/MOA-011.md) — Exportar PNG y manifiesto de salida
- [MOA-012](issues/MOA-012.md) — Exponer API pública y CLI estático
- [MOA-029](issues/MOA-029.md) — Verificar determinismo entre procesos y plataformas

## P3 — Arte y edición

Puerta de salida: Técnicas editables y batches atómicos con historial.

Estado: 0/8 issues completados.

- [MOA-007](issues/MOA-007.md) — Añadir adaptador de paths AggDraw
- [MOA-013](issues/MOA-013.md) — Añadir máscaras y regiones semánticas
- [MOA-014](issues/MOA-014.md) — Crear contornos y análisis de clusters
- [MOA-015](issues/MOA-015.md) — Añadir bandas de sombreado e iluminación
- [MOA-016](issues/MOA-016.md) — Implementar dithering ordenado
- [MOA-017](issues/MOA-017.md) — Crear presets de materiales versionados
- [MOA-018](issues/MOA-018.md) — Implementar batches de edición atómica
- [MOA-019](issues/MOA-019.md) — Añadir undo/redo e historial inmutable

## P4 — Persistencia y animación

Puerta de salida: Proyecto reversible, atlas y timeline decodificado.

Estado: 0/6 issues completados.

- [MOA-020](issues/MOA-020.md) — Persistir proyectos y assets seguros
- [MOA-021](issues/MOA-021.md) — Versionar y migrar formatos de proyecto
- [MOA-022](issues/MOA-022.md) — Implementar timeline y evaluación de frames
- [MOA-023](issues/MOA-023.md) — Exportar spritesheets y manifest reversible
- [MOA-024](issues/MOA-024.md) — Exportar GIF con política de pérdidas
- [MOA-025](issues/MOA-025.md) — Añadir APNG y WebP lossless opcionales

## P5 — Evaluación y release

Puerta de salida: Corpus revisado, seguridad, benchmarks y wheel limpio.

Estado: 0/8 issues completados.

- [MOA-026](issues/MOA-026.md) — Crear informes de calidad gráfica
- [MOA-027](issues/MOA-027.md) — Construir corpus artístico y rúbrica humana
- [MOA-030](issues/MOA-030.md) — Ejercitar amenazas y entradas adversarias
- [MOA-031](issues/MOA-031.md) — Medir rendimiento y memoria de referencia
- [MOA-032](issues/MOA-032.md) — Optimizar caché y render incremental acotados
- [MOA-033](issues/MOA-033.md) — Documentar flujos IA y previews editables
- [MOA-034](issues/MOA-034.md) — Añadir ejemplos de tiles y escenarios modulares
- [MOA-035](issues/MOA-035.md) — Preparar release y comprobar Definition of Done

## Siguiente paso

Implementar MOA-001; continuar con MOA-002 y los fundamentos según el [DAG](DEPENDENCIES.md). La asignación de fases no sustituye las dependencias.
