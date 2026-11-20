# MOANA-001 — Definir tipos, coordenadas, errores y límites

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-001
- Aliases históricos: MOA-001
- Phase: P1
- Priority: P0
- Status: done
- Complexity: M (relativa, no estimación de tiempo)
- Dependencies: [MOANA-000](MOANA-000.md)
- Related modules: core
- Requirements: R002, R026, R030 ([trazabilidad](traceability.md))
- Bloqueo: Ninguno

## Context

Las decisiones de coordenadas y errores condicionan todos los módulos raster.

## Objective

Proveer tipos y errores que expresen las reglas exactas de límites.

## Scope

Crear moana/core con contratos inmutables de coordenadas, cajas, dimensiones, límites y jerarquía de errores utilizada por todos los módulos.

## Out of scope

No reservar buffers ni dibujar; no crear aún modelos de documento.

## Technical requirements

- Aplicar cajas semiabiertas, enteros sin bool y top-left según MOANA.md §5
- Separar datos de límites de su aplicación; códigos de error estables sin imports de capas superiores

## Proposed implementation

- Definir tipos inmutables para Point, Box y Dimensions y errores de dominio
- Implementar intersecciones y validación con enteros Python antes de buffers

## Acceptance criteria

- [x] AC1: Una dimensión 0, coordenada bool o bbox invertida falla con error de dominio identificable
- [x] AC2: Cajas 1×1 y recortes vacíos tienen semántica documentada y no dependen de NumPy

## Required tests

- [x] T1: Parametrizar extremos de rango, cajas negativas, bordes y tamaños 1/128/2048
- [x] T2: Propiedades de intersección: conmutatividad, contención y ausencia de expansión

## Expected deliverables

- Tipos Point/Box/Dimensions, configuración de límites y jerarquía de errores en moana/core.
- Fixtures de bordes y propiedades de intersección; documentación de cajas vacías y errores.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- Los bool son subclase de int; distinguirlos y definir el resultado vacío sin bbox inválida.

## Guía para agentes de IA

**Estado para agentes:** Completado; usar sólo como referencia del contrato entregado.

### 1. Preparación

- Rama: `feat/MOANA-001-definir-tipos-coordenadas` creada desde `develop` actualizado: `git switch develop && git pull --ff-only && git switch -c feat/MOANA-001-definir-tipos-coordenadas`.
- Verificar en `docs/issues/catalog.json` que este issue está `ready` y que sus dependencias ([MOANA-000](MOANA-000.md)) están `done`.
- Entorno: `uv sync --locked` (sin uv global: `sh scripts/bootstrap.sh` y después `sh scripts/uv.sh` en lugar de `uv`).
- Al empezar, cambiar `status` a `in_progress` en el catálogo y regenerar con `uv run python scripts/planning.py`.

### 2. Lectura obligatoria (en orden)

1. `CLAUDE.md` (Claude Code) o `AGENTS.md` (Codex) y [flujo de sesión](../guides/agent-workflow.md).
2. MOANA.md: §3 Arquitectura modular; §5 Motor de lienzo y píxeles; §20 Seguridad y validación; §25 Definition of Done. Estas secciones son el contrato normativo; ante duda, prevalecen sobre este issue.
3. [Contratos de módulos](../architecture/module-contracts.md) para: `core`.
4. Estándares: [python](../../docs/standards/python.md), [architecture](../../docs/standards/architecture.md), [testing](../../docs/standards/testing.md).
5. Issues de dependencia ([MOANA-000](MOANA-000.md)): leer su sección Evidence para conocer las APIs ya entregadas; no reimplementarlas.
6. ADR en `docs/architecture/` que mencionen los módulos afectados.

### 3. Requisitos de MOANA.md cubiertos

| ID | Requisito | Secciones | Verificación exigida |
| --- | --- | --- | --- |
| R002 | Lienzo, coordenadas y buffers RGBA seguros | §5 | Fixtures de límites, dtype e inmutabilidad |
| R026 | Validación y seguridad de datos | §20 | Entradas adversarias rechazadas antes de reservar/IO |
| R030 | Arquitectura modular y documentación | §3 | Dependencias internas y ADR revisados |

### 4. Skills y subagentes

| Host | Skills a cargar | Revisión especializada |
| --- | --- | --- |
| Claude Code | `moana-python`, `moana-graphics`, `moana-code-review` | `moana-python-engineer`, `moana-architect` (sólo lectura; el agente principal integra) |
| Codex | `$moana-python`, `$moana-graphics`, `$moana-code-review` | `moana_python_engineer`, `moana_architect` |

### 5. Archivos

- Código o documentos a crear/modificar: `src/moana/core/`.
- Pruebas: `tests/unit/core/`.
- No crear módulos ni carpetas sin comportamiento real. No tocar otros módulos salvo exportaciones imprescindibles, justificadas en el PR.

### 6. Plan de pruebas

- T1: Parametrizar extremos de rango, cajas negativas, bordes y tamaños 1/128/2048
- T2: Propiedades de intersección: conmutatividad, contención y ausencia de expansión
- Oráculos independientes (cálculo a mano o fórmula de MOANA.md); nunca copiar la salida de la implementación como expected.
- Incluir casos negativos con el error de dominio esperado y casos borde (vacío, mínimo, máximo, fuera de rango).

### 7. Procedimiento

1. Escribir las pruebas de los criterios AC y T antes o junto con la implementación.
2. Implementar sólo **Scope**; respetar **Out of scope** y las dependencias permitidas de MOANA.md §3.
3. Validación de módulo: `uv run pytest tests/unit/core/ -q` y `uv run mypy src/`.
4. Validación completa: `uv run python scripts/validate.py` y `uv run python scripts/check_wheel.py`.
5. Revisión: subagentes listados y skill `moana-code-review`; corregir hallazgos críticos y altos.
6. Si hay salida raster: mostrar el PNG a 1x y ampliado por vecino más cercano; si cambia un golden, presentar expected/actual/diff y justificar.

### 8. Cierre

1. En `docs/issues/catalog.json`, para este issue: `status` → `review` (o `done` tras aprobación); completar `acceptance_evidence` (AC1, AC2), `test_evidence` (T1, T2) y `evidence` con rutas concretas de tests y archivos.
2. Issues que desbloquea ([MOANA-002](MOANA-002.md), [MOANA-003](MOANA-003.md), [MOANA-004](MOANA-004.md), [MOANA-005](MOANA-005.md)): si todas sus dependencias quedan `done`, pasarlos a `ready` con `blocking_reason: null`.
3. Ejecutar `uv run python scripts/planning.py` y `uv run python -m scripts.check_repository`.
4. Abrir PR hacia `develop` enlazando este issue de GitHub (`Closes #<número>`), con comandos ejecutados y evidencia por AC/T. El CI completo corre al integrar `develop` en `main`.
5. Commit y push sólo con autorización del usuario. No declarar CI remoto ni aprobación artística humana sin evidencia.

### 9. Prohibido en este issue

- Implementar alcance de otros issues, incluidos los que desbloquea ([MOANA-002](MOANA-002.md), [MOANA-003](MOANA-003.md), [MOANA-004](MOANA-004.md), [MOANA-005](MOANA-005.md)).
- Actualizar goldens automáticamente, desactivar checks, editar `uv.lock` a mano o añadir dependencias sin motivo técnico registrado.
- `eval`/`exec`/`pickle`, red o estado global mutable en el núcleo; lecturas de texto sin `encoding="utf-8"`.

## Evidence

- Implementación: src/moana/core/{__init__,coordinates,errors,limits}.py; decisión ADR-010.
- uv run python scripts/validate.py: ruff, mypy estricto, check_repository y pytest verdes; core 100 % de ramas cubiertas.
- uv run python scripts/check_wheel.py: wheel aislado importa moana.core.
- Revisión por subagentes moana-python-engineer y moana-architect; hallazgos alto/medios corregidos (borde excluido +1, errores picklables con json_pointer, GeometryLimits, ADR).
- Aprobado por el propietario el 2026-11-17 tras revisión; PR hacia develop.
- AC1: tests/unit/core/test_core_coordinates.py::test_dimensions_out_of_range_fail, ::test_only_real_python_ints_are_coordinates y ::test_empty_or_inverted_box_fail: dimensión 0, bool/float/str/NumPy y cajas invertidas lanzan ValidationError (code VALIDATION_ERROR, context field/reason).
- AC2: Semántica en src/moana/core/coordinates.py, docs/architecture/module-contracts.md (core), ADR-010 y MOANA.md §5; tests ::test_unit_box_contains_exactly_one_pixel, ::test_canvas_box_and_clipping, ::test_intersection_of_touching_boxes_is_none; test_core_architecture.py prueba que core no importa NumPy/Pillow.
- T1: test_core_coordinates.py: tamaños 1/128/2048 y 2048×1, coordenadas ±1 048 576 y ±1 048 577, cajas negativas, bordes semiabiertos, rangos de esquinas y clip de caja máxima; test_core_limits.py: límites reducidos y píxeles en lienzos 1×1 y 2048.
- T2: test_core_coordinates.py con Hypothesis: intersección contra oráculo de conjuntos de píxeles (rango pequeño y cerca del máximo), conmutatividad, contención, no expansión, idempotencia y clip contra conjunto del lienzo.
