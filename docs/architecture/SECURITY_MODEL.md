# Modelo de amenazas

El núcleo opera sobre documentos no confiables; la aplicación anfitriona autoriza los paths de entrada/salida. Ningún documento concede permisos. Contrato normativo: MOANA.md §20.

| Amenaza | Frontera | Mitigación prevista | Evidencia |
| --- | --- | --- | --- |
| Campos/código arbitrarios | JSON → modelo | strict, extra forbid, lista explícita de operaciones, sin eval | MOA-002/030 |
| Coordenadas/áreas enormes | modelo → plan | límites y coste antes de buffers, int64/Python int | MOA-003/004 |
| Ciclos/referencias ocultas | resolución → render | DAG y unicidad global | MOA-002/013 |
| Memoria/CPU excesivos | plan → raster | presupuesto de temporales, visitas, deadline y proceso anfitrión | MOA-003/030 |
| Decompression bomb | asset → Pillow | dimensiones/frames/bytes antes del decode, límites Pillow | MOA-020/030 |
| Zip slip/symlink/ratio | ZIP → filesystem | allowlist de rutas/entradas, resolver raíz, límite expansión | MOA-020/030 |
| Pérdida parcial al guardar | export/project → disco | temporal hermano, commit atómico, no overwrite por defecto | MOA-011/020 |
| Edición obsoleta/parcial | batch → documento | base_revision y validación transaccional | MOA-018/019 |
| Dependencia comprometida | instalación/CI | lock con hashes, revisión de updates, CI sin secretos de escritura | MOA-000/035 |

Un checksum verifica integridad, no autoría. No se procesan documentos mediante pickle. El CLI no debe filtrar secretos en traceback por defecto. El servicio futuro necesita aislamiento del SO; el render in-process no garantiza interrumpir una librería nativa bloqueada.

La inicialización sólo implementa controles del tooling; las mitigaciones de producto son trabajo de los issues listados. Las pruebas adversarias deben verificar rechazo antes de la reserva/IO y dejar los archivos originales intactos.
