# Estándares de Pixel Art

Objetivo: sprites legibles y editables a su resolución real. Las reglas matemáticas están en [MOANA.md §§5–11](../../MOANA.md); esta guía explica decisiones artísticas. Pillow y NumPy no garantizan calidad profesional.

## Flujo visual

Definir lectura, pose, foco, tamaño, paleta y dirección de luz antes de añadir detalle. Revisar una silueta plana a 1×; después organizar clusters y volúmenes, ajustar rampas y sólo entonces agregar materiales o rasgos pequeños. Conservar IDs semánticos para partes que el usuario pueda modificar.

| Técnica | Cuándo usarla | Error frecuente que debe revisarse |
| --- | --- | --- |
| Clusters | Organizar formas y masas de color reconocibles | Píxeles aislados accidentales o textura que rompe el volumen |
| Silueta y espacio negativo | Verificar pose, separación de miembros y foco a 1× | Tangencias que fusionan partes o un contorno legible sólo ampliado |
| Contorno por píxel | Separar figura/fondo y definir planos | Grosor irregular involuntario, escalones ruidosos y dobles bordes |
| Selective outlining | Cambiar el borde según luz/material sin perder lectura | Abrir zonas que hacen desaparecer la silueta o iluminar todos los bordes igual |
| Rampas de color | Sombrear con una familia deliberada de tonos | Añadir muchos colores casi idénticos sin función visible |
| Hue shifting | Diferenciar sombra/luz y enriquecer materiales cuando el estilo lo admite | Cambios de matiz arbitrarios o rampas que pierden orden de lectura |
| Bandas de sombra | Expresar volumen con regiones y luz consistente | Sombrear concéntricamente desde todos los bordes, sin dirección de luz |
| Dithering | Transición o textura localizada con dos tonos controlados | Aplicarlo a toda la superficie, introducir ruido o cambiar fase entre frames |
| AA manual interior | Suavizar una pendiente elegida con tonos de la paleta | Blur automático, alfa parcial no pedido o colores fuera del perfil |

Un singleton puede ser un ojo, brillo o partícula intencional. Las heurísticas deben ofrecer evidencia y permitir excepciones por región; no borrar automáticamente esos detalles. Las correcciones artísticas se expresan como operaciones/batches editables.

## Inspección y animación

Mostrar el maestro a 1× y una ampliación entera por nearest-neighbor. Revisar silueta, mapa de clusters, paleta y foco visual; no juzgar sólo una preview grande. La composición debe distribuir contraste y detalle para guiar la lectura, sin dar igual énfasis a cada borde.

En animación mantener pivote, volumen, contacto con suelo, paleta y fase de patrones salvo cambio intencional. Distinguir desplazamiento diseñado de jitter accidental. Un onion skin sirve para diagnóstico y no debe aparecer en frames exportados.

## GIF animado

GIF es un formato de intercambio con pérdidas, no el maestro (que es el PNG RGBA; MOANA.md §18, ADR-034):

- Duraciones múltiplo de 10 ms y de al menos 20 ms; mejor 30–40 ms o más, porque los navegadores alargan los retardos más cortos.
- Sin alfa intermedio en los frames; si existe, pasar como `background` el color real del fondo de destino (otro deja halo) o resolverlo en la fuente con contorno sólido o dithering.
- Como mucho 255 colores opacos más el transparente, compartidos por todos los frames de la animación.
- Para un preview grande, ampliar los frames por un entero con nearest-neighbor antes de exportar; el exportador no escala.
- Usar disposal `background` (el predeterminado) para sprites con huecos transparentes; `none` sólo sirve si la transparencia nunca aparece donde el frame anterior era opaco.

## APNG y WebP

APNG y WebP son exportaciones lossless opcionales (MOANA.md §18, ADR-035); el maestro sigue siendo el PNG RGBA:

- Conservan cada color RGBA, también el alfa intermedio (bordes suavizados a mano, sombras translúcidas), sin `background` de aplanado ni límite de 256 colores.
- Admiten cualquier duración entera de 1 a 60 000 ms, sin redondeo a centésimas.
- El APNG se guarda con extensión `.png` (`image/apng`): los visores sin APNG muestran el primer frame, así que conviene que el frame 0 sea una pose legible.
- WebP fusiona frames iguales consecutivos (el tiempo total se conserva) y, si todos los frames son iguales o hay uno solo, guarda una imagen fija sin tiempo ni bucle (advertencia `still_image`).
- Antes de exportar, `moana.export.export_capabilities()` dice si este build tiene el codec; si falta, el exportador falla sin escribir nada y no cambia de formato.
- Igual que en GIF, el exportador no escala: para un preview grande, ampliar antes por un entero con nearest-neighbor.

La rúbrica humana de MOANA.md §19 evalúa legibilidad, silueta, clusters, paleta, luz/material y continuidad. Cumplir dimensiones, paleta y hashes sólo demuestra conformidad técnica. El corpus conserva fuente, semilla, procedencia y estado real de revisión.
