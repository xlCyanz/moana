---
paths:
  - "src/**/*.py"
  - "scripts/**/*.py"
  - "tests/**/*.py"
---

# Python en MoanArt

Estándar completo: [docs/standards/python.md](../../docs/standards/python.md). Skill: `moanart-python`.

- mypy `strict` cubre `src`, `scripts` y `tests`; no añadas `# type: ignore` sin código de error y motivo. `Any` sólo en fronteras de librería.
- Rechaza `bool` donde se espera `int` (es subclase). Sin floats implícitos en coordenadas.
- Docstrings e identificadores en inglés; mensajes al usuario pueden ser español si el módulo ya lo hace.
- `Path.read_text`/`write_text`/`open` siempre con `encoding="utf-8"` (ADR-008, CI Windows).
- Sin estado global mutable, sin `hash()`/reloj/RNG global como semilla.
- Errores de dominio (`MoanArtError` y subclases) en fronteras; no filtrar excepciones de Pillow/NumPy.
- Funciones pequeñas y composición; si una función supera ~50 líneas, justifica o divide.
- Validación rápida automática: hook Ruff. Antes de cerrar: `uv run mypy` y pytest del módulo.
