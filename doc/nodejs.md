# Node.js server

## Managed runtimes

Live verification on 2026-10-22:

| Host / consumer | Executable | Node version |
| --- | --- | --- |
| NUC / Node-RED | `/usr/bin/node` | `22.23.4` (`22.23.4-1nodesource1`) |
| NUC / Watson OpenClaw | `/home/pink/.local/share/openclaw-node/current/bin/node` | `24.22.1` |
| Liderflor VPS / Flora OpenClaw | `/usr/bin/node` | `24.22.1` (`24.22.1-1nodesource1`) |

Node-RED remains `3.0.2`; both OpenClaw deployments remain `2026.10.5`.
Their installed package metadata declares Node `>=14` and
`>=24.16.0 <25 || >=26.1.0`, respectively. The system and private NUC runtimes
serve different applications; keep that separation when applying updates.
See [Watson maintenance](watson-openclaw-runtime.md).

## Security updates

The [21 October 2026 Node.js advisory](https://nodejs.org/en/blog/vulnerability/october-2026-security-releases)
sets security floors of **22.23.4, 24.22.1 and 26.12.1** for their respective
release lines. It covers ten issues, including Brotli decoder memory corruption
(`CVE-2026-111497`), DNS NUL handling (`CVE-2026-105482`) and TLS identity checks
(`CVE-2026-105483`, `CVE-2026-106069`, `CVE-2026-106072`). A version on another
major line is not a substitute for checking the relevant fixed release.

Applied on 2026-10-22: NUC system Node `22.23.3` → `22.23.4`, Watson private
Node `24.21.0` → `24.22.1`, and VPS Node `24.21.0` → `24.22.1`. Only the Node
runtime changed; application package metadata and OpenClaw configuration contents
were verified unchanged. Node-RED and both Gateways were restarted.

For future maintenance:

1. Inventory **running executables** through `/proc/<pid>/exe` and their systemd
   units, not just the shell's `node --version`. Include private runtimes and
   child processes. Check the application's installed `engines.node`.
2. Refresh the existing signed NodeSource index for the same major and simulate
   `apt-get install --only-upgrade nodejs=<reviewed-version>`. Back up service
   configuration and the package inventory privately before applying it.
3. For Watson, download the official Node archive into a new versioned directory
   and verify its exact filename against the release's `SHASUMS256.txt`. Hold
   the existing `openclaw-maintenance-update.lock` while switching `current`,
   updating both the generated Gateway unit's executable and PATH, reloading
   systemd and restarting. Preserve the maintenance unit's `current/bin/node`
   selection and npm's `/usr` prefix.
4. On the VPS, hold `lider-ops-maintenance exclusive` across the package operation
   and Gateway stop/recovery. APT retains its own package locks. Use a scoped
   `NEEDRESTART_MODE=l` to avoid unrelated restarts, then explicitly restart
   every consumer. Require `openclaw gateway status --require-rpc` before ending
   the maintenance window.
5. Validate package integrity, live process versions/digests, service readiness,
   ordinary application requests and relevant regression behavior. Do not run
   memory-corruption exploit payloads against production.

The official Watson archive `node-v24.22.1-linux-x64.tar.xz` was checked against
SHA-256 `6c172a9ab6718f7b801fb5a7bd486af2ee5e32758086a04b84fcce2aa77095e6`.
Private configuration backups are under
`/var/backups/selfhosted/node-security-20261022/` on the NUC,
`~pink/.openclaw-backups/node-security-20261022/` for Watson, and
`/var/backups/lider-ops/node-security-20261022/` on the VPS. These are runtime
configuration backups, not application database snapshots. The inactive old
Watson directory is retained for recovery; selecting it would reopen the flaws.

Verification used isolated, network-free calls to the actual DNS resolver input
guards and TLS `checkServerIdentity`, based on upstream fixes
[843a1627dc](https://github.com/nodejs/node/commit/843a1627dc) and
[935918e342](https://github.com/nodejs/node/commit/935918e342). The old Node 24
accepted the tested noncanonical TLS identities and DNS NUL inputs; patched
runtimes rejected them. All three updated runtimes passed callback/promise DNS
guards, five noncanonical TLS rejection cases, four legitimate identity controls,
ordinary Brotli compression/decompression and the patched Brotli constant check.
The latter confirms compatibility and patch presence, not reproduction of the RCE.

Both Gateway RPC probes passed. Node-RED logged started flows and an MQTT broker
connection, and its public HTTPS endpoint returned 200. Public Liderflor API
health and WordPress also returned 200. No channel messages or exploit traffic
were sent. These checks do not establish absence of past compromise or test every
application workflow.

## PM2 reference

This server is useful to execute backend commands in the computer hosting a website. We will generate a `server.js` file that node will run. We will keep the server running in the background by using the process manager PM2.

- [Create a user that will run PM2](#create-a-user-that-will-run-pm2)

## Create a user that will run PM2

Create a regular user for PM2:

`sudo adduser pm2user`
