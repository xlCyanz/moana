# Clusters, silueta y composición

Usa esta referencia si la pose se pierde a 1×, los detalles compiten entre sí o aparecen grupos de píxeles sin función visual. El contrato de análisis y conectividad está en [MOANA.md §8](../../../../MOANA.md).

Empieza con la silueta plana: separa cabeza, extremidades y accesorios mediante masa o espacio negativo antes de depender de color. Una mano que toca tangencialmente el cuerpo puede desaparecer; prueba separar un píxel o solapar con intención. Revisa pose, dirección y centro de interés sobre el fondo previsto, no sólo sobre un checker de transparencia.

Construye clusters de color que describan planos o volúmenes. Un detalle aislado debe comunicar algo específico, como un ojo, destello o partícula. No borres singletons automáticamente: el diagnóstico de componente pequeño es una advertencia, no un juicio de intención.

Mantén el contraste más fuerte donde debe mirar el usuario. Reduce contraste/densidad en zonas secundarias antes de añadir más tonos. Deja descansos visuales; llenar 128×128 con textura suele ocultar la forma principal. Repite familias de escalones en una curva cuando la forma lo permita y corrige saltos accidentales sin imponer una simetría que cambie la pose.

Errores comunes: ruido de píxel que sustituye volumen, siluetas que sólo se entienden ampliadas, tangencias ambiguas y el mismo contraste en cada parte. Verifica antes/después a 1× y 4× nearest-neighbor, silueta y mapa de clusters. En animación, compara masa, contacto con suelo y jerarquía en todos los frames.
