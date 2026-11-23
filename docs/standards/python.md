# Estándares Python

Norma operativa: [AGENTS.md](../../AGENTS.md). Contratos del producto: [MOANART.md](../../MOANART.md). Python >=3.12, layout `src/`, distribución `moanart` e import `moanart`.

## Tipos y API

Escribir identificadores y docstrings de API en inglés; la documentación del proyecto permanece en español. Usar colecciones nativas tipadas, `Path` para I/O, parámetros keyword-only para opciones ambiguas y excepciones de dominio. Las funciones públicas tienen anotaciones completas y describen propiedad, mutabilidad, límites y errores.

Preferir un tipo específico o una unión discriminada frente a diccionarios abiertos. `Any` sólo se justifica en una frontera de librería que no pueda tiparse razonablemente; convertir y validar allí antes de entregar valores al dominio. No desactivar mypy para un módulo completo con el fin de ocultar una API imprecisa. La excepción actual de AggDraw se limita a su import.

## Datos gráficos

Validar enteros sin aceptar `bool`, strings numéricos o floats implícitos. Un buffer tiene propietario, shape, dtype y política de copias documentados. Elevar dtype antes de productos o sumas que puedan desbordar `uint8`. No entregar una vista supuestamente de sólo lectura si el consumidor puede recuperar su base escribible.

Resolver coordenadas/clipping según el contrato de MoanArt, no según índices negativos de NumPy o defaults de Pillow. El núcleo no abre archivos ni accede a red. La semilla no utiliza `hash()`, reloj o RNG global. Los resultados no dependen del cwd ni de locale.

## Paquete y dependencias

`uv.lock` se modifica mediante uv. Añadir una dependencia exige un uso del issue, revisar origen/licencia y probar instalación en las plataformas declaradas. Mantener imports ligeros: importar `moanart` no ejecuta rasterización ni crea directorios. No registrar un entrypoint de dibujo antes de que su comportamiento esté implementado.

Los tests deben distinguir el import desde el wheel instalado del import accidental desde el checkout. Los archivos incluidos en wheel/sdist se verifican; venv, cachés, credenciales y artefactos transitorios se excluyen. La licencia de publicación sigue siendo una decisión del propietario.

## Verificación

```sh
uv run ruff check .
uv run ruff format --check .
uv run mypy src/
uv run mypy
uv run pytest
uv build
```

`mypy src/` cubre el paquete; `mypy` usa el alcance configurado de paquete, scripts y tests. Corregir la causa de un fallo antes de añadir una supresión. El [flujo de desarrollo](../guides/development.md) explica el entorno local y el gate común.
