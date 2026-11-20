# Flujo de una sesión de agente (Codex o Claude Code)

El repositorio debe contener todo el contexto necesario para continuar. No depender de conversaciones anteriores ni inferir APIs disponibles a partir de ejemplos de diseño.

## Recorrido de implementación

1. Leer [AGENTS.md](../../AGENTS.md) (Claude Code lo recibe importado desde [CLAUDE.md](../../CLAUDE.md)) y comprobar estado de Git, rama y cambios existentes.
2. Leer las secciones relevantes de [MOANA.md](../../MOANA.md) y los ADR aplicables.
3. Consultar [roadmap](../issues/roadmap.md), [dependencias](../issues/dependency-map.md) y [trazabilidad](../issues/traceability.md).
4. Elegir el siguiente issue cuyas dependencias estén `done`; respetar el alcance solicitado aunque otros issues estén disponibles.
5. Leer el issue completo: contexto, objetivo, límites, propuesta, pruebas, riesgos y DoD.
6. Cargar las skills pertinentes; comprobar su contenido y herramientas realmente disponibles.
7. Inspeccionar implementación existente, tipos, pruebas y convenciones antes de cambiar código.
8. Implementar únicamente el alcance; un módulo se crea con comportamiento real, no con stubs que simulan entrega.
9. Añadir pruebas que demuestren contratos y riesgos pertinentes; no duplicar la implementación como oráculo.
10. Ejecutar los comandos de [desarrollo](development.md), el gate y checks específicos del issue.
11. Revisar el diff y la evidencia; inspeccionar imágenes cuando exista un cambio raster.
12. Actualizar documentación, ejemplos y catálogos; regenerar Markdown y comprobar consistencia.
13. Actualizar estado según el [ciclo de vida](issue-lifecycle.md) y reportar resultados y límites reales.

La instrucción vigente del usuario define el trabajo autorizado. Un issue pendiente no autoriza su implementación por sí solo. En una tarea de infraestructura no se adelanta la creación de un canvas, renderer o CLI gráfico.

Para usar el motor (no desarrollarlo) desde un agente —crear un documento, previsualizarlo a 1×/4× y editarlo por ID con revisión y snapshot— sigue la [guía de flujos IA](ai-workflows.md).

## Selección de skills y responsabilidades

| Necesidad | Skill / resultado esperado |
| --- | --- |
| Contratos y dependencias de módulos | `moana-architecture`: decisión, fronteras y ADR si aplica |
| Implementación Python | `moana-python`: tipos, código mantenible y pruebas de fronteras |
| Raster, máscaras y composición | `moana-graphics`: algoritmo, costes y fixtures exactas |
| Lectura visual y materiales | `moana-pixel-art`: propuesta editable, inspección 1×/4× y límites artísticos |
| Calidad y regresión | `moana-testing`: oráculos, casos negativos y resultados reproducibles |
| Backlog y trazabilidad | `moana-issue-planning`: issue acotado, DAG y criterios comprobables |
| Revisión | `moana-code-review`: defectos accionables con escenario, ubicación y consecuencia |

El trabajo de documentación transforma contratos y evidencia en guías consistentes; no inventa resultados ni cambia la semántica del producto para resolver una contradicción editorial. Los roles configurados heredan permisos y modelo del host. Que un archivo exista no prueba que una UI o sesión concreta lo haya cargado; registrar la evidencia de descubrimiento disponible.

## Equivalencias por host

| Necesidad | Codex | Claude Code |
| --- | --- | --- |
| Instrucciones | `AGENTS.md` | `CLAUDE.md` → `@AGENTS.md` + `.claude/rules/` por ruta |
| Skills | `.agents/skills/` | envoltorios `.claude/skills/` que remiten a `.agents/skills/` |
| Roles | `.codex/agents/*.toml` | `.claude/agents/*.md` (revisores de sólo lectura + documentación) |
| Automatización | pre-commit y CI | lo mismo, más hooks ligeros de `.claude/settings.json` |

En Claude Code, delega revisiones en paralelo a `moana-architect`, `moana-python-engineer`, `moana-graphics-engineer`, `moana-pixel-artist` o `moana-qa-engineer` cuando el cambio lo justifique; integra tú sus hallazgos. Usa `moana-documentation` para regenerar catálogos y documentar decisiones. Validación: rápida (hook), módulo, completa y pre-commit según [CLAUDE.md](../../CLAUDE.md).

## Coordinación independiente

Delegar cuando esté autorizado y el host lo soporte. Cada encargo define contrato de entrada, alcance, archivos propios, límites de efectos, entregables y comandos de verificación. Dos agentes no modifican el mismo archivo en paralelo. Un agente puede revisar sin editar los archivos del otro y enviar hallazgos al integrador.

El DAG identifica candidatos independientes; compartir un archivo de contrato puede impedir su ejecución simultánea aunque no exista una arista entre issues. El agente principal integra cambios, resuelve contradicciones, ejecuta el gate conjunto y comprueba que las afirmaciones del reporte coinciden con herramientas observadas. No se abren otros chats como sustituto de subagentes sin solicitud del usuario.

## Cierre y bloqueos

Registrar comando, resultado, entorno y evidencia de un fallo; distinguir error del producto de falta de acceso del entorno. Un bloqueo no justifica desactivar controles ni marcar un check como aprobado. Continuar con el trabajo independiente y describir el dato/permiso externo necesario para lo restante.

El cierre enumera cambios, checks aprobados/fallidos/no ejecutados, estado de issues y siguiente paso. Commit, push, publicación y cambios remotos sólo se realizan dentro de una autorización vigente que los incluya. No afirmar revisión artística humana, activación de perfiles ni CI remoto sin observarlo.
