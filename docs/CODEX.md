# Auditoría de Codex e integraciones

Observación local: **2026-11-16**, proyecto nuevo en macOS arm64. No se consultaron credenciales ni se alteró configuración personal.

| Superficie | Evidencia observada | Configuración / límite |
| --- | --- | --- |
| Codex CLI | `codex-cli 0.169.0-alpha.11.1`, help y features disponibles | Configuración local; no fijar modelo ni desactivar permisos |
| Skills | Skill creator disponible y formato documentado | Siete skills en `.agents/skills/`, con metadata UI |
| Agentes | Herramientas de colaboración presentes en esta sesión | Siete roles TOML; heredan modelo/herramientas/permisos |
| Feature flags CLI | `hooks` stable=true; `multi_agent` deprecated=true; `multi_agent_v2` stable=false | No activar flags experimentales/deprecated por suposición |
| Proyecto Codex | `[agents]` con enabled y máximo de 3 subagentes | Estructura verificable; no demuestra carga activa en esta conversación |
| Git | Disponible; repositorio local inicializado en main | Sin remote ni commits creados en la inicialización |
| Git hooks | pre-commit instalado en `.git/hooks/pre-commit` | Ejecuta tools del venv; no requiere uv global |
| GitHub CLI | `gh` está instalado | No se usó autenticación ni se creó repo remoto |
| GitHub Actions | Workflow y plantillas reales en `.github/` | Se ejecutarán tras publicar en GitHub; CI remoto no observado |
| Plugins externos | GitHub y OpenAI Developers aparecen disponibles para instalar, no conectados como herramientas de esta sesión | No necesarios para preparar el repo local; no se afirma integración activa |
| Automatizaciones | Gate local, hooks Git, workflow y Dependabot de acciones | No se crearon recordatorios ni tareas periódicas de la app |

Los roles son `moana_architect`, `moana_python_engineer`, `moana_graphics_engineer`, `moana_pixel_artist`, `moana_test_engineer`, `moana_reviewer` y `moana_issue_planner`. Se registran como archivos de proyecto según la documentación oficial. No se ejecutó inferencia con estos perfiles durante P0; su descubrimiento depende de la confianza del proyecto y de la superficie que abra la sesión. No se crean otros chats ni se necesita delegar para usar las skills.

Codex puede descubrir skills en `.agents/skills`. Si la UI no refleja cambios, abrir otra sesión o reiniciar la app según su documentación. `agents/openai.yaml` describe la skill en la UI; no configura un subagente. Los roles están separados bajo `.codex/agents/`.

No se instalaron hooks de ciclo de vida de Codex: el soporte local no garantiza ejecución bajo orquestación cloud y existe un mecanismo de confianza específico. La automatización efectiva de calidad usa Git/pre-commit y CI, que se pueden ejecutar manualmente y verificar sin esa dependencia.

## Comprobaciones reproducibles

```sh
codex --version
codex features list
codex app-server --strict-config --print-startup-config -c 'agents.enabled=true' -c 'agents.max_concurrent_threads_per_session=3'
uv run python -m scripts.check_repository
```

El checker valida TOML, campos de los roles y metadata de skills. La comprobación nativa mediante `app-server --strict-config --print-startup-config` terminó con código 0, sin iniciar el servidor; su payload de configuración se omitió del reporte. Esto comprueba los ajustes reconocidos, no que la app haya aplicado el archivo del proyecto. `--strict-config` no es compatible con `features list` en esta CLI. No existe aquí una API comprobada para enumerar los roles cargados de esta conversación. Esa distinción evita presentar configuración en disco como activación observada.

## Fuentes consultadas

- [Skills locales](https://learn.chatgpt.com/docs/build-skills): descubrimiento en `.agents/skills` y frontmatter.
- [Agentes personalizados](https://learn.chatgpt.com/docs/agent-configuration/subagents): TOML por rol, campos requeridos y herencia.
- [Configuración de Codex](https://learn.chatgpt.com/docs/config-file/config-reference): capas de proyecto, confianza y claves de agentes.
- [Hooks](https://learn.chatgpt.com/docs/hooks): soporte y diferencias de ejecución.
- [Instalación de uv](https://docs.astral.sh/uv/getting-started/installation/) y [CI con uv](https://docs.astral.sh/uv/guides/integration/github/).
- [Formatos Pillow](https://pillow.readthedocs.io/en/stable/handbook/image-file-formats.html) y [Pydantic strict](https://pydantic.dev/docs/validation/latest/concepts/strict_mode/), para contratos futuros.

También se consultó el manual oficial mediante el helper de la skill openai-docs y el validador local de skill-creator. El permiso de red fue necesario para descargar herramientas; las rutas `.agents`, `.codex` y `.git` requirieron escritura autorizada por ser protegidas. No se modificaron permisos globales.
