# Grafana

Grafana OSS visualizes read-only TimescaleDB data behind the server's TLS reverse
proxy.

This public runbook intentionally omits internal ports, database usernames,
dashboard identifiers, administrator accounts, certificate dates and filesystem
paths.

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
