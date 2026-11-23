---
paths:
  - "tests/**"
---

# Testing

Estándar: [docs/standards/testing.md](../../docs/standards/testing.md), MOANART.md §21. Skill: `moanart-testing`. Subagente: `moanart-qa-engineer`.

- Organización: `tests/unit/` reglas locales; `tests/integration/` documento→render→export o tooling completo; `tests/visual/` goldens exactos (marker `visual`); fixtures en `tests/fixtures/`. Crea cada carpeta cuando exista su primer test real.
- Oráculos independientes (máscaras a mano, fórmulas); nunca copies la salida de la implementación como expected.
- Markers registrados: `visual`, `slow`, `security`, `benchmark` (`--strict-markers`). Hypothesis para invariantes con dominio acotado.
- Goldens: igualdad RGBA exacta; nunca regenerar automáticamente para que pase CI. Presentar expected/actual/diff.
- Cada AC/T del issue debe mapear a un test o evidencia citable.
