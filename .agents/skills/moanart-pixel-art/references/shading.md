# Sombreado, materiales y dithering

Usa bandas de sombreado para que las masas describan volumen bajo la luz declarada; utiliza máscaras/regiones editables y ramps de [MOANART.md §§9–10](../../../../MOANART.md). No infieras normales 3D que el documento no contiene.

Haz que la dirección y extensión de sombra respondan a planos y oclusión. Una esfera suele pedir bandas curvas; un plano puede pedir una masa amplia uniforme. Para metal puede servir un salto de valor corto y fuerte; tela o piel suelen necesitar transiciones de masa distintas. Son decisiones a revisar sobre el brief y el corpus, no presets que garanticen realismo.

Evita pillow shading cuando no sea la intención: capas de sombra equidistantes del borde e iluminación centrada hacen perder la dirección de la luz. Evita banding accidental cuando borde y sombra forman escaleras paralelas que engrosan visualmente la silueta. Cambia la forma de las masas antes de añadir tonos para ocultarlo.

Dithering mezcla dos colores mediante un patrón visible. Úsalo cuando la estética o material pide textura, o para una transición con paleta limitada en una región suficientemente grande. En superficies pequeñas, cara u ojos puede destruir la lectura; una banda plana suele ser más clara. Conserva origen y fase del patrón entre tiles y frames para evitar costuras o parpadeo.

MoanArt comienza con Bayer 2×2/4×4 y coverage entera: usa las tablas normativas, limita por máscara y no introduzcas RNG global. Si se necesita textura aleatoria, la semilla por operación/coordenadas mantiene estabilidad. Comprueba cobertura 0/completa, bordes de región, paleta y continuidad temporal. No apliques ruido, dithering o blur global como una mejora automática.
