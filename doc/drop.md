# Drop

**Author:** Mr. Watson 🦄  
**Date:** 2026-07-23

## Objetivo

Página protegida que descarga una URL pública, guarda el archivo con nombre
aleatorio conservando la extensión y permite copiar el enlace o borrarlo.

URL:

```text
https://beachlab.org/drop/
```

Las credenciales están solo en `/etc/nginx/.htpasswd-drop`.

## Operación

```bash
sudo systemctl status url-drop
sudo journalctl -u url-drop -n 100 --no-pager
sudo systemctl restart url-drop
```

Archivos descargados:

```text
/var/lib/url-drop/files/
```

## Límites y seguridad

- Solo HTTP/HTTPS por puertos 80 y 443.
- Máximo 20 GiB por archivo.
- Reserva mínima de 5 GiB en disco.
- Dos descargas simultáneas; el resto espera en cola.
- Bloqueo de IP privadas, loopback, link-local, multicast y destinos reservados.
- Cada redirección se vuelve a validar.
- El servicio usa un socket Unix; no abre un puerto TCP.
- Nginx entrega los archivos mediante `X-Accel-Redirect`.
- Todo `/drop/`, incluidos los enlaces, requiere autenticación.

## Instalación

Código y unidad versionados:

```text
services/drop.py
services/drop.service
```

Despliegue:

```bash
sudo install -d -m 0755 /opt/url-drop
sudo install -m 0755 services/drop.py /opt/url-drop/drop.py
sudo install -m 0644 services/drop.service /etc/systemd/system/url-drop.service
sudo systemctl daemon-reload
sudo systemctl enable --now url-drop
```

Crear o cambiar las credenciales:

```bash
sudo htpasswd -cB /etc/nginx/.htpasswd-drop <usuario>
sudo chown root:www-data /etc/nginx/.htpasswd-drop
sudo chmod 0640 /etc/nginx/.htpasswd-drop
```

La ruta Nginx vive en `/etc/nginx/sites-available/beachlab.org`. Después de
cambiarla:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

## Pruebas

```bash
curl -I https://beachlab.org/drop/                  # 401
curl -u '<usuario>:<clave>' -I https://beachlab.org/drop/  # 200
```

Una URL privada debe rechazarse:

```bash
curl --unix-socket /run/url-drop/url-drop.sock \
  -H 'Content-Type: application/json' \
  -d '{"url":"http://127.0.0.1/"}' \
  http://localhost/api/download
```
