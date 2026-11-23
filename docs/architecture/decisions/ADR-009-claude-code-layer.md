# ADR-009 — Capa de Claude Code sobre la infraestructura existente

Estado: aceptado · 2026-11-17. Ampliado por [ADR-041](ADR-041-rename-moanart.md): skills y subagentes `moanart-*`.

## Contexto

La inicialización P0 ([MOANA-000](../../issues/MOANA-000.md)) dejó entorno Python, CI, estándares, backlog generado y skills/roles para Codex ([ADR-004](../ADR-004-agent-infrastructure.md)). Se solicitó preparar también Claude Code: memoria del proyecto, reglas por ruta, skills, subagentes, hooks y evaluación de MCP. La solicitud proponía además una estructura de issues por carpetas de ocho fases y documentos `coding.md`/`ai-development.md`.

## Decisión

1. **Memoria**: `CLAUDE.md` importa `@AGENTS.md` y añade sólo lo específico de Claude. Una única fuente de reglas operativas evita divergencia entre hosts.
2. **Reglas**: ocho archivos en `.claude/rules/` con frontmatter `paths`; cada uno resume y enlaza el estándar de `docs/standards/` o la sección de MOANA.md, sin repetirlo.
3. **Skills**: `.agents/skills/` sigue siendo canónico. `.claude/skills/moana-*/SKILL.md` son envoltorios con frontmatter idéntico que remiten a la fuente. Se descartaron enlaces simbólicos porque la matriz CI incluye Windows, donde Git puede materializarlos como texto. El checker detecta deriva de metadata.
4. **Subagentes**: seis roles en `.claude/agents/` (arquitectura, Python, gráficos, Pixel Art, QA, documentación). Los cinco revisores son de sólo lectura; documentación es el único con Edit/Write. No se crea revisor ni planificador separados: `/code-review`, `moana-code-review` y `moana-documentation` cubren esas funciones.
5. **Hooks**: `scripts/claude_hooks.py` (tipado y probado) protege `uv.lock`/`.env`, bloquea comandos Git/rm destructivos y ejecuta Ruff sólo sobre el `.py` editado. Validaciones de módulo, completa y pre-commit quedan en puntos de control manuales/CI.
6. **MCP**: ninguno. El backlog es local, `gh` cubre GitHub con confirmación y Claude lee PNG sin servidor extra.
7. **Backlog**: se conservan los 36 issues `MOANA-xxx`, fases P0–P5 de MOANA.md §23 y la generación desde `catalog.json`. No se reorganiza en ocho carpetas: cambiaría rutas y enlaces de IDs estables, duplicaría la fase como carpeta y metadata, y contradiría el roadmap normativo. Hardening (seguridad, rendimiento, documentación final, release) ya existe en P5 (MOANA-030…035).
8. **Estándares**: `docs/standards/python.md` cumple el papel de `coding.md`; la guía de IA es `docs/guides/agent-workflow.md` más este ADR. No se crean duplicados.

## Alternativas

- Duplicar reglas en `CLAUDE.md`: rechazado por deriva con `AGENTS.md`.
- Copiar las skills completas: rechazado; dos fuentes editables.
- Hook Stop con la suite completa: rechazado por coste y por la petición explícita de no ejecutar todo tras cada cambio.
- Instalar skills/plugins comunitarios: rechazado tras revisión ([auditoría](../../CLAUDE_CODE.md)).

## Consecuencias

El checker valida la capa Claude junto al resto; cambiar una skill exige actualizar su envoltorio. Los hooks dependen del `.venv` local y fallan de forma no bloqueante si falta. La carga efectiva de skills/agentes en una sesión nueva debe observarse, no presumirse.
