# Desarrollo local y flujo Git

Comenzar por [AGENTS.md](../../AGENTS.md), el [roadmap](../issues/roadmap.md) y el issue elegido. No hay CLI todavía: el paquete publica su versión, el marcador de tipos, `moana.core`, `moana.schema`, el render determinista y su plan de coste (`moana.render`), el lienzo RGBA de `moana.core.canvas`, `moana.palette`, las máscaras y transformaciones de `moana.geometry` la composición de `moana.layers` y la exportación PNG de `moana.export`. El JSON Schema de `schemas/` se regenera con `uv run python scripts/generate_schema.py` sólo ante un cambio de contrato revisado (`--check` lo verifica). El entorno actual usa Python 3.12; las plataformas declaradas se verifican según la evidencia del reporte y CI.

## Preparar el entorno

Con uv disponible:

```sh
uv sync --locked
uv run python -c 'import moana; print(moana.__version__)'
```

`uv sync` es el comando ordinario de sincronización; `--locked` impide actualizar el lock por accidente durante una reproducción. Si se cambia deliberadamente una dependencia, resolver mediante uv y revisar `pyproject.toml` y `uv.lock` juntos.

En macOS/Linux sin uv global, `sh scripts/bootstrap.sh` instala herramientas dentro del checkout y `sh scripts/uv.sh` puede sustituir a `uv` en cualquier comando. Por ejemplo, `sh scripts/uv.sh run pytest`. No es necesario cambiar la instalación global ni ejecutar Python del sistema para trabajar el paquete. En Windows, usar uv instalado por un mecanismo confiable y ejecutar los comandos uv indicados.

## Comandos de trabajo

```sh
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src/
uv run mypy
uv build
uv run python scripts/validate.py
uv run python scripts/planning.py --check
uv run python -m scripts.check_repository
```

`mypy src/` comprueba la API del paquete; `mypy` incluye tooling/tests según la configuración. El gate reúne las comprobaciones comunes. Los exports y benchmarks se añadirán con sus issues; la disponibilidad de un marker no significa que esas pruebas ya existan. Las regresiones visuales exactas se ejecutan con `uv run pytest -m visual`; aceptar un cambio de golden sigue el procedimiento revisado de [tests/visual](../../tests/visual/README.md) y nunca se hace en CI.

Instalar el hook por checkout con `uv run pre-commit install`. El hook usa el venv local y evita depender de que uv esté en el PATH de Git. Para comprobar todos los archivos versionados: `uv run pre-commit run --all-files`. Las herramientas del hook no se descargan durante cada commit.

## Organización del trabajo

La organización propuesta es `main` para versiones integradas, `develop` para integración cuando el equipo necesite ese nivel y `feat/MOANA-001-coordinates` para un issue. Para cambios pequeños, una rama de issue puede partir directamente de la rama de integración vigente. No se crean ramas remotas ni se cambia la rama predeterminada como efecto de instalar infraestructura.

Antes de editar, comprobar `git status --short --branch`, los remotos y el historial relevante. Aislar el trabajo autorizado; conservar cambios ajenos y no asumir que todo el working tree pertenece al issue. El nombre de rama no cierra el issue ni prueba que sus dependencias estén terminadas.

La revisión describe el problema, comportamiento resultante, alcance y comandos ejecutados. Para cambios gráficos adjuntar expected/actual/diff y fuente; para contratos actualizar spec, ADR cuando aplique y trazabilidad. Un commit no sustituye la validación y un push no demuestra que CI terminó correctamente.

## Protecciones propuestas, no configuradas por esta guía

Para `main` y, si se usa, `develop`: requerir pull request, al menos una revisión, checks de CI de la matriz exigida (el workflow Quality sólo corre para PR contra `main` y pushes a `main`; exigirlo en `develop` requiere ampliar sus disparadores), resolución de conversaciones y ausencia de force push/borrado. La lista de checks debe corresponder a nombres observados en GitHub; no inventar un check requerido que nunca se publique. La política de revisión puede ajustar el número de aprobaciones al equipo.

Estas son condiciones recomendadas para el propietario. Cambiar protecciones, configurar reglas remotas, crear ramas remotas o publicar un paquete requiere autorización específica. La infraestructura local no necesita modificar esos recursos para ser verificable.
