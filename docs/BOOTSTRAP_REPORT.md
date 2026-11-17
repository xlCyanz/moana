# Preparación de infraestructura y entorno IA

Fecha: **2026-11-17**, America/Santo_Domingo. Refinamiento del repositorio existente; se conservan el commit 9388c57, la rama codex/initialize-moana y origin xlCyanz/moana. Esta tarea no crea commits ni hace push. El motor gráfico sigue sin implementar: src/moana contiene sólo __init__.py y py.typed.

## Cambios entregados

- Python 3.12.16 fijado, entorno uv y lock; dependencias runtime Pillow/NumPy/AggDraw/Pydantic. Hatchling construye mediante uv; se retira el frontend build redundante.
- Gate reutilizable con Ruff, mypy estricto, pytest/cobertura, catálogos, enlaces, configuración y distribución. Logs, JUnit y coverage XML quedan en artifacts; CI conserva diagnósticos al aprobar o fallar.
- Lecturas/escrituras UTF-8 explícitas y prueba de regresión del fallo Windows observado. El smoke del wheel admite invocación directa y comprueba una instalación temporal fuera del checkout.
- AGENTS.md operativo, estándares de Python/arquitectura/testing/arte/seguridad, guías de desarrollo/sesión/ciclo, plantillas GitHub, overview y contratos de módulos. El [inventario](FILE_INVENTORY.md) enumera los archivos actuales.
- Siete skills del proyecto revisadas y ocho roles TOML, incluido documentation_writer. Referencias artísticas separan clusters, contornos, paletas e iluminación.
- Catálogo con IDs MOANA-000…035, aliases MOA históricos, seis estados, prioridad, complejidad, módulos, propuesta, entregables, riesgos y evidencia AC/T. Se generan 79 documentos, incluidos 36 redirects de compatibilidad; no son 72 issues.
- Cuatro ADR nuevos: backends/fronteras, identidad/ciclo del backlog, clarificaciones de contrato y portabilidad/build. Se conservan los cuatro ADR iniciales.

## Entorno y verificación

Validación ejecutada en macOS arm64. Los artefactos locales quedan bajo artifacts y dist, ignorados por Git. El [reporte original](INITIALIZATION_REPORT.md) conserva la evidencia histórica del 2026-11-16.

| Herramienta o dependencia | Versión observada |
| --- | --- |
| Python / uv | 3.12.16 / 0.13.8 |
| Pillow / NumPy | 13.0.0 / 2.5.5 |
| AggDraw / Pydantic | 1.4.1 / 2.14.3 |
| Ruff / mypy | 0.17.5 / 1.20.2 |
| pytest / pytest-cov | 9.2.0 / 7.1.0 |
| Hypothesis / PyYAML | 6.170.15 / 6.0.3 |
| Hatchling / pre-commit | 1.33.0 / 4.7.0 |

uv resolvió 38 paquetes y sincronizó el entorno; build y pyproject-hooks se retiraron al quedar sin uso. Las herramientas y Python administrado permanecen dentro del checkout. Se usa uv local mediante scripts/uv.sh o un PATH temporal; no se altera el PATH global.

| Comando o comprobación | Resultado observado |
| --- | --- |
| `uv sync` | Aprobado, lock actualizado y entorno sincronizado |
| `uv run pytest` | 26 pruebas aprobadas |
| `uv run ruff check .` | Aprobado |
| `uv run ruff format --check .` | Aprobado |
| `uv run mypy src/` | Aprobado, 1 archivo de API |
| `uv build` | Sdist y wheel construidos; wheel generado desde el sdist |
| `uv run python scripts/validate.py` | Gate completo aprobado, incluido lock offline y mypy sobre 10 archivos |
| `uv run python scripts/check_wheel.py` | Wheel instalado en venv temporal fuera del checkout; import, versión y py.typed correctos |
| `uv run python scripts/planning.py --check` | 79 derivados coherentes con catálogo/requisitos |
| `uv run python -m scripts.check_repository` | 36 issues, 40 requisitos, enlaces y configuración válidos |
| `pre-commit run --files …` | Ruff, formato y consistencia aprobados sobre los 169 archivos existentes, incluidos nuevos sin stage |
| Validador oficial quick_validate.py | Siete skills aprobadas |
| Codex skills/list | Siete skills locales habilitadas, cero errores |
| Configuración TOML nativa de Codex | Claves agents aceptadas mediante app-server --strict-config --print-startup-config |
| `git diff --check` | Sin errores de whitespace |

El gate produjo artifacts/validation.log, pytest.xml y coverage.xml. Cobertura medida por pytest: **71% conjunta** (líneas y ramas), planning.py 91%, check_repository.py 75%; el paquete de una constante figura con 100%. validate.py y check_wheel.py se ejecutaron como comandos externos al proceso medido y figuran con 0% en ese informe. No se usa ese porcentaje como prueba de cobertura del futuro motor.

La inspección del paquete encontró 170 archivos en el sdist (169 del repositorio más PKG-INFO) y cinco entradas en el wheel: dos del paquete y tres de metadata. No se incluyeron cachés, entornos, .git, artefactos ni código de tooling en el wheel. Evidencia local: artifacts/package-audit.json.

Fallos encontrados y resueltos: lectura de texto dependiente del locale en Windows; import de scripts al invocar check_wheel.py directamente; acceso DNS restringido durante uv sync. El último se resolvió con red autorizada, sin cambiar controles del entorno. Los comandos requeridos volvieron a ejecutarse con éxito. El aviso de uv sobre caché dentro del árbol se contrasta mediante inspección del archivo distribuido; no se incluyen entornos, cachés ni artefactos locales.

## Codex

Se reutilizaron las instrucciones oficiales de openai-docs y skill-creator; no se instalaron paquetes de skills de terceros ni herramientas globales. Las siete skills son moana-architecture, moana-python, moana-pixel-art, moana-graphics, moana-testing, moana-issue-planning y moana-code-review. Las dos últimas sustituyen los nombres locales anteriores, sin duplicar instrucciones.

La consulta nativa skills/list de codex-cli 0.169.0-alpha.11.1, con cwd del proyecto y forceReload, devolvió las siete con enabled=true, scope=repo y cero errores. Evidencia filtrada: artifacts/codex-skills.json. El primer intento no pudo abrir la base SQLite personal bajo sandbox; la consulta se completó con acceso autorizado. No creó chats ni ejecutó inferencia.

Roles preparados: architect, python_engineer, graphics_engineer, pixel_artist, test_engineer, documentation_writer, reviewer e issue_planner, con prefijo moana_. Se validan sus TOML y se heredan modelo/permisos. La comprobación nativa de configuración acepta las claves agents; no se afirma que estos ocho perfiles se hayan cargado o ejecutado en la conversación. Se usó delegación independiente para auditoría/documentación y se integró y validó el resultado desde el agente principal.

AGENTS.md raíz es suficiente por ahora: no hay instrucciones distintas por directorio que justifiquen archivos anidados. No se configuran hooks de ciclo de vida de Codex ni automatizaciones periódicas de la app; la automatización verificable usa Git, scripts y CI. [Auditoría detallada](CODEX.md).

## Backlog y cobertura

| Fase | Issues | Condición de salida |
| --- | ---: | --- |
| P0 — Inicialización | 1 | Infraestructura, skills y backlog válidos |
| P1 — Contratos y core | 8 | Modelos estrictos, límites y fixtures enteras |
| P2 — Imagen estática | 5 | Render, PNG roundtrip y determinismo |
| P3 — Arte y edición | 8 | Técnicas editables, batches e historial |
| P4 — Persistencia y animación | 6 | Proyecto reversible, atlas y timeline |
| P5 — Evaluación y release | 8 | Corpus, seguridad, benchmarks y packaging |

**36 issues**: prioridades P0=7, P1=25, P2=4, P3=0. No se inventan mejoras opcionales para rellenar P3. Estados: done=1 (infraestructura histórica), ready=1, blocked=34; ningún issue de implementación está completado.

Se conservan las seis fases existentes para respetar sus dependencias; las ocho áreas sugeridas están representadas dentro de ellas. No se crean carpetas temáticas vacías. Los 40 requisitos cubren las 25 secciones de MOANA.md y tienen issues asociados. Esa es cobertura de planificación, no de funcionalidad implementada.

El validador rechaza IDs duplicados, aliases repetidos, referencias inexistentes, ciclos, inversión de fase, estados activos con dependencias incompletas y cierres sin evidencia por criterio/prueba. El [mapa](issues/dependency-map.md) contiene bloqueantes, dependientes, orden topológico, niveles paralelizables y ruta crítica estructural por número de nodos; no estima duración. El [roadmap](issues/roadmap.md) y la [trazabilidad](issues/traceability.md) se derivan del mismo catálogo.

## Decisiones técnicas

Pillow es el adaptador de imagen/export; NumPy opera buffers con propiedad explícita; AggDraw queda acotado a paths futuros; Pydantic valida datos estrictos. El núcleo no ejecuta código ni consume modelos generativos. El diseño mantiene documento declarativo, IDs estables, edición local, renderer determinista y disco en fronteras.

MOANA.md 0.1.1-draft aclara cuatro contratos antes de implementarlos: polígonos even-odd autointersectados no se descartan por área algebraica cero; batches comparan revisión y digest del snapshot para distinguir ramas; ProjectManifest envuelve documento/assets/historial; assets inmutables y publicación atómica sin sobrescritura evitan carreras. Los issues afectados incluyen pruebas de esos casos. [ADR-007](architecture/decisions/ADR-007-contract-clarifications.md).

El build del gate usa Hatchling fijado por el lock mediante uv build --no-build-isolation. El comando estándar uv build también forma parte de la verificación requerida. No se añade un segundo gestor de dependencias. Python 3.12.16 es la versión local reproducible; CI prueba las líneas 3.12–3.14 en tres plataformas.

## CI y límites pendientes

El [run Quality del commit 9388c57](https://github.com/xlCyanz/moana/actions/runs/43995965656) falló en Windows al leer texto UTF-8 con el codec local charmap. Se inspeccionaron los logs, se corrigió la causa y se agregó una simulación cp1252. Esa evidencia local no demuestra que una nueva matriz remota haya pasado. Los cambios de esta tarea no se han enviado; no hay una ejecución remota nueva de ellos.

El YAML se comprueba localmente con PyYAML y reglas del repositorio. actionlint no está disponible; no se afirma validación con ese ejecutable. No se cambiaron protecciones, rama predeterminada, permisos ni recursos remotos. Las protecciones propuestas están documentadas en la guía de desarrollo.

La licencia de distribución sigue pendiente del propietario y se trata en MOANA-035 antes de publicar. No bloquea MOANA-001. No hay renderer, goldens, benchmarks ni evaluación artística humana completados. La igualdad de píxeles entre plataformas deberá verificarse cuando exista el motor.

## Siguiente paso

Implementar [MOANA-001 — tipos, coordenadas, errores y límites](issues/MOANA-001.md): usar su alcance y pruebas, cargar moana-python/architecture/testing según corresponda y completar evidencia antes de cambiar su estado a done. La publicación de estos cambios y una nueva ejecución GitHub Actions requieren una solicitud que incluya el push.
