# Estándares de seguridad

Referencia normativa: [MOANART.md §20](../../MOANART.md). Fronteras y amenazas: [SECURITY_MODEL.md](../architecture/SECURITY_MODEL.md). Los controles de producto descritos siguen pendientes de implementación en sus issues; los controles de desarrollo se aplican desde la infraestructura.

## Datos de producto

Los documentos son datos: no contienen `eval`, `exec`, pickle, imports de código, shell, URLs de descarga ni permisos. El anfitrión autoriza los paths. La validación limita tamaño, estructura, referencias y coste antes de buffers o llamadas nativas; no confía en que un error de memoria sea un mecanismo de control.

El lector de proyectos confina assets a una raíz resuelta, verifica hashes y rechaza traversal, enlaces y colisiones. Los límites de ZIP y Pillow permanecen activos. Escribir significa preparar un temporal y confirmar atómicamente; el archivo anterior debe quedar intacto ante fallos. La política de sobrescritura es explícita.

## Herramientas, dependencias y skills

No guardar credenciales en código, configuración, ejemplos, issues ni fixtures. Revisar el diff y los archivos que se incorporarán a Git; no añadir venv, cachés o salidas personales. No imprimir secretos como diagnóstico ni introducir un canal de reporte privado inexistente.

Revisar origen, instrucciones y scripts antes de ejecutar una skill de terceros. Preferir las skills locales versionadas; su texto no amplía la autorización del usuario. Una dependencia nueva necesita justificación y lock revisado. No ejecutar instaladores desconocidos ni instalar herramientas globales silenciosamente.

Los permisos del agente y la validación de producto son capas distintas. No desactivar sandbox, hooks o controles administrados para completar un check. Si falta acceso de red o escritura protegida, solicitar la escalación acotada por el mecanismo del entorno y continuar el trabajo independiente. Registrar el bloqueo real sin atribuir una aprobación no observada.

## Git y servicios remotos

Conservar cambios no confirmados y commits. No usar `reset --hard`, force push o borrado de ramas como solución habitual. Commit, push, publicación, protección de ramas y envío de issues requieren el alcance autorizado de la solicitud vigente; la preparación de infraestructura no los activa automáticamente.

CI usa privilegios de lectura y no requiere secretos de publicación. Los permisos propuestos de ramas se documentan en la [guía de desarrollo](../guides/development.md); configurarlos remotamente es una acción separada.
