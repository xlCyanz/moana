# MOANA-000 — Inicializar infraestructura y planificación

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-000
- Aliases históricos: MOA-000
- Phase: P0
- Priority: P0
- Status: done
- Complexity: L (relativa, no estimación de tiempo)
- Dependencies: Ninguna
- Related modules: tooling, docs, agents
- Requirements: R001, R030, R031, R032, R033, R034, R035, R036, R039 ([trazabilidad](traceability.md))
- Bloqueo: Ninguno

## Context

Un checkout vacío no ofrecía contrato ni herramientas de desarrollo.

## Objective

Conservar una base reproducible y ampliar su planificación sin crear motor.

## Scope

Crear especificación, paquete mínimo, entorno, skills, roles, CI y backlog completo; registrar evidencia de las capacidades realmente observadas.

## Out of scope

No implementar canvas, rasterizador, API gráfica ni publicar repositorio/paquete.

## Technical requirements

- Python >=3.12, src layout, uv.lock resuelto y entorno virtual real
- Ruff, mypy, pytest, build y validación de DAG/skills accesibles desde scripts/validate.py

## Proposed implementation

- Auditar archivos y capacidades existentes; resolver divergencias con ADR
- Generar documentación desde un catálogo validado y ejecutar comandos reales

## Acceptance criteria

- [x] AC1: Las 25 secciones normativas y todos los requisitos tienen trazabilidad sin ciclos
- [x] AC2: Import y wheel aislado funcionan; siete skills válidas, configuración local documentada y gate verde

## Required tests

- [x] T1: Ejecutar lint, formato, tipos, smoke de bibliotecas y comprobación del backlog
- [x] T2: Construir wheel/sdist, instalar wheel fuera de src y validar las siete skills con el validador disponible

## Expected deliverables

- Entorno uv, paquete mínimo tipado, gate y workflow CI verificables.
- AGENTS.md, siete skills, ocho roles, contratos, backlog generado y reporte de evidencia.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- Confundir configuración guardada con una capacidad activa; registrar evidencia por superficie.

## Evidence

- 2026-11-16: scripts/validate.py aprobó lock, Ruff, mypy, checker, 20 tests y build en macOS arm64 / Python 3.12.16.
- Wheel construido desde sdist e instalado fuera del checkout; metadata y py.typed verificados.
- Siete skills aprobadas por quick_validate.py; roles/config TOML verificados y ajustes aceptados por CLI Codex.
- pre-commit instalado y ejecutado sobre todos los archivos nuevos. Ver docs/INITIALIZATION_REPORT.md para límites y versiones.
- 2026-11-17: refinamiento validado localmente con 26 tests, gate completo, uv build, wheel aislado y siete skills descubiertas por Codex; docs/BOOTSTRAP_REPORT.md. Sin push de esta revisión.
- AC1: 2026-11-17: scripts.check_repository y planning.py --check validan 36 IDs canónicos, DAG acíclico, 40 requisitos y 25 secciones; docs/BOOTSTRAP_REPORT.md.
- AC2: 2026-11-17: validate.py aprobado; check_wheel.py verificó import/metadata/py.typed en venv aislado; skills/list devolvió siete skills habilitadas de scope repo sin errores.
- T1: 2026-11-17: Ruff, formato, mypy (10 archivos), checker y pytest (26 aprobados) en macOS arm64/Python 3.12.16; artifacts/validation.log.
- T2: 2026-11-17: uv build y build del gate generaron sdist/wheel; instalación aislada aprobada y quick_validate.py aprobó las siete skills.
