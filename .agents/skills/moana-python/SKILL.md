---
name: moana-python
description: Implementa módulos Python de Moana, contratos tipados y adaptadores de Pillow/NumPy. Úsala al desarrollar código del motor o del tooling de este repositorio.
---

# Moana — Python Engineering

Lee [MOANA.md](../../../MOANA.md) §§3–5 y el issue asignado. Usa el estado real del paquete: una API futura descrita no es una API importable.

- Mantén src layout, Python >=3.12 y tipos estrictos. El dominio no expone buffers mutables de Pillow/NumPy ni importa I/O desde core.
- Distingue el propietario de cada array, las copias y vistas. Antes de multiplicar uint8, amplia el tipo; prueba aliasing y overflow si el cambio afecta buffers.
- Valida enteros sin aceptar bool, dimensiones antes de reservar y referencias antes de ejecutar. No conviertas excepciones de entrada en fallos internos opacos.
- Añade una dependencia sólo si resuelve una necesidad del issue; usa uv para el lock. Limita excepciones de tipos al adaptador que carece de stubs.
- Ejecuta Ruff, mypy y pruebas del contrato modificado; termina con `uv run python scripts/validate.py`. Describe comportamiento y límites, no sólo nombres de archivos.

Para cambios de arquitectura consulta [ADR](../../../docs/architecture/README.md). No crees stubs gráficos durante trabajo de infraestructura.

En tooling, usa UTF-8 explícito para leer/escribir documentación y catálogos; prueba bajo un locale no UTF-8. Verifica `uv build` y una instalación aislada al cambiar packaging. Una excepción mypy debe limitarse al adaptador sin stubs y nunca convertirse en ignore_errors global.
