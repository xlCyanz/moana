# MOANA-026 — Crear informes de calidad gráfica

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-026
- Aliases históricos: MOA-026
- Phase: P5
- Priority: P1
- Status: blocked
- Complexity: L (relativa, no estimación de tiempo)
- Dependencies: [MOANA-014](MOANA-014.md), [MOANA-015](MOANA-015.md), [MOANA-022](MOANA-022.md)
- Related modules: quality
- Requirements: R025, R005 ([trazabilidad](traceability.md))
- Bloqueo: Dependencias pendientes: MOANA-014, MOANA-015, MOANA-022

## Context

Heurísticas artísticas y errores de contrato tienen distinta severidad.

## Objective

Producir informes reproducibles y accionables sin modificar el sprite.

## Scope

Crear moana/quality para hard checks, heurísticas configurables, métricas y diagnósticos por región.

## Out of scope

No puntaje automático que garantice calidad profesional ni revisión humana ficticia.

## Technical requirements

- Informe ordenado con rule_id, severidad, bbox, explicación y evidencia; no modifica render
- Separar conformidad matemática de advertencias artísticas y permitir supresiones localizadas

## Proposed implementation

- Implementar hard checks primero y métricas sobre fixtures sintéticas
- Añadir heurísticas/supresiones y orden estable por regla/región/posición

## Acceptance criteria

- [ ] AC1: Un color fuera de paleta strict se detecta como fallo y un singleton como advertencia
- [ ] AC2: Informe se reproduce idéntico y supresión de un ojo no oculta errores de otra región

## Required tests

- [ ] T1: Corpus sintético con defectos conocidos y versiones corregidas
- [ ] T2: Tests de no mutación, orden estable, regiones superpuestas y estabilidad temporal

## Expected deliverables

- Reporte estructurado de calidad con hard checks y warnings identificables.
- Fixtures positivas/negativas por regla y separación entre métricas y juicio artístico.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- Un score no debe presentarse como garantía profesional ni como aprobación humana.

## Guía para agentes de IA

**Estado para agentes:** No empezar: estado `blocked`. Esperar a que [MOANA-014](MOANA-014.md), [MOANA-015](MOANA-015.md), [MOANA-022](MOANA-022.md) estén `done` y el catálogo marque este issue `ready`.

### 1. Preparación

- Rama: `feat/MOANA-026-crear-informes-calidad` creada desde `develop` actualizado: `git switch develop && git pull --ff-only && git switch -c feat/MOANA-026-crear-informes-calidad`.
- Verificar en `docs/issues/catalog.json` que este issue está `ready` y que sus dependencias ([MOANA-014](MOANA-014.md), [MOANA-015](MOANA-015.md), [MOANA-022](MOANA-022.md)) están `done`.
- Entorno: `uv sync --locked` (sin uv global: `sh scripts/bootstrap.sh` y después `sh scripts/uv.sh` en lugar de `uv`).
- Al empezar, cambiar `status` a `in_progress` en el catálogo y regenerar con `uv run python scripts/planning.py`.

### 2. Lectura obligatoria (en orden)

1. `CLAUDE.md` (Claude Code) o `AGENTS.md` (Codex) y [flujo de sesión](../guides/agent-workflow.md).
2. MOANA.md: §3 Arquitectura modular; §7 Técnicas profesionales de Pixel Art; §19 Control de calidad gráfico; §25 Definition of Done. Estas secciones son el contrato normativo; ante duda, prevalecen sobre este issue.
3. [Contratos de módulos](../architecture/module-contracts.md) para: `quality`.
4. Estándares: [python](../../docs/standards/python.md), [architecture](../../docs/standards/architecture.md), [testing](../../docs/standards/testing.md), [pixel-art](../../docs/standards/pixel-art.md).
5. Issues de dependencia ([MOANA-014](MOANA-014.md), [MOANA-015](MOANA-015.md), [MOANA-022](MOANA-022.md)): leer su sección Evidence para conocer las APIs ya entregadas; no reimplementarlas.
6. ADR en `docs/architecture/` que mencionen los módulos afectados.

### 3. Requisitos de MOANA.md cubiertos

| ID | Requisito | Secciones | Verificación exigida |
| --- | --- | --- | --- |
| R025 | Evaluación gráfica y diagnósticos | §19 | Hard/soft checks, bbox y supresiones |
| R005 | Técnicas profesionales y calidad artística | §7, §19 | Corpus editable y rúbrica humana documentada |

### 4. Skills y subagentes

| Host | Skills a cargar | Revisión especializada |
| --- | --- | --- |
| Claude Code | `moana-pixel-art`, `moana-testing`, `moana-code-review` | `moana-pixel-artist`, `moana-qa-engineer` (sólo lectura; el agente principal integra) |
| Codex | `$moana-pixel-art`, `$moana-testing`, `$moana-code-review` | `moana_pixel_artist`, `moana_qa_engineer` |

### 5. Archivos

- Código o documentos a crear/modificar: `src/moana/quality/`.
- Pruebas: `tests/unit/quality/`.
- No crear módulos ni carpetas sin comportamiento real. No tocar otros módulos salvo exportaciones imprescindibles, justificadas en el PR.

### 6. Plan de pruebas

- T1: Corpus sintético con defectos conocidos y versiones corregidas
- T2: Tests de no mutación, orden estable, regiones superpuestas y estabilidad temporal
- Oráculos independientes (cálculo a mano o fórmula de MOANA.md); nunca copiar la salida de la implementación como expected.
- Incluir casos negativos con el error de dominio esperado y casos borde (vacío, mínimo, máximo, fuera de rango).

### 7. Procedimiento

1. Escribir las pruebas de los criterios AC y T antes o junto con la implementación.
2. Implementar sólo **Scope**; respetar **Out of scope** y las dependencias permitidas de MOANA.md §3.
3. Validación de módulo: `uv run pytest tests/unit/quality/ -q` y `uv run mypy src/`.
4. Validación completa: `uv run python scripts/validate.py` y `uv run python scripts/check_wheel.py`.
5. Revisión: subagentes listados y skill `moana-code-review`; corregir hallazgos críticos y altos.
6. Si hay salida raster: mostrar el PNG a 1x y ampliado por vecino más cercano; si cambia un golden, presentar expected/actual/diff y justificar.

### 8. Cierre

1. En `docs/issues/catalog.json`, para este issue: `status` → `review` (o `done` tras aprobación); completar `acceptance_evidence` (AC1, AC2), `test_evidence` (T1, T2) y `evidence` con rutas concretas de tests y archivos.
2. Issues que desbloquea ([MOANA-027](MOANA-027.md), [MOANA-033](MOANA-033.md)): si todas sus dependencias quedan `done`, pasarlos a `ready` con `blocking_reason: null`.
3. Ejecutar `uv run python scripts/planning.py` y `uv run python -m scripts.check_repository`.
4. Abrir PR hacia `develop` enlazando este issue de GitHub (`Closes #<número>`), con comandos ejecutados y evidencia por AC/T. El CI completo corre al integrar `develop` en `main`.
5. Commit y push sólo con autorización del usuario. No declarar CI remoto ni aprobación artística humana sin evidencia.

### 9. Prohibido en este issue

- Implementar alcance de otros issues, incluidos los que desbloquea ([MOANA-027](MOANA-027.md), [MOANA-033](MOANA-033.md)).
- Actualizar goldens automáticamente, desactivar checks, editar `uv.lock` a mano o añadir dependencias sin motivo técnico registrado.
- `eval`/`exec`/`pickle`, red o estado global mutable en el núcleo; lecturas de texto sin `encoding="utf-8"`.

## Evidence

Pendiente de implementación.
