# MOANA-022 — Implementar timeline y evaluación de frames

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-022
- Aliases históricos: MOA-022
- Phase: P4
- Priority: P1
- Status: ready
- Complexity: L (relativa, no estimación de tiempo)
- Dependencies: [MOANA-018](MOANA-018.md), [MOANA-019](MOANA-019.md), [MOANA-010](MOANA-010.md)
- Related modules: animation, schema
- Requirements: R020 ([trazabilidad](traceability.md))
- Bloqueo: Ninguno

## Context

Evaluar frames incrementalmente introduce dependencia del orden y deriva temporal.

## Objective

Evaluar cada frame contra la misma base con tiempos/pivotes verificables.

## Scope

Crear animaciones con duración, loops, pivote común y overrides evaluados siempre contra la base.

## Out of scope

No tweening implícito, rigging ni interpolación aprendida.

## Technical requirements

- Validar IDs y presupuestos acumulados antes de export; frames no heredan cambios del anterior
- Estabilidad de semilla por defecto y variación temporal sólo explícita

## Proposed implementation

- Definir timeline y overrides limitados sin revision persistente
- Presupuestar todos los frames y evaluar cada uno independientemente

## Acceptance criteria

- [ ] AC1: Cambiar el orden de evaluación de frames no cambia ninguno de sus resultados
- [ ] AC2: Duraciones y pivotes se preservan y un override inválido impide el render parcial de la solicitud

## Required tests

- [ ] T1: Frame único, 256 frames, límite de duración/área y loops
- [ ] T2: Overrides de geometría/color/visibilidad y textura estable entre frames

## Expected deliverables

- Timeline con evaluación de frames/overrides y reglas de duración/composición.
- Fixtures de límites temporales, estabilidad de IDs y determinismo por frame.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- Un bucle infinito de playback no autoriza un render infinito; exportar secuencia finita.

## Guía para agentes de IA

**Estado para agentes:** Listo: todas las dependencias están `done`; puede empezarse.

### 1. Preparación

- Rama: `feat/MOANA-022-implementar-timeline-evaluacion` creada desde `develop` actualizado: `git switch develop && git pull --ff-only && git switch -c feat/MOANA-022-implementar-timeline-evaluacion`.
- Verificar en `docs/issues/catalog.json` que este issue está `ready` y que sus dependencias ([MOANA-018](MOANA-018.md), [MOANA-019](MOANA-019.md), [MOANA-010](MOANA-010.md)) están `done`.
- Entorno: `uv sync --locked` (sin uv global: `sh scripts/bootstrap.sh` y después `sh scripts/uv.sh` en lugar de `uv`).
- Al empezar, cambiar `status` a `in_progress` en el catálogo y regenerar con `uv run python scripts/planning.py`.

### 2. Lectura obligatoria (en orden)

1. `CLAUDE.md` (Claude Code) o `AGENTS.md` (Codex) y [flujo de sesión](../guides/agent-workflow.md).
2. MOANA.md: §3 Arquitectura modular; §17 Animaciones y spritesheets; §25 Definition of Done. Estas secciones son el contrato normativo; ante duda, prevalecen sobre este issue.
3. [Contratos de módulos](../architecture/module-contracts.md) para: `animation`, `schema`.
4. Estándares: [python](../../docs/standards/python.md), [architecture](../../docs/standards/architecture.md), [testing](../../docs/standards/testing.md), [pixel-art](../../docs/standards/pixel-art.md), [security](../../docs/standards/security.md).
5. Issues de dependencia ([MOANA-018](MOANA-018.md), [MOANA-019](MOANA-019.md), [MOANA-010](MOANA-010.md)): leer su sección Evidence para conocer las APIs ya entregadas; no reimplementarlas.
6. ADR en `docs/architecture/` que mencionen los módulos afectados.

### 3. Requisitos de MOANA.md cubiertos

| ID | Requisito | Secciones | Verificación exigida |
| --- | --- | --- | --- |
| R020 | Animaciones, duraciones y pivotes | §17 | Evaluación independiente y continuidad temporal |

### 4. Skills y subagentes

| Host | Skills a cargar | Revisión especializada |
| --- | --- | --- |
| Claude Code | `moana-graphics`, `moana-pixel-art`, `moana-python`, `moana-architecture`, `moana-code-review` | `moana-graphics-engineer`, `moana-pixel-artist`, `moana-python-engineer`, `moana-architect` (sólo lectura; el agente principal integra) |
| Codex | `$moana-graphics`, `$moana-pixel-art`, `$moana-python`, `$moana-architecture`, `$moana-code-review` | `moana_graphics_engineer`, `moana_pixel_artist`, `moana_python_engineer`, `moana_architect` |

### 5. Archivos

- Código o documentos a crear/modificar: `src/moana/animation/`, `src/moana/schema/`.
- Pruebas: `tests/unit/animation/`, `tests/unit/schema/`.
- No crear módulos ni carpetas sin comportamiento real. No tocar otros módulos salvo exportaciones imprescindibles, justificadas en el PR.

### 6. Plan de pruebas

- T1: Frame único, 256 frames, límite de duración/área y loops
- T2: Overrides de geometría/color/visibilidad y textura estable entre frames
- Oráculos independientes (cálculo a mano o fórmula de MOANA.md); nunca copiar la salida de la implementación como expected.
- Incluir casos negativos con el error de dominio esperado y casos borde (vacío, mínimo, máximo, fuera de rango).

### 7. Procedimiento

1. Escribir las pruebas de los criterios AC y T antes o junto con la implementación.
2. Implementar sólo **Scope**; respetar **Out of scope** y las dependencias permitidas de MOANA.md §3.
3. Validación de módulo: `uv run pytest tests/unit/animation/ tests/unit/schema/ -q` y `uv run mypy src/`.
4. Validación completa: `uv run python scripts/validate.py` y `uv run python scripts/check_wheel.py`.
5. Revisión: subagentes listados y skill `moana-code-review`; corregir hallazgos críticos y altos.
6. Si hay salida raster: mostrar el PNG a 1x y ampliado por vecino más cercano; si cambia un golden, presentar expected/actual/diff y justificar.

### 8. Cierre

1. En `docs/issues/catalog.json`, para este issue: `status` → `review` (o `done` tras aprobación); completar `acceptance_evidence` (AC1, AC2), `test_evidence` (T1, T2) y `evidence` con rutas concretas de tests y archivos.
2. Issues que desbloquea ([MOANA-023](MOANA-023.md), [MOANA-024](MOANA-024.md), [MOANA-025](MOANA-025.md), [MOANA-026](MOANA-026.md), [MOANA-027](MOANA-027.md), [MOANA-030](MOANA-030.md), [MOANA-031](MOANA-031.md)): si todas sus dependencias quedan `done`, pasarlos a `ready` con `blocking_reason: null`.
3. Ejecutar `uv run python scripts/planning.py` y `uv run python -m scripts.check_repository`.
4. Abrir PR hacia `develop` enlazando este issue de GitHub (`Closes #<número>`), con comandos ejecutados y evidencia por AC/T. El CI completo corre al integrar `develop` en `main`.
5. Commit y push sólo con autorización del usuario. No declarar CI remoto ni aprobación artística humana sin evidencia.

### 9. Prohibido en este issue

- Implementar alcance de otros issues, incluidos los que desbloquea ([MOANA-023](MOANA-023.md), [MOANA-024](MOANA-024.md), [MOANA-025](MOANA-025.md), [MOANA-026](MOANA-026.md), [MOANA-027](MOANA-027.md), [MOANA-030](MOANA-030.md), [MOANA-031](MOANA-031.md)).
- Actualizar goldens automáticamente, desactivar checks, editar `uv.lock` a mano o añadir dependencias sin motivo técnico registrado.
- `eval`/`exec`/`pickle`, red o estado global mutable en el núcleo; lecturas de texto sin `encoding="utf-8"`.

## Evidence

Pendiente de implementación.
