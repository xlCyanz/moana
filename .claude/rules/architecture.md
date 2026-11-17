---
paths:
  - "src/moana/**"
  - "docs/architecture/**"
---

# Arquitectura

Contratos: [module-contracts](../../docs/architecture/module-contracts.md), [estándar](../../docs/standards/architecture.md), MOANA.md §3. Skill: `moana-architecture`. Subagente revisor: `moana-architect`.

- Respeta la tabla de dependencias permitidas de MOANA.md §3. `core` no importa nada interno; nada del dominio importa `cli`, `project` ni `export`.
- Pillow, NumPy y AggDraw quedan detrás de adaptadores; los contratos de dominio no exponen objetos mutables de esas bibliotecas.
- Crea un módulo sólo cuando su issue lo implementa con comportamiento real; nada de stubs vacíos.
- Un cambio de contrato público actualiza MOANA.md, ejemplos, issues y un ADR nuevo (no edites un ADR aceptado: sustitúyelo).
