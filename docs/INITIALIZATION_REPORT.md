# Reporte de inicialización

Fecha: **2026-11-16**, America/Santo_Domingo. Resultado: **P0 completada**, lista para implementar MOA-001. La carpeta estaba vacía; no había trabajo previo que conservar. No se implementó el motor gráfico.

## Entregables

| Grupo | Archivos / resultados |
| --- | --- |
| Especificación | [MOANA.md](../MOANA.md), 25 secciones con contratos de geometría, color, capas, JSON, edición, determinismo y seguridad |
| Operación | [AGENTS.md](../AGENTS.md), README, CONTRIBUTING, SECURITY, CHANGELOG y convenciones de editor/Git |
| Python | pyproject.toml, uv.lock, .python-version, .uv-version, src/moana/__init__.py y py.typed |
| Entorno local | .venv con Python 3.12.16; uv y Python administrado en .tools; cachés ignoradas por Git |
| Calidad | Ruff, mypy estricto, pytest, Hypothesis disponible, coverage, build/Hatchling, pre-commit |
| Agentes | Siete skills con SKILL.md y metadata UI; siete roles TOML y configuración de proyecto |
| Documentación | Arquitectura modular, cuatro ADR, threat model, flujos, testing y auditoría Codex |
| Planificación | 36 issues MOA-000…MOA-035; 40 requisitos; seis fases; DAG y matriz generados desde JSON |
| Ejemplos | Documento mínimo y batch de recolor como contratos futuros, sin renderer |
| Automatización | Scripts de bootstrap/validación/backlog, hook Git instalado, CI de nueve combinaciones y Dependabot de acciones |
| Distribución | Wheel y sdist construidos en dist; wheel generado desde sdist verificado en entorno aislado |

El [inventario completo](FILE_INVENTORY.md) enumera todos los archivos de fuente/configuración creados. `.venv/`, `.tools/`, `.cache/`, outputs de pruebas y `dist/` son artefactos locales ignorados, no contenido que deba subirse a Git.

## Versiones realmente instaladas

| Herramienta | Versión |
| --- | --- |
| Python del proyecto | 3.12.16 |
| uv | 0.13.8 |
| Pillow | 13.0.0 |
| NumPy | 2.5.5 |
| AggDraw | 1.4.1 |
| Pydantic | 2.14.3 |
| Ruff | 0.17.5 |
| mypy | 1.20.2 |
| pytest | 9.2.0 |
| Hatchling | 1.33.0 |
| pre-commit | 4.7.0 |

El lock contiene 40 paquetes resueltos contando Moana. Las versiones transitivas y hashes están en uv.lock. `uv` no estaba instalado y el Python predeterminado del shell era 3.9.6; se preparó un bootstrap local con el Python 3.14 disponible y luego se instaló el intérprete 3.12 del proyecto, sin cambiar el Python global.

## Validaciones observadas

| Comprobación | Resultado |
| --- | --- |
| `uv lock --check --offline` | Resolución coherente con pyproject, 40 paquetes |
| Bootstrap repetido con `UV_OFFLINE=1` | Instalación idempotente y gate completo sin red usando la caché preparada |
| `ruff check .` y `ruff format --check .` | Correcto |
| `mypy` | Sin errores, nueve archivos Python |
| `python -m scripts.check_repository` | 36 issues, 40 requisitos, siete skills; DAG sin ciclos y sin huérfanos |
| `python scripts/planning.py --check` | Markdown generado sincronizado con catálogos |
| `pytest` | **20 tests aprobados** |
| Smoke nativo | Pillow/NumPy/PNG, AggDraw y Pydantic estricto funcionando |
| `python -m build --no-isolation` | Wheel y sdist construidos; wheel construido a partir del sdist |
| `python -m scripts.check_wheel` | Instalación aislada, versión y py.typed correctos sin importar desde src |
| Validador de skill-creator | Siete respuestas `Skill is valid!` |
| pre-commit sobre todos los archivos nuevos | Ruff lint, formato y consistencia del repositorio aprobados |
| CLI Codex nativa | Validación strict de ajustes de agentes con app-server/print-startup-config: exit 0 |
| Workflow GitHub | YAML y entradas verificadas; acciones fijadas a SHAs publicados y uv fijado a .uv-version |

Los tests ejercitan dependencia desconocida, ciclos directos/indirectos, requisitos huérfanos, duplicados, inversión de fases, cierre sin evidencia, cierre con dependencias pendientes, campos inválidos, documentos derivados obsoletos, links rotos y skills mal formadas. El porcentaje de cobertura del paquete mínimo de metadata no mide cobertura del futuro motor.

## Estado real y límites

- MOA-000 está completado; **35 issues de implementación permanecen planned**. Cobertura de requisitos significa cobertura del backlog, no funcionalidad ya implementada.
- El paquete sólo contiene metadata y marcador de tipos. Aún no existen canvas, renderer, CLI gráfico, modelos de sprite ni edición de producto.
- Git está inicializado en `main`, sin commits ni remote. No se crearon issues remotos ni publicaciones.
- GitHub Actions está preparado para Python 3.12/3.13/3.14 en Linux/macOS/Windows. Sólo se ejecutaron comprobaciones locales en macOS arm64 con 3.12.16; no se atribuye éxito a la matriz remota.
- Los siete perfiles de agente están configurados y sus archivos validados. No se ejecutó una sesión de inferencia con cada perfil ni se verificó su descubrimiento en la UI de esta conversación.
- Se usa automatización de Git/CI; no se instalaron hooks de ciclo de vida de Codex ni tareas recurrentes de la app. La [auditoría](CODEX.md) explica soporte y fuentes oficiales.
- No se asignó una licencia por suposición. La decisión del propietario queda como gate anterior a publicación en MOA-035; no bloquea implementar el primer módulo.
- No se evaluó calidad artística humana ni se generaron goldens del motor inexistente.

## Siguiente paso

Implementar [MOA-001](issues/MOA-001.md): tipos de coordenadas/cajas, errores y límites, con fixtures de fronteras y propiedades de intersección. Luego MOA-002 añade documento Pydantic y schema. El [roadmap](ROADMAP.md) y el [DAG](DEPENDENCIES.md) guían las fases restantes.

Comando de verificación en esta carpeta, sin depender de uv global:

```sh
sh scripts/uv.sh run --locked python scripts/validate.py
```

Para reproducir desde otra copia: `sh scripts/bootstrap.sh` en macOS/Linux, o instalar uv y ejecutar `uv sync --locked` en Windows. No se requieren APIs externas para comenzar el desarrollo.
