---
paths:
  - "**/*.md"
  - "docs/**"
---

# Documentación

- Documentación del proyecto en español; código, identificadores y docstrings en inglés.
- `docs/issues/*.md`, `roadmap.md`, `dependency-map.md`, `traceability.md` y `README.md` de issues son **generados**: edita `docs/issues/catalog.json` / `docs/requirements.json` y ejecuta `uv run python scripts/planning.py`.
- Enlaces relativos verificados por `scripts/check_repository.py`; no enlaces locales rotos.
- No declares resultados, CI remoto, carga de roles o aprobaciones humanas sin evidencia observada.
- Subagente: `moanart-documentation`.
