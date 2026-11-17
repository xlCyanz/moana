# ADR-004 — Configuración local y roles especializados

Estado: aceptado · 2026-11-16.

## Contexto

El entorno de Codex puede variar entre desktop, CLI y orquestación cloud. Es incorrecto presentar una configuración local como prueba de activación en cualquier host.

## Decisión

`AGENTS.md` define trabajo operativo; siete skills en `.agents/skills/` aportan flujos concretos; siete TOML en `.codex/agents/` definen roles sin fijar modelos ni permisos. Heredan la sesión. El control mecánico se hace con pre-commit y CI. No se instalan hooks de ciclo de vida de Codex: su ejecución/trust depende de la superficie y no es necesaria para el gate.

## Alternativas y consecuencias

Modificar configuración global contaminaría otros proyectos. Añadir servidores MCP sin una necesidad y credenciales reales daría una falsa integración. Los roles y skills son versionables y utilizables en una sola sesión; delegación sólo si está solicitada y disponible. Las capacidades observadas y lo no ensayado se registran en `docs/CODEX.md`.

## Ampliación del inventario — 2026-11-17

El inventario inicial de siete roles se amplía a ocho con documentation_writer, conservando el mismo formato, herencia y fronteras. Las skills siguen siendo siete; planificación y revisión adoptan los nombres moana-issue-planning y moana-code-review. La consulta nativa skills/list confirmó su descubrimiento local. El [reporte actual](../BOOTSTRAP_REPORT.md) detalla la evidencia y los límites de activación de roles.
