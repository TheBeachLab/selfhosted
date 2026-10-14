# Vaultwarden

Open [passwords.beachlab.org](https://passwords.beachlab.org/) and use
**hola@beachlab.org → master password**. SSO is temporarily disabled from
2026-10-14 to allow clients that do not implement SSO. Use the existing master
password; the account and encrypted vault are retained.

In each Bitwarden app or browser extension, choose **Self-hosted**, enter
`https://passwords.beachlab.org`, and sign in with **hola@beachlab.org** and
the existing master password.
See [client configuration](https://bitwarden.com/help/change-client-environment/)
and [Vaultwarden SSO](https://github.com/dani-garcia/vaultwarden/wiki/Enabling-SSO-support-using-OpenId-Connect).

## Access

The official Vaultwarden container
[1.37.4](https://github.com/dani-garcia/vaultwarden/releases/tag/1.37.4) is
pinned by digest in [compose.yaml](../services/vaultwarden/compose.yaml).
Nginx serves its dedicated host with a Let's Encrypt certificate. The existing
`passwords` CNAME points to `beachlab.org`; Certbot renews the certificate and
`50-vaultwarden-nginx` validates and reloads Nginx.

`SSO_ENABLED=false` and `SSO_ONLY=false` enable email and master-password login;
see the upstream [SSO configuration](https://github.com/dani-garcia/vaultwarden/wiki/Enabling-SSO-support-using-OpenId-Connect#configuration).
Public registration, SSO signup
without invitation and organization invitations are disabled. The local
invitation for `hola@beachlab.org` permits the first account. Public `/admin`
returns 404. SMTP and Bitwarden mobile push services are not configured.

The disabled SSO configuration is retained for reactivation. Authentik has a
separate `passwords` OIDC application and provider, with a
single personal access binding for `fran`. It uses the existing
`beachlab-passkey` flow, requiring WebAuthn and user verification, plus PKCE.
Only authorization-code and refresh-token grants are enabled. Access tokens
last 15 minutes and refresh tokens 12 hours. The issuer is:

```text
https://auth.beachlab.org/application/o/passwords/
```

Fran's Authentik profile has no email. The private `Passwords Fran email`
scope mapping assigns `hola@beachlab.org` only for this application, based on
Fran's explicit address choice. It marks this administrative identity claim
as verified; SMTP ownership verification was not performed. Other Authentik
profiles and application bindings were retained.

[configure-oidc.py](../services/vaultwarden/configure-oidc.py) provisions these
objects without changing the shared flow. It refuses an existing application,
provider or credential file. The configuration follows upstream
[Vaultwarden's Authentik guidance](https://github.com/dani-garcia/vaultwarden/wiki/Enabling-SSO-support-using-OpenId-Connect#authentik)
and [Authentik's OAuth2 provider](https://docs.goauthentik.io/add-secure-apps/providers/oauth2/).
Interactive forward-auth redirects are not placed in front of the API;
when enabled, the native SSO flow enforces passkey authentication for clients.
To restore that mode, set both `SSO_ENABLED` and `SSO_ONLY` to `true` in the
versioned Compose file, back up, recreate the container and verify a passkey
sign-in. The retained provider and account association avoid another migration.

## Consolidating imported copies

[deduplicate.py](../services/vaultwarden/deduplicate.py) consolidates personal
login copies through a user-unlocked official Bitwarden CLI. It matches both
username and password plus a shared site or title, excluding the Wi-Fi folder.
It retains every passkey-bearing item ID, unions the original URI variants,
notes, custom fields and password history, and stores different titles as
`Nombre anterior (importación)` fields. Conflicting OTPs, folders, unsupported
data, attachments and groups with more than one passkey-bearing item are kept
for review. A reused password on different sites alone is not a duplicate.

Run a backup first. Install the official CLI in a task-specific private
directory (0700), configure `https://passwords.beachlab.org`, then have the
user run `bw login hola@beachlab.org --raw > session` with `umask 077`.
The master password is entered interactively by the user, never recorded.
The script uses an owner-only Unix socket for the CLI's local API; it does
not open a TCP listener or disable origin protection. See the upstream
[CLI reference](https://bitwarden.com/help/cli/) for login, edit, sync and
soft deletion; the Unix-socket listener was checked in the installed CLI
source (`ServeCommand`, `--hostname unix://...`).

Pass `--bw`, `--private-dir`, `--baseline` and `--receipt`; preview is the
default and `--apply` enables changes. The migration baseline's IDs prefer
the newer import when neither copy has passkeys. The script reads decrypted
data only into memory, verifies merged content before trashing any copy, and
checks all protected passkeys and untouched items after a final sync. The
receipt contains IDs and counts, without credential values or hashes.
Delete only uses the recoverable Trash operation; it does not purge Trash.
For retention and restore behavior, see [Bitwarden delete/restore](https://bitwarden.com/help/cli/#delete).
Back up the result, retain the receipt in `/var/lib/vaultwarden-migration/`,
log out the temporary CLI and remove its profile and session directory.

The completed 2026-10-14 cleanup moved 676 copies in 553 groups to Trash,
leaving 750 active items. All 29 passkey credentials (in their original item
IDs), 162 Wi-Fi items and unrelated item contents were retained. A final
preview found zero remaining groups under the above matching rules; this
does not imply that every remaining password is unique across different
services. The owner-only receipt is
`/var/lib/vaultwarden-migration/dedup-20261014-receipt.json`; the pre-change
encrypted Restic snapshot is `a72284ad`. Two verified runs were combined in
the receipt after changing server readback from one full sync per group to
one per batch, without purging any entry. SQLite integrity check returned
`ok` after the cleanup.

For copies with different usernames,
[review_duplicates.py](../services/vaultwarden/review_duplicates.py) matches
the same HTTP(S) host and exact password, ignoring usernames, URL paths,
`www.` and default HTTP(S) ports. A URL-like item title also supplies a host.
These are candidates for review, including potentially valid different
accounts; the script does not choose the correct username or consolidate
credentials. It moves **every member** of each matching group into the
personal `Duplicados` folder, without deleting or merging anything. Wi-Fi,
passkey-only logins without a password and organization-owned entries are
excluded. All passkeys remain in their existing item IDs, even when their
items are moved.

Use the same private, user-unlocked official CLI workflow, with `--bw`,
`--private-dir`, `--receipt` and optionally `--apply`. The script preserves
each entire decrypted item (including usernames, credential private keys,
notes and fields), verifies the content returned by each edit and then
checks all server items after a final sync. Only folder IDs and modification
timestamps may change. Its owner-only receipt records each previous folder
ID so that the move can be undone without exposing credential contents.

On 2026-10-14 the NUC resolver failed to resolve `passwords.beachlab.org`
(`resolvectl query`: the CNAME target had no requested RR). HTTPS to the
local Nginx with that hostname and certificate succeeded (HTTP 200 for
`/api/config`). `/etc/hosts` now maps `passwords.beachlab.org` to
`127.0.0.1` for NUC-local clients. Certificate validation remains enabled;
this mapping does not change public DNS or other hosts.

## Paths and operation

```text
/opt/vaultwarden/compose.yaml
/opt/vaultwarden/.env
/opt/vaultwarden/admin-token
/opt/vaultwarden/deployment/
/opt/vaultwarden/oidc-provision.json
/var/lib/vaultwarden/
/etc/nginx/sites-available/passwords.beachlab.org
/etc/letsencrypt/live/passwords.beachlab.org/
/etc/letsencrypt/renewal-hooks/deploy/50-vaultwarden-nginx
/usr/local/sbin/vaultwarden-invite
/usr/local/sbin/vaultwarden-backup
```

The container runs as the dedicated `vaultwarden` user, with a read-only root
filesystem, no Linux capabilities, a 512 MiB memory limit and one CPU.
Only `127.0.0.1:18080` is published. Data is private (0700); deployment secrets
are root-only (0600). The administration token is stored as an Argon2id hash
in the server environment. Do not print `.env`, the recovery token or
unfiltered Docker inspection output.

On the NUC (`ssh pink-sudo`):

```bash
sudo docker compose --project-directory /opt/vaultwarden config --quiet
sudo docker compose --project-directory /opt/vaultwarden ps
sudo docker compose --project-directory /opt/vaultwarden up -d --force-recreate
curl -fsS http://127.0.0.1:18080/alive
sudo nginx -t
```

[install.py](../services/vaultwarden/install.py) is for a first installation
only. It refuses existing paths, users and containers. Existing data and
credentials must be preserved during upgrades; update the pinned image,
back up first, then recreate the container. When SSO is enabled, another person
also requires an explicit Authentik binding and a suitable email mapping;
an invitation alone does not grant SSO access.

## Backup and recovery

`vaultwarden-backup.timer` runs daily at **02:10 Europe/Madrid**, with up to five
minutes of delay. It briefly stops the container to capture SQLite, attachments,
keys and deployment together, restarts it even if capture fails, then uploads the
capture to the encrypted, separate Restic repository:

```text
/mnt/nas-downloads/backups/vaultwarden-restic
```

The job refuses a missing or unexpected Synology NFS mount and checks the
repository identity. Retention is 7 daily, 4 weekly and 6 monthly snapshots.
It uses `/root/.config/thebeachlab-backup/restic-password`; recovery password
location and NAS access are in [Backups](backups.md).
See [Vaultwarden backup and restore requirements](https://github.com/dani-garcia/vaultwarden/wiki/Backing-up-your-vault).

```bash
sudo systemctl start vaultwarden-backup.service
systemctl show vaultwarden-backup.service -p Result -p ExecMainStatus
systemctl list-timers vaultwarden-backup.timer
sudo cat /var/lib/vaultwarden-backup/last-success.json
```

Restore into a private, separate directory before changing live data:

```bash
sudo install -d -m 700 /var/tmp/vaultwarden-restore
sudo env \
  RESTIC_REPOSITORY=/mnt/nas-downloads/backups/vaultwarden-restic \
  RESTIC_PASSWORD_FILE=/root/.config/thebeachlab-backup/restic-password \
  restic restore latest --tag vaultwarden --target /var/tmp/vaultwarden-restore
sudo sqlite3 /var/tmp/vaultwarden-restore/var/lib/vaultwarden-backup/payload/data/db.sqlite3 \
  'PRAGMA integrity_check;'
```

Stop the container and preserve current data before a live restore. Recover
`data/` as a whole, including its matching WAL if captured. Keep ownership with
`vaultwarden`. Restore deployment secrets only when needed, then start the
container and check `/alive` and the configured login method. Do not mix a
recovered database with the current WAL or overwrite newer data. When SSO is
enabled, Authentik and its signing key must also be available; this backup
captures Vaultwarden, not the Authentik database.

The initial capture was restored on 2026-10-13 into an isolated container with
no network or published ports. SQLite integrity, database hash, signing keys,
deployment credentials and the restored image's healthcheck passed. The vault
was still empty, with one invited account. Proof is stored privately at
`/var/lib/vaultwarden-backup/restore-proof.json`.
