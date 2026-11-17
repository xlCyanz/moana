# Matriz de trazabilidad

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

40 requisitos con cobertura de planificación. Cobertura no significa implementación; consultar estado y evidencia de cada issue.

| Requisito | Descripción | MOANA.md § | Issues | Verificación exigida |
| --- | --- | --- | --- | --- |
| R001 | Visión, alcance y especificación exhaustiva | 1, 2, 23, 24, 25 | [MOA-000](issues/MOA-000.md) | Revisión de las 25 secciones y gate P0 |
| R002 | Lienzo, coordenadas y buffers RGBA seguros | 5 | [MOA-001](issues/MOA-001.md), [MOA-004](issues/MOA-004.md) | Fixtures de límites, dtype e inmutabilidad |
| R003 | Primitivas exactas, clipping y flood fill | 6 | [MOA-006](issues/MOA-006.md) | Oráculos de píxel por primitiva y casos degenerados |
| R004 | Geometría complementaria AggDraw | 4, 6 | [MOA-007](issues/MOA-007.md) | Fixtures de paths y capabilities por backend |
| R005 | Técnicas profesionales y calidad artística | 7, 19 | [MOA-017](issues/MOA-017.md), [MOA-026](issues/MOA-026.md), [MOA-027](issues/MOA-027.md), [MOA-034](issues/MOA-034.md) | Corpus editable y rúbrica humana documentada |
| R006 | Siluetas, contornos y clusters | 8 | [MOA-014](issues/MOA-014.md) | Morfología y componentes conocidos |
| R007 | Paletas, ramps y perfiles de color | 9 | [MOA-005](issues/MOA-005.md) | Referencias, cardinalidad y conservación de colores |
| R008 | Iluminación y sombreado por bandas | 9, 10 | [MOA-015](issues/MOA-015.md) | Fixtures de rampas y prioridades de máscaras |
| R009 | Dithering controlado | 10 | [MOA-016](issues/MOA-016.md) | Patrones exactos, coverage y fase temporal |
| R010 | Materiales editables y reproducibles | 10 | [MOA-017](issues/MOA-017.md) | Fixtures de cinco materiales y semillas |
| R011 | Capas, grupos y composición | 11 | [MOA-009](issues/MOA-009.md) | Source-over entero y orden/opacidad de grupos |
| R012 | Máscaras y regiones semánticas | 11 | [MOA-013](issues/MOA-013.md) | DAG, álgebra de máscaras y targeting por ID |
| R013 | JSON estricto y schema para agentes | 12 | [MOA-002](issues/MOA-002.md) | Pydantic, JSON Schema y corpus inválido |
| R014 | API Python y CLI públicas | 13 | [MOA-012](issues/MOA-012.md), [MOA-033](issues/MOA-033.md) | Wheel limpio y contratos de errores/resultados |
| R015 | Renderizado determinista | 14 | [MOA-007](issues/MOA-007.md), [MOA-010](issues/MOA-010.md), [MOA-029](issues/MOA-029.md), [MOA-032](issues/MOA-032.md) | Digests RGBA en procesos/OS y semillas distintas |
| R016 | Edición no destructiva atómica | 15 | [MOA-018](issues/MOA-018.md) | Batch reversible, revisión obsoleta y diff local |
| R017 | Historial y undo/redo | 15 | [MOA-019](issues/MOA-019.md) | Snapshots y ramas con igualdad exacta |
| R018 | Formato de proyectos y assets | 16 | [MOA-020](issues/MOA-020.md) | Roundtrip y escritura atómica confinada |
| R019 | Versionado y migraciones | 16 | [MOA-021](issues/MOA-021.md) | Fixtures entre versiones y original preservado |
| R020 | Animaciones, duraciones y pivotes | 17 | [MOA-022](issues/MOA-022.md) | Evaluación independiente y continuidad temporal |
| R021 | Spritesheets y manifest | 17 | [MOA-023](issues/MOA-023.md) | Reconstrucción exacta de cada frame |
| R022 | Exportación PNG RGBA/indexada | 18 | [MOA-011](issues/MOA-011.md) | Roundtrip decoded y destino intacto al fallar |
| R023 | Exportación GIF | 18 | [MOA-024](issues/MOA-024.md) | Timeline/disposal y pérdidas explícitas |
| R024 | Formatos adicionales | 18 | [MOA-025](issues/MOA-025.md) | APNG/WebP lossless según codec disponible |
| R025 | Evaluación gráfica y diagnósticos | 19 | [MOA-014](issues/MOA-014.md), [MOA-026](issues/MOA-026.md) | Hard/soft checks, bbox y supresiones |
| R026 | Validación y seguridad de datos | 20 | [MOA-001](issues/MOA-001.md), [MOA-002](issues/MOA-002.md), [MOA-003](issues/MOA-003.md), [MOA-020](issues/MOA-020.md), [MOA-030](issues/MOA-030.md) | Entradas adversarias rechazadas antes de reservar/IO |
| R027 | Testing y regresión visual | 21 | [MOA-004](issues/MOA-004.md), [MOA-027](issues/MOA-027.md), [MOA-028](issues/MOA-028.md), [MOA-029](issues/MOA-029.md), [MOA-030](issues/MOA-030.md) | Unit/property/integration y diffs exactos |
| R028 | Rendimiento y recursos medidos | 22 | [MOA-003](issues/MOA-003.md), [MOA-031](issues/MOA-031.md), [MOA-032](issues/MOA-032.md) | Benchmark reproducible y memoria acotada |
| R029 | Caché e incrementalidad | 22 | [MOA-032](issues/MOA-032.md) | Equivalencia caché on/off y límites LRU |
| R030 | Arquitectura modular y documentación | 3 | [MOA-000](issues/MOA-000.md), [MOA-001](issues/MOA-001.md), [MOA-010](issues/MOA-010.md) | Dependencias internas y ADR revisados |
| R031 | Paquete instalable y artefactos | 4, 25 | [MOA-000](issues/MOA-000.md), [MOA-035](issues/MOA-035.md) | Build y smoke de wheel/sdist aislados |
| R032 | Entorno Python y herramientas de calidad | 4, 21 | [MOA-000](issues/MOA-000.md) | uv locked, Ruff, mypy, pytest y dependencias nativas |
| R033 | Siete skills especializadas | 3, 25 | [MOA-000](issues/MOA-000.md) | Frontmatter, UI metadata, referencias y validador de skills |
| R034 | Codex, roles y flujos de agentes | 3, 13, 25 | [MOA-000](issues/MOA-000.md), [MOA-033](issues/MOA-033.md) | Auditoría de capacidades y configuración local válida |
| R035 | Hooks y automatización CI | 21, 25 | [MOA-000](issues/MOA-000.md), [MOA-029](issues/MOA-029.md) | pre-commit y workflow en matriz sin publicación |
| R036 | Issues, roadmap, dependencias y trazabilidad | 23, 24 | [MOA-000](issues/MOA-000.md), [MOA-035](issues/MOA-035.md) | Checker DAG, cobertura y documentos sincronizados |
| R037 | Objetos, tiles y escenarios | 2, 7 | [MOA-034](issues/MOA-034.md) | Ejemplos editables y costuras verificadas |
| R038 | Preview y modificación específica por IA | 1, 13, 15 | [MOA-012](issues/MOA-012.md), [MOA-018](issues/MOA-018.md), [MOA-027](issues/MOA-027.md), [MOA-033](issues/MOA-033.md) | Tutorial render-preview-edit con IDs preservados |
| R039 | Criterios de aceptación y Definition of Done | 24, 25 | [MOA-000](issues/MOA-000.md), [MOA-035](issues/MOA-035.md) | Evidencias por issue y gate de release |
| R040 | Transformaciones pixel-perfect | 6 | [MOA-008](issues/MOA-008.md) | Identidades de giros/espejos y nearest-neighbor |
