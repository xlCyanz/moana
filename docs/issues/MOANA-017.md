# MOANA-017 — Crear presets de materiales versionados

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-017
- Aliases históricos: MOA-017
- Phase: P3
- Priority: P1
- Status: blocked
- Complexity: L (relativa, no estimación de tiempo)
- Dependencies: [MOANA-014](MOANA-014.md), [MOANA-015](MOANA-015.md), [MOANA-016](MOANA-016.md)
- Related modules: techniques, schema
- Requirements: R010, R005 ([trazabilidad](traceability.md))
- Bloqueo: Dependencias pendientes: MOANA-015

## Context

Un material repetible debe exponer parámetros y conservar paleta/IDs.

## Objective

Entregar cinco recetas de material editables con versión y procedencia.

## Scope

Crear presets editables de piel, tela, metal, madera y piedra definidos por rampas, bandas y patrones.

## Out of scope

No afirmar calidad profesional sólo por aprobar fixtures ni usar assets sin licencia.

## Technical requirements

- Semilla por operación/coordenada según §14; ningún shader ejecutable en JSON
- Parámetros con rango, fuente, versión y recetas reproducibles; registrar procedencia de ejemplos

## Proposed implementation

- Definir presets como composición de bandas, ramps y patrones existentes
- Añadir controles de rango, semillas y ejemplos propios por material

## Acceptance criteria

- [ ] AC1: Cada material puede editarse sin perder IDs ni introducir colores fuera del perfil
- [ ] AC2: Misma semilla genera igual textura y una operación nueva no altera material existente

## Required tests

- [ ] T1: Fixtures pequeñas por material con máscara y límites de densidad/escala
- [ ] T2: Pruebas de estabilidad entre frames y revisión visual a 1×/4× documentada como humana o pendiente

## Expected deliverables

- Presets de materiales versionados con parámetros y semilla local explícitos.
- Ejemplos editables, fixtures de repetibilidad y límites de cada material.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- Una receta reproducible puede seguir siendo visualmente mala; separar evaluación humana.

## Guía para agentes de IA

**Estado para agentes:** No empezar: estado `blocked`. Esperar a que [MOANA-014](MOANA-014.md), [MOANA-015](MOANA-015.md), [MOANA-016](MOANA-016.md) estén `done` y el catálogo marque este issue `ready`.

### 1. Preparación

- Rama: `feat/MOANA-017-crear-presets-materiales` creada desde `develop` actualizado: `git switch develop && git pull --ff-only && git switch -c feat/MOANA-017-crear-presets-materiales`.
- Verificar en `docs/issues/catalog.json` que este issue está `ready` y que sus dependencias ([MOANA-014](MOANA-014.md), [MOANA-015](MOANA-015.md), [MOANA-016](MOANA-016.md)) están `done`.
- Entorno: `uv sync --locked` (sin uv global: `sh scripts/bootstrap.sh` y después `sh scripts/uv.sh` en lugar de `uv`).
- Al empezar, cambiar `status` a `in_progress` en el catálogo y regenerar con `uv run python scripts/planning.py`.

### 2. Lectura obligatoria (en orden)

1. `CLAUDE.md` (Claude Code) o `AGENTS.md` (Codex) y [flujo de sesión](../guides/agent-workflow.md).
2. MOANA.md: §3 Arquitectura modular; §7 Técnicas profesionales de Pixel Art; §10 Sombreado, dithering y materiales; §19 Control de calidad gráfico; §25 Definition of Done. Estas secciones son el contrato normativo; ante duda, prevalecen sobre este issue.
3. [Contratos de módulos](../architecture/module-contracts.md) para: `techniques`, `schema`.
4. Estándares: [python](../../docs/standards/python.md), [architecture](../../docs/standards/architecture.md), [testing](../../docs/standards/testing.md), [pixel-art](../../docs/standards/pixel-art.md), [security](../../docs/standards/security.md).
5. Issues de dependencia ([MOANA-014](MOANA-014.md), [MOANA-015](MOANA-015.md), [MOANA-016](MOANA-016.md)): leer su sección Evidence para conocer las APIs ya entregadas; no reimplementarlas.
6. ADR en `docs/architecture/` que mencionen los módulos afectados.

### 3. Requisitos de MOANA.md cubiertos

| ID | Requisito | Secciones | Verificación exigida |
| --- | --- | --- | --- |
| R010 | Materiales editables y reproducibles | §10 | Fixtures de cinco materiales y semillas |
| R005 | Técnicas profesionales y calidad artística | §7, §19 | Corpus editable y rúbrica humana documentada |

### 4. Skills y subagentes

| Host | Skills a cargar | Revisión especializada |
| --- | --- | --- |
| Claude Code | `moana-graphics`, `moana-pixel-art`, `moana-python`, `moana-architecture`, `moana-code-review` | `moana-graphics-engineer`, `moana-pixel-artist`, `moana-python-engineer`, `moana-architect` (sólo lectura; el agente principal integra) |
| Codex | `$moana-graphics`, `$moana-pixel-art`, `$moana-python`, `$moana-architecture`, `$moana-code-review` | `moana_graphics_engineer`, `moana_pixel_artist`, `moana_python_engineer`, `moana_architect` |

### 5. Archivos

- Código o documentos a crear/modificar: `src/moana/techniques/`, `src/moana/schema/`.
- Pruebas: `tests/unit/techniques/`, `tests/unit/schema/`.
- No crear módulos ni carpetas sin comportamiento real. No tocar otros módulos salvo exportaciones imprescindibles, justificadas en el PR.

### 6. Plan de pruebas

- T1: Fixtures pequeñas por material con máscara y límites de densidad/escala
- T2: Pruebas de estabilidad entre frames y revisión visual a 1×/4× documentada como humana o pendiente
- Oráculos independientes (cálculo a mano o fórmula de MOANA.md); nunca copiar la salida de la implementación como expected.
- Incluir casos negativos con el error de dominio esperado y casos borde (vacío, mínimo, máximo, fuera de rango).

### 7. Procedimiento

1. Escribir las pruebas de los criterios AC y T antes o junto con la implementación.
2. Implementar sólo **Scope**; respetar **Out of scope** y las dependencias permitidas de MOANA.md §3.
3. Validación de módulo: `uv run pytest tests/unit/techniques/ tests/unit/schema/ -q` y `uv run mypy src/`.
4. Validación completa: `uv run python scripts/validate.py` y `uv run python scripts/check_wheel.py`.
5. Revisión: subagentes listados y skill `moana-code-review`; corregir hallazgos críticos y altos.
6. Si hay salida raster: mostrar el PNG a 1x y ampliado por vecino más cercano; si cambia un golden, presentar expected/actual/diff y justificar.

### 8. Cierre

1. En `docs/issues/catalog.json`, para este issue: `status` → `review` (o `done` tras aprobación); completar `acceptance_evidence` (AC1, AC2), `test_evidence` (T1, T2) y `evidence` con rutas concretas de tests y archivos.
2. Issues que desbloquea ([MOANA-027](MOANA-027.md)): si todas sus dependencias quedan `done`, pasarlos a `ready` con `blocking_reason: null`.
3. Ejecutar `uv run python scripts/planning.py` y `uv run python -m scripts.check_repository`.
4. Abrir PR hacia `develop` enlazando este issue de GitHub (`Closes #<número>`), con comandos ejecutados y evidencia por AC/T. El CI completo corre al integrar `develop` en `main`.
5. Commit y push sólo con autorización del usuario. No declarar CI remoto ni aprobación artística humana sin evidencia.

### 9. Prohibido en este issue

- Implementar alcance de otros issues, incluidos los que desbloquea ([MOANA-027](MOANA-027.md)).
- Actualizar goldens automáticamente, desactivar checks, editar `uv.lock` a mano o añadir dependencias sin motivo técnico registrado.
- `eval`/`exec`/`pickle`, red o estado global mutable en el núcleo; lecturas de texto sin `encoding="utf-8"`.

## Evidence

Pendiente de implementación.
