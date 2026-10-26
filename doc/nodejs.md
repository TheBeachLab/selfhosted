# Node.js server

## Managed runtimes

Runtime inventory verified on 2026-10-26:

| Host / consumer | Executable | Node version |
| --- | --- | --- |
| NUC / Node-RED | `/usr/bin/node` | `22.23.4` (`22.23.4-1nodesource1`) |
| NUC / Watson OpenClaw | `/home/pink/.local/share/openclaw-node/current/bin/node` | `24.22.1` |
| Liderflor VPS / Flora OpenClaw | `/usr/bin/node` | `24.22.1` (`24.22.1-1nodesource1`) |

Node-RED is `5.0.9`; the NUC and VPS OpenClaw inventories were `2026.10.7`.
Their installed package metadata declares Node `>=22.9` and
`>=24.22.1 <25 || >=26.12.1`, respectively. The system and private NUC runtimes
serve different applications; keep that separation when applying updates.
See [Watson maintenance](watson-openclaw-runtime.md).

### Node-RED application maintenance

The 2026-10-22 maintenance advanced Node-RED 3.0.2 → 4.1.17 → 5.0.9.
The complete 4.1.17 dependency tree still contained high-severity advisories in
the palette installer's npm/pacote chain. The 5.0.9 production tree and the
active custom-node tree both returned zero advisories from `npm audit --omit=dev`.
Node remains on the patched 22.23.4 branch, preserving its native-module ABI.

The custom node tree was repaired in a private copy with `npm audit fix`
without `--force`; Dashboard advanced to 3.6.6. Five packages with no references
in any current flow or configuration were removed from the active palette:
`node-red-contrib-chatbot`, `node-red-contrib-homekit-bridged`,
`node-red-contrib-openhab3`, `node-red-contrib-web-worldmap` and
`node-red-node-openweathermap`. Chatbot and OpenHAB3 registered HTTP handlers
when loaded even without flow instances. The complete former installation is
retained in the private backup below. Reinstall only after reviewing the
package and its dependencies against current advisories.

Staging used `--safe --no-telemetry`, a copied user directory and loopback port
1881. It loaded the installed node types and served HTTPS successfully without
starting flows. Activation preserved the live flows, credentials, runtime key,
settings and context; only the global package, custom `node_modules`,
`package.json` and lockfile changed. The active service logged started flows and
its MQTT broker connection. Backups are under
`/var/backups/selfhosted/services-security-20261022/`, including
`nodered-global.tgz`, `nodered-userdata.tgz` and `nodered-node_modules-pre5`.

The legacy [Dashboard](https://github.com/node-red/node-red-dashboard) is
deprecated; 3.6.6 preserves the existing dashboard nodes. Its
[changelog](https://github.com/node-red/node-red-dashboard/blob/master/CHANGELOG.md)
records removal of old bundled jQuery files in 3.6.5. A future dashboard
replacement needs its own UI migration.

## Dependency security backports, 2026-10-26

Latest vendor applications were still Node-RED 5.0.9 and OpenClaw 2026.10.7,
with affected exact dependency pins. The NUC uses these reviewed local backports:

| Dependency | Corrected version | Official fix |
| --- | --- | --- |
| body-parser | 1.20.9 | [CVE-2026-111181](https://github.com/expressjs/body-parser/security/advisories/GHSA-27r3-jxmh-p828) |
| multer | 2.5.0 | [CVE-2026-113872](https://github.com/expressjs/multer/security/advisories/GHSA-q7qp-rjg7-q26m) |
| undici | 6.29.1 / 8.12.2, retaining each major | [CVE-2026-109869](https://github.com/nodejs/undici/security/advisories/GHSA-xjj6-f33q-929c), [CVE-2026-109924](https://github.com/nodejs/undici/security/advisories/GHSA-4qv8-2p9j-2685) |
| zod | 4.6.6 | [Collection-size fix](https://github.com/colinhacks/zod/pull/6652) |
| ip-address | 10.7.4 minimum; existing 10.7.5 retained | [CVE-2026-111997](https://github.com/beaugunderson/ip-address/security/advisories/GHSA-rxp7-6hxx-x8q5) |
| brace-expansion | 5.0.12 | [CPU/recursion fixes](https://github.com/juliangruber/brace-expansion/security/advisories/GHSA-q2hr-2g5m-vwhr) |
| postcss-selector-parser | 7.1.6 | [CVE-2026-104844](https://github.com/postcss/postcss-selector-parser/security/advisories/GHSA-rj75-hqrm-r3gf) |

`services/node-security-dependencies.py` checks every installed copy, including
npm's nested dependencies. It uses fixed vendor tarball SHA-512 values, validates
package identity, rejects links/path traversal and changed dependency contracts,
and adjusts exact consumer pins to match. Verified public vendor files are
normalized to 0644/0755 even under a private umask; state and configuration
permissions are preserved. Newer safe versions and other majors
are preserved. A transaction marker and unfinished-swap detection fail closed
on interruption; restore the protected code backup before retrying. The policy
covers the listed reviewed majors, not advisories published in the future.

Run without `--apply` to inspect a tree (exit 0 = current, 10 = pending; any other
failure needs investigation). Apply only to a private staging copy or a stopped
service with code/state backups. Never replace libraries in a running process.
The installed root-owned helper is
`/usr/local/libexec/selfhosted/node-security-dependencies.py`.

Staging used private copies, complete `npm ls --all --omit=dev` checks, and
`tests/node-security-runtime.cjs`. Node-RED bound HTTPS to 127.0.0.1:1881 in safe
mode, with no started flows or missing node types. Isolated old-library processes
crashed on compressed trailing bytes and pending multipart filters; patched
processes passed both regression cases plus JSON/gzip/uploads and fetch controls.
Zod's old version visited oversized collections; its replacement rejected them
before any element transform. No exploit request was sent to production services.
After activation Node-RED started flows/MQTT, public HTTPS returned 200, and
Watson passed config/SQLite checks and Gateway RPC. Configuration was unchanged.

Node-RED's full production tree returned zero npm advisories. OpenClaw's remaining
`http-cache-semantics` 4.2.0 alert, CVE-2026-93748, is explicitly
[disputed by its maintainer](https://github.com/kornelski/http-cache-semantics/issues/56#issuecomment-5975759591):
Set-Cookie alone does not prohibit shared caching. It is in npm's fetch tooling;
no confirmed security patch was identified. Track the dispute rather than claim
an unverified corrected version or alter cache behavior without evidence.

Backups and private comparison logs are under
`/var/backups/selfhosted/security-20261026/`; Watson's transactional backup is
`~pink/.openclaw-backups/updates/20261026T092153Z-pre-2026.10.7-to-2026.10.7/`.
The current daily updater checks these floors before its no-update exit and
reapplies them after a core replacement, under the existing lock. A Node-incompatible
future core does not suppress a compatible repair of the current version.

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
2. Refresh all configured signed APT indexes, then simulate
   `apt-get install --only-upgrade nodejs=<reviewed-version>`. Back up service
   configuration and the package inventory privately before applying it.
   If a scoped index refresh is required, set `APT::Get::List-Cleanup=false`
   so it does not discard the other repositories' cached indexes.
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
