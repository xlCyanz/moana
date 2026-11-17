# ADR-008 — Tooling UTF-8 y build mediante uv

Estado: aceptado · 2026-11-17.

## Evidencia

El [workflow Quality de 9388c57](https://github.com/xlCyanz/moana/actions/runs/43995965656) falló en Windows al leer el catálogo: el codec charmap no podía decodificar un byte UTF-8. La validación local en macOS no había ejercitado ese entorno. Los archivos del proyecto se declaran UTF-8 en .editorconfig, pero Path.read_text sin encoding depende del locale.

## Decisión

Todas las lecturas/escrituras de texto del tooling y sus fixtures especifican encoding="utf-8". Un test simula cp1252 como encoding implícito para detectar regresiones en el flujo real. Los procesos del gate usan stdout/stderr UTF-8 y guardan un log de diagnóstico en artifacts cuando se ejecutan. Esa configuración complementa las lecturas explícitas; no las sustituye.

El gate usa uv build. Hatchling permanece como backend y dependencia de desarrollo fijada en uv.lock; el gate puede usar --no-build-isolation para construir con ese entorno bloqueado. El comando uv build sin opciones también se ejecuta como comprobación de packaging estándar. No se agrega un segundo gestor ni se instala tooling global.

## Consecuencias y límites

La corrección se valida localmente mediante simulación de locale y ejecución real del tooling. Sólo una nueva ejecución remota podrá confirmar el estado de la matriz modificada. Esta tarea no hace push ni cambia protecciones. Los fallos del commit anterior se registran como evidencia histórica, no como resultado de estos cambios locales.
