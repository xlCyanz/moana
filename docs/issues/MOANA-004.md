# MOANA-004 — Crear lienzo RGBA y propiedad de buffers

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-004
- Aliases históricos: MOA-004
- Phase: P1
- Priority: P1
- Status: review
- Complexity: M (relativa, no estimación de tiempo)
- Dependencies: [MOANA-001](MOANA-001.md), [MOANA-003](MOANA-003.md)
- Related modules: core
- Requirements: R002, R027 ([trazabilidad](traceability.md))
- Bloqueo: Ninguno

## Context

NumPy y Pillow difieren en ownership, índices y representación de datos.

## Objective

Proveer un buffer RGBA seguro con adaptadores sin alias públicos mutables.

## Scope

Crear buffer de canvas y adaptadores Pillow/NumPy con propiedad explícita, normalización de transparencia y acceso seguro.

## Out of scope

No dibujar primitivas ni componer capas.

## Technical requirements

- uint8 C-contiguo [y,x,4], alfa recto y píxel transparente negro
- Copias o vistas inmutables hacia el exterior; acumuladores amplios y límites antes de reservar

## Proposed implementation

- Reservar buffers sólo tras presupuesto y validar shape/dtype/contigüidad
- Añadir copias de frontera y normalizar transparencia al importar/exportar

## Acceptance criteria

- [ ] AC1: Leer/escribir coordenadas válidas preserva RGBA y coordenadas negativas no hacen wrap
- [ ] AC2: Una copia/export de array no puede mutar silenciosamente el canvas original

## Required tests

- [ ] T1: Fixtures 1×1 y 128×128, transparentes con RGB residual y roundtrip NumPy/Pillow
- [ ] T2: Pruebas de aliasing, dtype/shape inválidos, límite de memoria y acceso fuera de rango

## Expected deliverables

- Canvas RGBA y adaptadores con reglas de ownership/copia documentadas.
- Fixtures de canal alfa, clipping, buffers no compartidos y dimensiones extremas.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- Vistas writeable=false pueden reabrirse si el propietario se filtra; probar ownership real.

## Guía para agentes de IA

**Estado para agentes:** En revisión: sólo correcciones de la revisión; no añadir alcance.

### 1. Preparación

- Rama: `feat/MOANA-004-crear-lienzo-rgba` creada desde `develop` actualizado: `git switch develop && git pull --ff-only && git switch -c feat/MOANA-004-crear-lienzo-rgba`.
- Verificar en `docs/issues/catalog.json` que este issue está `ready` y que sus dependencias ([MOANA-001](MOANA-001.md), [MOANA-003](MOANA-003.md)) están `done`.
- Entorno: `uv sync --locked` (sin uv global: `sh scripts/bootstrap.sh` y después `sh scripts/uv.sh` en lugar de `uv`).
- Al empezar, cambiar `status` a `in_progress` en el catálogo y regenerar con `uv run python scripts/planning.py`.

### 2. Lectura obligatoria (en orden)

1. `CLAUDE.md` (Claude Code) o `AGENTS.md` (Codex) y [flujo de sesión](../guides/agent-workflow.md).
2. MOANA.md: §3 Arquitectura modular; §5 Motor de lienzo y píxeles; §21 Testing y regresiones visuales; §25 Definition of Done. Estas secciones son el contrato normativo; ante duda, prevalecen sobre este issue.
3. [Contratos de módulos](../architecture/module-contracts.md) para: `core`.
4. Estándares: [python](../../docs/standards/python.md), [architecture](../../docs/standards/architecture.md), [testing](../../docs/standards/testing.md).
5. Issues de dependencia ([MOANA-001](MOANA-001.md), [MOANA-003](MOANA-003.md)): leer su sección Evidence para conocer las APIs ya entregadas; no reimplementarlas.
6. ADR en `docs/architecture/` que mencionen los módulos afectados.

### 3. Requisitos de MOANA.md cubiertos

| ID | Requisito | Secciones | Verificación exigida |
| --- | --- | --- | --- |
| R002 | Lienzo, coordenadas y buffers RGBA seguros | §5 | Fixtures de límites, dtype e inmutabilidad |
| R027 | Testing y regresión visual | §21 | Unit/property/integration y diffs exactos |

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

- T1: Fixtures 1×1 y 128×128, transparentes con RGB residual y roundtrip NumPy/Pillow
- T2: Pruebas de aliasing, dtype/shape inválidos, límite de memoria y acceso fuera de rango
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
2. Issues que desbloquea ([MOANA-006](MOANA-006.md), [MOANA-009](MOANA-009.md), [MOANA-028](MOANA-028.md)): si todas sus dependencias quedan `done`, pasarlos a `ready` con `blocking_reason: null`.
3. Ejecutar `uv run python scripts/planning.py` y `uv run python -m scripts.check_repository`.
4. Abrir PR hacia `develop` enlazando este issue de GitHub (`Closes #<número>`), con comandos ejecutados y evidencia por AC/T. El CI completo corre al integrar `develop` en `main`.
5. Commit y push sólo con autorización del usuario. No declarar CI remoto ni aprobación artística humana sin evidencia.

### 9. Prohibido en este issue

- Implementar alcance de otros issues, incluidos los que desbloquea ([MOANA-006](MOANA-006.md), [MOANA-009](MOANA-009.md), [MOANA-028](MOANA-028.md)).
- Actualizar goldens automáticamente, desactivar checks, editar `uv.lock` a mano o añadir dependencias sin motivo técnico registrado.
- `eval`/`exec`/`pickle`, red o estado global mutable en el núcleo; lecturas de texto sin `encoding="utf-8"`.

## Evidence

- src/moana/core/canvas.py: Canvas propietario del buffer uint8 C-contiguo (h, w, 4), construcción cerrada, copias en ambos sentidos, alfa cero normalizado, check_canvas_budget antes de reservar.
- src/moana/core/pillow_adapter.py: canvas_to_pillow/canvas_from_pillow sólo RGBA de un frame, sin conversión implícita, errores de Pillow envueltos.
- ADR-013 (docs/architecture/decisions/ADR-013-canvas-buffer.md): adaptadores como submódulos de core no importados por moana.core; sustituye parcialmente ADR-012 §3. MOANA.md 0.1.5-draft.
- tests/unit/core/test_core_architecture.py: NumPy sólo en canvas.py, Pillow sólo en pillow_adapter.py, ningún otro módulo de core importa los adaptadores e import moana.core no carga numpy/PIL/pydantic.
- Gate: scripts/validate.py y scripts/check_wheel.py verdes; cobertura 100 % de canvas.py y pillow_adapter.py.
- Revisión: moana-python-engineer y moana-architect; hallazgos (copy.copy con alias, constructor público, pico de memoria de normalización, errores de Pillow, MaskedArray, limits obligatorio, redacción ADR-012/013) corregidos con pruebas.
- AC1: tests/unit/core/test_core_canvas.py::test_set_get_preserves_rgba_or_normalizes_alpha_zero (Hypothesis 128×128, sin escrituras colaterales) y ::test_out_of_range_access_raises_without_wrap (x/y = -1 y 128 lanzan OutOfBoundsError sin modificar el lienzo).
- AC2: tests/unit/core/test_core_canvas.py::test_exported_array_does_not_alias_canvas, ::test_imported_array_is_copied_and_never_modified, ::test_shallow_and_deep_copy_do_not_share_the_buffer, ::test_direct_construction_is_closed y ::test_pillow_export_and_import_do_not_alias.
- T1: tests/unit/core/test_core_canvas.py::test_blank_canvas_is_transparent_black_uint8_c_contiguous y ::test_from_array_normalizes_transparent_residual_rgb (1×1 y 128×128, oráculo a mano), ::test_numpy_and_pillow_roundtrip_preserve_rgba, ::test_from_pillow_normalizes_transparent_residual_rgb y ::test_visual_digest_matches_section_14_oracle.
- T2: tests/unit/core/test_core_canvas.py: aliasing (::test_exported_array_does_not_alias_canvas, ::test_shallow_and_deep_copy_do_not_share_the_buffer), dtype/shape/tipo (::test_from_array_rejects_invalid_type_dtype_shape, ::test_from_array_rejects_masked_array, ::test_from_pillow_rejects_wrong_source_or_mode, ::test_from_pillow_rejects_multiframe_image), memoria (::test_budget_is_checked_before_numpy_allocates, ::test_from_array_checks_budget_before_copying, ::test_lowered_geometry_rejects_largest_canvas_without_allocating, ::test_transparent_import_peak_memory_stays_near_4a con tracemalloc) y fuera de rango (::test_out_of_range_access_raises_without_wrap).
