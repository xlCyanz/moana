# MOANA-024 — Exportar GIF con política de pérdidas

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-024
- Aliases históricos: MOA-024
- Phase: P4
- Priority: P1
- Status: ready
- Complexity: L (relativa, no estimación de tiempo)
- Dependencies: [MOANA-022](MOANA-022.md), [MOANA-005](MOANA-005.md), [MOANA-011](MOANA-011.md)
- Related modules: export, animation
- Requirements: R023 ([trazabilidad](traceability.md))
- Bloqueo: Ninguno

## Context

GIF no representa alfa parcial, colores arbitrarios ni todos los tiempos.

## Objective

Exportar una timeline equivalente con pérdidas explícitas y controladas.

## Scope

Implementar GIF con paleta compartida, transparencia, disposal y duración efectiva declarada.

## Out of scope

No cuantización silenciosa ni equiparar GIF al maestro RGBA.

## Technical requirements

- <=256 índices, reserva de transparencia y rechazo de alfa intermedio sin background explícito
- Duración múltiplo de 10 ms o redondeo solicitado; comprobar timeline tras decode

## Proposed implementation

- Preparar paleta compartida/reserva transparente y política de duración
- Codificar frames/disposal y reconstruir timeline decodificada

## Acceptance criteria

- [ ] AC1: Frames decodificados/composited y tiempos son equivalentes al objetivo bajo las opciones elegidas
- [ ] AC2: Colores o tiempos no representables generan error o informe de pérdida explícitamente aceptada

## Required tests

- [ ] T1: Paleta llena, 255 colores más transparente, alpha intermedio y disposal
- [ ] T2: Frames duplicados fusionados, loop, duraciones cortas y decode acumulado en Pillow

## Expected deliverables

- Exportador GIF con política explícita de pérdidas, paleta y duración efectiva.
- Pruebas de timeline decodificado, transparencia, límites y rechazos sin pérdida autorizada.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- Los encoders pueden fusionar frames idénticos; comparar tiempo/imagen, no sólo count.

## Guía para agentes de IA

**Estado para agentes:** Listo: todas las dependencias están `done`; puede empezarse.

### 1. Preparación

- Rama: `feat/MOANA-024-exportar-gif-politica` creada desde `develop` actualizado: `git switch develop && git pull --ff-only && git switch -c feat/MOANA-024-exportar-gif-politica`.
- Verificar en `docs/issues/catalog.json` que este issue está `ready` y que sus dependencias ([MOANA-022](MOANA-022.md), [MOANA-005](MOANA-005.md), [MOANA-011](MOANA-011.md)) están `done`.
- Entorno: `uv sync --locked` (sin uv global: `sh scripts/bootstrap.sh` y después `sh scripts/uv.sh` en lugar de `uv`).
- Al empezar, cambiar `status` a `in_progress` en el catálogo y regenerar con `uv run python scripts/planning.py`.

### 2. Lectura obligatoria (en orden)

1. `CLAUDE.md` (Claude Code) o `AGENTS.md` (Codex) y [flujo de sesión](../guides/agent-workflow.md).
2. MOANA.md: §3 Arquitectura modular; §18 Exportación PNG, GIF y formatos adicionales; §25 Definition of Done. Estas secciones son el contrato normativo; ante duda, prevalecen sobre este issue.
3. [Contratos de módulos](../architecture/module-contracts.md) para: `export`, `animation`.
4. Estándares: [python](../../docs/standards/python.md), [architecture](../../docs/standards/architecture.md), [testing](../../docs/standards/testing.md), [pixel-art](../../docs/standards/pixel-art.md).
5. Issues de dependencia ([MOANA-022](MOANA-022.md), [MOANA-005](MOANA-005.md), [MOANA-011](MOANA-011.md)): leer su sección Evidence para conocer las APIs ya entregadas; no reimplementarlas.
6. ADR en `docs/architecture/` que mencionen los módulos afectados.

### 3. Requisitos de MOANA.md cubiertos

| ID | Requisito | Secciones | Verificación exigida |
| --- | --- | --- | --- |
| R023 | Exportación GIF | §18 | Timeline/disposal y pérdidas explícitas |

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

- T1: Paleta llena, 255 colores más transparente, alpha intermedio y disposal
- T2: Frames duplicados fusionados, loop, duraciones cortas y decode acumulado en Pillow
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
