# MOANA-016 — Implementar dithering ordenado

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-016
- Aliases históricos: MOA-016
- Phase: P3
- Priority: P1
- Status: ready
- Complexity: M (relativa, no estimación de tiempo)
- Dependencies: [MOANA-005](MOANA-005.md), [MOANA-013](MOANA-013.md)
- Related modules: techniques
- Requirements: R009 ([trazabilidad](traceability.md))
- Bloqueo: Ninguno

## Context

Un patrón mal anclado produce costuras y parpadeo.

## Objective

Aplicar Bayer exacto con coverage entera y fase estable.

## Scope

Añadir patrones Bayer 2×2/4×4 con coverage entera, anclaje explícito y clipping por máscara.

## Out of scope

No error diffusion ni dithering automático global.

## Technical requirements

- Tablas y módulo matemático fijados en §10; dos IDs de color
- El patrón se ancla al canvas y conserva fase entre tiles y frames salvo instrucción explícita

## Proposed implementation

- Implementar tablas normativas y módulo matemático
- Aplicar la selección A/B sobre máscara y origen compartido

## Acceptance criteria

- [ ] AC1: Coverage 0 produce sólo A y N² sólo B dentro de la máscara
- [ ] AC2: Patrones con origen negativo y traducciones múltiplo del período coinciden exactamente

## Required tests

- [ ] T1: Todos los thresholds, coberturas y posiciones del período
- [ ] T2: Máscaras no rectangulares, costuras entre tiles y repetición temporal sin parpadeo

## Expected deliverables

- Dithering ordenado con patrón/anclaje documentado y máscara de aplicación.
- Fixtures exactas de patrones, transparencia y estabilidad ante recortes.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- El módulo negativo y los overrides temporales deben tener tests propios.

## Guía para agentes de IA

**Estado para agentes:** Listo: todas las dependencias están `done`; puede empezarse.

### 1. Preparación

- Rama: `feat/MOANA-016-implementar-dithering-ordenado` creada desde `develop` actualizado: `git switch develop && git pull --ff-only && git switch -c feat/MOANA-016-implementar-dithering-ordenado`.
- Verificar en `docs/issues/catalog.json` que este issue está `ready` y que sus dependencias ([MOANA-005](MOANA-005.md), [MOANA-013](MOANA-013.md)) están `done`.
- Entorno: `uv sync --locked` (sin uv global: `sh scripts/bootstrap.sh` y después `sh scripts/uv.sh` en lugar de `uv`).
- Al empezar, cambiar `status` a `in_progress` en el catálogo y regenerar con `uv run python scripts/planning.py`.

### 2. Lectura obligatoria (en orden)

1. `CLAUDE.md` (Claude Code) o `AGENTS.md` (Codex) y [flujo de sesión](../guides/agent-workflow.md).
2. MOANA.md: §3 Arquitectura modular; §10 Sombreado, dithering y materiales; §25 Definition of Done. Estas secciones son el contrato normativo; ante duda, prevalecen sobre este issue.
3. [Contratos de módulos](../architecture/module-contracts.md) para: `techniques`.
4. Estándares: [python](../../docs/standards/python.md), [architecture](../../docs/standards/architecture.md), [testing](../../docs/standards/testing.md), [pixel-art](../../docs/standards/pixel-art.md).
5. Issues de dependencia ([MOANA-005](MOANA-005.md), [MOANA-013](MOANA-013.md)): leer su sección Evidence para conocer las APIs ya entregadas; no reimplementarlas.
6. ADR en `docs/architecture/` que mencionen los módulos afectados.

### 3. Requisitos de MOANA.md cubiertos

| ID | Requisito | Secciones | Verificación exigida |
| --- | --- | --- | --- |
| R009 | Dithering controlado | §10 | Patrones exactos, coverage y fase temporal |

### 4. Skills y subagentes

| Host | Skills a cargar | Revisión especializada |
| --- | --- | --- |
| Claude Code | `moana-graphics`, `moana-pixel-art`, `moana-code-review` | `moana-graphics-engineer`, `moana-pixel-artist` (sólo lectura; el agente principal integra) |
| Codex | `$moana-graphics`, `$moana-pixel-art`, `$moana-code-review` | `moana_graphics_engineer`, `moana_pixel_artist` |

### 5. Archivos

- Código o documentos a crear/modificar: `src/moana/techniques/`.
- Pruebas: `tests/unit/techniques/`.
- No crear módulos ni carpetas sin comportamiento real. No tocar otros módulos salvo exportaciones imprescindibles, justificadas en el PR.

### 6. Plan de pruebas

- T1: Todos los thresholds, coberturas y posiciones del período
- T2: Máscaras no rectangulares, costuras entre tiles y repetición temporal sin parpadeo
- Oráculos independientes (cálculo a mano o fórmula de MOANA.md); nunca copiar la salida de la implementación como expected.
- Incluir casos negativos con el error de dominio esperado y casos borde (vacío, mínimo, máximo, fuera de rango).

### 7. Procedimiento

1. Escribir las pruebas de los criterios AC y T antes o junto con la implementación.
2. Implementar sólo **Scope**; respetar **Out of scope** y las dependencias permitidas de MOANA.md §3.
3. Validación de módulo: `uv run pytest tests/unit/techniques/ -q` y `uv run mypy src/`.
4. Validación completa: `uv run python scripts/validate.py` y `uv run python scripts/check_wheel.py`.
5. Revisión: subagentes listados y skill `moana-code-review`; corregir hallazgos críticos y altos.
6. Si hay salida raster: mostrar el PNG a 1x y ampliado por vecino más cercano; si cambia un golden, presentar expected/actual/diff y justificar.

### 8. Cierre

1. En `docs/issues/catalog.json`, para este issue: `status` → `review` (o `done` tras aprobación); completar `acceptance_evidence` (AC1, AC2), `test_evidence` (T1, T2) y `evidence` con rutas concretas de tests y archivos.
2. Issues que desbloquea ([MOANA-017](MOANA-017.md), [MOANA-034](MOANA-034.md)): si todas sus dependencias quedan `done`, pasarlos a `ready` con `blocking_reason: null`.
3. Ejecutar `uv run python scripts/planning.py` y `uv run python -m scripts.check_repository`.
4. Abrir PR hacia `develop` enlazando este issue de GitHub (`Closes #<número>`), con comandos ejecutados y evidencia por AC/T. El CI completo corre al integrar `develop` en `main`.
5. Commit y push sólo con autorización del usuario. No declarar CI remoto ni aprobación artística humana sin evidencia.

### 9. Prohibido en este issue

- Implementar alcance de otros issues, incluidos los que desbloquea ([MOANA-017](MOANA-017.md), [MOANA-034](MOANA-034.md)).
- Actualizar goldens automáticamente, desactivar checks, editar `uv.lock` a mano o añadir dependencias sin motivo técnico registrado.
- `eval`/`exec`/`pickle`, red o estado global mutable en el núcleo; lecturas de texto sin `encoding="utf-8"`.

## Evidence

Pendiente de implementación.
