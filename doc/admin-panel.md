# Server administration

Open [admin.beachlab.org](https://admin.beachlab.org/) to see, start, stop and
open services. The code is in `services/admin-panel/`.

The switches change the running state. They do not enable or disable boot
startup.

Each switch shows what it starts and stops, including shared tools and the
effect of stopping a job. These descriptions come from `CONTROL_HINTS` in
[`control.py`](../services/admin-panel/control.py); they are also attached to
the switch for screen readers and included in search.

ComfyUI has one switch for Noct Q, the face/pose/clothing editors, Krea2,
SeedVR2, UniRig, Wan 2.1 and its other workflows. These are tools inside
`comfyui.service`, not separate services. The workflow files were confirmed
on the NUC under `/opt/comfyui/user/default/workflows/` on 2026-10-06; see
[the ComfyUI runbook](comfyui.md) for how to open them. Stopping ComfyUI
interrupts its running jobs.

## Access

Authentik protects the panel with its own `beachlab-admin` provider.
`fran` and `fran-jr` have personal OR (`any`) bindings and can operate all
services in the catalog. They are not Authentik administrators. Removing panel
access does not remove access to the other websites.

Fran Jr uses his private onboarding link to register a passkey at
`https://auth.beachlab.org/if/flow/default-authenticator-webauthn-setup/`.
Keep recovery links and credentials out of Git. Grafana, Gotify and other
applications with their own login still need native accounts.

## Services and dependencies

`control.py` contains the executable catalog; `sudoers` lists the allowed
root commands.

| Service | Control | Dependency |
| --- | --- | --- |
| ComfyUI | comfyui.service | Physical eGPU |
| Qwen3-TTS | qwen3-tts.service | Physical eGPU |
| Whisper | whisper-web.service | Physical eGPU |
| RAG library | rag-library-ingest.service | Physical eGPU |
| Transmission | transmission-vpn, existing Compose | Docker + built-in VPN |
| Remote browser | remote-browser.service | Docker + remote-browser-firewall.service |
| Drop | url-drop.service | None declared |
| Minecraft Java | minecraft-java.service | None declared |
| Grafana | grafana container | Docker |
| Gotify | gotify container | Docker |
| iGotify | igotify container | Docker + Gotify |
| TiTiler | titiler container | Docker |

Docker and the eGPU are displayed without a global switch. The panel allows
[one AI workload at a time](gpu-services.md), but cannot see GPU jobs started
manually outside its catalog.

Starting the browser keeps its systemd dependencies. iGotify starts Gotify
first; Gotify cannot stop while iGotify runs. Transmission's VPN stays inside
its container.

Minecraft uses `minecraft-java.service`, SIGINT and up to 120 seconds to save
the world. The old `minecraftjava.service` is not used. The game port is 25565.
Stopping Minecraft, Transmission or the browser requires confirmation.

A running container with a failed healthcheck shows **Revisar salud** and can
still be stopped. Check the application's logs to find the failure.

## Configuration

Nginx validates each request with Authentik and replaces
`X-Authentik-Username`. The Python API runs as `beachlab-admin` on
`/run/beachlab-admin/http.sock`, mode 0660 and group `www-data`, with no TCP
listener.

The React/Vite frontend refreshes every five seconds. A lost connection disables
the controls. A 401 renews the SSO session through normal navigation, without
repeating a pending operation. The CPU figure is one-minute load average.

POST requires the exact origin, JSON, a Secure/HttpOnly/SameSite=Strict cookie
and a user-bound HMAC token. GET does not change services. The root helper
`/usr/local/sbin/beachlab-admin-control` accepts fixed service IDs and
operations. Sudoers enumerates them; a lock serializes operations and checks
the state again. The service journal records user, service, action and result.

Code and build files live in `/opt/beachlab-admin`, owned by root. The CSRF key
is `/var/lib/beachlab-admin/csrf.key`. The helper needs sudo, so
`NoNewPrivileges=true` would break it. Do not give the HTTP user Docker socket
access.

## Update

Build and test from the repository:

```sh
npm ci --prefix services/admin-panel/frontend
npm run build --prefix services/admin-panel/frontend
python3 -m unittest discover -s services/admin-panel/tests -v
```

Copy `server.py`, `control.py` and `frontend/dist/` into `/opt/beachlab-admin/`
as root. Install:

- `control.py` as `/usr/local/sbin/beachlab-admin-control`, mode 0755.
- `sudoers` as `/etc/sudoers.d/beachlab-admin`, mode 0440.
- The unit as `/etc/systemd/system/beachlab-admin.service`.

Run `visudo -cf` before replacing sudoers. After a unit change, run
`systemctl daemon-reload` and restart the panel. Keep old JS/CSS hashes until
open sessions finish.

`provision-access.py` runs as root on the NUC and preserves other outpost
providers. It needs the existing Authentik instance and both users.
`authentik/configure.py` also preserves unrelated providers and updates
applications and flows by slug.

The `admin` CNAME points to `beachlab.org`. Certbot uses
`/var/www/letsencrypt` and stores the certificate under
`/etc/letsencrypt/live/admin.beachlab.org`. Install the vhost after issuing
the certificate, run `nginx -t` and reload. The renewal hook is
`services/authentik/renew-nginx.sh`.

To remove the panel, disable its vhost and unit and validate Nginx. The
controlled services keep running. Revoke its Authentik permissions separately.

## Transmission

Transmission uses its own RPC login for Remote GUI. The old
`protect-transmission.py` script added Authentik and was reverted on
2026-09-14. Only run it again when explicitly asked to change that access model.

The script writes the RPC secret include with mode 0600, backs up Nginx under
`/opt/authentik/nginx-before-transmission-*` and restores it if validation fails.
For the VPN healthcheck and Remote GUI setup, see [Transmission](transmission.md).
