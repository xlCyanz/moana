# Benchmark de Moana (informativo)

Formato `moana-benchmark/1`; corpus `sha256:4409ea3f483260a13837177433d6b5b2a2f769df64fce1cdfd31799baa8ee284`.
5 warmups y 30 muestras por fase; p95 por rango más cercano; un proceso nuevo por caso.

Objetivos de MOANA.md §22: informativos hasta disponer de un runner estable. Los presupuestos de seguridad (§20) siguen vigentes aunque no se cumplan.

## Máquina

- CPU: Apple M4 (10 núcleos lógicos, arm64)
- SO: Darwin 25.6.0 (macOS 26.6.2)
- Python: CPython 3.12.16; numpy 2.5.5, Pillow 13.0.0, aggdraw 1.4.1, pydantic 2.14.3
- Moana 0.1.0.dev0, render-v1 (integer), budget-v8; commit `33ee89ee7b501a5941d6c16d7a0d05dc893bbf2b` (dirty: True); uv.lock `1fffab8bd7f25768d94164aad62be810e3ddcd526da8c5a9742656aa3e1b560c`

## Objetivos

| Objetivo | Límite | Medido | ¿Cumple? |
| --- | ---: | ---: | --- |
| static_render_median_ms | 100 | 30.11 | sí |
| animation_16_frames_median_ms | 2000 | 853.44 | sí |
| process_peak_rss_mib | 256 | 66.84 | sí |

## Fases (ms)

| Caso | Fase | min | mediana | p95 | max | media |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| static | encode_png | 1.69 | 1.71 | 1.74 | 1.74 | 1.71 |
| static | parse | 5.94 | 5.97 | 6.01 | 6.06 | 5.97 |
| static | render | 29.49 | 30.11 | 30.95 | 31.23 | 30.14 |
| static | write_png | 1.95 | 1.99 | 2.05 | 2.06 | 2.00 |
| animation | parse | 9.91 | 9.99 | 10.12 | 10.19 | 9.99 |
| animation | render | 848.28 | 853.44 | 869.82 | 881.33 | 854.53 |
| animation | render_frame | 29.26 | 29.81 | 30.20 | 50.35 | 29.86 |
| corpus/adventurer | encode_png | 0.17 | 0.19 | 0.22 | 0.22 | 0.19 |
| corpus/adventurer | parse | 1.58 | 1.62 | 1.66 | 1.71 | 1.63 |
| corpus/adventurer | render | 4.33 | 4.39 | 4.43 | 4.53 | 4.39 |
| corpus/adventurer | write_png | 0.38 | 0.41 | 0.45 | 0.46 | 0.42 |
| corpus/chest | encode_png | 0.15 | 0.16 | 0.19 | 0.20 | 0.16 |
| corpus/chest | parse | 0.91 | 0.93 | 1.00 | 1.01 | 0.94 |
| corpus/chest | render | 4.26 | 4.30 | 4.34 | 4.36 | 4.31 |
| corpus/chest | write_png | 0.36 | 0.40 | 0.47 | 0.52 | 0.41 |
| corpus/frog | encode_png | 0.17 | 0.18 | 0.20 | 0.20 | 0.18 |
| corpus/frog | parse | 0.88 | 0.90 | 0.93 | 0.95 | 0.90 |
| corpus/frog | render | 3.53 | 3.59 | 3.74 | 3.80 | 3.60 |
| corpus/frog | write_png | 0.38 | 0.41 | 0.49 | 0.52 | 0.42 |
| corpus/stone-tile | encode_png | 0.07 | 0.08 | 0.10 | 0.11 | 0.08 |
| corpus/stone-tile | parse | 0.94 | 0.96 | 0.99 | 1.00 | 0.96 |
| corpus/stone-tile | render | 2.85 | 2.89 | 3.02 | 3.07 | 2.90 |
| corpus/stone-tile | write_png | 0.29 | 0.32 | 0.38 | 0.39 | 0.32 |
| corpus/adventurer-walk | parse | 3.63 | 3.69 | 3.82 | 3.88 | 3.70 |
| corpus/adventurer-walk | render | 70.35 | 71.12 | 71.83 | 71.89 | 71.13 |
| corpus/adventurer-walk | render_frame | 4.36 | 4.43 | 4.48 | 4.51 | 4.43 |

## Memoria (MiB)

| Caso | Pico RSS del proceso | Fuente | Pico RSS antes del caso | Pico tracemalloc (sólo Python) |
| --- | ---: | --- | ---: | ---: |
| static | 61.1 | ru_maxrss | 57.7 | 1.0 |
| animation | 66.8 | ru_maxrss | 57.9 | 4.2 |
| corpus/adventurer | 60.2 | ru_maxrss | 57.7 | 0.2 |
| corpus/chest | 60.6 | ru_maxrss | 58.0 | 0.1 |
| corpus/frog | 60.3 | ru_maxrss | 57.7 | 0.1 |
| corpus/stone-tile | 60.3 | ru_maxrss | 57.9 | 0.1 |
| corpus/adventurer-walk | 59.4 | ru_maxrss | 57.8 | 0.7 |

## Casos adversos (presupuestos de §20)

| Caso | ¿Rechazado? | Recursos excedidos | Llamadas al rasterizador | Pico tracemalloc (KiB) |
| --- | --- | --- | ---: | ---: |
| cumulative_animation | sí | buffer_bytes, frame_pixels, pixel_visits | 0 | 60 |
| operations_over_limit | sí | operations | 0 | 764 |
| oversized_static | sí | pixel_visits | 0 | 768 |
