---
name: moana-pixel-art
description: Diseña y evalúa sprites Moana mediante siluetas, clusters, paletas, luz y materiales; úsala para dirección artística o cambios locales de un sprite editable.
---

# Moana — Pixel Art

Lee [MOANA.md](../../../MOANA.md) §§7–10 y 19, y el [flujo artístico](../../../docs/WORKFLOWS.md). Comprueba primero si el renderer solicitado ya existe.

1. Convierte el brief en lectura, pose, tamaño, foco, paleta y luz. El objetivo 128×128 no obliga a llenar cada píxel de detalle.
2. Trabaja silueta → clusters → rampas/volumen → detalles → limpieza. Usa familias de pendientes y espacio negativo deliberados.
3. Conserva IDs semánticos para partes editables. Modifica documento/batch; no sustituyas una edición por regeneración mediante un modelo visual.
4. Usa dithering local con fase explícita, ramps authored y sombreado por máscaras. No suavices con blur ni distribuyas ruido por defecto.
5. Inspecciona 1× y 4× nearest-neighbor, silueta y paleta. Distingue fallos estructurales de decisiones estilísticas como píxeles brillantes aislados.
6. En animación comprueba volumen, suelo, pivote y estabilidad de patrones. Muestra antes/después y región afectada.

Para crear, previsualizar y recolorear por ID con los comandos reales (`moana validate`/`inspect`/`export --scale 4`/`edit`, revisión y `base_snapshot`, recuperación de errores y limitaciones que hay que comunicar) sigue la [guía de flujos IA](../../../docs/guides/ai-workflows.md).

La rúbrica humana es evidencia aparte de los tests. Si no hubo revisión humana, indícala pendiente. Pillow/NumPy no garantizan arte profesional.

Elige sólo la referencia pertinente:

- [Clusters, silueta y composición](references/pixel-clusters.md) cuando falle lectura o jerarquía.
- [Contornos y selective outlining](references/outlines.md) para separación, grosor y color de borde.
- [Rampas y hue shifting](references/palettes.md) para contraste, temperatura y recolor.
- [Sombreado y dithering](references/shading.md) para volumen, materiales, banding y fase temporal.
