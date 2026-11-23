# Flujos para agentes

Entrada operativa: [flujo de sesión](guides/agent-workflow.md), [desarrollo](guides/development.md) y [ciclo de issues](guides/issue-lifecycle.md). Los flujos artísticos siguientes son planificados hasta disponer del renderer.

## Implementar un issue

Leer MOANART.md y el archivo MOANA-xxx correspondiente. Verificar dependencias en catálogo; seleccionar la skill pertinente. Diseñar el contrato mínimo, añadir pruebas de comportamiento, implementar y pasar `scripts/validate.py`. Una dependencia pendiente impide declarar el issue listo; puede implementarse en secuencia dentro de una solicitud que lo autorice. Registrar evidencia en el catálogo y regenerar derivados.

## Diseñar y revisar Pixel Art (cuando exista renderer)

El brief define personaje/objeto, pose, tamaño, paleta, luz y restricciones. Empezar por silueta, pasar a clusters y volúmenes, y finalmente detalles. Guardar documento y semilla; renderizar PNG, mostrar a 1×/4× y consultar el reporte de calidad. La revisión humana evalúa intención y lectura, mientras las pruebas verifican píxeles y presupuesto.

## Modificar una parte

Resolver la región/ID y mostrar qué elementos se afectan. Crear batch con base_revision y base_snapshot; validar, aplicar a copia, renderizar y comparar bbox/hash. Guardar la nueva revisión y conservar la previa. Si «ojo» corresponde a varios IDs sin contexto suficiente, aclarar sólo esa ambigüedad; no reconstruir toda la escena ni usar generación visual.

## Revisar un cambio

`moanart-code-review` examina contrato, casos límite, propiedad de buffers, determinismo y pruebas. Priorizar fallos reproducibles sobre estilo cubierto por Ruff. Para raster, inspeccionar diff y fuente de fixture; para tooling, ejecutar gate y un caso de fallo del validador. La revisión no implica permiso para publicar.

## Planificar y mantener la fuente de verdad

`docs/issues/catalog.json` contiene alcance, dependencias y criterios; `docs/requirements.json` contiene requisitos y sección de MOANART.md. `scripts/planning.py` regenera issues, índice, mapa, roadmap y matriz; `--check` detecta divergencia sin escribir. Los estados son todo, ready, in_progress, blocked, review y done. Los estados activos exigen dependencias done; blocked necesita motivo. Done exige evidencia general y por cada criterio/prueba (AC/T).

## Automatización e integraciones

Git pre-commit comprueba lint/formato/estructura, GitHub Actions hace el gate completo en matriz sólo en pull requests contra `main`, en commits que llegan a `main` y en ejecuciones manuales (`workflow_dispatch`); las ramas de issue y los PR hacia otras ramas se validan localmente con `scripts/validate.py`. Incluye build con backend del lock e instalación aislada del wheel. Dependabot sólo mantiene acciones. No hay jobs de publicación, envío de mensajes ni automaciones periódicas de Codex. Una actualización de dependencias Python se hace con `uv lock --upgrade`, pruebas y revisión del diff del lock, no silenciosamente.
