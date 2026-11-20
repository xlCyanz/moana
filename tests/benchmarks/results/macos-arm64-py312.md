# Benchmark de Moana (informativo)

Formato `moana-benchmark/1`; corpus `sha256:4409ea3f483260a13837177433d6b5b2a2f769df64fce1cdfd31799baa8ee284`.
5 warmups y 30 muestras por fase; p95 por rango más cercano; un proceso nuevo por caso.

Objetivos de MOANA.md §22: informativos hasta disponer de un runner estable. Los presupuestos de seguridad (§20) siguen vigentes aunque no se cumplan.

## Máquina

- CPU: Apple M4 (10 núcleos lógicos, arm64)
- SO: Darwin 25.6.0 (macOS 26.6.2)
- Python: CPython 3.12.16; numpy 2.5.5, Pillow 13.0.0, aggdraw 1.4.1, pydantic 2.14.3
- Moana 0.1.0rc1, render-v1 (integer), budget-v8; commit `1d54429009fadd0812471802f49518a21095fa6e` (dirty: False); uv.lock `1fffab8bd7f25768d94164aad62be810e3ddcd526da8c5a9742656aa3e1b560c`

## Objetivos

| Objetivo | Límite | Medido | ¿Cumple? |
| --- | ---: | ---: | --- |
| static_render_median_ms | 100 | 30.34 | sí |
| animation_16_frames_median_ms | 2000 | 662.67 | sí |
| process_peak_rss_mib | 256 | 62.50 | sí |

## Fases (ms)

| Caso | Fase | min | mediana | p95 | max | media |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| static | encode_png | 1.64 | 1.71 | 1.81 | 1.84 | 1.71 |
| static | parse | 5.74 | 5.85 | 5.93 | 5.94 | 5.84 |
| static | render | 29.69 | 30.34 | 31.66 | 32.95 | 30.43 |
| static | write_png | 1.96 | 2.06 | 2.43 | 2.77 | 2.12 |
| animation | parse | 9.85 | 10.03 | 10.19 | 10.27 | 10.03 |
| animation | render | 654.94 | 662.67 | 759.17 | 847.50 | 676.42 |
| animation | render_frame | 29.67 | 30.47 | 33.89 | 80.20 | 31.27 |
| corpus/adventurer | encode_png | 0.20 | 0.21 | 0.37 | 0.57 | 0.23 |
| corpus/adventurer | parse | 1.59 | 1.63 | 1.69 | 1.73 | 1.63 |
| corpus/adventurer | render | 4.38 | 4.46 | 4.64 | 4.71 | 4.49 |
| corpus/adventurer | write_png | 0.45 | 0.62 | 0.90 | 1.27 | 0.63 |
| corpus/chest | encode_png | 0.17 | 0.22 | 0.32 | 0.36 | 0.23 |
| corpus/chest | parse | 0.90 | 0.93 | 1.02 | 1.03 | 0.94 |
| corpus/chest | render | 4.24 | 4.30 | 4.47 | 4.48 | 4.32 |
| corpus/chest | write_png | 0.38 | 0.44 | 0.56 | 0.58 | 0.45 |
| corpus/frog | encode_png | 0.18 | 0.19 | 0.23 | 0.25 | 0.20 |
| corpus/frog | parse | 0.87 | 0.89 | 0.97 | 1.19 | 0.91 |
| corpus/frog | render | 3.55 | 3.62 | 3.80 | 3.84 | 3.64 |
| corpus/frog | write_png | 0.40 | 0.49 | 0.65 | 0.71 | 0.51 |
| corpus/stone-tile | encode_png | 0.08 | 0.11 | 0.18 | 0.21 | 0.11 |
| corpus/stone-tile | parse | 0.95 | 0.97 | 1.00 | 1.03 | 0.98 |
| corpus/stone-tile | render | 2.86 | 2.94 | 3.04 | 3.10 | 2.95 |
| corpus/stone-tile | write_png | 0.32 | 0.37 | 0.45 | 0.51 | 0.37 |
| corpus/adventurer-walk | parse | 3.71 | 3.93 | 6.94 | 8.63 | 4.32 |
| corpus/adventurer-walk | render | 45.32 | 46.63 | 55.87 | 61.68 | 47.85 |
| corpus/adventurer-walk | render_frame | 4.36 | 4.54 | 5.14 | 34.26 | 4.93 |

## Memoria (MiB)

| Caso | Pico RSS del proceso | Fuente | Pico RSS antes del caso | Pico tracemalloc (sólo Python) |
| --- | ---: | --- | ---: | ---: |
| static | 56.3 | ru_maxrss | 53.3 | 1.0 |
| animation | 62.5 | ru_maxrss | 53.1 | 4.2 |
| corpus/adventurer | 55.2 | ru_maxrss | 53.0 | 0.2 |
| corpus/chest | 55.5 | ru_maxrss | 53.2 | 0.1 |
| corpus/frog | 55.4 | ru_maxrss | 53.2 | 0.1 |
| corpus/stone-tile | 55.2 | ru_maxrss | 53.2 | 0.1 |
| corpus/adventurer-walk | 55.0 | ru_maxrss | 53.2 | 0.7 |

## Casos adversos (presupuestos de §20)

| Caso | ¿Rechazado? | Recursos excedidos | Llamadas al rasterizador | Pico tracemalloc (KiB) |
| --- | --- | --- | ---: | ---: |
| cumulative_animation | sí | buffer_bytes, frame_pixels, pixel_visits | 0 | 60 |
| operations_over_limit | sí | operations | 0 | 764 |
| oversized_static | sí | pixel_visits | 0 | 768 |
