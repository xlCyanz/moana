# Auditoría de Claude Code e integraciones

Observación local: **2026-11-17**, macOS arm64, `claude` 2.1.311 (Claude Code), sesión en la app de escritorio. No se modificó configuración global (`~/.claude`) ni se consultaron credenciales. Complementa la [auditoría de Codex](CODEX.md); la decisión está en [ADR-009](architecture/decisions/ADR-009-claude-code-layer.md).

## Inventario

| Componente | Ubicación | Estado | Evidencia |
| --- | --- | --- | --- |
| Memoria del proyecto | `CLAUDE.md` (importa `@AGENTS.md`) | configurado | `scripts.check_repository` exige el import |
| Reglas por ruta | `.claude/rules/` (8: python, architecture, testing, pixel-art, rendering, documentation, security, issues) | configurado y observado | Al escribir `scripts/*.py` y `tests/**` la sesión cargó `python.md`, `security.md` y `testing.md` por su frontmatter `paths` |
| Skills de proyecto | `.claude/skills/moana-*` (7 envoltorios) | configurado y descubierto | Frontmatter idéntico al canónico, comprobado por el checker; una sesión nueva `claude -p` (modelo haiku) enumeró las siete y la sesión actual las recargó |
| Subagentes | `.claude/agents/` (6) | configurado y descubierto | Frontmatter validado; la misma sesión nueva enumeró los seis; sólo `moana-documentation` tiene Edit/Write |
| Hooks | `.claude/settings.json` → `scripts/claude_hooks.py` | configurado y observado | Durante la preparación, PostToolUse devolvió un error de formato Ruff y PreToolUse bloqueó un comando con un force push literal; 25 tests unitarios |
| Permisos | `.claude/settings.json` | configurado | allow para gate/lectura Git; ask para commit/push/lock/gh; deny para force push, reset duro, `.env`, `uv.lock`, publish |
| Ajustes personales | `.claude/settings.local.json` | ignorado por Git | No se crea; cada desarrollador lo usa para preferencias propias |
| MCP del proyecto | sin `.mcp.json` | no configurado (decisión) | Ver abajo |

## Skills de terceros

Se revisaron las skills disponibles en la cuenta y el catálogo de plugins (búsqueda: pixel art, python, image processing, pytest, computer graphics). Resultado:

- No existe una skill oficial de Anthropic para Pixel Art, rasterización o NumPy/Pillow que aporte procedimientos verificables más allá de los estándares de Moana.
- Las coincidencias del catálogo (por ejemplo, un gate Python Ruff/Pyright/pytest) son de nivel comunitario y duplican `scripts/validate.py` con otra herramienta de tipos (Pyright frente a mypy). No se instalan.
- `anthropic-skills:pixel-sprites-iso` existe en la cuenta del usuario pero pertenece a otro proyecto (sprites isométricos de un juego) y usa Pillow directo, contrario al contrato de Moana. No se adopta.
- Skills genéricas útiles ya disponibles a nivel de usuario/plugin (no se versionan): `engineering:architecture` (ADR), `engineering:testing-strategy`, `engineering:code-review`, `simplify`, `/code-review`, `security-review`, `skill-creator`. Son opcionales; las siete skills Moana son la referencia normativa.

Por tanto, las skills del proyecto son propias (ya existentes en `.agents/skills/`) y se exponen a Claude mediante envoltorios. No se ejecutó código de terceros.

## Subagentes

| Agente | Rol | Herramientas | Cuándo |
| --- | --- | --- | --- |
| `moana-architect` | fronteras, ciclos, contratos, ADR | Read, Grep, Glob, Bash | módulo nuevo, cambio de contrato, diff multi-módulo |
| `moana-python-engineer` | tipos, errores, rendimiento, refactor | Read, Grep, Glob, Bash | tras implementar en `src/`/`scripts/` |
| `moana-graphics-engineer` | raster, máscaras, composición, determinismo | Read, Grep, Glob, Bash | core/geometry/layers/render/export |
| `moana-pixel-artist` | silueta, clusters, paleta, luz | Read, Grep, Glob, Bash | ejemplos, presets, corpus, PNG |
| `moana-qa-engineer` | tests, cobertura, bordes, regresiones | Read, Grep, Glob, Bash | planificar/verificar AC y T |
| `moana-documentation` | specs, ADR, backlog, coherencia | Read, Grep, Glob, Edit, Write, Bash | actualizar docs y catálogos |

Los revisores no editan: el agente principal integra, evitando cambios paralelos conflictivos. Revisión general de diffs: `/code-review` integrado o la skill `moana-code-review`; por eso no se crea un agente revisor duplicado. Los roles de Codex en `.codex/agents/` se mantienen para ese host.

## Hooks y niveles de validación

| Evento | Acción | Coste |
| --- | --- | --- |
| PreToolUse Edit/Write | bloquea `uv.lock` y `.env*` | <0,1 s |
| PreToolUse Bash | bloquea force push, `reset --hard`, `clean -f`, `--no-verify`, `checkout -- .`, `rm -r` fuera de `artifacts/dist/build/htmlcov/caches` | <0,1 s |
| PostToolUse Edit/Write | `ruff check` + `ruff format --check` del archivo `.py` editado; devuelve el problema a Claude | ~0,1 s |

Los hooks usan el Python del `.venv` mediante `scripts/run_hook.sh`; sin venv fallan de forma no bloqueante con el mensaje «run uv sync --locked». Validación de módulo, completa y pre-commit se describen en [CLAUDE.md](../CLAUDE.md); no se ejecuta la suite completa por hook.

## MCP

Servidores observados con `claude mcp list` (2026-11-17): conectores de la cuenta (Claude Docs, GitLab, Figma, Google Drive) y plugins de ingeniería/diseño (GitHub, Linear, Slack, Notion, Atlassian, Datadog…) que requieren autenticación, más `next-devtools`. Ninguno es necesario para Moana:

- Repositorio/issues: el backlog es local y generado; `gh` CLI cubre consultas de GitHub con permiso `ask`. Un MCP de GitHub necesitaría autenticación OAuth del propietario (`/mcp`); queda **pendiente opcional** si se decide sincronizar issues con GitHub.
- Imágenes: Claude lee PNG directamente con la herramienta Read; no hace falta un MCP de análisis de imágenes.
- Documentación: los contratos están en el repo.

No se añade `.mcp.json` ni se guardan credenciales.

## Comprobaciones reproducibles

```sh
uv run python -m scripts.check_repository
uv run pytest tests/unit/test_claude_hooks.py -q
claude mcp list
```

Descubrimiento observado con una sesión no interactiva (`claude -p`, sin herramientas de escritura, pidiendo enumerar skills y agentes `moana`). No demuestra el comportamiento de cada subagente bajo carga real; eso se evaluará al usarlos en MOANA-001.

Limitación conocida: el guard de Bash analiza el texto del comando, así que también bloquea un comando que sólo *contiene* un patrón peligroso como literal (por ejemplo, dentro de un heredoc o `echo`). Es un falso positivo deliberado y seguro; para editar documentación que lo mencione, usa Edit en lugar de la shell.
