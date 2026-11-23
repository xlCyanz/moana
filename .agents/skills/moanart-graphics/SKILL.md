---
name: moanart-graphics
description: Diseña e implementa geometría, composición, máscaras y transformaciones del motor MoanArt. Úsala cuando se modifiquen reglas de píxel, adaptadores gráficos o rendimiento raster.
---

# MoanArt — Computer Graphics

Consulta [MOANART.md](../../../MOANART.md) §§5–6, 11, 14 y 22 antes de elegir un algoritmo.

- Deriva una fixture pequeña y verificable a mano: origen top-left, array[y,x], cajas semiabiertas y centros de píxel. Fija empates de línea y cruces de polígonos.
- El perfil entero no utiliza AA implícito. AggDraw tiene backend y garantía separados; convierte cobertura con el umbral normativo y declara versiones.
- Composición usa RGBA recto y la fórmula entera especificada. No premultipliques dos veces ni mezcles convenciones de alfa; normaliza RGB cuando alfa=0.
- Recorta y estima coste antes de buffers. Las coordenadas fuera del canvas no pueden provocar arrays enormes ni bucles sin presupuesto.
- Verifica invariantes de transformación, bordes, paleta y determinismo; compara RGBA decodificado, no solamente bytes PNG.
- Optimiza con benchmark y equivalencia on/off. No añadas SIMD/GPU/threads por intuición.

Entrega algoritmo, coste, casos límite y evidencia visual pertinente. La precisión raster no prueba calidad artística.

Escala previews y sprites por vecino más cercano con factor entero. Inspecciona shape/dtype, alfa, límites y pertenencia a paleta al cruzar adaptadores. Las máscaras están en coordenadas de canvas: aclara su relación con grupos transformados y prueba un borde recortado. Un polígono even-odd no es vacío sólo porque su área firmada sea cero.
