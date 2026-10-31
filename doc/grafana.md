# Grafana

Grafana OSS visualizes read-only TimescaleDB data behind the server's TLS reverse
proxy. The public hostname is `https://grafana.beachlab.org/`. The same URL is
in the [administration catalog](../services/admin-panel/control.py). On
2026-10-22, `https://grafana.beachlab.org/api/health` returned database `ok`.

Current deployment (2026-10-22): **13.0.11**, pinned in
`/srv/grafana/docker-compose.yml` to
`grafana/grafana:13.0.11@sha256:2abd2114bb65e4d6f0614206b7c882c1e7c6a992827ba08396aa5afc23ca07f5`.
This replaces 13.0.2 and includes the fixes for
[CVE-2026-93294](https://grafana.com/security/security-advisories/cve-2026-93294/),
[CVE-2026-76154](https://grafana.com/security/security-advisories/cve-2026-76154/)
and [CVE-2026-15815](https://grafana.com/security/security-advisories/cve-2026-15815/).
The image is published under `grafana/grafana`; `grafana/grafana-oss:13.0.11`
was unavailable.

Stop Grafana before archiving its SQLite data and deployment configuration.
The pre-update copy is
`/var/backups/selfhosted/services-security-20261022/grafana.tgz`.
After migration the database retained one user, one data source and zero saved
dashboards. The health URL above returned database `ok`.

## Architecture

```text
Browser -> TLS reverse proxy -> local Grafana service -> read-only database role
```

The Grafana backend and database must not be exposed directly. Public dashboards
may use anonymous viewer access, but editing, data-source configuration and
administration remain authenticated.

## Operations

Run maintenance from the private deployment directory:

```bash
docker compose pull
docker compose up -d
docker compose ps
docker compose logs --tail 50
```

Before publishing a dashboard:

1. Confirm its data source uses a read-only database role.
2. Check that queries cannot expose precise location, credentials or private
   operational fields.
3. Test the anonymous view in a signed-out browser.
4. Keep exported dashboard JSON out of Git until it has been checked for URLs,
   datasource identifiers and embedded secrets.

Administrator credentials belong in the password manager or secret store, not
in this repository or command history.
