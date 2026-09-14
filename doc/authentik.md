# Acceso web con passkey

## Estado y alcance

Desde el 14 de septiembre de 2026, Authentik 2026.8.2 protege estos accesos
mediante passkey, sustituyendo el HTTP Basic de Nginx:

| Aplicación | URL |
| --- | --- |
| Deutsch Sprint | https://beachlab.org/deutsch/ |
| Whisper | https://beachlab.org/whisper/ |
| Qwen3-TTS | https://beachlab.org/tts/ |
| Drop | https://beachlab.org/drop/ |
| Navegador remoto | https://beachlab.org/browser/ |
| ComfyUI | https://comfyui.beachlab.org/ |
| Barrakuda Designer | https://designer.daswerklab.de/ |

Portal: https://auth.beachlab.org/ . La cuenta `fran` tiene una passkey
registrada en Apple Passwords para el RP `auth.beachlab.org`. No es administrador.
Tres proveedores `forward_single` cubren los tres hosts; las cinco rutas de
Beachlab comparten proveedor y permisos. Las aplicaciones están restringidas
explícitamente a `fran`. La web pública y las demás aplicaciones no se migraron.
El alias `www.beachlab.org` se redirige al host canónico solo en las rutas protegidas.

El flujo `beachlab-passkey` exige WebAuthn con verificación del usuario y
credencial residente; no acepta contraseña como alternativa. La sesión dura
12 horas. No hay registro público. El acceso de emergencia se realiza por SSH.

Fuentes de implementación consultadas el 2026-09-14:
- [Forward auth](https://docs.goauthentik.io/add-secure-apps/providers/proxy/forward_auth).
- [Integración Nginx](https://docs.goauthentik.io/add-secure-apps/providers/proxy/server_nginx/).
- [Flujo sin contraseña](https://docs.goauthentik.io/add-secure-apps/flows-stages/stages/authenticator_validate/).
- [Instalación Compose](https://docs.goauthentik.io/install-config/install/docker-compose/).

## Despliegue

Configuración versionada: `services/authentik/`.
En el NUC (`ssh pink-sudo`):

- `/opt/authentik/compose.yaml`: PostgreSQL 16, servidor y worker Authentik.
- `/opt/authentik/.env`: secretos aleatorios y token de aprovisionamiento, modo 0600;
  directorio padre 0700. Nunca copiar a Git ni mostrar con `docker compose config`.
- `authentik_database`: volumen Docker con la base de datos.
- `/opt/authentik/data`, `certs`, `custom-templates`: datos persistentes.
- `/etc/nginx/sites-available/auth.beachlab.org`: HTTPS hacia `127.0.0.1:19000`.
- `/etc/nginx/snippets/authentik-check.conf` y `authentik-outpost.conf`: protección.

No se monta el socket Docker. PostgreSQL no publica puertos y Authentik solo
publica HTTP en loopback. Límites: servidor y worker 2 GiB/2 CPU cada uno;
PostgreSQL 512 MiB/1 CPU. Los contenedores resuelven `auth.beachlab.org` mediante
`host-gateway` para llegar al Nginx local con TLS válido, sin depender del DNS
recursivo ni del NAT de retorno. El CNAME público `auth` apunta a `beachlab.org`.

El certificado usa Certbot webroot `/var/www/letsencrypt`; conservar el bloque
ACME de HTTP para renovaciones. `certbot.timer` está activo y el hook
`/etc/letsencrypt/renewal-hooks/deploy/50-authentik-nginx` valida y recarga Nginx
solo al renovar este certificado. El hook se ejecutó correctamente en la instalación.

```bash
sudo docker compose --project-directory /opt/authentik -f /opt/authentik/compose.yaml ps
sudo docker compose --project-directory /opt/authentik -f /opt/authentik/compose.yaml config --quiet
sudo nginx -t
```

El script `configure.py` configura cuenta, flujo, aplicaciones y proveedores
por la API local autenticada. Está diseñado para este despliegue: revisar sus
valores antes de volver a ejecutarlo, pues establece los permisos declarados.
El script `switch-nginx.py prepare` prepara cinco archivos sin activar cambios;
`activate` verifica una passkey de `fran` para el RP correcto, compara hashes,
guarda originales y valida Nginx antes de recargar. Es una migración de una sola
vez: no ejecutarla sobre una configuración ya migrada. Un fallo de validación o
recarga restaura los originales. No se leen ni borran los `.htpasswd`.

## Recuperación y copias

Si se pierde la passkey, desde una sesión SSH autorizada:

```bash
sudo docker exec authentik-server-1 ak create_recovery_key 15 fran
```

El comando entrega una ruta temporal de acceso: abrirla bajo
`https://auth.beachlab.org`, registrar una nueva passkey en
`/if/flow/default-authenticator-webauthn-setup/` y probarla en una sesión nueva.
No publicar, versionar ni compartir ese enlace. Para administración de emergencia,
el mismo comando admite `akadmin`; reservarlo para administración autorizada.

Incluir en las copias privadas la base de datos PostgreSQL (mediante `pg_dump`),
`.env`, los directorios persistentes y los archivos Nginx. No basta con copiar el
Compose. No se ha probado una restauración de Authentik en este despliegue.

Originales previos al cambio:
`/opt/authentik/nginx-backup-20260914T111847Z/`. Para revertir, restaurar cada
archivo en su ruta original según `FILES` de `switch-nginx.py`, ejecutar
`nginx -t` y recargar Nginx. Las contraseñas Basic originales siguen disponibles.
No restaurar sin comprobar antes si hubo cambios posteriores de otros trabajos.

## Verificación realizada

- Los tres contenedores estaban saludables; Compose y Nginx validaron.
- Las siete URLs sin sesión terminaron en el flujo HTTPS `beachlab-passkey`.
- Se registró Apple Passwords para `fran` y `auth.beachlab.org`.
- A las 11:20 UTC, Authentik registró un login `auth_webauthn_pwl` de `fran`;
  Nginx sirvió `/deutsch/` y sus JS/CSS con 200 inmediatamente después.
- El usuario confirmó el acceso desde una ventana privada. El alias `www` y los
  recursos de Deutsch mantuvieron la protección con cookies/cabeceras inválidas.
- Las páginas públicas raíz de Beachlab y Das Werklab siguieron respondiendo 200.

El acceso real con passkey se verificó con Deutsch Sprint. No equivale a una
prueba funcional completa de las siete aplicaciones: al comprobar los upstreams,
Whisper, TTS, ComfyUI y el navegador remoto estaban apagados (conexión rechazada).
Su arranque sigue sus procedimientos propios; la migración de autenticación no
arranca servicios GPU ni cambia su ciclo de trabajo.
