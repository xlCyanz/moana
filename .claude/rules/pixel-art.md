---
paths:
  - "examples/**"
  - "tests/visual/**"
  - "tests/fixtures/**"
  - "src/moanart/techniques/**"
  - "src/moanart/palette/**"
  - "src/moanart/quality/**"
---

# Pixel Art

Estándar: [docs/standards/pixel-art.md](../../docs/standards/pixel-art.md), MOANART.md §§7–10, 19. Skill: `moanart-pixel-art`. Subagente: `moanart-pixel-artist`.

- Revisa todo resultado visual a 1× y ampliado por vecino más cercano (factor entero); evalúa silueta, clusters, rampas y luz.
- Sin blur, AA implícito, ruido global ni cuantización silenciosa. AA manual sólo con colores de rampa en píxeles explícitos.
- Las heurísticas artísticas son advertencias, no rechazos. Ningún agente declara aprobación artística humana.
- No uses generación de imágenes para sustituir la edición de un sprite MoanArt. Registra procedencia/licencia de cada ejemplo.
