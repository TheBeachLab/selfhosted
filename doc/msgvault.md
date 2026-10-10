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
/etc/nginx/sites-available/msgvault.beachlab.org
/etc/nginx/snippets/msgvault-api-key.conf
/etc/letsencrypt/live/msgvault.beachlab.org/
/etc/letsencrypt/renewal-hooks/deploy/50-msgvault-nginx
/usr/local/bin/msgvault-mcp-client
/opt/msgvault/mcp-venv/
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

## Maintain

On the NUC (`ssh pink-sudo`):

```bash
sudo systemctl status msgvault
sudo journalctl -u msgvault -n 50 --no-pager
sudo systemctl restart msgvault
sudo -u msgvault env MSGVAULT_HOME=/var/lib/msgvault msgvault list-accounts
sudo -u msgvault env MSGVAULT_HOME=/var/lib/msgvault msgvault stats
curl http://127.0.0.1:8096/health
```

Always use `MSGVAULT_HOME=/var/lib/msgvault` and the service user for archive
commands. The serving process owns database writes; `daemon_auto_start=false`
and `daemon_auto_restart="never"` leave lifecycle management to systemd.
`serve` initializes the database itself. `init-db` cannot bootstrap this
configuration while its supervised daemon is stopped.
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
