# Seguridad

Moana está en diseño; no procesa todavía documentos gráficos. El contrato de seguridad está en MOANA.md §20 y el threat model en `docs/architecture/SECURITY_MODEL.md`.

No adjuntar secretos ni archivos personales a issues. Antes de publicar el repositorio, el propietario debe definir un canal privado de reporte y la política de versiones mantenidas; actualmente no existe un contacto de seguridad público configurado.

Las dependencias se fijan en uv.lock. Las actualizaciones se revisan con pruebas de codecs y entradas adversarias. JSON y assets serán datos no ejecutables, con presupuestos de CPU/memoria, rutas confinadas y escritura atómica. No se afirma que un sandbox del agente sustituya las validaciones del producto.
