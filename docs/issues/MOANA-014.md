# MOANA-014 — Crear contornos y análisis de clusters

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-014
- Aliases históricos: MOA-014
- Phase: P3
- Priority: P1
- Status: blocked
- Complexity: L (relativa, no estimación de tiempo)
- Dependencies: [MOANA-013](MOANA-013.md), [MOANA-005](MOANA-005.md)
- Related modules: techniques, quality
- Requirements: R006, R025 ([trazabilidad](traceability.md))
- Bloqueo: Dependencias pendientes: MOANA-013, MOANA-005

## Context

Los contornos y clusters deben admitir excepciones artísticas locales.

## Objective

Generar outlines editables y diagnósticos de componentes sin limpieza automática.

## Scope

Implementar morfología binaria para outlines y análisis conectado de clusters con salida editable y diagnósticos.

## Out of scope

No clasificar intención artística como error matemático ni borrar detalles automáticamente.

## Technical requirements

- Vecindad Chebyshev para contornos y conectividad 4/8 explícita para clusters
- Advertencias por singleton y escalones con supresión por región; no limpieza destructiva automática

## Proposed implementation

- Implementar dilatación/erosión acotada y análisis 4/8 conectado
- Representar resultado como operaciones y advertencias con bbox/región

## Acceptance criteria

- [ ] AC1: Contornos internos/externos respetan ancho, huecos y clipping
- [ ] AC2: Un brillo aislado puede conservarse mediante excepción; el análisis no cambia el documento

## Required tests

- [ ] T1: Máscaras con huecos, contactos de esquina, diagonal y borde de canvas
- [ ] T2: Componentes conocidos, outline de ancho 1/2 y operación editable que reproduce la máscara

## Expected deliverables

- Operaciones de contorno y análisis de clusters con conectividad explícita.
- Máscaras de referencia para bordes/huecos/diagonales y ejemplos ampliados.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- No eliminar ojos o partículas por ser singletons; las métricas no inferirán intención.

## Guía para agentes de IA

**Estado para agentes:** No empezar: estado `blocked`. Esperar a que [MOANA-013](MOANA-013.md), [MOANA-005](MOANA-005.md) estén `done` y el catálogo marque este issue `ready`.

### 1. Preparación

- Rama: `feat/MOANA-014-crear-contornos-analisis` creada desde `develop` actualizado: `git switch develop && git pull --ff-only && git switch -c feat/MOANA-014-crear-contornos-analisis`.
- Verificar en `docs/issues/catalog.json` que este issue está `ready` y que sus dependencias ([MOANA-013](MOANA-013.md), [MOANA-005](MOANA-005.md)) están `done`.
- Entorno: `uv sync --locked` (sin uv global: `sh scripts/bootstrap.sh` y después `sh scripts/uv.sh` en lugar de `uv`).
- Al empezar, cambiar `status` a `in_progress` en el catálogo y regenerar con `uv run python scripts/planning.py`.

### 2. Lectura obligatoria (en orden)

1. `CLAUDE.md` (Claude Code) o `AGENTS.md` (Codex) y [flujo de sesión](../guides/agent-workflow.md).
2. MOANA.md: §3 Arquitectura modular; §8 Siluetas, contornos y pixel clusters; §19 Control de calidad gráfico; §25 Definition of Done. Estas secciones son el contrato normativo; ante duda, prevalecen sobre este issue.
3. [Contratos de módulos](../architecture/module-contracts.md) para: `techniques`, `quality`.
4. Estándares: [python](../../docs/standards/python.md), [architecture](../../docs/standards/architecture.md), [testing](../../docs/standards/testing.md), [pixel-art](../../docs/standards/pixel-art.md).
5. Issues de dependencia ([MOANA-013](MOANA-013.md), [MOANA-005](MOANA-005.md)): leer su sección Evidence para conocer las APIs ya entregadas; no reimplementarlas.
6. ADR en `docs/architecture/` que mencionen los módulos afectados.

### 3. Requisitos de MOANA.md cubiertos

| ID | Requisito | Secciones | Verificación exigida |
| --- | --- | --- | --- |
| R006 | Siluetas, contornos y clusters | §8 | Morfología y componentes conocidos |
| R025 | Evaluación gráfica y diagnósticos | §19 | Hard/soft checks, bbox y supresiones |

### 4. Skills y subagentes

| Host | Skills a cargar | Revisión especializada |
| --- | --- | --- |
| Claude Code | `moana-graphics`, `moana-pixel-art`, `moana-testing`, `moana-code-review` | `moana-graphics-engineer`, `moana-pixel-artist`, `moana-qa-engineer` (sólo lectura; el agente principal integra) |
| Codex | `$moana-graphics`, `$moana-pixel-art`, `$moana-testing`, `$moana-code-review` | `moana_graphics_engineer`, `moana_pixel_artist`, `moana_qa_engineer` |

### 5. Archivos

- Código o documentos a crear/modificar: `src/moana/techniques/`, `src/moana/quality/`.
- Pruebas: `tests/unit/techniques/`, `tests/unit/quality/`.
- No crear módulos ni carpetas sin comportamiento real. No tocar otros módulos salvo exportaciones imprescindibles, justificadas en el PR.

### 6. Plan de pruebas

- T1: Máscaras con huecos, contactos de esquina, diagonal y borde de canvas
- T2: Componentes conocidos, outline de ancho 1/2 y operación editable que reproduce la máscara
- Oráculos independientes (cálculo a mano o fórmula de MOANA.md); nunca copiar la salida de la implementación como expected.
- Incluir casos negativos con el error de dominio esperado y casos borde (vacío, mínimo, máximo, fuera de rango).

### 7. Procedimiento

1. Escribir las pruebas de los criterios AC y T antes o junto con la implementación.
2. Implementar sólo **Scope**; respetar **Out of scope** y las dependencias permitidas de MOANA.md §3.
3. Validación de módulo: `uv run pytest tests/unit/techniques/ tests/unit/quality/ -q` y `uv run mypy src/`.
4. Validación completa: `uv run python scripts/validate.py` y `uv run python scripts/check_wheel.py`.
5. Revisión: subagentes listados y skill `moana-code-review`; corregir hallazgos críticos y altos.
6. Si hay salida raster: mostrar el PNG a 1x y ampliado por vecino más cercano; si cambia un golden, presentar expected/actual/diff y justificar.

### 8. Cierre

1. En `docs/issues/catalog.json`, para este issue: `status` → `review` (o `done` tras aprobación); completar `acceptance_evidence` (AC1, AC2), `test_evidence` (T1, T2) y `evidence` con rutas concretas de tests y archivos.
2. Issues que desbloquea ([MOANA-017](MOANA-017.md), [MOANA-026](MOANA-026.md)): si todas sus dependencias quedan `done`, pasarlos a `ready` con `blocking_reason: null`.
3. Ejecutar `uv run python scripts/planning.py` y `uv run python -m scripts.check_repository`.
4. Abrir PR hacia `develop` enlazando este issue de GitHub (`Closes #<número>`), con comandos ejecutados y evidencia por AC/T. El CI completo corre al integrar `develop` en `main`.
5. Commit y push sólo con autorización del usuario. No declarar CI remoto ni aprobación artística humana sin evidencia.

### 9. Prohibido en este issue

- Implementar alcance de otros issues, incluidos los que desbloquea ([MOANA-017](MOANA-017.md), [MOANA-026](MOANA-026.md)).
- Actualizar goldens automáticamente, desactivar checks, editar `uv.lock` a mano o añadir dependencias sin motivo técnico registrado.
- `eval`/`exec`/`pickle`, red o estado global mutable en el núcleo; lecturas de texto sin `encoding="utf-8"`.

## Evidence

Pendiente de implementación.
