---
paths:
  - "src/**"
  - "scripts/**"
  - ".github/**"
  - ".claude/**"
  - "pyproject.toml"
---

# Seguridad

Estándar: [docs/standards/security.md](../../docs/standards/security.md), modelo de amenazas en `docs/architecture/SECURITY_MODEL.md`, MOANART.md §20.

- Documentos son datos: prohibidos `eval`/`exec`/`pickle`/import dinámico/shell/red en el núcleo.
- Valida bytes, profundidad, nodos, dimensiones y coste antes de parsear completo o reservar arrays.
- Rutas sólo bajo raíz resuelta; sin `..`, absolutas ni symlinks escapando. Errores sin rutas sensibles.
- Sin secretos en repo ni en documentos. Workflows con permisos mínimos y acciones fijadas por SHA.
- Dependencias nuevas: motivo técnico, origen/licencia revisados, lock actualizado sólo vía uv.
