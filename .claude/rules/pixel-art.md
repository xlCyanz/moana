---
paths:
  - "examples/**"
  - "tests/visual/**"
  - "tests/fixtures/**"
  - "src/moana/techniques/**"
  - "src/moana/palette/**"
  - "src/moana/quality/**"
---

# Pixel Art

Estándar: [docs/standards/pixel-art.md](../../docs/standards/pixel-art.md), MOANA.md §§7–10, 19. Skill: `moana-pixel-art`. Subagente: `moana-pixel-artist`.

- Revisa todo resultado visual a 1× y ampliado por vecino más cercano (factor entero); evalúa silueta, clusters, rampas y luz.
- Sin blur, AA implícito, ruido global ni cuantización silenciosa. AA manual sólo con colores de rampa en píxeles explícitos.
- Las heurísticas artísticas son advertencias, no rechazos. Ningún agente declara aprobación artística humana.
- No uses generación de imágenes para sustituir la edición de un sprite Moana. Registra procedencia/licencia de cada ejemplo.
