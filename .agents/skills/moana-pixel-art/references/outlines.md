# Contornos y selective outlining

Usa un contorno cuando haga falta separar la silueta del fondo o conservar lectura en sprites pequeños. Usa contorno interior para separar planos/partes cuando el color por sí solo no baste. El ancho, la morfología y la vecindad normativa pertenecen a [MOANA.md §8](../../../../MOANA.md).

Primero comprueba la silueta. Un borde más oscuro no corrige una pose ilegible. Inspecciona esquinas, uniones, agujeros y contacto con el límite del canvas: engrosar un borde puede cerrar un hueco o fusionar partes que antes eran distintas.

El selective outlining cambia el color del borde según luz, material y contraste del fondo. Úsalo cuando una línea uniforme aplaste el volumen o robe atención; selecciona tonos de una rampa y una máscara de luz declarada. Conserva tramos oscuros donde sostienen lectura. Evita aclarar todo el contorno: puede desaparecer sobre fondos claros o producir un halo.

Mantén la intención de escalones. Dobles bordes paralelos, esquinas hinchadas y alternancia irregular de grosor pueden sugerir textura o bultos inexistentes. Revisa la versión con y sin outline y el fondo de uso antes de corregir.

No actives AA de biblioteca ni blur para suavizar un contorno strict. Si el estilo requiere antialias manual interior, coloca deliberadamente píxeles de colores existentes en la rampa; no introduzcas cobertura fraccional. El borde exterior transparente sigue el perfil declarado. El resultado debe seguir siendo una operación editable con ID y máscara, no una limpieza raster irreversible.
