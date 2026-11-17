# MOANA-011 — Exportar PNG y manifiesto de salida

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-011
- Aliases históricos: MOA-011
- Phase: P2
- Priority: P1
- Status: blocked
- Complexity: M (relativa, no estimación de tiempo)
- Dependencies: [MOANA-010](MOANA-010.md)
- Related modules: export
- Requirements: R022 ([trazabilidad](traceability.md))
- Bloqueo: Dependencias pendientes: MOANA-010

## Context

Exportar no debe perder píxeles ni sobrescribir archivos por accidente.

## Objective

Escribir PNG maestro y manifiesto con roundtrip y atomicidad comprobados.

## Scope

Crear exportador PNG RGBA/indexado con escala entera y escritura atómica que no sobrescribe por defecto.

## Out of scope

No GIF ni publicar archivos en servicios externos.

## Technical requirements

- Metadata estable; indexed conserva orden y valida cardinalidad/transparencia
- ExportManifest incluye dimensiones, hash, ruta y warnings; evitar cuantización implícita

## Proposed implementation

- Separar encode en memoria del commit a filesystem
- Validar formato/indexado/escala y escribir temporal hermano antes del commit

## Acceptance criteria

- [ ] AC1: PNG decodificado es exactamente igual al RenderResult en escala 1
- [ ] AC2: Fallo de escritura deja el destino anterior intacto y no devuelve éxito parcial

## Required tests

- [ ] T1: Roundtrip RGBA e indexado, transparencia y escala nearest 1/2/4
- [ ] T2: Paleta 256/257, destino existente, permiso denegado y fallo simulado durante escritura
- [ ] T3: Carrera de dos escritores con overwrite=false: uno gana y el otro falla sin reemplazar; no usar exists+replace como exclusión.

## Expected deliverables

- Exportador PNG y manifiesto de salida con escritura atómica sin sobrescritura accidental.
- Roundtrips RGBA, pruebas de fallo de I/O y carrera entre escritores.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- Una comprobación exists seguida de replace puede sobreescribir por carrera; usar commit sin reemplazo cuando overwrite=false.

## Guía para agentes de IA

**Estado para agentes:** No empezar: estado `blocked`. Esperar a que [MOANA-010](MOANA-010.md) estén `done` y el catálogo marque este issue `ready`.

### 1. Preparación

- Rama: `feat/MOANA-011-exportar-png-manifiesto` creada desde `develop` actualizado: `git switch develop && git pull --ff-only && git switch -c feat/MOANA-011-exportar-png-manifiesto`.
- Verificar en `docs/issues/catalog.json` que este issue está `ready` y que sus dependencias ([MOANA-010](MOANA-010.md)) están `done`.
- Entorno: `uv sync --locked` (sin uv global: `sh scripts/bootstrap.sh` y después `sh scripts/uv.sh` en lugar de `uv`).
- Al empezar, cambiar `status` a `in_progress` en el catálogo y regenerar con `uv run python scripts/planning.py`.

### 2. Lectura obligatoria (en orden)

1. `CLAUDE.md` (Claude Code) o `AGENTS.md` (Codex) y [flujo de sesión](../guides/agent-workflow.md).
2. MOANA.md: §3 Arquitectura modular; §18 Exportación PNG, GIF y formatos adicionales; §25 Definition of Done. Estas secciones son el contrato normativo; ante duda, prevalecen sobre este issue.
3. [Contratos de módulos](../architecture/module-contracts.md) para: `export`.
4. Estándares: [python](../../docs/standards/python.md), [architecture](../../docs/standards/architecture.md), [testing](../../docs/standards/testing.md).
5. Issues de dependencia ([MOANA-010](MOANA-010.md)): leer su sección Evidence para conocer las APIs ya entregadas; no reimplementarlas.
6. ADR en `docs/architecture/` que mencionen los módulos afectados.

### 3. Requisitos de MOANA.md cubiertos

| ID | Requisito | Secciones | Verificación exigida |
| --- | --- | --- | --- |
| R022 | Exportación PNG RGBA/indexada | §18 | Roundtrip decoded y destino intacto al fallar |

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

- T1: Roundtrip RGBA e indexado, transparencia y escala nearest 1/2/4
- T2: Paleta 256/257, destino existente, permiso denegado y fallo simulado durante escritura
- T3: Carrera de dos escritores con overwrite=false: uno gana y el otro falla sin reemplazar; no usar exists+replace como exclusión.
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

1. En `docs/issues/catalog.json`, para este issue: `status` → `review` (o `done` tras aprobación); completar `acceptance_evidence` (AC1, AC2), `test_evidence` (T1, T2, T3) y `evidence` con rutas concretas de tests y archivos.
2. Issues que desbloquea ([MOANA-012](MOANA-012.md), [MOANA-020](MOANA-020.md), [MOANA-023](MOANA-023.md), [MOANA-024](MOANA-024.md), [MOANA-025](MOANA-025.md), [MOANA-029](MOANA-029.md)): si todas sus dependencias quedan `done`, pasarlos a `ready` con `blocking_reason: null`.
3. Ejecutar `uv run python scripts/planning.py` y `uv run python -m scripts.check_repository`.
4. Abrir PR hacia `develop` enlazando este issue de GitHub (`Closes #<número>`), con comandos ejecutados y evidencia por AC/T. El CI completo corre al integrar `develop` en `main`.
5. Commit y push sólo con autorización del usuario. No declarar CI remoto ni aprobación artística humana sin evidencia.

### 9. Prohibido en este issue

- Implementar alcance de otros issues, incluidos los que desbloquea ([MOANA-012](MOANA-012.md), [MOANA-020](MOANA-020.md), [MOANA-023](MOANA-023.md), [MOANA-024](MOANA-024.md), [MOANA-025](MOANA-025.md), [MOANA-029](MOANA-029.md)).
- Actualizar goldens automáticamente, desactivar checks, editar `uv.lock` a mano o añadir dependencias sin motivo técnico registrado.
- `eval`/`exec`/`pickle`, red o estado global mutable en el núcleo; lecturas de texto sin `encoding="utf-8"`.

## Evidence

Pendiente de implementación.
