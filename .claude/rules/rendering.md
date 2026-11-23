---
paths:
  - "src/moanart/core/**"
  - "src/moanart/geometry/**"
  - "src/moanart/layers/**"
  - "src/moanart/render/**"
  - "src/moanart/export/**"
---

# Rasterización y render

Contrato exacto: MOANART.md §§5–6, 11, 14, 18. Skill: `moanart-graphics`. Subagente: `moanart-graphics-engineer`.

- RGBA recto `uint8`, `array[y, x, c]`, C-contiguo, origen arriba-izquierda; alfa 0 se normaliza a `(0,0,0,0)`.
- Cajas semiabiertas `[x0,y0,x1,y1)`; clipping sin wraparound y después de presupuestar; nunca índices negativos de NumPy.
- Fórmulas normativas (Bresenham ordenado, elipse por centros, polígono even-odd, `round_half_up`) se implementan literalmente con enteros Python o tipos sin overflow demostrable.
- Presupuesto antes de reservar buffers. Sin concurrencia, sets, locale ni `hash()` en el orden de render.
- Ninguna operación escribe fuera de su máscara/bbox recortada; las pruebas lo comprueban.
