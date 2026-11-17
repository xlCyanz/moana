# MOANA-007 — Añadir adaptador de paths AggDraw

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-007
- Aliases históricos: MOA-007
- Phase: P3
- Priority: P2
- Status: ready
- Complexity: M (relativa, no estimación de tiempo)
- Dependencies: [MOANA-006](MOANA-006.md), [MOANA-010](MOANA-010.md), [MOANA-028](MOANA-028.md)
- Related modules: geometry, render
- Requirements: R004, R015 ([trazabilidad](traceability.md))
- Bloqueo: Ninguno

## Context

Curvas complementarias requieren backend explícito sin diluir el contrato entero.

## Objective

Añadir paths con cobertura binaria y garantía de compatibilidad limitada.

## Scope

Agregar path M/L/Q/C/Z con punto fijo, versión de backend y binarización de cobertura; mantener separado el perfil entero.

## Out of scope

No fuentes, SVG completo ni rasterización vectorial genérica.

## Technical requirements

- Umbral >=128 a resolución nativa; comandos limitados y sin SVG externo
- Registrar aggdraw-v1 y versiones en provenance; exponer capacidad real y estimación de trabajo

## Proposed implementation

- Definir el payload de comandos fijo 1/256 en schema junto al adaptador
- Validar segmentos, rasterizar con AggDraw y aplicar threshold/documentar provenance

## Acceptance criteria

- [ ] AC1: Paths cerrados producen únicamente máscara binaria y no introducen colores por AA
- [ ] AC2: Entradas desconocidas o excesivas fallan antes del adaptador; ausencia de capacidad da error explícito

## Required tests

- [ ] T1: Fixtures de curvas pequeñas, joins, cierres y curvas fuera de lienzo
- [ ] T2: Repetición con entorno fijado y comparación backend por plataforma sin prometer equivalencia al raster entero

## Expected deliverables

- Adaptador AggDraw para paths con política explícita de muestreo y cuantización.
- Fixtures de curvas y uniones; evaluación RGBA y de errores del adaptador.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- No asumir que AggDraw comparte píxeles entre versiones o plataformas no ensayadas.

## Guía para agentes de IA

**Estado para agentes:** Listo: todas las dependencias están `done`; puede empezarse.

### 1. Preparación

- Rama: `feat/MOANA-007-anadir-adaptador-paths` creada desde `develop` actualizado: `git switch develop && git pull --ff-only && git switch -c feat/MOANA-007-anadir-adaptador-paths`.
- Verificar en `docs/issues/catalog.json` que este issue está `ready` y que sus dependencias ([MOANA-006](MOANA-006.md), [MOANA-010](MOANA-010.md), [MOANA-028](MOANA-028.md)) están `done`.
- Entorno: `uv sync --locked` (sin uv global: `sh scripts/bootstrap.sh` y después `sh scripts/uv.sh` en lugar de `uv`).
- Al empezar, cambiar `status` a `in_progress` en el catálogo y regenerar con `uv run python scripts/planning.py`.

### 2. Lectura obligatoria (en orden)

1. `CLAUDE.md` (Claude Code) o `AGENTS.md` (Codex) y [flujo de sesión](../guides/agent-workflow.md).
2. MOANA.md: §3 Arquitectura modular; §4 Stack tecnológico; §6 Geometría y primitivas; §14 Renderizado y determinismo; §25 Definition of Done. Estas secciones son el contrato normativo; ante duda, prevalecen sobre este issue.
3. [Contratos de módulos](../architecture/module-contracts.md) para: `geometry`, `render`.
4. Estándares: [python](../../docs/standards/python.md), [architecture](../../docs/standards/architecture.md), [testing](../../docs/standards/testing.md).
5. Issues de dependencia ([MOANA-006](MOANA-006.md), [MOANA-010](MOANA-010.md), [MOANA-028](MOANA-028.md)): leer su sección Evidence para conocer las APIs ya entregadas; no reimplementarlas.
6. ADR en `docs/architecture/` que mencionen los módulos afectados.

### 3. Requisitos de MOANA.md cubiertos

| ID | Requisito | Secciones | Verificación exigida |
| --- | --- | --- | --- |
| R004 | Geometría complementaria AggDraw | §4, §6 | Fixtures de paths y capabilities por backend |
| R015 | Renderizado determinista | §14 | Digests RGBA en procesos/OS y semillas distintas |

### 4. Skills y subagentes

| Host | Skills a cargar | Revisión especializada |
| --- | --- | --- |
| Claude Code | `moana-graphics`, `moana-architecture`, `moana-code-review` | `moana-graphics-engineer`, `moana-python-engineer`, `moana-architect` (sólo lectura; el agente principal integra) |
| Codex | `$moana-graphics`, `$moana-architecture`, `$moana-code-review` | `moana_graphics_engineer`, `moana_python_engineer`, `moana_architect` |

### 5. Archivos

- Código o documentos a crear/modificar: `src/moana/geometry/`, `src/moana/render/`.
- Pruebas: `tests/unit/geometry/`, `tests/unit/render/`.
- No crear módulos ni carpetas sin comportamiento real. No tocar otros módulos salvo exportaciones imprescindibles, justificadas en el PR.

### 6. Plan de pruebas

- T1: Fixtures de curvas pequeñas, joins, cierres y curvas fuera de lienzo
- T2: Repetición con entorno fijado y comparación backend por plataforma sin prometer equivalencia al raster entero
- Oráculos independientes (cálculo a mano o fórmula de MOANA.md); nunca copiar la salida de la implementación como expected.
- Incluir casos negativos con el error de dominio esperado y casos borde (vacío, mínimo, máximo, fuera de rango).

### 7. Procedimiento

1. Escribir las pruebas de los criterios AC y T antes o junto con la implementación.
2. Implementar sólo **Scope**; respetar **Out of scope** y las dependencias permitidas de MOANA.md §3.
3. Validación de módulo: `uv run pytest tests/unit/geometry/ tests/unit/render/ -q` y `uv run mypy src/`.
4. Validación completa: `uv run python scripts/validate.py` y `uv run python scripts/check_wheel.py`.
5. Revisión: subagentes listados y skill `moana-code-review`; corregir hallazgos críticos y altos.
6. Si hay salida raster: mostrar el PNG a 1x y ampliado por vecino más cercano; si cambia un golden, presentar expected/actual/diff y justificar.

### 8. Cierre

1. En `docs/issues/catalog.json`, para este issue: `status` → `review` (o `done` tras aprobación); completar `acceptance_evidence` (AC1, AC2), `test_evidence` (T1, T2) y `evidence` con rutas concretas de tests y archivos.
2. Issues que desbloquea ([MOANA-035](MOANA-035.md)): si todas sus dependencias quedan `done`, pasarlos a `ready` con `blocking_reason: null`.
3. Ejecutar `uv run python scripts/planning.py` y `uv run python -m scripts.check_repository`.
4. Abrir PR hacia `develop` enlazando este issue de GitHub (`Closes #<número>`), con comandos ejecutados y evidencia por AC/T. El CI completo corre al integrar `develop` en `main`.
5. Commit y push sólo con autorización del usuario. No declarar CI remoto ni aprobación artística humana sin evidencia.

### 9. Prohibido en este issue

- Implementar alcance de otros issues, incluidos los que desbloquea ([MOANA-035](MOANA-035.md)).
- Actualizar goldens automáticamente, desactivar checks, editar `uv.lock` a mano o añadir dependencias sin motivo técnico registrado.
- `eval`/`exec`/`pickle`, red o estado global mutable en el núcleo; lecturas de texto sin `encoding="utf-8"`.

## Evidence

Pendiente de implementación.
