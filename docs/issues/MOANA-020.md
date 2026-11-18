# MOANA-020 — Persistir proyectos y assets seguros

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-020
- Aliases históricos: MOA-020
- Phase: P4
- Priority: P1
- Status: ready
- Complexity: L (relativa, no estimación de tiempo)
- Dependencies: [MOANA-018](MOANA-018.md), [MOANA-019](MOANA-019.md), [MOANA-011](MOANA-011.md)
- Related modules: project
- Requirements: R018, R026 ([trazabilidad](traceability.md))
- Bloqueo: Ninguno

## Context

Los assets y archivos de proyecto atraviesan una frontera de datos no confiables.

## Objective

Guardar/cargar documentos y assets de forma confinada, íntegra y atómica.

## Scope

Crear formato .moana.json, proyecto directorio y contenedor ZIP opcional con assets declarados, hashes y escritura atómica.

## Out of scope

No soporte PSD/Aseprite ni assets remotos o ejecutables.

## Technical requirements

- Confinar rutas y rechazar symlinks, duplicados y traversal antes de extracción
- Limitar entradas, expansión/ratio, bytes y decode Pillow; guardar temporal y conservar destino al fallar
- Modelar ProjectManifest separado de Document y persistir assets/snapshots bajo rutas inmutables por hash antes del commit del manifiesto.

## Proposed implementation

- Definir manifiesto separado del documento y almacenamiento content-addressed de assets
- Inspeccionar ZIP/paths/tamaños antes de escribir y comprometer manifiesto al final

## Acceptance criteria

- [ ] AC1: Guardar/cargar preserva IDs, revisiones, historial y RGBA
- [ ] AC2: Un asset con checksum incorrecto o ruta maliciosa no escribe fuera de la raíz ni carga parcialmente

## Required tests

- [ ] T1: Roundtrip proyecto geométrico y con PNG; fallo simulado de disco
- [ ] T2: ZIP con ../, rutas absolutas, symlink, nombres en colisión, ratio excesivo y bomba de imagen
- [ ] T3: Fallo después de escribir nuevos assets conserva manifiesto y assets previos; el envelope rechaza campos extra sin alterar el schema de Document.

## Expected deliverables

- ProjectManifest, persistencia de assets verificados y guardado con commit final atómico.
- Roundtrips, rechazo de rutas/archivos peligrosos y fallos durante la escritura.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- Guardar el mismo asset path in-place antes del manifiesto rompe atomicidad; versiones inmutables necesarias.
- Convergencia del historial (MOANA-019, ADR-026 §4): un digest alcanzado desde otro padre se rechaza con EditConflict (existing_snapshot); permitirla exige separar la identidad de la entrada de historial (padre + batch + digest) del almacén por contenido, con un ADR nuevo antes de persistir.

## Guía para agentes de IA

**Estado para agentes:** Listo: todas las dependencias están `done`; puede empezarse.

### 1. Preparación

- Rama: `feat/MOANA-020-persistir-proyectos-assets` creada desde `develop` actualizado: `git switch develop && git pull --ff-only && git switch -c feat/MOANA-020-persistir-proyectos-assets`.
- Verificar en `docs/issues/catalog.json` que este issue está `ready` y que sus dependencias ([MOANA-018](MOANA-018.md), [MOANA-019](MOANA-019.md), [MOANA-011](MOANA-011.md)) están `done`.
- Entorno: `uv sync --locked` (sin uv global: `sh scripts/bootstrap.sh` y después `sh scripts/uv.sh` en lugar de `uv`).
- Al empezar, cambiar `status` a `in_progress` en el catálogo y regenerar con `uv run python scripts/planning.py`.

### 2. Lectura obligatoria (en orden)

1. `CLAUDE.md` (Claude Code) o `AGENTS.md` (Codex) y [flujo de sesión](../guides/agent-workflow.md).
2. MOANA.md: §3 Arquitectura modular; §16 Formato de proyectos; §20 Seguridad y validación; §25 Definition of Done. Estas secciones son el contrato normativo; ante duda, prevalecen sobre este issue.
3. [Contratos de módulos](../architecture/module-contracts.md) para: `project`.
4. Estándares: [python](../../docs/standards/python.md), [architecture](../../docs/standards/architecture.md), [testing](../../docs/standards/testing.md), [security](../../docs/standards/security.md).
5. Issues de dependencia ([MOANA-018](MOANA-018.md), [MOANA-019](MOANA-019.md), [MOANA-011](MOANA-011.md)): leer su sección Evidence para conocer las APIs ya entregadas; no reimplementarlas.
6. ADR en `docs/architecture/` que mencionen los módulos afectados.

### 3. Requisitos de MOANA.md cubiertos

| ID | Requisito | Secciones | Verificación exigida |
| --- | --- | --- | --- |
| R018 | Formato de proyectos y assets | §16 | Roundtrip y escritura atómica confinada |
| R026 | Validación y seguridad de datos | §20 | Entradas adversarias rechazadas antes de reservar/IO |

### 4. Skills y subagentes

| Host | Skills a cargar | Revisión especializada |
| --- | --- | --- |
| Claude Code | `moana-python`, `moana-code-review` | `moana-python-engineer`, `moana-architect` (sólo lectura; el agente principal integra) |
| Codex | `$moana-python`, `$moana-code-review` | `moana_python_engineer`, `moana_architect` |

### 5. Archivos

- Código o documentos a crear/modificar: `src/moana/project/`.
- Pruebas: `tests/unit/project/`.
- No crear módulos ni carpetas sin comportamiento real. No tocar otros módulos salvo exportaciones imprescindibles, justificadas en el PR.

### 6. Plan de pruebas

- T1: Roundtrip proyecto geométrico y con PNG; fallo simulado de disco
- T2: ZIP con ../, rutas absolutas, symlink, nombres en colisión, ratio excesivo y bomba de imagen
- T3: Fallo después de escribir nuevos assets conserva manifiesto y assets previos; el envelope rechaza campos extra sin alterar el schema de Document.
- Oráculos independientes (cálculo a mano o fórmula de MOANA.md); nunca copiar la salida de la implementación como expected.
- Incluir casos negativos con el error de dominio esperado y casos borde (vacío, mínimo, máximo, fuera de rango).

### 7. Procedimiento

1. Escribir las pruebas de los criterios AC y T antes o junto con la implementación.
2. Implementar sólo **Scope**; respetar **Out of scope** y las dependencias permitidas de MOANA.md §3.
3. Validación de módulo: `uv run pytest tests/unit/project/ -q` y `uv run mypy src/`.
4. Validación completa: `uv run python scripts/validate.py` y `uv run python scripts/check_wheel.py`.
5. Revisión: subagentes listados y skill `moana-code-review`; corregir hallazgos críticos y altos.
6. Si hay salida raster: mostrar el PNG a 1x y ampliado por vecino más cercano; si cambia un golden, presentar expected/actual/diff y justificar.

### 8. Cierre

1. En `docs/issues/catalog.json`, para este issue: `status` → `review` (o `done` tras aprobación); completar `acceptance_evidence` (AC1, AC2), `test_evidence` (T1, T2, T3) y `evidence` con rutas concretas de tests y archivos.
2. Issues que desbloquea ([MOANA-021](MOANA-021.md), [MOANA-030](MOANA-030.md), [MOANA-033](MOANA-033.md), [MOANA-034](MOANA-034.md)): si todas sus dependencias quedan `done`, pasarlos a `ready` con `blocking_reason: null`.
3. Ejecutar `uv run python scripts/planning.py` y `uv run python -m scripts.check_repository`.
4. Abrir PR hacia `develop` enlazando este issue de GitHub (`Closes #<número>`), con comandos ejecutados y evidencia por AC/T. El CI completo corre al integrar `develop` en `main`.
5. Commit y push sólo con autorización del usuario. No declarar CI remoto ni aprobación artística humana sin evidencia.

### 9. Prohibido en este issue

- Implementar alcance de otros issues, incluidos los que desbloquea ([MOANA-021](MOANA-021.md), [MOANA-030](MOANA-030.md), [MOANA-033](MOANA-033.md), [MOANA-034](MOANA-034.md)).
- Actualizar goldens automáticamente, desactivar checks, editar `uv.lock` a mano o añadir dependencias sin motivo técnico registrado.
- `eval`/`exec`/`pickle`, red o estado global mutable en el núcleo; lecturas de texto sin `encoding="utf-8"`.

## Evidence

Pendiente de implementación.
