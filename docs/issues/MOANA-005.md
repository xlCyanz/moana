# MOANA-005 — Implementar paletas y rampas

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-005
- Aliases históricos: MOA-005
- Phase: P1
- Priority: P1
- Status: blocked
- Complexity: M (relativa, no estimación de tiempo)
- Dependencies: [MOANA-001](MOANA-001.md), [MOANA-002](MOANA-002.md)
- Related modules: palette, schema
- Requirements: R007 ([trazabilidad](traceability.md))
- Bloqueo: Dependencias pendientes: MOANA-001, MOANA-002

## Context

Una paleta por referencia permite recolor coherente y edición local intencional.

## Objective

Mantener colores y rampas con IDs estables y perfiles explícitos.

## Scope

Crear moana/palette con IDs de color, canonicalización RGBA, ramps y validación de perfiles strict/rgba.

## Out of scope

No cuantización automática ni iluminación.

## Technical requirements

- Referencias por ID y formato canónico #RRGGBBAA; orden explícito de ramps
- Validar alfa y cardinalidad por perfil; cambios de color no renumeran consumidores

## Proposed implementation

- Crear índice de IDs y canonicalización RGBA
- Validar rampas/perfiles y separar advertencias de luminancia de rechazos

## Acceptance criteria

- [ ] AC1: Paleta strict rechaza alfa intermedio y referencias de rampa inexistentes
- [ ] AC2: Serializar y cargar preserva orden, valores e identidad; advertencia de luminancia no bloquea estilos válidos

## Required tests

- [ ] T1: Casos de colores duplicados por valor pero IDs diferentes y IDs duplicados inválidos
- [ ] T2: Pruebas de límites 256/4096, transparencia y remapeo explícito sin colores ocultos

## Expected deliverables

- Modelos y resolución de paletas/rampas por ID, con remapeo explícito.
- Fixtures de cardinalidad, perfil de color, referencias y estabilidad de índices.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- La transparencia normalizada puede cambiar RGB residual; definirla antes de comparar pertenencia.

## Guía para agentes de IA

**Estado para agentes:** No empezar: estado `blocked`. Esperar a que [MOANA-001](MOANA-001.md), [MOANA-002](MOANA-002.md) estén `done` y el catálogo marque este issue `ready`.

### 1. Preparación

- Rama: `feat/MOANA-005-implementar-paletas-rampas` creada desde `develop` actualizado: `git switch develop && git pull --ff-only && git switch -c feat/MOANA-005-implementar-paletas-rampas`.
- Verificar en `docs/issues/catalog.json` que este issue está `ready` y que sus dependencias ([MOANA-001](MOANA-001.md), [MOANA-002](MOANA-002.md)) están `done`.
- Entorno: `uv sync --locked` (sin uv global: `sh scripts/bootstrap.sh` y después `sh scripts/uv.sh` en lugar de `uv`).
- Al empezar, cambiar `status` a `in_progress` en el catálogo y regenerar con `uv run python scripts/planning.py`.

### 2. Lectura obligatoria (en orden)

1. `CLAUDE.md` (Claude Code) o `AGENTS.md` (Codex) y [flujo de sesión](../guides/agent-workflow.md).
2. MOANA.md: §3 Arquitectura modular; §9 Paletas, color e iluminación; §25 Definition of Done. Estas secciones son el contrato normativo; ante duda, prevalecen sobre este issue.
3. [Contratos de módulos](../architecture/module-contracts.md) para: `palette`, `schema`.
4. Estándares: [python](../../docs/standards/python.md), [architecture](../../docs/standards/architecture.md), [testing](../../docs/standards/testing.md), [pixel-art](../../docs/standards/pixel-art.md), [security](../../docs/standards/security.md).
5. Issues de dependencia ([MOANA-001](MOANA-001.md), [MOANA-002](MOANA-002.md)): leer su sección Evidence para conocer las APIs ya entregadas; no reimplementarlas.
6. ADR en `docs/architecture/` que mencionen los módulos afectados.

### 3. Requisitos de MOANA.md cubiertos

| ID | Requisito | Secciones | Verificación exigida |
| --- | --- | --- | --- |
| R007 | Paletas, ramps y perfiles de color | §9 | Referencias, cardinalidad y conservación de colores |

### 4. Skills y subagentes

| Host | Skills a cargar | Revisión especializada |
| --- | --- | --- |
| Claude Code | `moana-python`, `moana-pixel-art`, `moana-architecture`, `moana-code-review` | `moana-python-engineer`, `moana-pixel-artist`, `moana-architect` (sólo lectura; el agente principal integra) |
| Codex | `$moana-python`, `$moana-pixel-art`, `$moana-architecture`, `$moana-code-review` | `moana_python_engineer`, `moana_pixel_artist`, `moana_architect` |

### 5. Archivos

- Código o documentos a crear/modificar: `src/moana/palette/`, `src/moana/schema/`.
- Pruebas: `tests/unit/palette/`, `tests/unit/schema/`.
- No crear módulos ni carpetas sin comportamiento real. No tocar otros módulos salvo exportaciones imprescindibles, justificadas en el PR.

### 6. Plan de pruebas

- T1: Casos de colores duplicados por valor pero IDs diferentes y IDs duplicados inválidos
- T2: Pruebas de límites 256/4096, transparencia y remapeo explícito sin colores ocultos
- Oráculos independientes (cálculo a mano o fórmula de MOANA.md); nunca copiar la salida de la implementación como expected.
- Incluir casos negativos con el error de dominio esperado y casos borde (vacío, mínimo, máximo, fuera de rango).

### 7. Procedimiento

1. Escribir las pruebas de los criterios AC y T antes o junto con la implementación.
2. Implementar sólo **Scope**; respetar **Out of scope** y las dependencias permitidas de MOANA.md §3.
3. Validación de módulo: `uv run pytest tests/unit/palette/ tests/unit/schema/ -q` y `uv run mypy src/`.
4. Validación completa: `uv run python scripts/validate.py` y `uv run python scripts/check_wheel.py`.
5. Revisión: subagentes listados y skill `moana-code-review`; corregir hallazgos críticos y altos.
6. Si hay salida raster: mostrar el PNG a 1x y ampliado por vecino más cercano; si cambia un golden, presentar expected/actual/diff y justificar.

### 8. Cierre

1. En `docs/issues/catalog.json`, para este issue: `status` → `review` (o `done` tras aprobación); completar `acceptance_evidence` (AC1, AC2), `test_evidence` (T1, T2) y `evidence` con rutas concretas de tests y archivos.
2. Issues que desbloquea ([MOANA-006](MOANA-006.md), [MOANA-009](MOANA-009.md), [MOANA-014](MOANA-014.md), [MOANA-015](MOANA-015.md), [MOANA-016](MOANA-016.md), [MOANA-024](MOANA-024.md)): si todas sus dependencias quedan `done`, pasarlos a `ready` con `blocking_reason: null`.
3. Ejecutar `uv run python scripts/planning.py` y `uv run python -m scripts.check_repository`.
4. Abrir PR hacia `develop` enlazando este issue de GitHub (`Closes #<número>`), con comandos ejecutados y evidencia por AC/T. El CI completo corre al integrar `develop` en `main`.
5. Commit y push sólo con autorización del usuario. No declarar CI remoto ni aprobación artística humana sin evidencia.

### 9. Prohibido en este issue

- Implementar alcance de otros issues, incluidos los que desbloquea ([MOANA-006](MOANA-006.md), [MOANA-009](MOANA-009.md), [MOANA-014](MOANA-014.md), [MOANA-015](MOANA-015.md), [MOANA-016](MOANA-016.md), [MOANA-024](MOANA-024.md)).
- Actualizar goldens automáticamente, desactivar checks, editar `uv.lock` a mano o añadir dependencias sin motivo técnico registrado.
- `eval`/`exec`/`pickle`, red o estado global mutable en el núcleo; lecturas de texto sin `encoding="utf-8"`.

## Evidence

Pendiente de implementación.
