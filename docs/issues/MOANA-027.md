# MOANA-027 — Construir corpus artístico y rúbrica humana

> Generado por `scripts/planning.py`; editar los catálogos JSON y regenerar.

## Metadata

- ID: MOANA-027
- Aliases históricos: MOA-027
- Phase: P5
- Priority: P1
- Status: review
- Complexity: L (relativa, no estimación de tiempo)
- Dependencies: [MOANA-017](MOANA-017.md), [MOANA-022](MOANA-022.md), [MOANA-026](MOANA-026.md), [MOANA-028](MOANA-028.md)
- Related modules: examples, quality
- Requirements: R005, R027, R038 ([trazabilidad](traceability.md))
- Bloqueo: Ninguno

## Context

Las técnicas requieren un corpus editable y evaluación de lectura real.

## Objective

Demostrar cinco categorías con fuentes propias y rúbrica documentada.

## Scope

Crear ejemplos propios de personaje, criatura, objeto, tile y animación con JSON, PNG, paleta, procedencia y evaluación.

## Out of scope

No inventar aprobaciones humanas ni generar ejemplos finales con un modelo visual.

## Technical requirements

- Cada ejemplo conserva fuente editable, semilla, versión de renderer y licencia/procedencia
- Mostrar 1×/4×, silueta y clusters; rúbrica de §19 con aprobación humana registrada o pendiente

## Proposed implementation

- Crear brief/JSON/semilla por ejemplo y renders reproducibles
- Registrar procedencia y revisión humana con categorías y justificación

## Acceptance criteria

- [ ] AC1: Corpus cubre cinco categorías y pasa hard checks sin ocultar warnings
- [ ] AC2: Sólo se califica profesional un ejemplo revisado por una persona con >=4 en categorías aplicables

## Required tests

- [ ] T1: Render de todo el corpus y cambio localizado por región con diff
- [ ] T2: Inspección visual documentada, estabilidad de animación y auditoría de procedencia

## Expected deliverables

- Corpus propio de personaje, criatura, objeto, tile y animación con fuentes editables.
- Previews 1×/4×, procedencia/licencia y rúbrica humana con evidencia de evaluación.

## Definition of Done

Cumplir [MOANA.md §25](../../MOANA.md), todos los criterios AC y pruebas T; adjuntar evidencia por ID, pasar el gate y revisar el resultado. Dependencias completadas y [ciclo de vida](../guides/issue-lifecycle.md) respetado.

## Risks and notes

- No marcar como aprobada la calidad artística mientras falte una persona revisora.

## Guía para agentes de IA

**Estado para agentes:** En revisión: sólo correcciones de la revisión; no añadir alcance.

### 1. Preparación

- Rama: `feat/MOANA-027-construir-corpus-artistico` creada desde `develop` actualizado: `git switch develop && git pull --ff-only && git switch -c feat/MOANA-027-construir-corpus-artistico`.
- Verificar en `docs/issues/catalog.json` que este issue está `ready` y que sus dependencias ([MOANA-017](MOANA-017.md), [MOANA-022](MOANA-022.md), [MOANA-026](MOANA-026.md), [MOANA-028](MOANA-028.md)) están `done`.
- Entorno: `uv sync --locked` (sin uv global: `sh scripts/bootstrap.sh` y después `sh scripts/uv.sh` en lugar de `uv`).
- Al empezar, cambiar `status` a `in_progress` en el catálogo y regenerar con `uv run python scripts/planning.py`.

### 2. Lectura obligatoria (en orden)

1. `CLAUDE.md` (Claude Code) o `AGENTS.md` (Codex) y [flujo de sesión](../guides/agent-workflow.md).
2. MOANA.md: §1 Visión y objetivos; §3 Arquitectura modular; §7 Técnicas profesionales de Pixel Art; §13 API pública de Python; §15 Edición no destructiva; §19 Control de calidad gráfico; §21 Testing y regresiones visuales; §25 Definition of Done. Estas secciones son el contrato normativo; ante duda, prevalecen sobre este issue.
3. [Contratos de módulos](../architecture/module-contracts.md) para: `examples`, `quality`.
4. Estándares: [pixel-art](../../docs/standards/pixel-art.md), [python](../../docs/standards/python.md), [architecture](../../docs/standards/architecture.md), [testing](../../docs/standards/testing.md).
5. Issues de dependencia ([MOANA-017](MOANA-017.md), [MOANA-022](MOANA-022.md), [MOANA-026](MOANA-026.md), [MOANA-028](MOANA-028.md)): leer su sección Evidence para conocer las APIs ya entregadas; no reimplementarlas.
6. ADR en `docs/architecture/` que mencionen los módulos afectados.

### 3. Requisitos de MOANA.md cubiertos

| ID | Requisito | Secciones | Verificación exigida |
| --- | --- | --- | --- |
| R005 | Técnicas profesionales y calidad artística | §7, §19 | Corpus editable y rúbrica humana documentada |
| R027 | Testing y regresión visual | §21 | Unit/property/integration y diffs exactos |
| R038 | Preview y modificación específica por IA | §1, §13, §15 | Tutorial render-preview-edit con IDs preservados |

### 4. Skills y subagentes

| Host | Skills a cargar | Revisión especializada |
| --- | --- | --- |
| Claude Code | `moana-pixel-art`, `moana-testing`, `moana-code-review` | `moana-pixel-artist`, `moana-documentation`, `moana-qa-engineer` (sólo lectura; el agente principal integra) |
| Codex | `$moana-pixel-art`, `$moana-testing`, `$moana-code-review` | `moana_pixel_artist`, `moana_documentation`, `moana_qa_engineer` |

### 5. Archivos

- Código o documentos a crear/modificar: `examples/`, `src/moana/quality/`.
- Pruebas: `tests/integration/`, `tests/unit/quality/`.
- No crear módulos ni carpetas sin comportamiento real. No tocar otros módulos salvo exportaciones imprescindibles, justificadas en el PR.

### 6. Plan de pruebas

- T1: Render de todo el corpus y cambio localizado por región con diff
- T2: Inspección visual documentada, estabilidad de animación y auditoría de procedencia
- Oráculos independientes (cálculo a mano o fórmula de MOANA.md); nunca copiar la salida de la implementación como expected.
- Incluir casos negativos con el error de dominio esperado y casos borde (vacío, mínimo, máximo, fuera de rango).

### 7. Procedimiento

1. Escribir las pruebas de los criterios AC y T antes o junto con la implementación.
2. Implementar sólo **Scope**; respetar **Out of scope** y las dependencias permitidas de MOANA.md §3.
3. Validación de módulo: `uv run pytest tests/integration/ tests/unit/quality/ -q` y `uv run mypy src/`.
4. Validación completa: `uv run python scripts/validate.py` y `uv run python scripts/check_wheel.py`.
5. Revisión: subagentes listados y skill `moana-code-review`; corregir hallazgos críticos y altos.
6. Si hay salida raster: mostrar el PNG a 1x y ampliado por vecino más cercano; si cambia un golden, presentar expected/actual/diff y justificar.

### 8. Cierre

1. En `docs/issues/catalog.json`, para este issue: `status` → `review` (o `done` tras aprobación); completar `acceptance_evidence` (AC1, AC2), `test_evidence` (T1, T2) y `evidence` con rutas concretas de tests y archivos.
2. Issues que desbloquea ([MOANA-031](MOANA-031.md), [MOANA-035](MOANA-035.md)): si todas sus dependencias quedan `done`, pasarlos a `ready` con `blocking_reason: null`.
3. Ejecutar `uv run python scripts/planning.py` y `uv run python -m scripts.check_repository`.
4. Abrir PR hacia `develop` enlazando este issue de GitHub (`Closes #<número>`), con comandos ejecutados y evidencia por AC/T. El CI completo corre al integrar `develop` en `main`.
5. Commit y push sólo con autorización del usuario. No declarar CI remoto ni aprobación artística humana sin evidencia.

### 9. Prohibido en este issue

- Implementar alcance de otros issues, incluidos los que desbloquea ([MOANA-031](MOANA-031.md), [MOANA-035](MOANA-035.md)).
- Actualizar goldens automáticamente, desactivar checks, editar `uv.lock` a mano o añadir dependencias sin motivo técnico registrado.
- `eval`/`exec`/`pickle`, red o estado global mutable en el núcleo; lecturas de texto sin `encoding="utf-8"`.

## Evidence

- Corpus artístico de referencia en examples/corpus/<slug>/ (ADR-037): adventurer (personaje 24×32), frog (criatura 32×27), chest (objeto 32×28), stone-tile (tile 16×16 sin costuras) y adventurer-walk (animación de 6 frames a 120 ms); paleta strict y luz NW en todos. Cada ejemplo: documento .moana.json (única fuente), registro .corpus.json (moana-corpus-entry/1) con brief, procedencia (creado por un agente de IA mediante operaciones de Moana; licencia PENDIENTE de decisión del propietario), digests de render fijados, informe de calidad, inspección del agente y rúbrica; previews 1×, 4×, silueta y clusters (más 3×3 del tile y tira de la animación) como goldens del harness visual.
- Rúbrica moana-rubric/1 validada por moana.quality.parse_rubric: categorías legibilidad, silueta, clusters, paleta, luz/material y continuidad temporal en animaciones; cada una pending_human_review o reviewed (1–5); professional sólo con hard checks superados, human_review (reviewer_kind human, render_fingerprint del render revisado) y todas las puntuaciones ≥ 4; agent_assessment etiquetado como no humano y nunca cuenta.
- scripts/corpus.py check/facts sin escritura: audita procedencia, versiones de renderer/estimador/semilla, digests, hard checks, categorías y huella del render revisado (un cambio de arte tras una revisión humana falla la auditoría); rechaza claves JSON duplicadas.
- Los cinco ejemplos superan los hard checks con 0 advertencias y sin supresiones. Revisiones de agente: pixel-art (piernas separadas, ciclo de 6 frames con contrapeso, ruido de la rana, biseles del cofre a favor de la luz NW, periodo del tile), QA (invariante de rúbrica, ramas de auditoría parametrizadas) y documentación (licencia explícitamente pendiente, autoría de agente) aplicadas. Revisión artística humana PENDIENTE: ningún ejemplo es profesional.
- Documentación: MOANA.md 0.1.25-draft (§19), ADR-037, module-contracts, examples/corpus/README.md, tests/visual/README.md. Gate local macOS: scripts/validate.py 3273 passed con src/moana al 100 %, corpus check OK, check_wheel OK, mypy --platform win32 OK, pre-commit OK; matriz pendiente en main. Seguimiento propuesto: reglas de clusters por frame en quality (fuera de alcance).
- AC1: tests/integration/test_art_corpus.py::test_five_categories_pass_hard_checks_and_show_every_warning (cinco categorías, hard checks superados, advertencias registradas iguales a las reales, sin supresiones), ::test_check_requires_the_five_categories, ::test_provenance_audit_passes; scripts/corpus.py check → «Corpus OK: 5 examples, 5 pending human review».
- AC2: tests/unit/quality/test_quality_rubric.py::test_professional_without_human_review_is_rejected, ::test_agent_assessment_never_makes_an_example_professional, ::test_one_low_score_blocks_professional, ::test_failed_hard_checks_block_professional, ::test_fixture_human_review_makes_a_professional_example, ::test_malformed_reviews_are_rejected; tests/integration/test_art_corpus.py::test_real_records_satisfy_the_rubric_invariant, ::test_real_corpus_is_pending_until_reviewed.
- T1: tests/integration/test_art_corpus.py::test_corpus_renders_to_its_pinned_digests (doble render y digests por frame), ::test_localized_shirt_recolour_stays_inside_the_shirt_region (oráculo con cajas literales y expected/actual/diff del harness); tests/visual/test_corpus_previews.py::test_corpus_preview_matches_its_golden, ::test_scale_is_nearest_neighbour, ::test_cluster_view_singletons_agree_with_quality_metrics.
- T2: tests/integration/test_art_corpus.py::test_walk_cycle_is_stable (sin hallazgos temporales, costura del bucle, suelo, paleta y frames sin singletons), ::test_provenance_audit_passes, ::test_audit_reports_tampered_records (mutaciones parametrizadas incluida la deriva de versiones y semilla), ::test_audit_reports_a_real_failing_hard_check, ::test_main_exit_codes, ::test_records_reject_duplicate_keys; inspección visual del agente a 1× y 8× registrada en agent_inspection (no humana).
