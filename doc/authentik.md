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
| Msgvault (Fran only) | https://msgvault.beachlab.org/ |

Transmission keeps its own web and RPC login so Remote GUI can connect over
HTTPS. The public websites keep their existing access.

## Access

The shared applications use personal bindings for `fran` and `fran-jr` in OR
mode. Neither account is an Authentik administrator. Five `forward_single` providers cover
the five hosts. The six Beachlab routes share a provider; the administration
panel has its own provider and permission. Msgvault has a separate provider
and grants archive access only to `fran`; see [its runbook](msgvault.md).
Source for the 2026-10-10 addition: Authentik proxy providers, applications,
policy bindings and embedded-outpost API readback on the NUC.

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

## Beach Lab branding

`services/authentik/branding.py` applies the identity of
[beachlab.org](https://beachlab.org/) to the existing login page using
[Authentik 2026.8 branding](https://version-2026-8.goauthentik.io/customize/branding/).
The original orange logo, yellow water, favicon and Univers fonts are in
`services/authentik/branding/`; asset provenance and hashes are recorded in
`branding/SOURCES.md`.

The login stays on the site's yellow water background in both light and dark
browser themes, matching the public site's header. The form is transparent
and centered, with the original logo and Univers typography. Authentik keeps
the passkey prompt, status messages, retry button, language selector and footer.
CSS adds no replacement text and hides no authentication errors.

Only `branding_logo`, `branding_favicon`, `branding_default_flow_background`
and `branding_custom_css` are patched. The existing title `Beachlab`, flow
assignments, credentials, permissions and WebAuthn relying party are preserved.
The script identifies the brand matched by `auth.beachlab.org`, accepts its
explicit domain or the established `authentik-default` fallback, and requires
the installed version to be `2026.8.2` and authentication flow to be
`beachlab-passkey`. Inspection on 2026-10-08 found the default brand, and the
flow's own `background` was empty, so it inherits the brand background.

Keep the source package's relative paths when installing: place `branding.py`
and its sibling `branding/` directory under `/opt/authentik/`. Running the
script requires root to read the existing provisioning token from `.env`.
Neither the token nor signed file URLs are logged.

```bash
sudo python3 /opt/authentik/branding.py --dry-run
sudo python3 /opt/authentik/branding.py --apply
```

The default action is also a read-only plan. Applying first creates a private
JSON backup in `/opt/authentik/branding-backups/` (directory 0700, file 0600),
then uploads three immutable media files through Authentik's native Files API.
It verifies the uploaded bytes, rechecks that the brand has not changed since
the plan, patches the four appearance fields and reads them back. All other
brand fields must remain identical. Reapplying the same package makes no
changes. The media folder includes a content digest, so later designs do not
overwrite the previous assets.

The [file picker](https://version-2026-8.goauthentik.io/customize/file-picker/)
uses relative media paths and serves signed URLs. Fonts are embedded in the
brand CSS to avoid cross-origin requests and expired media URLs. No Nginx
change or container restart is required. The CSS uses flow component
selectors and the public `main`, `branding`, `footer`, `locale-select` and
status parts; review them when upgrading Authentik. The 2026.8.2 implementation
injects brand CSS into each component's shadow root in
[web/src/elements/Base.ts](https://github.com/goauthentik/authentik/blob/version/2026.8.2/web/src/elements/Base.ts)
and into the document in
[base/skeleton.html](https://github.com/goauthentik/authentik/blob/version/2026.8.2/authentik/core/templates/base/skeleton.html).
The API's Django REST Framework `CharField` trims surrounding whitespace;
the script sends stripped CSS and normalizes backup CSS before rollback.
Authentik's
[global reset](https://github.com/goauthentik/authentik/blob/version/2026.8.2/web/src/styles/global/reset/globals.css)
enables the flow background on `body::before` only at widths of at least
`35rem` and heights of at least `17.5rem`. Beach Lab CSS applies the same
resolved brand image at every size, retaining the water on narrow screens.
The existing profile-switch link is dark and underlined, with a visible focus
outline; its label and behavior remain Authentik's.

After applying, open a fresh session at
[the passkey flow](https://auth.beachlab.org/if/flow/beachlab-passkey/).
Check desktop and narrow screens, light and dark browser themes, readable
status/error messages, the language selector and keyboard focus on retry.
Use native Safari for passkey checks. Do not open passkey flows in agents'
internal browsers; this is the user's explicit browser preference. Safari
Responsive Design can check the layout at 390 x 844 without changing the flow.
Confirm the original title `Accede con tu passkey` and the same passkey
challenge. The native Touch ID/Face ID dialog belongs to the browser and
operating system; the branding covers Authentik's page.

To restore the previous appearance, use the exact backup path printed during
application:

```bash
sudo python3 /opt/authentik/branding.py --rollback /opt/authentik/branding-backups/<backup>.json
```

Rollback requires the current appearance to match that backup's applied values,
so it refuses to overwrite a later design. It restores only the four appearance
fields, verifies the readback and preserves all current non-branding fields.
Uploaded media is retained for recovery. Authentik recovery sessions also
disable custom CSS, as implemented by
[CurrentBrandSerializer](https://github.com/goauthentik/authentik/blob/version/2026.8.2/authentik/brands/api.py).
