# Passkey access with Authentik

The September 2026 setup uses Authentik 2026.8.2 instead of Nginx HTTP Basic.
Open [auth.beachlab.org](https://auth.beachlab.org/) to sign in.

| Application | URL |
| --- | --- |
| Deutsch Sprint | https://beachlab.org/deutsch/ |
| Whisper | https://beachlab.org/whisper/ |
| Qwen3-TTS | https://beachlab.org/tts/ |
| Downloads / Drop | https://beachlab.org/downloads/ (also `/drop/`) |
| Remote browser | https://beachlab.org/browser/ |
| ComfyUI | https://comfyui.beachlab.org/ |
| Barrakuda Designer | https://designer.daswerklab.de/ |
| Administration | https://admin.beachlab.org/ |

Transmission keeps its own web and RPC login so Remote GUI can connect over
HTTPS. The public websites keep their existing access.

## Access

The `fran` and `fran-jr` accounts have personal bindings in OR mode. Neither
account is an Authentik administrator. Four `forward_single` providers cover
the four hosts. The six Beachlab routes share a provider; the administration
panel has its own provider and permission.

The `beachlab-passkey` flow requires a resident WebAuthn credential and user
verification, with no password fallback. Sessions last 12 hours. There is no
public registration. The `www.beachlab.org` alias redirects to the canonical
host only on protected routes.

Fran's passkey is stored in Apple Passwords for `auth.beachlab.org`. Fran Jr
registers his own through the private onboarding link, then opens
`/if/flow/default-authenticator-webauthn-setup/`. Keep these links private.
Authentik access does not create native accounts in Grafana or Gotify.

Nginx uses [forward auth](https://docs.goauthentik.io/add-secure-apps/providers/proxy/forward_auth)
with the [Authentik Nginx integration](https://docs.goauthentik.io/add-secure-apps/providers/proxy/server_nginx/).
The [authenticator validation stage](https://docs.goauthentik.io/add-secure-apps/flows-stages/stages/authenticator_validate/)
controls the passwordless flow.

## Install paths

The configuration is in `services/authentik/`. On the NUC (`ssh pink-sudo`):

- `/opt/authentik/compose.yaml`: PostgreSQL 16, Authentik server and worker,
  following the [Compose setup](https://docs.goauthentik.io/install-config/install/docker-compose/).
- `/opt/authentik/.env`: secrets and provisioning token, mode 0600 inside a
  0700 directory. Keep it out of Git; use `docker compose config --quiet`.
- `authentik_database`: Docker volume for the database.
- `/opt/authentik/data`, `certs` and `custom-templates`: persistent files.
- `/etc/nginx/sites-available/auth.beachlab.org`: HTTPS to `127.0.0.1:19000`.
- `/etc/nginx/snippets/authentik-check.conf` and `authentik-outpost.conf`:
  proxy protection.

The Docker socket is not mounted. PostgreSQL has no published port;
Authentik's HTTP port is on localhost. Server and worker each have 2 GiB and
two CPU; PostgreSQL has 512 MiB and one CPU.

Containers resolve `auth.beachlab.org` through `host-gateway` to reach local
Nginx with valid TLS. The public `auth` CNAME points to `beachlab.org`.

Certbot uses `/var/www/letsencrypt`. Keep the HTTP ACME block for renewals.
`certbot.timer` runs the renewal and
`/etc/letsencrypt/renewal-hooks/deploy/50-authentik-nginx` validates and reloads
Nginx for the `auth` and `admin` certificates.

```bash
sudo docker compose --project-directory /opt/authentik -f /opt/authentik/compose.yaml ps
sudo docker compose --project-directory /opt/authentik -f /opt/authentik/compose.yaml config --quiet
sudo nginx -t
```

`configure.py` provisions the accounts, flow, applications and providers
through the local API. Review its declared permissions before running it again.

`switch-nginx.py prepare` prepares five files. `activate` checks Fran's
passkey, compares hashes, backs up the originals and validates Nginx before
reloading. It restores the files if validation or reload fails and leaves
`.htpasswd` files alone. This was the one-time migration; do not run it on
an already migrated configuration.

## Recovery and backups

If a passkey is lost, connect through SSH and create a temporary recovery link:

```bash
sudo docker exec authentik-server-1 ak create_recovery_key 15 fran
```

Open the returned path under `https://auth.beachlab.org`, register a new
passkey and try it in a fresh session. The same command accepts `akadmin`
for administrator recovery. Do not publish or commit the recovery link.

Back up PostgreSQL with `pg_dump`, plus `.env`, the persistent directories
and Nginx files. Restoring this deployment still needs testing.

The pre-migration Nginx files are in
`/opt/authentik/nginx-backup-20260914T111847Z/`. Restore each file to its
original path using `FILES` in `switch-nginx.py`, then run `nginx -t` and
reload. Check for later changes before restoring an old file. The original
Basic passwords are retained for recovery.

Signing in does not start GPU services or the browser. Use the
[administration panel](admin-panel.md) to start them.
