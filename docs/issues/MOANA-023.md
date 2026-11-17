# MOANA-023 — Exportar spritesheets y manifest reversible

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-023
- Aliases históricos: MOA-023
- Phase: P4
- Priority: P1
- Status: blocked
- Complexity: M (relativa, no estimación de tiempo)
- Dependencies: [MOANA-022](MOANA-022.md), [MOANA-011](MOANA-011.md)
- Related modules: export, animation
- Requirements: R021 ([trazabilidad](traceability.md))
- Bloqueo: Dependencias pendientes: MOANA-022, MOANA-011

## Context

Un atlas sin manifest íntegro pierde pivotes, duración o tamaño fuente.

## Objective

Exportar un grid reversible que reconstruya exactamente sus frames.

## Scope

Crear atlas grid con margen/padding, manifiesto de frames, pivotes y tiempos; reconstrucción comprobable.

## Out of scope

No packing heurístico compacto hasta tener contrato de desempate independiente.

## Technical requirements

- Orden de frames estable, sin rotación/trim implícito y dimensiones presupuestadas
- Manifest versionado con rect, source_size, trim_offset, duration y digest

## Proposed implementation

- Calcular layout desde columnas/margen/padding y presupuesto
- Serializar manifest versionado y verificar recortes contra originales

## Acceptance criteria

- [ ] AC1: Recortar atlas por manifest reconstruye RGBA exacto de cada frame
- [ ] AC2: Export idéntico con misma configuración y ningún frame solapa padding o sale del sheet

## Required tests

- [ ] T1: Columnas 1/N, último renglón incompleto, margen/padding y canvas no cuadrado
- [ ] T2: Atlas excesivo, manifest corrupto y roundtrip recortes/tiempos

## Expected deliverables

- Exportador de spritesheets y manifiesto reversible con pivotes/duraciones.
- Reconstrucción exacta de frames desde atlas y pruebas de packing/límites.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- Confundir rect xywh con bbox semiabierta causa offsets; especificar ambos claramente.

## Guía para agentes de IA

**Estado para agentes:** No empezar: estado `blocked`. Esperar a que [MOANA-022](MOANA-022.md), [MOANA-011](MOANA-011.md) estén `done` y el catálogo marque este issue `ready`.

### 1. Preparación

- Rama: `feat/MOANA-023-exportar-spritesheets-manifest` creada desde `develop` actualizado: `git switch develop && git pull --ff-only && git switch -c feat/MOANA-023-exportar-spritesheets-manifest`.
- Verificar en `docs/issues/catalog.json` que este issue está `ready` y que sus dependencias ([MOANA-022](MOANA-022.md), [MOANA-011](MOANA-011.md)) están `done`.
- Entorno: `uv sync --locked` (sin uv global: `sh scripts/bootstrap.sh` y después `sh scripts/uv.sh` en lugar de `uv`).
- Al empezar, cambiar `status` a `in_progress` en el catálogo y regenerar con `uv run python scripts/planning.py`.

### 2. Lectura obligatoria (en orden)

1. `CLAUDE.md` (Claude Code) o `AGENTS.md` (Codex) y [flujo de sesión](../guides/agent-workflow.md).
2. MOANA.md: §3 Arquitectura modular; §17 Animaciones y spritesheets; §25 Definition of Done. Estas secciones son el contrato normativo; ante duda, prevalecen sobre este issue.
3. [Contratos de módulos](../architecture/module-contracts.md) para: `export`, `animation`.
4. Estándares: [python](../../docs/standards/python.md), [architecture](../../docs/standards/architecture.md), [testing](../../docs/standards/testing.md), [pixel-art](../../docs/standards/pixel-art.md).
5. Issues de dependencia ([MOANA-022](MOANA-022.md), [MOANA-011](MOANA-011.md)): leer su sección Evidence para conocer las APIs ya entregadas; no reimplementarlas.
6. ADR en `docs/architecture/` que mencionen los módulos afectados.

### 3. Requisitos de MOANA.md cubiertos

| ID | Requisito | Secciones | Verificación exigida |
| --- | --- | --- | --- |
| R021 | Spritesheets y manifest | §17 | Reconstrucción exacta de cada frame |

### 4. Skills y subagentes

| Host | Skills a cargar | Revisión especializada |
| --- | --- | --- |
| Claude Code | `moana-graphics`, `moana-python`, `moana-pixel-art`, `moana-code-review` | `moana-graphics-engineer`, `moana-python-engineer`, `moana-pixel-artist` (sólo lectura; el agente principal integra) |
| Codex | `$moana-graphics`, `$moana-python`, `$moana-pixel-art`, `$moana-code-review` | `moana_graphics_engineer`, `moana_python_engineer`, `moana_pixel_artist` |

### 5. Archivos

- Código o documentos a crear/modificar: `src/moana/export/`, `src/moana/animation/`.
- Pruebas: `tests/unit/export/`, `tests/unit/animation/`.
- No crear módulos ni carpetas sin comportamiento real. No tocar otros módulos salvo exportaciones imprescindibles, justificadas en el PR.

### 6. Plan de pruebas

- T1: Columnas 1/N, último renglón incompleto, margen/padding y canvas no cuadrado
- T2: Atlas excesivo, manifest corrupto y roundtrip recortes/tiempos
- Oráculos independientes (cálculo a mano o fórmula de MOANA.md); nunca copiar la salida de la implementación como expected.
- Incluir casos negativos con el error de dominio esperado y casos borde (vacío, mínimo, máximo, fuera de rango).

### 7. Procedimiento

1. Escribir las pruebas de los criterios AC y T antes o junto con la implementación.
2. Implementar sólo **Scope**; respetar **Out of scope** y las dependencias permitidas de MOANA.md §3.
3. Validación de módulo: `uv run pytest tests/unit/export/ tests/unit/animation/ -q` y `uv run mypy src/`.
4. Validación completa: `uv run python scripts/validate.py` y `uv run python scripts/check_wheel.py`.
5. Revisión: subagentes listados y skill `moana-code-review`; corregir hallazgos críticos y altos.
6. Si hay salida raster: mostrar el PNG a 1x y ampliado por vecino más cercano; si cambia un golden, presentar expected/actual/diff y justificar.

### 8. Cierre

1. En `docs/issues/catalog.json`, para este issue: `status` → `review` (o `done` tras aprobación); completar `acceptance_evidence` (AC1, AC2), `test_evidence` (T1, T2) y `evidence` con rutas concretas de tests y archivos.
2. Issues que desbloquea ([MOANA-034](MOANA-034.md), [MOANA-035](MOANA-035.md)): si todas sus dependencias quedan `done`, pasarlos a `ready` con `blocking_reason: null`.
3. Ejecutar `uv run python scripts/planning.py` y `uv run python -m scripts.check_repository`.
4. Abrir PR hacia `develop` enlazando este issue de GitHub (`Closes #<número>`), con comandos ejecutados y evidencia por AC/T. El CI completo corre al integrar `develop` en `main`.
5. Commit y push sólo con autorización del usuario. No declarar CI remoto ni aprobación artística humana sin evidencia.

### 9. Prohibido en este issue

- Implementar alcance de otros issues, incluidos los que desbloquea ([MOANA-034](MOANA-034.md), [MOANA-035](MOANA-035.md)).
- Actualizar goldens automáticamente, desactivar checks, editar `uv.lock` a mano o añadir dependencias sin motivo técnico registrado.
- `eval`/`exec`/`pickle`, red o estado global mutable en el núcleo; lecturas de texto sin `encoding="utf-8"`.

## Evidence

Pendiente de implementación.
