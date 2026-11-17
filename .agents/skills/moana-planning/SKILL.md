---
name: moana-planning
description: Crea o actualiza issues, fases, dependencias y requisitos de Moana con criterios verificables. Úsala cuando cambie el alcance o estado del roadmap.
---

# Moana — Issue Planning

Lee [MOANA.md](../../../MOANA.md), [roadmap](../../../docs/ROADMAP.md) y `docs/issues/catalog.json`.

- Edita `docs/issues/catalog.json` para trabajo y `docs/requirements.json` para requisitos; los Markdown son derivados. No mantengas versiones manuales contradictorias.
- Cada issue necesita resultado acotado, exclusiones, requisitos técnicos, dependencias directas, aceptación observable y pruebas positivas/negativas concretas.
- No añadas dependencia sólo por orden numérico. Comprueba aciclicidad, fases y cobertura; separa la puerta de fase del trabajo independiente.
- Estado done requiere evidencia real y dependencias done. Configurado, instalado, ejecutado y publicado son estados distintos.
- Ejecuta `uv run python scripts/planning.py` y `uv run python scripts/check_repository.py`; revisa el diff de issues/matriz/DAG.
- Los IDs MOA son locales. Publicar issues, asignarlos o enviar mensajes a terceros requiere una instrucción que lo autorice.

Prioriza el primer contrato desbloqueado y evita estimaciones de calendario sin datos. No implementes el motor como parte de una tarea sólo de planificación.
