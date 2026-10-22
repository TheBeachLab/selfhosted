# Headscale

The NUC serves Headscale at `https://hs.beachlab.org`, with SQLite state in
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

## Patched Go runtime build

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
