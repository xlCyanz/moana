# Modelo de amenazas

El núcleo opera sobre documentos no confiables; la aplicación anfitriona autoriza los paths de entrada/salida. Ningún documento concede permisos. Contrato normativo: MOANA.md §20.

Los nombres que elige el llamador deben codificarse en UTF-8 estricto en todas las plataformas, y los nombres de entradas ZIP se validan sobre el nombre almacenado (NUL y barra invertida son `invalid_name`): [ADR-039](decisions/ADR-039-ci-matrix-portability.md).

| Amenaza | Frontera | Mitigación prevista | Evidencia |
| --- | --- | --- | --- |
| Campos/código arbitrarios | JSON → modelo | strict, extra forbid, lista explícita de operaciones, sin eval | MOANA-002/030 |
| Coordenadas/áreas enormes | modelo → plan | límites y coste antes de buffers, int64/Python int | MOANA-003/004 |
| Ciclos/referencias ocultas | resolución → render | DAG y unicidad global | MOANA-002/013 |
| Memoria/CPU excesivos | plan → raster | presupuesto de temporales, visitas, deadline y proceso anfitrión | MOANA-003/030 |
| Decompression bomb | asset → Pillow | dimensiones/frames/bytes antes del decode, límites Pillow | MOANA-020/030 |
| Atlas o manifiesto hostil | spritesheet → frames | manifiesto acotado y estricto, IHDR y presupuesto antes del decode, digests | MOANA-023/030 |
| Zip slip/symlink/ratio | ZIP → filesystem | allowlist de rutas/entradas, resolver raíz, límite expansión | MOANA-020/030 |
| Pérdida parcial al guardar | export/project → disco | temporal hermano, commit atómico, no overwrite por defecto | MOANA-011/020 |
| Edición obsoleta/parcial | batch → documento | base_revision + base_snapshot y validación transaccional | MOANA-018/019 |
| Dependencia comprometida | instalación/CI | lock con hashes, revisión de updates, CI sin secretos de escritura | MOANA-000/035 |

Un checksum verifica integridad, no autoría. No se procesan documentos mediante pickle. El CLI no debe filtrar secretos en traceback por defecto. El servicio futuro necesita aislamiento del SO; el render in-process no garantiza interrumpir una librería nativa bloqueada.

La inicialización sólo implementa controles del tooling; las mitigaciones de producto son trabajo de los issues listados. Las pruebas adversarias deben verificar rechazo antes de la reserva/IO y dejar los archivos originales intactos.

## Cobertura adversaria (MOANA-030)

La suite [`tests/security/`](../../tests/security/README.md) (marker `security`) ejercita cada frontera de la tabla con un caso reproducible: un corpus malicioso versionado y generado en memoria, propiedades Hypothesis acotadas y trampas que fallan si una entrada hostil llega a reservar buffers (NumPy/Pillow) o a escribir en disco antes de ser rechazada. También comprueba que el destino queda intacto ante fallos de IO inyectados y que ningún error revela rutas ni secretos. El mapa frontera → mitigación → pruebas vive en su README y `test_threat_coverage.py` lo mantiene sincronizado con esta tabla.
