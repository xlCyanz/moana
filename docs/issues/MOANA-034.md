# MOANA-034 — Añadir ejemplos de tiles y escenarios modulares

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-034
- Aliases históricos: MOA-034
- Phase: P5
- Priority: P2
- Status: blocked
- Complexity: M (relativa, no estimación de tiempo)
- Dependencies: [MOANA-008](MOANA-008.md), [MOANA-016](MOANA-016.md), [MOANA-020](MOANA-020.md), [MOANA-023](MOANA-023.md)
- Related modules: examples, geometry
- Requirements: R037, R005 ([trazabilidad](traceability.md))
- Bloqueo: Dependencias pendientes: MOANA-016, MOANA-020, MOANA-023

## Context

Tiles y escenarios requieren continuidad entre elementos y edición por identidad.

## Objective

Componer escenas/props y tiles con paleta compartida sin costuras.

## Scope

Crear composiciones de tiles/props/escena con origen de patrón común, IDs semánticos y paleta compartida.

## Out of scope

No editor de mapas, física ni sistema de juego.

## Technical requirements

- Instanciar geometría existente sin crear motor de mapas separado
- Definir grid, pivotes, bordes y licencia/procedencia; asegurar textura periódica en costuras

## Proposed implementation

- Usar operaciones/transformaciones existentes con grid/origen de patrón común
- Exportar atlas y reconstruir escena para comparar píxeles

## Acceptance criteria

- [ ] AC1: Un tile repetible no presenta costuras y una escena mantiene paleta e IDs editables
- [ ] AC2: Exportar atlas y reconstruir composición reproduce los píxeles originales

## Required tests

- [ ] T1: Costuras horizontal/vertical, espejos y traslación por múltiplos de tile
- [ ] T2: Editar un prop por ID y verificar regiones; inspección de legibilidad a escala nativa

## Expected deliverables

- Ejemplos editables de tiles y escenarios modulares con composición documentada.
- Pruebas de uniones, repetibilidad, procedencia y previews de ensamblaje.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- Repetición horizontal/vertical necesita fixtures de costura y revisión a escala nativa.

## Guía para agentes de IA

**Estado para agentes:** No empezar: estado `blocked`. Esperar a que [MOANA-008](MOANA-008.md), [MOANA-016](MOANA-016.md), [MOANA-020](MOANA-020.md), [MOANA-023](MOANA-023.md) estén `done` y el catálogo marque este issue `ready`.

### 1. Preparación

- Rama: `feat/MOANA-034-anadir-ejemplos-tiles` creada desde `develop` actualizado: `git switch develop && git pull --ff-only && git switch -c feat/MOANA-034-anadir-ejemplos-tiles`.
- Verificar en `docs/issues/catalog.json` que este issue está `ready` y que sus dependencias ([MOANA-008](MOANA-008.md), [MOANA-016](MOANA-016.md), [MOANA-020](MOANA-020.md), [MOANA-023](MOANA-023.md)) están `done`.
- Entorno: `uv sync --locked` (sin uv global: `sh scripts/bootstrap.sh` y después `sh scripts/uv.sh` en lugar de `uv`).
- Al empezar, cambiar `status` a `in_progress` en el catálogo y regenerar con `uv run python scripts/planning.py`.

### 2. Lectura obligatoria (en orden)

1. `CLAUDE.md` (Claude Code) o `AGENTS.md` (Codex) y [flujo de sesión](../guides/agent-workflow.md).
2. MOANA.md: §2 Alcance funcional y no funcional; §3 Arquitectura modular; §7 Técnicas profesionales de Pixel Art; §19 Control de calidad gráfico; §25 Definition of Done. Estas secciones son el contrato normativo; ante duda, prevalecen sobre este issue.
3. [Contratos de módulos](../architecture/module-contracts.md) para: `examples`, `geometry`.
4. Estándares: [pixel-art](../../docs/standards/pixel-art.md), [python](../../docs/standards/python.md), [architecture](../../docs/standards/architecture.md), [testing](../../docs/standards/testing.md).
5. Issues de dependencia ([MOANA-008](MOANA-008.md), [MOANA-016](MOANA-016.md), [MOANA-020](MOANA-020.md), [MOANA-023](MOANA-023.md)): leer su sección Evidence para conocer las APIs ya entregadas; no reimplementarlas.
6. ADR en `docs/architecture/` que mencionen los módulos afectados.

### 3. Requisitos de MOANA.md cubiertos

| ID | Requisito | Secciones | Verificación exigida |
| --- | --- | --- | --- |
| R037 | Objetos, tiles y escenarios | §2, §7 | Ejemplos editables y costuras verificadas |
| R005 | Técnicas profesionales y calidad artística | §7, §19 | Corpus editable y rúbrica humana documentada |

### 4. Skills y subagentes

| Host | Skills a cargar | Revisión especializada |
| --- | --- | --- |
| Claude Code | `moana-pixel-art`, `moana-graphics`, `moana-code-review` | `moana-pixel-artist`, `moana-documentation`, `moana-graphics-engineer`, `moana-python-engineer` (sólo lectura; el agente principal integra) |
| Codex | `$moana-pixel-art`, `$moana-graphics`, `$moana-code-review` | `moana_pixel_artist`, `moana_documentation`, `moana_graphics_engineer`, `moana_python_engineer` |

### 5. Archivos

- Código o documentos a crear/modificar: `examples/`, `src/moana/geometry/`.
- Pruebas: `tests/integration/`, `tests/unit/geometry/`.
- No crear módulos ni carpetas sin comportamiento real. No tocar otros módulos salvo exportaciones imprescindibles, justificadas en el PR.

### 6. Plan de pruebas

- T1: Costuras horizontal/vertical, espejos y traslación por múltiplos de tile
- T2: Editar un prop por ID y verificar regiones; inspección de legibilidad a escala nativa
- Oráculos independientes (cálculo a mano o fórmula de MOANA.md); nunca copiar la salida de la implementación como expected.
- Incluir casos negativos con el error de dominio esperado y casos borde (vacío, mínimo, máximo, fuera de rango).

### 7. Procedimiento

1. Escribir las pruebas de los criterios AC y T antes o junto con la implementación.
2. Implementar sólo **Scope**; respetar **Out of scope** y las dependencias permitidas de MOANA.md §3.
3. Validación de módulo: `uv run pytest tests/integration/ tests/unit/geometry/ -q` y `uv run mypy src/`.
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
