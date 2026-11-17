# Rampas, hue shifting y contraste

Usa una rampa para expresar un material o familia de planos de sombra a luz. Reutiliza sus IDs para mantener consistencia entre capas y frames; la representación y límites de paleta están en [MOANA.md §9](../../../../MOANA.md).

Define primero tono base, sombra y luz suficientes para leer el volumen. Añade un tono sólo si crea una transición o detalle visible a 1×. Dos colores casi indistinguibles pueden aumentar mantenimiento sin mejorar lectura; tampoco fuerces distancias iguales entre todos los tonos si el material requiere un salto brillante corto.

Hue shifting cambia el matiz a lo largo de la rampa para sugerir temperatura de luz/ambiente y evitar un sombreado monocromático plano. Decide la dirección a partir del brief: luces cálidas y sombras frías son una opción, no una ley. Un cambio de matiz sin relación con luz/material puede hacer que la pieza parezca de otro color.

Comprueba valor, saturación y matiz juntos sobre el fondo previsto. La luminancia creciente es una recomendación de lectura, no una obligación universal para una rampa estilizada. Documenta una excepción si alteras esa secuencia de forma deliberada.

Errores comunes: escalar todos los canales RGB para obtener sombras, saturar cada highlight, usar demasiados tonos próximos y cambiar una paleta global para resolver un detalle local. Para una edición local, duplica el color con otro ID antes de modificarlo si otros consumidores deben conservarse. Verifica membresía de paleta, contraste entre partes y coherencia entre frames; no cuantices la salida silenciosamente.
