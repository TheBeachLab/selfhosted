# PostgreSQL

**Author:** Fran

- [Current state](#current-state)
- [Quick checks](#quick-checks)
- [Install](#install)
- [Install pgbouncer](#install-pgbouncer)
- [Upgrade history](#upgrade-history)
- [Remote connection](#remote-connection)
- [Common psql commands](#common-psql-commands)
- [Roles and databases](#roles-and-databases)
- [Managing PostgreSQL with pgAdmin](#managing-postgresql-with-pgadmin)
- [SQL Tips and tricks](#sql-tips-and-tricks)
- [API and REST](#api-and-rest)

## Current state

| Component | Version | Notes |
|-----------|---------|-------|
| PostgreSQL | 18.3 | Active cluster on port 5432 |
| TimescaleDB | 2.25.2 | Extensions for PG 17 and 18 |
| PostGIS | 3.6.2 | For PG 18 |
| pgBouncer | active | Connection pooler |
| pgAdmin | 9.13 | Web UI via Apache on port 5050 |

Databases:

| Database | Purpose |
|----------|---------|
| `sensors` | Telemetry: `telemetry_stats`, `bluetti_stats` (TimescaleDB hypertables) |
| `orbita` | Orbita web app |
| `nextcloud` | Nextcloud file sync |
| `iot` | IoT data |
| `misc_data` | Misc lookup tables (countries, territories, etc.) |
| `fmcu` | FMCU project |

Config path: `/etc/postgresql/18/main/`

## Quick checks

```bash
# Version
sudo -u postgres psql -c 'SELECT version();'

# Clusters
pg_lsclusters

# Service
systemctl status postgresql

# Databases
sudo -u postgres psql -c '\l'

# Roles
sudo -u postgres psql -c '\du'

# Disk usage per database
sudo -u postgres psql -c "SELECT datname, pg_size_pretty(pg_database_size(datname)) FROM pg_database ORDER BY pg_database_size(datname) DESC;"
```

## Install

```bash
sudo apt update
sudo apt install postgresql postgresql-contrib
```

Check:

```bash
sudo -u postgres psql
```

```
psql (18.3 (Ubuntu 18.3-1.pgdg22.04+1))
Type "help" for help.

postgres=#
```

Exit with `\q`

## Install pgbouncer

PgBouncer is a lightweight connection pooler for PostgreSQL. Instead of each client opening expensive direct connections, they connect to PgBouncer, which maintains a pool of persistent connections and hands them out as needed. Reduces overhead and lets PostgreSQL handle many more clients.

```bash
sudo apt install pgbouncer
sudo systemctl enable --now pgbouncer
systemctl status pgbouncer
```

## Upgrade history

Current cluster: **18/main** on port 5432. Old versions (12, 14, 16, 17) have been migrated and removed over time.

Installed packages (as of 2026-03-30):

```
postgresql-16, postgresql-17, postgresql-18
timescaledb-2-postgresql-17, timescaledb-2-postgresql-18
postgresql-18-postgis-3
```

### General upgrade procedure

```bash
# Check current version
sudo -u postgres psql -c 'SELECT version();'
pg_lsclusters

# Install new version (e.g., 18)
sudo apt install postgresql-18

# Drop the auto-created empty cluster
sudo pg_dropcluster --stop 18 main

# Upgrade data from old cluster
sudo pg_upgradecluster 17 main

# Tune TimescaleDB for new version
sudo apt install timescaledb-2-postgresql-18
sudo timescaledb-tune

# Drop old cluster and purge packages
sudo pg_dropcluster 17 main
sudo apt purge postgresql-17 postgresql-client-17
```

> After major upgrades, also rerun `sudo /usr/pgadmin4/bin/setup-web.sh` if pgAdmin breaks.

## Remote connection

Config: `/etc/postgresql/18/main/postgresql.conf`

```bash
listen_addresses = '*'
```

Auth: `/etc/postgresql/18/main/pg_hba.conf`

```
local   all             postgres                                peer
local   all             all                                     peer
host    all             all             127.0.0.1/32            md5
host    all             all             192.168.1.0/24          md5
host    all             all             ::1/128                 md5
```

Firewall:

```bash
sudo ufw allow 5432 comment 'postgres'
sudo ufw reload
```

Test from remote: `psql -h 192.168.1.50 -U postgres`

## Common psql commands

| Command | Description |
|---------|-------------|
| `\l` | List databases |
| `\l+` | List databases with size |
| `\c database` | Connect to database |
| `\dt` / `\dt+` | List tables |
| `\du` | List users/roles |
| `\conninfo` | Show current connection |
| `\q` | Exit |

## Roles and databases

### Create a role

```bash
sudo -u postgres createuser --interactive
```

### Create a database

A PostgreSQL convention: a role will try to connect to a database with the same name by default.

```bash
sudo -u postgres createdb mydb
```

### Create a read-only user

```sql
CREATE USER readonly WITH PASSWORD '<PASSWORD>';
\c mydb
GRANT CONNECT ON DATABASE mydb TO readonly;
GRANT USAGE ON SCHEMA public TO readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO readonly;
```

### Connect as a role

Due to ident-based authentication, you need a Linux user with the same name as the role:

```bash
sudo adduser myuser
sudo -u myuser psql
```

A role can also connect to a different database:

```bash
sudo -u myuser psql -d postgres
```

## Managing PostgreSQL with pgAdmin

### Install pgAdmin 4

```bash
# Add repository
sudo curl https://www.pgadmin.org/static/packages_pgadmin_org.pub | sudo apt-key add
sudo sh -c 'echo "deb https://ftp.postgresql.org/pub/pgadmin/pgadmin4/apt/$(lsb_release -cs) pgadmin4 main" > /etc/apt/sources.list.d/pgadmin4.list && apt update'

# Install web mode
sudo apt install pgadmin4-web
```

### Apache coexistence with Nginx

pgAdmin runs under Apache. To avoid port conflicts with Nginx, change Apache ports in `/etc/apache2/ports.conf`:

```apache
Listen 5050

<IfModule ssl_module>
        Listen 8090
</IfModule>
```

Update `/etc/apache2/sites-available/000-default.conf`:

```apache
<VirtualHost *:5050>
```

```bash
sudo systemctl restart apache2
sudo ufw allow 5050 comment 'apache pgadmin'
```

pgAdmin is at `http://server-address:5050/pgadmin4`

### Setup and configuration

```bash
sudo /usr/pgadmin4/bin/setup-web.sh
```

### Reset password

```bash
mv /var/lib/pgadmin/pgadmin4.db /var/lib/pgadmin/pgadmin4.db.backup
sudo /usr/pgadmin4/bin/setup-web.sh
```

### Unlock account (after 3 failed logins)

```bash
sudo apt install sqlite3
sudo sqlite3 /var/lib/pgadmin/pgadmin4.db "UPDATE USER SET LOCKED = false, LOGIN_ATTEMPTS = 0 WHERE USERNAME = 'user@domain.com';" ".exit"
```

### Storage

ERD and other files: `/var/lib/pgadmin/storage/email_account.org/`

## SQL Tips and tricks

### Table conventions

- Column `id` with `bigint` or `int` IDENTITY as primary key
- Column `created` of `timestamp with timezone` default `now()`
- Column `modified` of `timestamp with timezone` default `now()`

### Auto-update modified timestamp

```sql
CREATE OR REPLACE FUNCTION update_timestamp_modified_column()
RETURNS TRIGGER AS $$
BEGIN
  CASE WHEN OLD.* IS DISTINCT FROM NEW.* THEN
    NEW.modified = NOW();
    RETURN NEW;
  ELSE
    RETURN OLD;
  END CASE;
END;
$$ LANGUAGE 'plpgsql';
```

Then for each table:

```sql
CREATE TRIGGER update_modified
BEFORE UPDATE ON users
FOR EACH ROW
EXECUTE PROCEDURE update_timestamp_modified_column();
```

### New table from existing table

```sql
CREATE TABLE template (LIKE users INCLUDING ALL);
```

Does not copy triggers.

### Add column with foreign key

```sql
ALTER TABLE interests ADD COLUMN IF NOT EXISTS interest_group_id INTEGER NOT NULL;

ALTER TABLE public.interests
    ADD FOREIGN KEY (interest_group_id)
    REFERENCES public.interest_group (id)
    NOT VALID;
```

### Create JSON from a table

```sql
SELECT json_agg(row_to_json(t))
FROM (
  SELECT *
  FROM your_table
) t
```

### Check table size

```sql
SELECT pg_size_pretty(pg_total_relation_size('table_name')) AS table_size;
```

### Unique constraint on column combination

```sql
ALTER TABLE regions
ADD CONSTRAINT unique_region_country UNIQUE (region_code, country_code);
```

### Copy table between databases (same server)

```bash
sudo -u postgres pg_dump -d misc_data -t territories -f /tmp/territories.sql
sudo -u postgres psql -d air -f /tmp/territories.sql
```

### Delete rows

```sql
DELETE FROM countries WHERE alpha_2_code IS NULL;
```

### View with fallback values

```sql
DROP VIEW IF EXISTS countries_view;
CREATE VIEW countries_view AS
SELECT
  alpha_3_code,
  name_es,
  COALESCE(name_ca, name_es) AS name_ca,
  name_en,
  name_fr,
  name_it,
  name_de
FROM countries;
```

### Get view definition

```sql
SELECT view_definition
FROM information_schema.views
WHERE table_name = 'view_name';
```

## API and REST

### PostgREST

PostgREST automatically generates a RESTful API from a PostgreSQL database. You define your data model and permissions in the database, and PostgREST exposes them as secure endpoints.

See [PostgREST](postgrest.md) and [PostgREST JWT Gateway](postgrest-jwt.md) for details.

### FastAPI

FastAPI is a high-performance Python API framework using type hints for validation and auto-docs.

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
```

Create the virtual environment (as pink):

```bash
mkdir -p ~/fastapi-app && cd ~/fastapi-app
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install fastapi "uvicorn[standard]" gunicorn psycopg[binary]
```

Hello world app at `/home/pink/fastapi-app/main.py`:

```python
from fastapi import FastAPI
app = FastAPI()
@app.get("/api/health")
def health(): return {"ok": True}
```

Service at `/etc/systemd/system/fastapi.service`:

```ini
[Unit]
Description=FastAPI (pink)
After=network.target

[Service]
User=pink
Group=pink
WorkingDirectory=/home/pink/fastapi-app
Environment="PATH=/home/pink/fastapi-app/.venv/bin"
# (optional) add your variables here:
# Environment="DATABASE_URL=postgres://api_ro:***@127.0.0.1:5432/mydb"
ExecStart=/home/pink/fastapi-app/.venv/bin/gunicorn \
          -k uvicorn.workers.UvicornWorker -w 4 \
          -b 127.0.0.1:8000 main:app
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now fastapi
```

Nginx reverse proxy (add to your site config):

```nginx
location /api/ {
  proxy_pass http://127.0.0.1:8000/;
  proxy_set_header Host $host;
  proxy_set_header X-Forwarded-For $remote_addr;
}
```

```bash
sudo nginx -t && sudo systemctl reload nginx
```
