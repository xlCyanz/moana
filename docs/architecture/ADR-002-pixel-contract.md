# ADR-002 — Contrato entero y perfil estricto

Estado: aceptado para implementación · 2026-11-16.

## Contexto

Delegar todos los bordes a defaults de bibliotecas produce ambigüedades de inclusión, antialias y redondeo. Una diferencia de un píxel importa en sprites pequeños.

## Decisión

Coordenadas enteras, cajas semiabiertas, máscaras binarias, Bresenham con empates definidos, relleno even-odd y composición entera. El perfil strict conserva paleta con alfa binario; rgba admite mezclas explícitas. El adaptador AggDraw es complementario, versionado y ensayado por separado. Las ampliaciones usan nearest-neighbor.

## Alternativas y consecuencias

Supersampling/AA por defecto produce cobertura suave pero cambia el estilo y la paleta. Usar floats es sencillo pero complica igualdad entre implementaciones. Enteros requieren fixtures de bordes y cuidado con overflow; la especificación fija fórmulas y la suite visual compara RGBA exacto. No se promete identidad de bytes comprimidos entre codecs distintos.
