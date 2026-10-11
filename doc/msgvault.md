# Msgvault

Open [msgvault.beachlab.org](https://msgvault.beachlab.org/) and sign in with
the existing [Authentik passkey](authentik.md). Access is assigned only to
`fran`. Nginx protects the UI, API, health endpoint and embedded assets; the
backend listens only on `127.0.0.1:8096`.

The NUC runs **0.21.0**, from the official Linux amd64
[release](https://github.com/kenn-io/msgvault/releases/tag/v0.21.0).
The downloaded archive's SHA-256 matched
`56b2438eab14f3cadd15b6edecc4ea30454b6584c1039c2d5593a0afa77d7497`.
The binary includes the browser application; no separate Node process is needed
([0.21.0 Web UI](https://github.com/kenn-io/msgvault/blob/v0.21.0/docs/web-ui.md)).

Installation on 2026-10-10 initialized an empty archive: no accounts, messages
or attachments. Connecting a source or importing an export is still pending.
Source: NUC `msgvault version`, daemon-backed `list-accounts` and `stats`, and
authenticated `/api/v1/stats`.

## Files

```text
/opt/msgvault/0.21.0/msgvault
/usr/local/bin/msgvault -> /opt/msgvault/0.21.0/msgvault
/opt/msgvault/deployment/
/opt/msgvault/backups/
/var/lib/msgvault/config.toml
/var/lib/msgvault/mcp.toml
/var/lib/msgvault/msgvault.db
/var/lib/msgvault/attachments/
/var/lib/msgvault/analytics/
/etc/systemd/system/msgvault.service
/etc/systemd/system/msgvault-mcp.service
/etc/systemd/system/msgvault-backup.service
/etc/systemd/system/msgvault-backup.timer
/etc/nginx/sites-available/msgvault.beachlab.org
/etc/nginx/snippets/msgvault-api-key.conf
/etc/letsencrypt/live/msgvault.beachlab.org/
/etc/letsencrypt/renewal-hooks/deploy/50-msgvault-nginx
/usr/local/bin/msgvault-mcp-client
/opt/msgvault/mcp-venv/
/usr/local/sbin/msgvault-backup
/var/lib/msgvault-backup/
/var/lib/msgvault/backup-staging/
/mnt/nas-downloads/backups/msgvault-restic/
```

The service runs as `msgvault`, with a private data directory (0700) and
configuration/database files (0600). Systemd restarts it after failure and
starts it at boot. Limits are 2 GiB RAM and two CPU.

Nginx adds the backend API key only after Authentik authorizes the request.
The include containing that key is root-only (0600), and the key remains out
of Git. This avoids a second login in msgvault. Only localhost is listed in
`server.trusted_proxies`, so the daemon recognizes the forwarded HTTPS scheme.
Configuration reference:
[0.21.0 server settings](https://github.com/kenn-io/msgvault/blob/v0.21.0/docs/configuration.md#server).

API-key authentication skips msgvault's browser-session CSRF checks, as shown in
[0.21.0 csrf.go](https://github.com/kenn-io/msgvault/blob/v0.21.0/internal/api/csrf.go).
The Nginx configuration therefore rejects mutations with a foreign Origin or
cross-origin Fetch Metadata before adding the key. It replaces forwarded host
and scheme headers and clears client Authorization and Forwarded headers.

## API and MCP

The REST API is active on `127.0.0.1:8096`. Its OpenAPI document is at
`/openapi.json`; the installed 0.21.0 daemon reports API schema **3.0.0**.
`GET /api/v1/settings` reads configuration and `PATCH /api/v1/settings` changes
editable settings. The public HTTPS routes still require the Authentik session,
including requests with an API key. Local scripts use the daemon's owner key
over loopback or SSH. See the
[0.21.0 API reference](https://github.com/kenn-io/msgvault/blob/v0.21.0/docs/api-server.md).

`msgvault-mcp.service` exposes a separate, private MCP endpoint at
`http://127.0.0.1:8097/mcp`. It runs without `--http-allow-writes`, so deletion
staging, attachment export, Saved View changes and profile writes are absent.
The inbound MCP key differs from the owner REST key. Its private `mcp.toml`
uses `[remote]` to authenticate to the existing daemon; the MCP key itself
cannot authenticate to the owner REST API (verified 401).
Source: [0.21.0 MCP transport and write controls](https://github.com/kenn-io/msgvault/blob/v0.21.0/docs/usage/chat.md).

The stdio bridge reads its credential on the NUC. Neither client configuration
contains a key:

| Client | Registration | Connection |
| --- | --- | --- |
| Mac Codex | `~/.codex/config.toml`, server `msgvault` | SSH `pink-sudo`, then `sudo -n -u msgvault /usr/local/bin/msgvault-mcp-client` |
| Watson | `/home/pink/.openclaw/openclaw.json`, `mcp.servers.msgvault` | Same local stdio client, with `codex.agents = ["main"]` |

The OpenClaw agent scope applies to native Codex projection; it is not a policy
for other runtime adapters. Mckenzie's existing `group:plugins` denial was
preserved; configured MCP tools are owned by the `bundle-mcp` plugin
([tool policy](https://docs.openclaw.ai/gateway/config-tools/tool-policy)).
Existing model, channel and other agent settings were preserved. Templates are
[codex-mcp.toml](../services/msgvault/codex-mcp.toml) and
[openclaw-mcp.json](../services/msgvault/openclaw-mcp.json).
Sources: [Codex MCP configuration](https://developers.openai.com/codex/mcp/) and
[OpenClaw registry and agent scope](https://docs.openclaw.ai/cli/mcp/registry).

The bridge uses `mcp-proxy` **0.13.0** and MCP Python SDK **1.30.0** in its
private virtual environment. All resolved versions are pinned in
[mcp-requirements.txt](../services/msgvault/mcp-requirements.txt).
[install-mcp.py](../services/msgvault/install-mcp.py) installs the endpoint and
bridge on an existing Msgvault host; it refuses existing MCP installation files.

OpenClaw 2026.9.9 initially rejected the entire tool list because `query_sql`
declares `oneOf` two object output schemas without an explicit root `type`.
[mcp-proxy-compat.py](../services/msgvault/mcp-proxy-compat.py) adds the redundant
`type: object` only for that schema, preserving both branches and all results.
The adapter leaves installed Msgvault/OpenClaw packages unchanged. The original
diagnostic and successful probe are retained privately in Watson's
`~/.openclaw/backups/msgvault-mcp-20261010T193147Z/`. Check for later changes
before recovery.

Check the endpoint and bridge on the NUC:

```bash
sudo systemctl status msgvault-mcp
sudo journalctl -u msgvault-mcp -n 30 --no-pager
sudo /opt/msgvault/mcp-venv/bin/python /opt/msgvault/deployment/probe-mcp.py
```

The probe checks authentication separation, absence of write tools,
`get_stats`, the corrected schema and a read-only `SELECT 1` through stdio.
On 2026-10-10, the Mac's exact registered SSH command also initialized MCP,
listed 36 tools and called `get_stats`. OpenClaw's native probe succeeded with
38 tools (including its generated resource utilities), with no diagnostics.
These checks exercise the MCP transports and clients, not an AI conversation.

OpenClaw's saved-server mutations and live CLI probes require its gateway to
be stopped for exclusive state ownership. Use its supported CLI with the
managed Node runtime, then start the gateway again. Read-only `mcp status` and
`mcp doctor` without `--probe` can run while it is active. Client configuration
backups stay private under each client's backup directory; restore only this
server's entry after checking later changes. Compare parsed Codex configuration
before and after registration: this run's readback showed `node_repl.args`
missing. It was restored from the baseline, then all prior settings matched.

## AI providers

On 2026-10-11, **message semantic search, semantic people search and automatic
people inference are active**. Both systemd services are running; authenticated
`/health` reports `ok`, vector `ready` and DuckDB. The settings endpoints report
no pending restart, and the configured and running people-policy fingerprints
match. The initial vector generation was created against an empty archive,
and a synthetic MCP hybrid query completed successfully with zero results.
A separate source sync then started, and messages are arriving. Index coverage
will catch up through the configured 15-minute schedule; retrieval quality and
real-person inference have not been exercised against the imported corpus.

The personal OpenAI key is `msgvault-restricted`, owned by Francisco Sanchez
in `Default project`, with **Restricted** permissions and expiration on
**2026-11-10**. Its creation form and saved key table were read back. Only model
listing, chat completions and embeddings were allowed. With that key,
`GET /v1/models` returned HTTP 200 and listed both configured models;
`GET /v1/files` returned HTTP 401 with explicit missing `api.files.read`
scope. The fixed synthetic embedding test subsequently returned HTTP 200,
1536 finite dimensions and six input tokens. The native people check returned
HTTP 200 for `gpt-6-luna`, with 60 input and 12 output tokens. No archive text
was needed for either capability check.

The approved Mac recovery copy is `/Users/Papi/.config/msgvault/openai.env`,
mode 0600 inside a 0700 directory. The daemon holds the same key in two native,
owner-only stores:

| Feature | Active configuration | Credential file on the NUC |
| --- | --- | --- |
| Message and people embeddings | `text-embedding-3-small`, 1536 dimensions, `https://api.openai.com/v1` | `/var/lib/msgvault/tokens/provider-credentials.json` |
| People inference | Profile `openai`, model `gpt-6-luna`, `openai_chat`, native JSON schema | `/var/lib/msgvault/tokens/people-providers/openai.json` |

Both NUC files were compared with the approved local copy without displaying
the secret and checked as mode 0600, owned by `msgvault`. The former service
account key was replaced in both live stores; its private Mac recovery copy
is `/Users/Papi/.config/msgvault/openai-service-account-20261011.env`.
The old cloud key has not been revoked. Provider keys are outside `config.toml`,
Git and command arguments. Embedding credentials are bound to the configured
endpoint origin; the people profile uses the native OpenAI preset. Sources:
[0.21.0 stored provider credentials](https://github.com/kenn-io/msgvault/blob/v0.21.0/docs/configuration.md#stored-provider-credentials)
and [people provider lifecycle](https://github.com/kenn-io/msgvault/blob/v0.21.0/docs/usage/people-automation.md#configure-a-provider).

[ai-settings.json](../services/msgvault/ai-settings.json) is the applied,
active settings profile. Message embeddings run every 15 minutes and after
supported scheduled source syncs. The daemon timezone is `Europe/Madrid`;
the native people sweep default is `15 2 * * *` (02:15). Native inference
budgets remain at their release defaults: up to 100 requests, one million
input tokens and 160,000 output tokens per run; up to 500 requests, five
million input tokens and 800,000 output tokens per day. No provider prices or
monetary caps were added. Review these limits before the first real run;
a local cost estimate is not an OpenAI billing cap. Sources:
[recommended scheduling and budgets](https://github.com/kenn-io/msgvault/blob/v0.21.0/docs/usage/recommended-configuration.md),
[sweep defaults](https://github.com/kenn-io/msgvault/blob/v0.21.0/internal/peoplesweep/config.go).

[people-openai.json](../services/msgvault/people-openai.json) is the policy body
used to create the selected people provider. Its sources are conversation and
meeting text from 2025-01-01 onward. `allow_sensitive` records the operator's
choice to permit private archive text; this release uses the same flag for
sensitive profile fields. The native exact-policy check and consent are active,
as is the separate curated-person semantic embedding consent.
`provider-declared` is a posture assertion, not verification of zero retention.
Profile automation requires choosing people to track; conversation briefs
require their own enrollment. No person was tracked or enrolled by this setup.
See the [0.21.0 policy boundary](https://github.com/kenn-io/msgvault/blob/v0.21.0/docs/usage/people-automation.md#understand-and-correct-automatic-facts).

MCP discovers the daemon's vector capabilities at startup; its separate
client-facing configuration does not need a copy of the vector settings.
Restart both services after changing those capabilities. After activation,
the HTTP and stdio probes each listed **37 read-only tools**, preserved owner
REST/MCP authentication separation and called `get_stats` successfully. Codex's
registered `semantic_search_messages` tool also completed a hybrid query against
active generation 1 (`text-embedding-3-small`, 1536 dimensions). Sources:
[pinned MCP capability wiring](https://github.com/kenn-io/msgvault/blob/v0.21.0/cmd/msgvault/cmd/mcp.go)
and the live probe and connector responses.

The first generation required `embeddings build --full-rebuild --yes`; the
incremental command reported that no active generation existed. It scanned
zero messages and activated generation 1 without inserting synthetic archive
data. Later manual imports require an incremental build; supported scheduled
syncs and the 15-minute cron trigger embedding automatically. Use the CLI
wrapper under [Maintain](#maintain), which sets a working directory accessible
to the service user. Sources:
[vector build and sync triggers](https://github.com/kenn-io/msgvault/blob/v0.21.0/docs/usage/vector-search.md).

Settings were saved through the daemon API with the current strong config
ETag; the separate provider-store ETag and people credential's opaque revision
were used for credential writes. Immediately after these API writes, parsed
TOML comparison showed only the six intended changes: vector enablement, semantic people
enablement, embedding cron, post-sync embedding, people sweep enablement and
selected people provider. Unrelated settings were preserved. The subsequent
source import's configuration and data changes were also preserved; final
readback still showed the checked, consented people policy running without a
pending restart. The private pre-activation copy is `/opt/msgvault/backups/ai-activation-20261011T094614Z/`;
its `synthetic-check.json` records the successful native provider check.

The encrypted backup service succeeded after activation. Snapshot `5aa04599`
was restored into an isolated private directory and passed the native integrity
check. At that point, recovered configuration and both credential files
matched the live files byte for byte; both active consent records were present
in the restored archive database. This snapshot predates the concurrent source
import and validates the initial AI setup, not populated-archive recovery.
The temporary restore was removed. The private receipt is
`/var/lib/msgvault-backup/ai-active-restore-20261011T095118Z.json`.
Earlier credential-only receipts remain under `/var/lib/msgvault-backup/`.

The service-account alternative was abandoned after assigning the saved
`Msgvault AI` role failed twice with `Organization ... not found`. The account
retained `Member`, and its former key could read `/v1/files`; the cause of that
assignment failure remains unverified. The operator approved the restricted
personal replacement. Before credit was added, a synthetic embedding request
returned HTTP 429, `insufficient_quota` and `credit_balance_exhausted`, while
Billing showed zero API credit. The same configured key now passes both
provider checks. No credit purchase was performed by this setup.

## Storage and encrypted backups

[storage-settings.json](../services/msgvault/storage-settings.json) is the
applied NUC profile. The settings API readback and authenticated `/health`
confirmed these values after restarting the daemon; DuckDB is active and
`pending_restart` is false.

| Setting | Value |
| --- | --- |
| Cache builder memory / threads | 512 MB / 1 |
| Cache builder temporary storage | 2 GB |
| Minimum automatic cache rebuild interval | 15 minutes |
| Beeper, Slack and Teams attachment size | 100 MiB per attachment |
| Discord attachment size | 50 MiB per attachment |
| Chat media participant threshold | 20 |

The media limits apply to future downloads from those four chat providers.
They do not impose a Gmail/IMAP attachment cap or remove existing files.
The daemon's systemd limit remains 2 GiB; a DuckDB buffer limit is not a total
process memory limit. Sources: [0.21.0 analytics settings](https://github.com/kenn-io/msgvault/blob/v0.21.0/docs/configuration.md#analytics)
and [media policy](https://github.com/kenn-io/msgvault/blob/v0.21.0/docs/configuration.md#media-policy).

`msgvault-backup.timer` runs daily at **02:30 Europe/Madrid**, with up to five
minutes of random delay and catch-up after downtime. Its separate encrypted
Restic repository is `/mnt/nas-downloads/backups/msgvault-restic`; the existing
server backup's script, timer, repository and retention were left intact.
This repository keeps **7 daily, 4 weekly and 6 monthly** snapshots. The job
checks 5% of repository data nightly and all data on Sundays. Sources:
[service](../services/msgvault/msgvault-backup.service),
[timer](../services/msgvault/msgvault-backup.timer),
[runner](../services/msgvault/backup.py), and
[Restic 0.12.1 retention](https://restic.readthedocs.io/en/v0.12.1/060_forget.html).

Each run first uses `msgvault backup create` to capture a coherent database,
attachments, deletion audit, configuration and OAuth tokens while the daemon
continues serving. It adds `mcp.toml`, service units and Nginx access files,
then encrypts this temporary capture with Restic before writing it to the NAS.
Msgvault 0.21.0's native repository has no encryption or retention; its temporary
capture stays under the private (0700) local data directory. The explicit
plaintext-secrets flag applies only to that local capture. The stage is removed
after the encrypted snapshot, checks and retention succeed.
Source: [0.21.0 capture and restore contract](https://github.com/kenn-io/msgvault/blob/v0.21.0/docs/usage/backup.md).

The capture temporarily needs space for another complete archive. The runner
estimates that space without relying on compression and requires another
**10 GiB free** on both disks. This is a backup preflight, not a total archive
quota. It refuses a missing/wrong NFS mount or a changed repository identity.
An upload failure retains the completed local capture for retry; an incomplete
capture is preserved for operator inspection rather than deleted automatically.
The five guard tests are in [test_msgvault_backup.py](../tests/test_msgvault_backup.py).

The job reuses the existing root-only Restic password file. Its private NAS
recovery copy was compared successfully before installation; locations and
access are in [Backups](backups.md). No key values enter Git or command arguments.
The repository identity, last successful run and restore receipt are private
files under `/var/lib/msgvault-backup/`. Command failure diagnostics also stay
there, mode 0600. Original pre-profile configuration is retained under
`/opt/msgvault/backups/storage-<UTC timestamp>/`.

First installation on this existing NUC layout:

```bash
sudo python3 services/msgvault/install-backup.py
```

The installer refuses existing backup paths and uses the settings API's current
strong `ETag` in `If-Match` so concurrent edits are rejected. It changes only
the profile's named settings. Contract: the installed OpenAPI `patchSettings`
operation and [API reference](https://github.com/kenn-io/msgvault/blob/v0.21.0/docs/api-server.md).

Run and inspect:

```bash
sudo systemctl start msgvault-backup.service
systemctl list-timers msgvault-backup.timer
systemctl show msgvault-backup.service -p Result -p ExecMainStatus
sudo journalctl -u msgvault-backup.service -n 30 --no-pager
```

For a restore test, run in a root shell and restore into a new private directory:

```bash
umask 077
backup_restore_dir=$(mktemp -d /var/lib/msgvault-backup/restore-XXXXXX)
restic -r /mnt/nas-downloads/backups/msgvault-restic \
  --password-file /root/.config/thebeachlab-backup/restic-password \
  --cache-dir /var/lib/msgvault-backup/restic-cache \
  restore latest --target "$backup_restore_dir/restic"
msgvault --home /var/lib/msgvault --no-log-file backup restore \
  --repo "$backup_restore_dir/restic/var/lib/msgvault/backup-staging/payload/archive" \
  --target "$backup_restore_dir/archive" --jobs 1 --integrity-check
```

Review machine-specific paths in the restored `config.toml` before starting
any daemon from it. The live archive is not overwritten by these commands.
The separate `host-files` tree contains MCP and Nginx configuration for recovery.
Keep test directories private and remove only the test directory after review.
See [Restic restore](https://restic.readthedocs.io/en/v0.12.1/050_restore.html)
and the native restore contract above.

Verified on 2026-10-10: encrypted snapshot **e26ba98c**, full Restic data check,
native repository verification, temporary restore and SQLite `integrity_check`
all passed. Restored configuration and MCP access configuration matched the
originals by SHA-256; a wrong repository password was rejected. Restored
`sources`, `messages` and `attachments` each contained zero rows. This checks
the initial empty archive, not populated message/attachment recovery. Repeat
the restore check after the first import. Both test and capture directories
were removed. Live proof: `/var/lib/msgvault-backup/restore-proof.json`, service
readback, authenticated `/health`, the MCP `get_stats` call and public HTTPS
302 into Authentik from the Mac.

## Maintain

On the NUC (`ssh pink-sudo`):

```bash
msgvault_cli() {
  sudo -n -u msgvault sh -c \
    'cd /var/lib/msgvault && exec /usr/local/bin/msgvault --home /var/lib/msgvault --no-log-file "$@"' msgvault "$@"
}

sudo systemctl status msgvault
sudo journalctl -u msgvault -n 50 --no-pager
sudo systemctl restart msgvault
msgvault_cli list-accounts
msgvault_cli stats
curl http://127.0.0.1:8096/health
```

Always use `MSGVAULT_HOME=/var/lib/msgvault` and the service user for archive
commands. The serving process owns database writes; `daemon_auto_start=false`
and `daemon_auto_restart="never"` leave lifecycle management to systemd.
`serve` initializes the database itself. `init-db` cannot bootstrap this
configuration while its supervised daemon is stopped.
The CLI proxy preserves the caller's working directory: invoking it from
`/home/pink` failed with `chdir /home/pink: permission denied`. The wrapper
above was verified from the SSH login directory. This host's sudo policy
rejects `--chdir` for the executable, so the service user's shell changes
directory before executing the native CLI.
Sources: installation readback and the
[0.21.0 configuration reference](https://github.com/kenn-io/msgvault/blob/v0.21.0/docs/configuration.md#server).

Before updating or restoring, keep a private backup of the complete data
directory, including configuration, tokens and attachments. For a stopped
archive:

```bash
sudo systemctl stop msgvault
sudo sh -c 'umask 077; tar -C /var/lib -czf /var/backups/msgvault-$(date +%Y%m%dT%H%M%S).tgz msgvault'
sudo systemctl start msgvault
```

Read the selected release's migration notes before opening this archive with
a newer binary. No automatic binary updates are configured.

## Install

The source package is [services/msgvault](../services/msgvault/).
[install.sh](../services/msgvault/install.sh) installs the pinned native release,
verifies its archive checksum, creates the service user and random API key,
and starts systemd. It refuses existing installation paths or an occupied port.
It is for a first installation, not an upgrade.

```bash
sudo bash services/msgvault/install.sh
sudo python3 services/msgvault/configure-authentik.py --apply
```

The Authentik script defaults to a read-only plan. It requires Fran's enrolled
passkey and the existing `beachlab-passkey` flow, creates only the `msgvault`
provider/application and its Fran binding, and adds that provider to the
embedded outpost while preserving other providers and its configuration.
The NUC's Authentik 2026.8.2 API schema was checked before provisioning.
Do not rerun the global Authentik `configure.py` for this service.
Sources: [forward auth](https://docs.goauthentik.io/add-secure-apps/providers/proxy/forward_auth/)
and [application access](https://docs.goauthentik.io/add-secure-apps/applications/manage_apps/).

For the HTTPS host:

1. Install `http-bootstrap.conf` as
   `/etc/nginx/sites-available/msgvault.beachlab.org`, enable its symlink, and
   run `nginx -t` before reloading. This serves only ACME challenges.
2. Issue the certificate with the existing Certbot account:
   `sudo certbot certonly --webroot -w /var/www/letsencrypt --cert-name msgvault.beachlab.org -d msgvault.beachlab.org --non-interactive`.
3. Create `/etc/nginx/snippets/msgvault-api-key.conf` as root, mode 0600,
   containing `proxy_set_header X-API-Key "<server.api_key>";` with the current
   key from the data configuration. Do not paste the key into shell history.
4. Install `msgvault.beachlab.org.conf` over the bootstrap, validate and reload
   Nginx. Keep a private copy of the previous file for rollback.
5. Install `50-msgvault-nginx` as the executable Certbot deploy hook. The
   existing `certbot.timer` renews the certificate; this hook validates and
   reloads Nginx only for msgvault's renewed lineage.

The first deployment's private backups are under `/opt/msgvault/backups/`:
the Authentik inventory, initial backend configuration and HTTP bootstrap.
Check current ownership/state before restoring them. A backend rollback to
the first configuration would reopen the initial Tailscale listener.

## Checks

Verified on 2026-10-10: systemd enabled/running, loopback listener, SQLite
`PRAGMA quick_check` returned `ok`, DuckDB cache initialized, and the public
certificate matched `msgvault.beachlab.org`. Unauthenticated requests to the
UI, API, health, OpenAPI and assets returned a redirect into Authentik, including
requests presenting the backend key or forged identity/forwarding headers.
Foreign-origin mutations returned 403. Direct Tailscale access to port 8096
failed after moving the listener to localhost.

The provider uses the existing WebAuthn-only flow with required user
verification, and its application has only Fran's access binding. Backend
requests carrying Nginx's key and HTTPS headers reported `auth_mode=api_key`,
`https=true`, no plain-HTTP warning, and zero archived messages/accounts.
Native Safari requested Touch ID for Fran's existing passkey, then loaded the
authenticated msgvault Settings page without a second API-key login.
Source: live Authentik API readback, NUC systemd/socket/SQLite checks, and HTTPS
requests from the Mac.
