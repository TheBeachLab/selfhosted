# Navegador remoto

Autor: Mr. Watson

Chromium remoto accesible en:

```text
https://beachlab.org/browser/
```

Usa autenticación HTTP Basic propia, separada de Drop. El contenedor solo
publica su puerto HTTP en `127.0.0.1`; Nginx termina HTTPS y reenvía WebSocket.

## Archivos

```text
/srv/remote-browser/docker-compose.yml
/srv/remote-browser/config/
/usr/local/sbin/remote-browser-firewall
/etc/systemd/system/remote-browser.service
/etc/systemd/system/remote-browser-firewall.service
/etc/nginx/snippets/remote-browser.conf
/etc/nginx/.htpasswd-browser
```

El perfil y las cookies persisten bajo `/srv/remote-browser/config/`. Las
descargas quedan en `/srv/remote-browser/config/Downloads`. El panel lateral
permite subir y bajar archivos mediante la sección **Archivos**.
La unidad systemd prepara `Downloads` con modo `0755` y deja `/config` en `0711`
para que el Nginx interno pueda servir esa ruta sin poder listar el perfil.
Es una única sesión de navegador: no abrirla simultáneamente entre personas.
Las cookies y sesiones iniciadas quedan almacenadas en el servidor.

## Operación

Estado:

```bash
sudo systemctl status remote-browser remote-browser-firewall
sudo docker logs --tail 100 remote-browser
```

Actualizar:

```bash
cd /srv/remote-browser
sudo docker compose pull
sudo systemctl restart remote-browser
```

Reiniciar:

```bash
sudo systemctl restart remote-browser
```

## Seguridad

- Chromium corre aislado en Docker, sin montar el socket de Docker ni rutas del
  host salvo su directorio de configuración.
- Las credenciales son exclusivas de este servicio y solo se guardan como hash
  bcrypt en `/etc/nginx/.htpasswd-browser`.
- Terminales, `sudo` y las herramientas para abrir aplicaciones externas están
  deshabilitados explícitamente. No se usa `HARDEN_DESKTOP`, porque las
  versiones actuales de la imagen eliminan el gestor de archivos cuando está
  activo, incluso si `SELKIES_FILE_TRANSFERS` solicita habilitarlo.
- La red `172.31.250.0/28` no puede iniciar conexiones hacia rangos privados,
  loopback, link-local ni otras redes Docker.
- `remote-browser.service` arranca después del filtro de red; Docker no inicia
  el contenedor directamente.
- Compartir sesión, micrófono y gamepads están deshabilitados.
- El contenedor tiene límites de 3 GiB de RAM, dos CPU y 1024 procesos.

Comprobar el filtro:

```bash
sudo iptables -S REMOTE-BROWSER
sudo docker exec remote-browser curl -I --max-time 5 http://192.168.1.1
sudo docker exec remote-browser curl -I --max-time 10 https://example.com
```

El primer `curl` debe fallar y el segundo debe devolver una respuesta HTTP.
