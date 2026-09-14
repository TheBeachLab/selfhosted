# Administración del servidor

Panel desplegado el 2026-09-14: https://admin.beachlab.org/ . Código en
`services/admin-panel/`. Permite consultar estado, encender/apagar y abrir servicios.
Los interruptores cambian el estado actual: no ejecutan `enable`/`disable` ni
modifican las políticas de arranque existentes.

## Acceso

Authentik protege el host con un proveedor independiente `beachlab-admin`.
Fran (`fran`) y Fran Jr (`fran-jr`) tienen bindings personales en modo OR (`any`).
Ambos pueden operar todos los servicios del catálogo. No son administradores de
Authentik. El permiso del panel se puede retirar sin retirar el acceso a las webs.

Fran Jr se incorpora mediante un enlace temporal privado y registra su propia
passkey en https://auth.beachlab.org/if/flow/default-authenticator-webauthn-setup/ .
No se versionan enlaces de recuperación ni credenciales. El acceso Authentik no
crea cuentas nativas en Grafana, Gotify u otros productos con login propio.

## Catálogo y dependencias

Inventario comprobado directamente con `systemctl show/cat`, `docker inspect` y
los Compose existentes en el NUC el 2026-09-14. La lista ejecutable está en
`control.py`; la lista sudo exacta está en `sudoers`.

| Servicio | Control | Dependencia |
| --- | --- | --- |
| ComfyUI | comfyui.service | eGPU física |
| Qwen3-TTS | qwen3-tts.service | eGPU física |
| Whisper | whisper-web.service | eGPU física |
| Biblioteca RAG | rag-library-ingest.service | eGPU física |
| Transmission | transmission-vpn, Compose existente | Docker + VPN integrada |
| Navegador remoto | remote-browser.service | Docker + remote-browser-firewall.service |
| Drop | url-drop.service | ninguna declarada |
| Minecraft Java | minecraft-java.service | ninguna declarada |
| Grafana | contenedor grafana | Docker |
| Gotify | contenedor gotify | Docker |
| iGotify | contenedor igotify | Docker + Gotify |
| TiTiler | contenedor titiler | Docker |

La eGPU y Docker se observan, sin interruptor global. El panel aplica la política
[una carga IA a la vez](gpu-services.md); rechaza un segundo arranque mientras otra
carga figura activa. No detecta trabajos GPU iniciados manualmente fuera del catálogo.
El arranque del navegador conserva las dependencias de su unidad systemd. iGotify
arranca Gotify primero; Gotify no se puede apagar mientras iGotify esté activo.
La VPN va dentro de Transmission y no puede apagarse por separado.

Minecraft usa la unidad Fabric actual, con SIGINT y hasta 120 s para guardar el
mundo; no usa la unidad antigua `minecraftjava.service`. Se comprobó `server-port=25565`.
El panel pide confirmación antes de apagar Minecraft, Transmission o el navegador.
Un contenedor activo con healthcheck fallido aparece como **Revisar salud** y
mantiene disponible el apagado. Activo no equivale a una prueba funcional completa.

## Arquitectura y mantenimiento

- Nginx valida cada petición con Authentik y sobrescribe `X-Authentik-Username`.
- API Python sin dependencias externas, usuario `beachlab-admin`, socket Unix
  `/run/beachlab-admin/http.sock` con permisos 0660, grupo `www-data`; sin puerto TCP.
- Frontend React/Vite con datos consultados cada 5 s. Pérdida de conexión desactiva
  controles. CPU es carga media de un minuto, no porcentaje de utilización.
- POST exige origen exacto, JSON, cookie Secure/HttpOnly/SameSite=Strict y token
  HMAC vinculado al usuario. GET no cambia servicios.
- El helper root `/usr/local/sbin/beachlab-admin-control` acepta solo IDs y
  operaciones fijos. No interpreta comandos shell ni rutas del cliente. Sudoers
  enumera cada comando. Un lock serializa operaciones y revalida el estado.
- Los diarios de `beachlab-admin.service` registran actor, servicio, acción y resultado.
- Código y build: `/opt/beachlab-admin`, propiedad root. Clave CSRF persistente
  privada: `/var/lib/beachlab-admin/csrf.key`.
- El servicio requiere sudo: no añadir `NoNewPrivileges=true` sin cambiar el
  mecanismo del helper. No conceder acceso al socket Docker al usuario HTTP.

Para actualizar desde un checkout revisado, compilar localmente:

```sh
npm ci --prefix services/admin-panel/frontend
npm run build --prefix services/admin-panel/frontend
python3 -m unittest discover -s services/admin-panel/tests -v
```

Copiar `server.py`, `control.py` y `frontend/dist/` a `/opt/beachlab-admin/` como
root; instalar `control.py` en `/usr/local/sbin/beachlab-admin-control` (0755),
`sudoers` en `/etc/sudoers.d/beachlab-admin` (0440), y la unidad en
`/etc/systemd/system/beachlab-admin.service`. Validar `visudo -cf` antes de sustituir
sudoers. Tras cambiar la unidad: `systemctl daemon-reload`; reiniciar solo el panel.
Conservar hashes antiguos de JS/CSS hasta que terminen las sesiones abiertas.

`provision-access.py`, ejecutado como root en el NUC, configura el proveedor y
preserva los demás proveedores del outpost. Requiere el Authentik existente y sus
dos usuarios. `authentik/configure.py` también preserva proveedores ajenos y usa
slugs para actualizar aplicaciones y flujos; se volvió a ejecutar con éxito.

El CNAME `admin` apunta a `beachlab.org`. Certbot usa webroot
`/var/www/letsencrypt`; certificado en `/etc/letsencrypt/live/admin.beachlab.org`.
El hook versionado `services/authentik/renew-nginx.sh` recarga Nginx para `auth` y
`admin`. Instalar el vhost después de emitir el certificado, validar `nginx -t` y
recargar. Para retirar el panel: desactivar su vhost y su unidad, validando Nginx;
esto no detiene los servicios controlados. Conservar los permisos de Authentik
hasta decidir expresamente su revocación.

## Transmission y verificación

La prueba real del usuario arrancó Transmission desde el panel. Se verificó la
web local y pública con HTTP 200 usando las credenciales existentes; el túnel
estaba levantado y una petición HTTPS desde el contenedor funcionó. El healthcheck
de la imagen falló en `nslookup google.com`: devolvió A y NXDOMAIN, saliendo con
error. No se considera validado el funcionamiento de todos los trackers ni la
resolución general DNS. No se desactivó el healthcheck ni se reinició el contenedor
para ocultar esta advertencia.

`protect-transmission.py` añadió Authentik al location existente, manteniendo
la autenticación RPC del upstream. Genera un include root 0600 con la credencial
existente de `rpc_creds`, nunca incorporada al repositorio. Reejecutar al rotar esa
credencial. Hace copia de Nginx bajo `/opt/authentik/nginx-before-transmission-*`
y restaura el archivo si falla la validación. La web se abrió en Safari con la
sesión passkey de Fran y mostró la interfaz y sus transferencias.

Verificaciones del 2026-09-14:

- 10 pruebas de controlador/CSRF y build Vite correctos.
- API desplegada: sin identidad 401; origen/CSRF inválidos 403; ID fuera de la
  lista 404. Cabecera de identidad falsificada desde Internet redirige al login.
- Arranque real de Whisper mediante la API: 200; web local: 200; apagado: 200,
  restaurando el estado inactivo. Minecraft y servicios compartidos no se detuvieron.
- API Authentik: los diez registros de aplicaciones incluyen Fran y Fran Jr en
  modo `any`; el outpost conserva cuatro proveedores (incluido administración).
- Safari autenticado: panel con 12 servicios; Transmission accesible por passkey.
- Vista local del mismo build con snapshot del servidor y acciones deshabilitadas:
  búsqueda, confirmación/cancelación, persistencia de errores, 390 px sin desborde
  horizontal; consola sin errores. La revisión móvil no prueba login WebAuthn móvil.

Diseño contrastado con el concepto generado antes de implementar: cabecera compacta,
título y métricas, paleta clara con azul, filas alineadas y jerarquía de dependencias
se conservan. Diferencias deliberadas: 12 servicios reales frente a 7 del concepto,
puerto de Minecraft para copiar, advertencia de salud y estados reales. Las capturas
de QA se inspeccionaron en escritorio y móvil; no se incorporan datos de prueba al
frontend desplegado.
