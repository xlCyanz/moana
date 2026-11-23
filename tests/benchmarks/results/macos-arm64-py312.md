# Benchmark de MoanArt (informativo)

Formato `moanart-benchmark/1`; corpus `sha256:4409ea3f483260a13837177433d6b5b2a2f769df64fce1cdfd31799baa8ee284`.
5 warmups y 30 muestras por fase; p95 por rango más cercano; un proceso nuevo por caso.

Objetivos de MOANART.md §22: informativos hasta disponer de un runner estable. Los presupuestos de seguridad (§20) siguen vigentes aunque no se cumplan.

## Máquina

- CPU: Apple M4 (10 núcleos lógicos, arm64)
- SO: Darwin 27.2.0 (macOS 27.2.1)
- Python: CPython 3.12.16; numpy 2.5.5, Pillow 13.0.0, aggdraw 1.4.1, pydantic 2.14.3
- MoanArt 0.1.0rc2, render-v1 (integer), budget-v8; commit `dde4ff882ced4a38024e1c4369c4b5c5c93de866` (dirty: True); uv.lock `9c3fd8c5faf393c633cd950b42f58092fb023755a427cb459d9b30ae598fd103`

## Objetivos

| Objetivo | Límite | Medido | ¿Cumple? |
| --- | ---: | ---: | --- |
| static_render_median_ms | 100 | 29.73 | sí |
| animation_16_frames_median_ms | 2000 | 652.74 | sí |
| process_peak_rss_mib | 256 | 61.02 | sí |

## Fases (ms)

| Caso | Fase | min | mediana | p95 | max | media |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| static | encode_png | 1.60 | 1.66 | 1.78 | 1.86 | 1.68 |
| static | parse | 5.61 | 5.78 | 5.92 | 6.00 | 5.78 |
| static | render | 29.27 | 29.73 | 33.71 | 37.05 | 30.43 |
| static | write_png | 1.89 | 2.02 | 2.18 | 2.19 | 2.02 |
| animation | parse | 9.68 | 9.86 | 10.22 | 10.34 | 9.90 |
| animation | render | 648.37 | 652.74 | 667.79 | 673.19 | 655.03 |
| animation | render_frame | 29.16 | 29.76 | 30.77 | 34.66 | 29.89 |
| corpus/adventurer | encode_png | 0.17 | 0.19 | 0.24 | 0.29 | 0.20 |
| corpus/adventurer | parse | 1.55 | 1.60 | 1.69 | 1.70 | 1.60 |
| corpus/adventurer | render | 4.29 | 4.42 | 4.64 | 4.76 | 4.43 |
| corpus/adventurer | write_png | 0.44 | 0.51 | 0.74 | 1.44 | 0.58 |
| corpus/chest | encode_png | 0.18 | 0.20 | 0.28 | 0.35 | 0.22 |
| corpus/chest | parse | 0.89 | 0.90 | 0.98 | 1.00 | 0.91 |
| corpus/chest | render | 4.26 | 4.48 | 4.73 | 5.07 | 4.52 |
| corpus/chest | write_png | 0.45 | 0.54 | 0.70 | 0.78 | 0.56 |
| corpus/frog | encode_png | 0.20 | 0.25 | 0.34 | 0.71 | 0.27 |
| corpus/frog | parse | 0.88 | 0.92 | 0.99 | 1.00 | 0.93 |
| corpus/frog | render | 3.56 | 3.72 | 3.88 | 4.13 | 3.74 |
| corpus/frog | write_png | 0.58 | 0.68 | 0.79 | 0.80 | 0.67 |
| corpus/stone-tile | encode_png | 0.08 | 0.09 | 0.15 | 0.16 | 0.10 |
| corpus/stone-tile | parse | 0.95 | 1.00 | 1.11 | 1.24 | 1.01 |
| corpus/stone-tile | render | 2.81 | 2.92 | 3.19 | 3.43 | 2.96 |
| corpus/stone-tile | write_png | 0.34 | 0.38 | 0.49 | 0.50 | 0.40 |
| corpus/adventurer-walk | parse | 3.60 | 3.66 | 3.80 | 3.80 | 3.67 |
| corpus/adventurer-walk | render | 44.83 | 45.42 | 47.65 | 48.19 | 45.58 |
| corpus/adventurer-walk | render_frame | 4.31 | 4.41 | 4.54 | 5.11 | 4.42 |

## Memoria (MiB)

| Caso | Pico RSS del proceso | Fuente | Pico RSS antes del caso | Pico tracemalloc (sólo Python) |
| --- | ---: | --- | ---: | ---: |
| static | 54.8 | ru_maxrss | 51.5 | 1.0 |
| animation | 61.0 | ru_maxrss | 51.5 | 4.2 |
| corpus/adventurer | 53.6 | ru_maxrss | 51.2 | 0.2 |
| corpus/chest | 53.7 | ru_maxrss | 51.2 | 0.1 |
| corpus/frog | 54.3 | ru_maxrss | 51.6 | 0.1 |
| corpus/stone-tile | 53.4 | ru_maxrss | 51.2 | 0.1 |
| corpus/adventurer-walk | 53.1 | ru_maxrss | 51.2 | 0.7 |

## Casos adversos (presupuestos de §20)

| Caso | ¿Rechazado? | Recursos excedidos | Llamadas al rasterizador | Pico tracemalloc (KiB) |
| --- | --- | --- | ---: | ---: |
| cumulative_animation | sí | buffer_bytes, frame_pixels, pixel_visits | 0 | 60 |
| operations_over_limit | sí | operations | 0 | 764 |
| oversized_static | sí | pixel_visits | 0 | 768 |
