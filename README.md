# MoanArt

Motor Python de Pixel Art **determinista y editable**. Un sprite es un documento JSON con capas, paleta y operaciones con IDs estables; MoanArt lo valida, lo renderiza a RGBA entero (el mismo documento produce los mismos píxeles en cualquier proceso y plataforma) y lo modifica con batches atómicos que nombran IDs en lugar de repintar la imagen. Está pensado para que personas y agentes de IA trabajen con el mismo flujo, sin GUI, red ni credenciales.

> **Estado: alpha.** La versión del código es el release candidate `0.1.0rc2` (sin publicar). El candidato anterior, `0.1.0rc1`, está publicado como [prerelease de GitHub](https://github.com/xlCyanz/moana/releases/tag/v0.1.0rc1) con el nombre del proyecto previo al renombrado ([CHANGELOG](CHANGELOG.md)). No está en PyPI. La revisión artística humana del corpus y de los ejemplos sigue pendiente: ningún ejemplo se declara de calidad profesional ([checklist de release](docs/RELEASE.md)).

## Inicio rápido

Requiere Python ≥ 3.12 y [uv](https://docs.astral.sh/uv/):

```sh
uv sync --locked
uv run moanart validate examples/specs/minimal.moanart.json
uv run moanart export examples/specs/minimal.moanart.json artifacts/minimal.png --scale 4
```

Sin uv global (macOS/Linux con Python ≥ 3.9), `sh scripts/bootstrap.sh` instala uv y Python dentro de `.tools/` y `.cache/` sin tocar tu PATH. A partir de ahí sustituye `uv` por `sh scripts/uv.sh`.

## Un documento mínimo

```json
{
  "schema_version": "1.0",
  "id": "sprite_demo",
  "revision": 0,
  "seed": 42,
  "canvas": {"width": 128, "height": 128, "profile": "strict"},
  "palette": {
    "id": "palette_main",
    "colors": [
      {"id": "ink", "rgba": "#182338FF"},
      {"id": "cloth", "rgba": "#36AFA5FF"}
    ],
    "ramps": []
  },
  "layers": [
    {
      "id": "body", "name": "Cuerpo", "visible": true, "locked": false,
      "opacity": 255, "blend": "normal",
      "operations": [
        {"id": "body_fill", "type": "rect", "box": [40, 32, 88, 104], "color": "cloth"}
      ]
    }
  ]
}
```

Es [examples/specs/minimal.moanart.json](examples/specs/minimal.moanart.json). Coordenadas enteras con origen arriba a la izquierda, cajas semiabiertas `[x0, y0, x1, y1)` y colores referenciados por ID de paleta. El esquema completo está en [schemas/](schemas/) y el contrato en [MOANART.md](MOANART.md).

## Línea de comandos

Cada comando imprime un único objeto JSON en stdout (`"ok"`, `"command"` y, si falla, `"error"` con código y puntero JSON):

| Comando | Qué hace |
| --- | --- |
| `moanart validate DOC` | valida y normaliza el documento |
| `moanart inspect DOC` | resume capas, paleta y presupuesto de render sin dibujar |
| `moanart render DOC` | renderiza en memoria e informa del digest (no escribe archivos) |
| `moanart export DOC OUT.png [--scale N]` | renderiza y escribe un PNG RGBA de forma atómica |
| `moanart edit DOC BATCH` | aplica un batch de edición y muestra la nueva revisión (no escribe archivos) |
| `moanart capabilities` | lista operaciones, comandos y codecs disponibles y previstos |

Códigos de salida: 0 éxito, 2 entrada inválida o capacidad no soportada, 3 presupuesto excedido, 4 conflicto de edición, 5 E/S, 1 error interno, 130 interrumpido.

## API de Python

```python
from moanart.api import apply_edit, export_png, load_document, render

document = load_document("examples/specs/minimal.moanart.json")
result = render(document)  # RGBA uint8 + digest + procedencia
print(result.digest)  # sha256:b080d367…
export_png(result, "artifacts/minimal.png", scale=4)

edited = apply_edit(document, "examples/specs/recolor.edit.json")
```

`moanart.api` es la fachada estable. El resto de módulos de [src/moanart/](src/moanart/) son contratos internos documentados en la [arquitectura](docs/architecture/overview.md).

## Qué incluye

- **Dibujo:** píxeles, rectángulos, elipses, líneas, polígonos, paths M/L/Q/C/Z (backend AggDraw `aggdraw-v1`) y transformaciones pixel-perfect.
- **Técnicas:** dithering Bayer 2×2/4×4, contornos interiores/exteriores, sombreado por bandas con luz discreta, materiales versionados (skin, cloth, metal, wood, stone) y contorno selectivo.
- **Estructura:** capas y grupos con composición source-over entera, máscaras y regiones semánticas por ID, paletas y rampas.
- **Edición:** batches atómicos con revisión optimista (`base_revision` + `base_snapshot`) y rollback total, e historial undo/redo con ramas.
- **Animación y exportación:** timeline con frames evaluados contra la base. Exporta a PNG, spritesheets con manifiesto reversible, GIF con pérdidas sólo explícitas, y APNG/WebP lossless si el build de Pillow tiene el codec.
- **Calidad:** informes con hard checks, advertencias artísticas configurables y análisis de clusters, sin puntuación agregada.
- **Proyectos:** persistencia confinada y atómica (directorio, ZIP `.moanart` o JSON) con migraciones explícitas que conservan el original. De momento sólo desde Python, sin CLI.
- **Seguridad:** límites de tamaño, profundidad y presupuesto comprobados antes de reservar memoria o tocar disco. Sin `eval`, `pickle` ni red en el núcleo ([modelo de amenazas](docs/architecture/SECURITY_MODEL.md), [política de seguridad](SECURITY.md)).

## Ejemplos

| Carpeta | Contenido |
| --- | --- |
| [examples/specs/](examples/specs/) | documentos de contrato por técnica (dither, paths, materiales, sombreado, animación) |
| [examples/tutorial/](examples/tutorial/) | poción 16 × 16 del [tutorial de flujos IA](docs/guides/ai-workflows.md), ejecutado tal cual por el gate |
| [examples/corpus/](examples/corpus/README.md) | corpus de referencia con procedencia, digests e informes de calidad |
| [examples/tiles/](examples/tiles/README.md) | tiles sin costuras y escena modular 128 × 128 con atlas |
| [examples/desk/](examples/desk/README.md) | escritorio isométrico 512 × 512 con su historial de edición |

## Desarrollo

```sh
uv run python scripts/validate.py      # gate completo: lock, lint, tipos, estructura, tests con cobertura y build
uv run python scripts/check_wheel.py   # audita e instala wheel y sdist en un entorno limpio
uv run pytest tests/unit -q            # validación por módulo
uv run pre-commit install              # hooks por checkout
```

La CI cubre Python 3.12–3.14 en Linux, macOS y Windows, más la verificación de determinismo entre plataformas. Antes de contribuir lee [CONTRIBUTING.md](CONTRIBUTING.md), [AGENTS.md](AGENTS.md) y la [guía de desarrollo](docs/guides/development.md).

## Documentación

- [MOANART.md](MOANART.md): fuente de verdad del producto y de los contratos.
- [Arquitectura](docs/architecture/overview.md), [contratos de módulos](docs/architecture/module-contracts.md) y [ADR](docs/architecture/README.md).
- [Roadmap](docs/issues/roadmap.md), [issues](docs/issues/README.md), [dependencias](docs/issues/dependency-map.md) y [trazabilidad](docs/issues/traceability.md).
- [Release](docs/RELEASE.md) y [CHANGELOG](CHANGELOG.md).
- Agentes: [CLAUDE.md](CLAUDE.md) y su [auditoría](docs/CLAUDE_CODE.md) para Claude Code. [AGENTS.md](AGENTS.md) y la [auditoría de entorno](docs/CODEX.md) para Codex.

## Licencia

[MIT](LICENSE) para código, documentación, ejemplos y corpus. Ninguna herramienta publica automáticamente: cada publicación (PyPI, releases o tags) requiere autorización explícita del propietario.
