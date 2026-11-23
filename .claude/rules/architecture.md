---
paths:
  - "src/moanart/**"
  - "docs/architecture/**"
---

# Arquitectura

Contratos: [module-contracts](../../docs/architecture/module-contracts.md), [estándar](../../docs/standards/architecture.md), MOANART.md §3. Skill: `moanart-architecture`. Subagente revisor: `moanart-architect`.

- Respeta la tabla de dependencias permitidas de MOANART.md §3. `core` no importa nada interno; nada del dominio importa `cli`, `project` ni `export`.
- Pillow, NumPy y AggDraw quedan detrás de adaptadores; los contratos de dominio no exponen objetos mutables de esas bibliotecas.
- Crea un módulo sólo cuando su issue lo implementa con comportamiento real; nada de stubs vacíos.
- Un cambio de contrato público actualiza MOANART.md, ejemplos, issues y un ADR nuevo (no edites un ADR aceptado: sustitúyelo).
