# Descargas y Drop

Página: https://beachlab.org/downloads/ . El acceso anterior
https://beachlab.org/drop/ sigue funcionando con la misma interfaz.
Ambas rutas, sus APIs y enlaces requieren la sesión [passkey de Authentik](authentik.md).

Permite navegar por carpetas, descargar archivos, borrar archivos o carpetas
(con confirmación de borrado definitivo) y añadir una URL pública HTTP/HTTPS.
Drop conserva su generación de nombres aleatorios con extensión. Las carpetas
ocultas, `.incomplete`, archivos `.part` y `.crdownload`, enlaces simbólicos y
archivos especiales no se muestran. Borrar archivos no elimina las entradas
correspondientes de Transmission: habrá que retirarlas allí si ya no se necesitan.

## Carpeta única

Transmission, Drop y Chromium guardan en `/home/pink/downloads`:

- Transmission: montaje existente `/downloads`.
- Chromium: montaje adicional `/config/Downloads` en
  [browser-compose.yml](../services/browser-compose.yml). Preferencia del perfil
  `download.default_directory=/config/Downloads` y `prompt_for_download=false`.
- Drop: [drop.service](../services/drop.service) ejecuta como `pink:www-data`.
  `BindPaths` expone la carpeta en `/var/lib/url-drop/files` dentro de su namespace;
  `ProtectHome=true` mantiene el resto de los hogares ocultos. `DROP_DIR` es esa
  ruta interna, no una segunda copia de los archivos.

Solo Transmission tiene la VPN de NordVPN. Compartir almacenamiento no cambia
las rutas de red de Drop o Chromium.

## Instalación y mantenimiento

Código: [drop.py](../services/drop.py). Servicio: `url-drop`.
Socket privado: `/run/url-drop/url-drop.sock` (0660, pink:www-data).
Nginx incluye [downloads-nginx.conf](../services/downloads-nginx.conf), instalado
como `/etc/nginx/snippets/downloads.conf` dentro del servidor HTTPS de beachlab.org.
No duplicar los antiguos bloques `/drop/` y `/drop-internal/` al incluirlo.
Nginx entrega los archivos mediante X-Accel-Redirect con `internal`,
`disable_symlinks on`, descarga como adjunto y CSP sandbox.

Dar a Nginx lectura de los archivos existentes y futuros sin cambiar propietarios:

```bash
sudo setfacl -R -m u:www-data:rX /home/pink/downloads
sudo find /home/pink/downloads -type d -exec setfacl -m d:u:www-data:rx {} +
sudo nginx -t
sudo systemctl daemon-reload
sudo systemctl restart url-drop
sudo systemctl reload nginx
```

Conservar las ACL al introducir archivos con herramientas externas. La aplicación
usa descriptores de directorio y O_NOFOLLOW para impedir escapes por enlaces;
el borrado recursivo es compatible con Python 3.10. Los POST requieren JSON,
`X-Drop-Request: 1` y rechazan Origin ajeno y Sec-Fetch-Site cross-site.
La autorización de usuario se aplica en Nginx; no publicar el socket por TCP.

El descargador conserva los límites de 20 GiB, reserva de 5 GiB, dos trabajos
simultáneos y validación de destinos públicos en cada redirección. La unidad
bloquea redes privadas mediante systemd. Consultar errores con
`journalctl -u url-drop`; `systemctl status url-drop` muestra el estado.

## Verificación del 2026-09-14

- Chromium tenía un archivo de aproximadamente 5,8 GB; se copió sin sobrescribir
  y `rsync -rcn` no mostró diferencias de contenido. Drop estaba vacío.
  Los originales permanecen en sus carpetas anteriores como respaldo.
- Chromium arrancó con `/config/Downloads` y la carpeta del host mostrando el
  mismo dispositivo/inodo. Un archivo creado como UID 1000 apareció en la API.
  Se devolvió Chromium a su estado inicial parado, con el montaje guardado.
- Safari abrió la página usando su sesión Authentik; se comprobó navegación,
  descarga por URL de example.com (559 bytes) y descarga de un archivo de prueba
  mediante Nginx (HTTP 200, 27 bytes). El borrado recursivo del fixture pasó por API.
- Sin sesión: página y API redirigen al login; ruta interna devuelve 404.
  Peticiones cross-origin devuelven 403 y rutas fuera de raíz devuelven 404.
- Tres pruebas de rutas, enlaces y borrado pasan tanto localmente como en el
  Python 3.10 del servidor. Vista de escritorio revisada; móvil no verificado.
- Transmission permaneció `healthy`. No se cambió su aislamiento VPN.

Backup de configuración anterior en el servidor:
`/opt/url-drop/backups/20260914T123117/`.
Antes de restaurarlo, revisar cambios posteriores y conservar la carpeta común.
