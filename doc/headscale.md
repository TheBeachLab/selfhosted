# Headscale

The NUC runs **Headscale 0.29.6 with Go 1.27.3** (activated 2026-10-26) at `https://hs.beachlab.org`, with SQLite state in
`/var/lib/headscale/db.sqlite` and configuration in `/etc/headscale/config.yaml`.
The NUC's own Tailscale client belongs to the official tailnet; SSH maintenance
does not depend on this Headscale instance.

## Security maintenance

The 2026-10-22 update followed the required sequence **0.27.1 → 0.28.0 →
0.29.5**. The official packages were checked against their published SHA-256
files. Stop the service and back up `/etc/headscale`, all of `/var/lib/headscale`
(including SQLite WAL/SHM files), and the executable before each migration.
The copies `headscale-pre028.tgz` and `headscale-pre029.tgz` are in
`/var/backups/selfhosted/services-security-20261022/`. A rollback must restore
matching code, configuration and database state.

The removed `randomize_client_port: false` key is unsupported in 0.29; omitting
it preserves the false default. The old `ephemeral_node_inactivity_timeout`
setting moved to `node.ephemeral.inactivity_timeout`, retaining 30 minutes.
Both registered clients meet the minimum
Tailscale 1.80 requirement. The two clients and one approved route were retained
through both database migrations. No OIDC provider or custom policy is configured.
See the [upgrade procedure](https://headscale.net/stable/setup/upgrade/) and
[0.29.5 release](https://github.com/juanfont/headscale/releases/tag/v0.29.5).

### 0.29.6 activation, 2026-10-26

The official `headscale_0.29.6_linux_amd64.deb` matched the vendor `checksums.txt`:
SHA-256 `a3b49916a16418c704cef89818d734bc8af0528aac965a2dd5ca4bfa4cef48e2`.
Configuration validation and APT simulation passed before stopping the service.
Configuration, the whole SQLite directory and executable were then archived in
`/var/backups/selfhosted/security-20261026/headscale-pre0296.tgz`; SQLite
`quick_check` returned `ok`. The package replaces the previous custom Go build.

The [vendor release](https://github.com/juanfont/headscale/releases/tag/v0.29.6)
updates x/net to 0.60.0, x/text to 0.42.0 and gRPC to 1.83.2, addressing
CVE-2026-97032, CVE-2026-56851 and CVE-2026-84304. Use Go 1.27.3 or later for
custom builds of this release, as required for its compromised-certificate fix.

The vendor version reports `v0.29.6+dirty`, commit
`a2b1d7863926834e94479dcdd91ab344a9356bd0`, built with Go 1.27.3. This is the
verified vendor artifact, not a local source edit. After activation the running
executable matched `/usr/bin/headscale`, `/health` returned `pass`, client IDs
1 and 2 and the existing approved route were unchanged.

## Historical Go runtime rebuild, 2026-10-22

The original 0.27.1 binary used Go 1.25.1. Its DERP map downloader uses the
standard HTTPS client, reaching the X.509 validation covered by
[CVE-2025-58187/58188](https://groups.google.com/g/golang-announce/c/4Emdl2iQ_bI).
The official 0.29.5 package advances to Go 1.26.8, but the
[Go release history](https://go.dev/doc/devel/release) identifies additional
security fixes in 1.26.9 and 1.26.10. The local package rebuild uses **Go
1.26.10**, keeping Headscale source and dependency versions unchanged.

Build directory: `/opt/headscale-builds/0.29.5-go1.26.10/`. The source is the
unchanged vendor tag `v0.29.5`, commit
`0f7d1e536bed9f01dd7161f7637af19bb0908335`. The official Go archive
`go1.26.10.linux-amd64.tar.gz` was verified against its go.dev SHA-256:
`ccfe7ae822d2c2f41f4fe7c956199967a4dac22d0ee0d2b2bfdb440aab3b20c5`.

Build and focused checks, from the source directory:

```sh
export GOTOOLCHAIN=local GOMAXPROCS=2 CGO_ENABLED=0
../go/bin/go build -p 2 -mod=readonly -trimpath -o ../headscale ./cmd/headscale
../go/bin/go test -p 2 crypto/x509 ./hscontrol/types
../go/bin/go test -short -p 2 crypto/tls
../headscale configtest
../headscale version
git status --porcelain
```

The local Debian revision is `0.29.5+go1.26.10-1`. It is repacked from the
verified official 0.29.5 package, replacing the binary and updating the package
version, maintainer and file checksum; vendor configuration and service scripts
are retained. A future vendor release must be newer than this revision and use
the current patched Go runtime. Check both `dpkg-query -W headscale` and
`headscale version`, then the actual running `/proc/<pid>/exe` and
`https://hs.beachlab.org/health` after activation.

The X.509, short TLS and Headscale type suites passed. The optional full TLS
BoringSSL interoperability runner failed with loopback connection refusals;
the targeted TLS verification, hostname, SNI and renegotiation tests also passed.
The vendor source remained clean after building.
