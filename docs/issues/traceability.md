# Matriz de trazabilidad

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

40 requisitos con cobertura de planificación. Esto no implica implementación: comprobar estado y evidencia por criterio en cada issue.

| Requisito | Descripción | MOANA.md § | Issues | Verificación exigida |
| --- | --- | --- | --- | --- |
| R001 | Visión, alcance y especificación exhaustiva | 1, 2, 23, 24, 25 | [MOANA-000](MOANA-000.md) | Revisión de las 25 secciones y gate P0 |
| R002 | Lienzo, coordenadas y buffers RGBA seguros | 5 | [MOANA-001](MOANA-001.md), [MOANA-004](MOANA-004.md) | Fixtures de límites, dtype e inmutabilidad |
| R003 | Primitivas exactas, clipping y flood fill | 6 | [MOANA-006](MOANA-006.md) | Oráculos de píxel por primitiva y casos degenerados |
| R004 | Geometría complementaria AggDraw | 4, 6 | [MOANA-007](MOANA-007.md) | Fixtures de paths y capabilities por backend |
| R005 | Técnicas profesionales y calidad artística | 7, 19 | [MOANA-017](MOANA-017.md), [MOANA-026](MOANA-026.md), [MOANA-027](MOANA-027.md), [MOANA-034](MOANA-034.md) | Corpus editable y rúbrica humana documentada |
| R006 | Siluetas, contornos y clusters | 8 | [MOANA-014](MOANA-014.md) | Morfología y componentes conocidos |
| R007 | Paletas, ramps y perfiles de color | 9 | [MOANA-005](MOANA-005.md) | Referencias, cardinalidad y conservación de colores |
| R008 | Iluminación y sombreado por bandas | 9, 10 | [MOANA-015](MOANA-015.md) | Fixtures de rampas y prioridades de máscaras |
| R009 | Dithering controlado | 10 | [MOANA-016](MOANA-016.md) | Patrones exactos, coverage y fase temporal |
| R010 | Materiales editables y reproducibles | 10 | [MOANA-017](MOANA-017.md) | Fixtures de cinco materiales y semillas |
| R011 | Capas, grupos y composición | 11 | [MOANA-009](MOANA-009.md) | Source-over entero y orden/opacidad de grupos |
| R012 | Máscaras y regiones semánticas | 11 | [MOANA-013](MOANA-013.md) | DAG, álgebra de máscaras y targeting por ID |
| R013 | JSON estricto y schema para agentes | 12 | [MOANA-002](MOANA-002.md) | Pydantic, JSON Schema y corpus inválido |
| R014 | API Python y CLI públicas | 13 | [MOANA-012](MOANA-012.md), [MOANA-033](MOANA-033.md) | Wheel limpio y contratos de errores/resultados |
| R015 | Renderizado determinista | 14 | [MOANA-007](MOANA-007.md), [MOANA-010](MOANA-010.md), [MOANA-029](MOANA-029.md), [MOANA-032](MOANA-032.md) | Digests RGBA en procesos/OS y semillas distintas |
| R016 | Edición no destructiva atómica | 15 | [MOANA-018](MOANA-018.md) | Batch reversible, revisión obsoleta y diff local |
| R017 | Historial y undo/redo | 15 | [MOANA-019](MOANA-019.md) | Snapshots y ramas con igualdad exacta |
| R018 | Formato de proyectos y assets | 16 | [MOANA-020](MOANA-020.md) | Roundtrip y escritura atómica confinada |
| R019 | Versionado y migraciones | 16 | [MOANA-021](MOANA-021.md) | Fixtures entre versiones y original preservado |
| R020 | Animaciones, duraciones y pivotes | 17 | [MOANA-022](MOANA-022.md) | Evaluación independiente y continuidad temporal |
| R021 | Spritesheets y manifest | 17 | [MOANA-023](MOANA-023.md) | Reconstrucción exacta de cada frame |
| R022 | Exportación PNG RGBA/indexada | 18 | [MOANA-011](MOANA-011.md) | Roundtrip decoded y destino intacto al fallar |
| R023 | Exportación GIF | 18 | [MOANA-024](MOANA-024.md) | Timeline/disposal y pérdidas explícitas |
| R024 | Formatos adicionales | 18 | [MOANA-025](MOANA-025.md) | APNG/WebP lossless según codec disponible |
| R025 | Evaluación gráfica y diagnósticos | 19 | [MOANA-014](MOANA-014.md), [MOANA-026](MOANA-026.md) | Hard/soft checks, bbox y supresiones |
| R026 | Validación y seguridad de datos | 20 | [MOANA-001](MOANA-001.md), [MOANA-002](MOANA-002.md), [MOANA-003](MOANA-003.md), [MOANA-020](MOANA-020.md), [MOANA-030](MOANA-030.md) | Entradas adversarias rechazadas antes de reservar/IO |
| R027 | Testing y regresión visual | 21 | [MOANA-004](MOANA-004.md), [MOANA-027](MOANA-027.md), [MOANA-028](MOANA-028.md), [MOANA-029](MOANA-029.md), [MOANA-030](MOANA-030.md) | Unit/property/integration y diffs exactos |
| R028 | Rendimiento y recursos medidos | 22 | [MOANA-003](MOANA-003.md), [MOANA-031](MOANA-031.md), [MOANA-032](MOANA-032.md), [MOANA-036](MOANA-036.md) | Benchmark reproducible y memoria acotada |
| R029 | Caché e incrementalidad | 22 | [MOANA-032](MOANA-032.md) | Equivalencia caché on/off y límites LRU |
| R030 | Arquitectura modular y documentación | 3 | [MOANA-000](MOANA-000.md), [MOANA-001](MOANA-001.md), [MOANA-010](MOANA-010.md) | Dependencias internas y ADR revisados |
| R031 | Paquete instalable y artefactos | 4, 25 | [MOANA-000](MOANA-000.md), [MOANA-035](MOANA-035.md) | Build y smoke de wheel/sdist aislados |
| R032 | Entorno Python y herramientas de calidad | 4, 21 | [MOANA-000](MOANA-000.md) | uv locked, Ruff, mypy, pytest y dependencias nativas |
| R033 | Siete skills especializadas | 3, 25 | [MOANA-000](MOANA-000.md) | Frontmatter, UI metadata, referencias y validador de skills |
| R034 | Codex, roles y flujos de agentes | 3, 13, 25 | [MOANA-000](MOANA-000.md), [MOANA-033](MOANA-033.md) | Auditoría de capacidades y configuración local válida |
| R035 | Hooks y automatización CI | 21, 25 | [MOANA-000](MOANA-000.md), [MOANA-029](MOANA-029.md) | pre-commit y workflow en matriz sin publicación |
| R036 | Issues, roadmap, dependencias y trazabilidad | 23, 24 | [MOANA-000](MOANA-000.md), [MOANA-035](MOANA-035.md) | Checker DAG, cobertura y documentos sincronizados |
| R037 | Objetos, tiles y escenarios | 2, 7 | [MOANA-034](MOANA-034.md) | Ejemplos editables y costuras verificadas |
| R038 | Preview y modificación específica por IA | 1, 13, 15 | [MOANA-012](MOANA-012.md), [MOANA-018](MOANA-018.md), [MOANA-027](MOANA-027.md), [MOANA-033](MOANA-033.md) | Tutorial render-preview-edit con IDs preservados |
| R039 | Criterios de aceptación y Definition of Done | 24, 25 | [MOANA-000](MOANA-000.md), [MOANA-035](MOANA-035.md) | Evidencias por issue y gate de release |
| R040 | Transformaciones pixel-perfect | 6 | [MOANA-008](MOANA-008.md) | Identidades de giros/espejos y nearest-neighbor |
