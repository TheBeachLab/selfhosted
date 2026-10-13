# Buchhaltung: repositorio propio

El software propio de contabilidad está en el repositorio privado
[TheBeachLab/buchhaltung](https://github.com/TheBeachLab/buchhaltung).
Desde el 13 de octubre de 2026 su implementación deja de estar en
`selfhosted/services/buchhaltung`.

- Carpeta local: `/Users/Papi/Repositories/buchhaltung`.
- [README y comprobaciones](https://github.com/TheBeachLab/buchhaltung/blob/main/README.md).
- [Runbook canónico](https://github.com/TheBeachLab/buchhaltung/blob/main/docs/operations.md).
- [Procedencia e historial](https://github.com/TheBeachLab/buchhaltung/blob/main/docs/migration.md).
- Aplicación privada: https://buchhaltung.beachlab.org/.

## Rutas del NUC

La separación del repositorio no cambia el runtime ni los datos:

- Código activo: `/opt/buchhaltung/current`, bajo `/opt/buchhaltung/releases/`.
- Servicio: `buchhaltung.service`; copias: `buchhaltung-backup.service` y timer.
- Datos y originales privados: `/var/lib/buchhaltung`.
- Credenciales: `/etc/buchhaltung/private.env`; no mostrarlas ni copiarlas a Git.
- Copias cifradas: directorio dedicado `backups/buchhaltung-encrypted` del NAS.

Antes de operar, lee el runbook del repositorio propio y comprueba la release,
el servicio, la importación y la copia actuales. La lectura del 13 de octubre
confirmó el servicio activo en la release
`e57731bd2d3146c1907bfb9327bb6e5c3758ab45`; es una observación fechada.
El código, sus pruebas y su documentación de aplicación se mantienen allí.
