---
name: moanart-issue-planning
description: Crea o actualiza issues, fases, dependencias y requisitos de MoanArt con criterios verificables. Úsala cuando cambie el alcance, prioridad o estado del roadmap.
---

# MoanArt — Issue Planning

Lee [MOANART.md](../../../MOANART.md), el [roadmap](../../../docs/issues/roadmap.md) y el [ciclo de issues](../../../docs/guides/issue-lifecycle.md). Edita `docs/issues/catalog.json` y `docs/requirements.json`; los Markdown y mapas derivados se regeneran, no se mantienen aparte.

- Conserva IDs canónicos MOANA-XXX y aliases históricos MOA-XXX. Un alias no es un issue duplicado y no altera las dependencias canónicas.
- Cada issue define contexto, objetivo, alcance/exclusiones, módulos, complejidad, requisitos técnicos, propuesta, entregables, riesgos, aceptación observable y pruebas concretas.
- Separa fundamento bloqueante (P0), núcleo (P1), avanzado (P2) y mejora opcional (P3). Complejidad no es una promesa de duración.
- Añade sólo dependencias causales. Comprueba referencias, ciclos, fases, bloqueantes/dependientes y cobertura de todas las secciones relevantes; no derives dependencias del número del issue.
- Usa `todo → ready → in_progress → review → done`; usa `blocked` para dependencias o impedimentos externos documentados. No declares ready si faltan dependencias; done requiere criterios, pruebas y evidencia completos.
- Documenta condiciones de salida de fase, un orden topológico y tareas paralelizables por contratos/archivos separados. Una ruta crítica estructural no equivale a una estimación de calendario.
- Ejecuta `uv run python scripts/planning.py` y `uv run python -m scripts.check_repository`; revisa issue, roadmap, mapa y matriz juntos.

Entrega catálogo coherente, cobertura y siguiente issue desbloqueado. No implementes el motor en una tarea de planificación ni publiques issues/remotos sin autorización explícita.

Para cerrar, completa `acceptance_evidence` (AC1…) y `test_evidence` (T1…) además de evidencia general; el checker exige cobertura de cada criterio/prueba.
