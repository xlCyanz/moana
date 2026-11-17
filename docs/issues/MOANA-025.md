# MOANA-025 — Añadir APNG y WebP lossless opcionales

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-025
- Aliases históricos: MOA-025
- Phase: P4
- Priority: P2
- Status: blocked
- Complexity: M (relativa, no estimación de tiempo)
- Dependencies: [MOANA-022](MOANA-022.md), [MOANA-011](MOANA-011.md)
- Related modules: export
- Requirements: R024 ([trazabilidad](traceability.md))
- Bloqueo: Dependencias pendientes: MOANA-022, MOANA-011

## Context

APNG/WebP dependen de capacidades del build y no justifican fallbacks ocultos.

## Objective

Exponer formatos adicionales sólo con codecs y roundtrip comprobados.

## Scope

Agregar exportadores adicionales sólo cuando el build de Pillow soporte los codecs, con capabilities públicas.

## Out of scope

No WebP lossy por defecto ni dependencia obligatoria de encoders ausentes.

## Technical requirements

- Detectar capacidad en runtime sin sustituir formatos; preservación de alfa/tiempos
- Opciones lossless explícitas y manifest con versiones de codec

## Proposed implementation

- Detectar capacidades y registrar opciones lossless
- Probar formatos disponibles y rechazar ausentes antes de crear destino

## Acceptance criteria

- [ ] AC1: Cada codec disponible pasa roundtrip RGBA y timeline
- [ ] AC2: Codec ausente produce UnsupportedOperation claro sin archivo con extensión engañosa

## Required tests

- [ ] T1: Pruebas condicionadas a capacidades con skip explicado y reporte del build
- [ ] T2: Mock de codec ausente y casos multi-frame, alfa parcial y duración

## Expected deliverables

- Adaptadores APNG/WebP lossless con detección de capacidades del codec.
- Roundtrips de timeline y errores verificables cuando una capacidad no está disponible.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- Un skip de codec no equivale a soporte probado; publicar capability matrix.

## Guía para agentes de IA

**Estado para agentes:** No empezar: estado `blocked`. Esperar a que [MOANA-022](MOANA-022.md), [MOANA-011](MOANA-011.md) estén `done` y el catálogo marque este issue `ready`.

### 1. Preparación

- Rama: `feat/MOANA-025-anadir-apng-webp` creada desde `develop` actualizado: `git switch develop && git pull --ff-only && git switch -c feat/MOANA-025-anadir-apng-webp`.
- Verificar en `docs/issues/catalog.json` que este issue está `ready` y que sus dependencias ([MOANA-022](MOANA-022.md), [MOANA-011](MOANA-011.md)) están `done`.
- Entorno: `uv sync --locked` (sin uv global: `sh scripts/bootstrap.sh` y después `sh scripts/uv.sh` en lugar de `uv`).
- Al empezar, cambiar `status` a `in_progress` en el catálogo y regenerar con `uv run python scripts/planning.py`.

### 2. Lectura obligatoria (en orden)

1. `CLAUDE.md` (Claude Code) o `AGENTS.md` (Codex) y [flujo de sesión](../guides/agent-workflow.md).
2. MOANA.md: §3 Arquitectura modular; §18 Exportación PNG, GIF y formatos adicionales; §25 Definition of Done. Estas secciones son el contrato normativo; ante duda, prevalecen sobre este issue.
3. [Contratos de módulos](../architecture/module-contracts.md) para: `export`.
4. Estándares: [python](../../docs/standards/python.md), [architecture](../../docs/standards/architecture.md), [testing](../../docs/standards/testing.md).
5. Issues de dependencia ([MOANA-022](MOANA-022.md), [MOANA-011](MOANA-011.md)): leer su sección Evidence para conocer las APIs ya entregadas; no reimplementarlas.
6. ADR en `docs/architecture/` que mencionen los módulos afectados.

### 3. Requisitos de MOANA.md cubiertos

| ID | Requisito | Secciones | Verificación exigida |
| --- | --- | --- | --- |
| R024 | Formatos adicionales | §18 | APNG/WebP lossless según codec disponible |

### 4. Skills y subagentes

| Host | Skills a cargar | Revisión especializada |
| --- | --- | --- |
| Claude Code | `moana-graphics`, `moana-python`, `moana-code-review` | `moana-graphics-engineer`, `moana-python-engineer` (sólo lectura; el agente principal integra) |
| Codex | `$moana-graphics`, `$moana-python`, `$moana-code-review` | `moana_graphics_engineer`, `moana_python_engineer` |

### 5. Archivos

- Código o documentos a crear/modificar: `src/moana/export/`.
- Pruebas: `tests/unit/export/`.
- No crear módulos ni carpetas sin comportamiento real. No tocar otros módulos salvo exportaciones imprescindibles, justificadas en el PR.

### 6. Plan de pruebas

- T1: Pruebas condicionadas a capacidades con skip explicado y reporte del build
- T2: Mock de codec ausente y casos multi-frame, alfa parcial y duración
- Oráculos independientes (cálculo a mano o fórmula de MOANA.md); nunca copiar la salida de la implementación como expected.
- Incluir casos negativos con el error de dominio esperado y casos borde (vacío, mínimo, máximo, fuera de rango).

### 7. Procedimiento

1. Escribir las pruebas de los criterios AC y T antes o junto con la implementación.
2. Implementar sólo **Scope**; respetar **Out of scope** y las dependencias permitidas de MOANA.md §3.
3. Validación de módulo: `uv run pytest tests/unit/export/ -q` y `uv run mypy src/`.
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
