---
paths:
  - "docs/issues/**"
  - "docs/requirements.json"
---

# Trabajo con issues

Ciclo: [issue-lifecycle](../../docs/guides/issue-lifecycle.md). Skill: `moana-issue-planning`.

- IDs `MOANA-xxx` estables; nunca reutilizar ni renumerar. Aliases `MOA-xxx` sólo históricos.
- Estados `todo → ready → in_progress → review → done`; `blocked` exige motivo y condición. `ready`+ exige dependencias `done`.
- Edita sólo los JSON fuente y regenera; después `uv run python -m scripts.check_repository`.
- Evidencia por cada AC y T antes de `review`/`done`; el validador comprueba presencia, el responsable su veracidad.
