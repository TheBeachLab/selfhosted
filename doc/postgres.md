# PostgreSQL

- [PostgreSQL](#postgresql)
  - [Install](#install)
  - [Install pgbouncer](#install-pgbouncer)
  - [Upgrade](#upgrade)
  - [Remote connection](#remote-connection)
  - [Common psql commands](#common-psql-commands)
  - [Create a new role](#create-a-new-role)
  - [Create a new database](#create-a-new-database)
  - [Open a postgres prompt with `iot` role](#open-a-postgres-prompt-with-iot-role)
  - [TimescaleDB](#timescaledb)
    - [Create a hypertable in `sensors` database](#create-a-hypertable-in-sensors-database)
    - [Manually insert sensor data in the hypertable](#manually-insert-sensor-data-in-the-hypertable)
    - [Automatic insert sensor data in the hypertable](#automatic-insert-sensor-data-in-the-hypertable)
    - [Add a Time series for the server internal sensors](#add-a-time-series-for-the-server-internal-sensors)
      - [1. Create the role and database](#1-create-the-role-and-database)
      - [2. Install collectors](#2-install-collectors)
      - [3. Configure Telegraf](#3-configure-telegraf)
      - [4. Test and enable](#4-test-and-enable)
      - [5. Verify in Timescale](#5-verify-in-timescale)
    - [Push hypertable data to web server](#push-hypertable-data-to-web-server)
  - [Managing PostgreSQL with pgAdmin](#managing-postgresql-with-pgadmin)
    - [Install pgadmin4](#install-pgadmin4)
    - [Apache and nginx together](#apache-and-nginx-together)
    - [Creating a subdomain (optional)](#creating-a-subdomain-optional)
    - [Securing pgadmin with https (optional)](#securing-pgadmin-with-https-optional)
    - [Configure pgadmin](#configure-pgadmin)
    - [Running pgadmin](#running-pgadmin)
    - [Reset pgadmin password](#reset-pgadmin-password)
    - [unlock pgadmin account](#unlock-pgadmin-account)
    - [pgadmin storage](#pgadmin-storage)
  - [SQL Tips and tricks](#sql-tips-and-tricks)
    - [Create a readonly user](#create-a-readonly-user)
    - [For every table](#for-every-table)
    - [Autoupdate the modified timestamp when a record is updated](#autoupdate-the-modified-timestamp-when-a-record-is-updated)
    - [New table from existing table](#new-table-from-existing-table)
    - [Add new column to existing table](#add-new-column-to-existing-table)
    - [Add one to many](#add-one-to-many)
    - [Create a JSON from a TABLE](#create-a-json-from-a-table)
    - [Check the size of a TABLE](#check-the-size-of-a-table)
    - [Create a unique constraint combination of 2 COLUMNS](#create-a-unique-constraint-combination-of-2-columns)
    - [Copy a TABLE from one DATABASE to another (same pg server)](#copy-a-table-from-one-database-to-another-same-pg-server)
    - [Delete ROWS](#delete-rows)
    - [Create a VIEW with fallback values](#create-a-view-with-fallback-values)
    - [Get the definition that created a VIEW](#get-the-definition-that-created-a-view)
  - [API and REST](#api-and-rest)
    - [PostgREST](#postgrest)
    - [FastAPI](#fastapi)


## Install

```bash
sudo apt update
sudo apt install postgresql postgresql-contrib
```

Check

```bash
pink@thebeachlab:~$ sudo -u postgres psql
psql (12.4 (Ubuntu 12.4-0ubuntu0.20.04.1))
Type "help" for help.

postgres=#
```

Exit with `\q`

## Install pgbouncer

PgBouncer is a lightweight connection pooler for PostgreSQL whose purpose is to manage and reuse database connections efficiently. Instead of each client (like your APIs or apps) opening and closing expensive PostgreSQL connections, they connect to PgBouncer, which maintains a small pool of persistent connections to the database and hands them out as needed. This reduces overhead, improves scalability, and lets PostgreSQL handle many more clients with fewer resources.

`sudo apt install pgbouncer`

Is it running? `systemctl status pgbouncer`if not start and enable

`sudo systemctl enable --now pgbouncer`

## Upgrade

Check version running `sudo -u postgres psql -c 'SELECT version();'`

Output if you are currently runnin 12:

```bash
 PostgreSQL 12.12 (Ubuntu 12.12-0ubuntu0.20.04.1) on x86_64-pc-linux-gnu, compiled by gcc (Ubuntu 9.4.0-1ubuntu1~20.04.1) 9.4.0, 64-bit
(1 row)
```

Check what postgres versions you have installed `pg_lsclusters`  

```bash
Ver Cluster       Port Status Owner    Data directory                       Log file
12  main          5432 online postgres /var/lib/postgresql/12/main          /var/log/postgresql/postgresql-12-main.log
14  main          5434 online postgres /var/lib/postgresql/14/main          /var/log/postgresql/postgresql-14-main.log
```

Please be aware that the installation of postgresql-14 will automatically create a default cluster 14/main. If you want to upgrade the 12/main cluster, you need to remove the already existing 14 cluster:

`sudo pg_dropcluster --stop 14 main`

Use `dpkg -l | grep postgresql` to check which postgres packages are installed:

```
ii  postgresql                            14+238                                  all          object-relational SQL database (supported version)
ii  postgresql-12                         12.12-0ubuntu0.20.04.1                  amd64        object-relational SQL database, version 12 server
ii  postgresql-14                         14.6-0ubuntu0.22.04.1                   amd64        The World's Most Advanced Open Source Relational Database
ii  postgresql-client-12                  12.12-0ubuntu0.20.04.1                  amd64        front-end programs for PostgreSQL 12
ii  postgresql-client-14                  14.6-0ubuntu0.22.04.1                   amd64        front-end programs for PostgreSQL 14
ii  postgresql-client-common              238                                     all          manager for multiple PostgreSQL client versions
ii  postgresql-common                     238                                     all          PostgreSQL database-cluster manager
ii  postgresql-contrib                    14+238                                  all          additional facilities for PostgreSQL (supported version)
ii  timescaledb-loader-postgresql-12      1.7.5~ubuntu20.04                       amd64        The loader for TimescaleDB to load individual versions.
ii  timescaledb-postgresql-12             1.7.5~ubuntu20.04                       amd64        An open-source time-series database based on PostgreSQL, as an extension.
```

> Somehow my timescaledb was broken after upgrading to Ubuntu 22 so I had to reinstall it. In any case you have to make sure you have already the version according to postgres before migrating the data.  
`curl -s https://packagecloud.io/install/repositories/timescale/timescaledb/script.deb.sh | sudo bash`  
`sudo apt install timescaledb-2-postgresql-14`

Now start with the data migration

`sudo pg_upgradecluster 12 main`

After this process 12 is down and 14 is up. Now tune timescale:

```
sudo apt install timescaledb-tools
sudo timescaledb-tune
```

> When I upgraded to Ubuntu 22 I also had to reinstall pgadmin4 and rerun `sudo /usr/pgadmin4/bin/setup-web.sh` but normally that is not required

Now drop the old database `sudo pg_dropcluster 12 main` and purge old packages `sudo apt-get purge postgresql-12 postgresql-client-12`

## Remote connection

- Add a firewall rule `sudo ufw allow 5432 comment 'postgres'`and `sudo ufw reload`
- Listen connections in `/etc/postgresql/14/main/postgresql.conf`

```bash
listen_addresses = '*' 
```

- Accept connections on `/etc/postgresql/14/main/pg_hba.conf` from local network `192.168.1.0/24`

```
# IPv4 local connections:
host    all             all             127.0.0.1/32            scram-sha-256
host    all             all             192.168.1.0/24          scram-sha-256
```

- On remote (arch) install `postgresql-libs` package
- Test `psql -h 192.168.1.50 -U postgres`

## Common psql commands

- List databases `\l`
- List databases with size, tablespace and description `\l+`
- Connect to database `\c database`
- Display tables `\dt` and `\dt+`
- Display users `\du`

## Create a new role

```bash
sudo -u postgres createuser --interactive
Enter name of role to add: iot
Shall the new role be a superuser? (y/n) y
```

## Create a new database

A postgres assumption is that a role will have a database with the same name which it can access. That means `iot` role will attempt to connect to `iot` database by default. So let's create `iot` database.

`sudo -u postgres createdb iot`

## Open a postgres prompt with `iot` role

Due to the ident based authentication, you need a Linux user with the same name as your postgres role and database.

`sudo adduser iot`

Now you can connect to the `iot` database with

`sudo -u iot psql`

Check your connection with `\connifo`

```bash
iot=# \conninfo
You are connected to database "iot" as user "iot" via socket in "/var/run/postgresql" at port "5432"
```

Exit with `\q`. A role can also connect to a different database

```bash
pink@thebeachlab:~$ sudo -u iot psql -d postgres
psql (12.4 (Ubuntu 12.4-0ubuntu0.20.04.1))
Type "help" for help.

postgres=# \conninfo
You are connected to database "postgres" as user "iot" via socket in "/var/run/postgresql" at port "5432".
```

## TimescaleDB

IoT stores huge time series data. Relational databases can be used to store the data but processing can be slow. TimescaleDB is an NoSQL database optimized to store time-series data. It is implemented as an extension of PostgreSQL combining the ease of use of relational databases and the speed of NoSQL databases.

Install

```bash
sudo add-apt-repository ppa:timescale/timescaledb-ppa
sudo apt update
sudo apt install timescaledb-postgresql-12
```

Configure and optimize

```bash
pink@thebeachlab:~$ sudo timescaledb-tune
Using postgresql.conf at this path:
/etc/postgresql/12/main/postgresql.conf

Is this correct? [(y)es/(n)o]: y
Writing backup to:
/tmp/timescaledb_tune.backup202010261003

shared_preload_libraries needs to be updated
Current:
#shared_preload_libraries = ''
Recommended:
shared_preload_libraries = 'timescaledb'
Is this okay? [(y)es/(n)o]: y
success: shared_preload_libraries will be updated

Tune memory/parallelism/WAL and other settings? [(y)es/(n)o]: y
Recommendations based on 7.74 GB of available memory and 4 CPUs for PostgreSQL 12

Memory settings recommendations
Current:
shared_buffers = 128MB
#effective_cache_size = 4GB
#maintenance_work_mem = 64MB
#work_mem = 4MB
Recommended:
shared_buffers = 1981MB
effective_cache_size = 5944MB
maintenance_work_mem = 1014453kB
work_mem = 5072kB
Is this okay? [(y)es/(s)kip/(q)uit]: y
success: memory settings will be updated

Parallelism settings recommendations
Current:
missing: timescaledb.max_background_workers
#max_worker_processes = 8
#max_parallel_workers_per_gather = 2
#max_parallel_workers = 8
Recommended:
timescaledb.max_background_workers = 8
max_worker_processes = 15
max_parallel_workers_per_gather = 2
max_parallel_workers = 4
Is this okay? [(y)es/(s)kip/(q)uit]: y
success: parallelism settings will be updated

WAL settings recommendations
Current:
#wal_buffers = -1
min_wal_size = 80MB
Recommended:
wal_buffers = 16MB
min_wal_size = 512MB
Is this okay? [(y)es/(s)kip/(q)uit]: y
success: WAL settings will be updated

Miscellaneous settings recommendations
Current:
#default_statistics_target = 100
#random_page_cost = 4.0
#checkpoint_completion_target = 0.5
#max_locks_per_transaction = 64
#autovacuum_max_workers = 3
#autovacuum_naptime = 1min
#effective_io_concurrency = 1
Recommended:
default_statistics_target = 500
random_page_cost = 1.1
checkpoint_completion_target = 0.9
max_locks_per_transaction = 64
autovacuum_max_workers = 10
autovacuum_naptime = 10
effective_io_concurrency = 200
Is this okay? [(y)es/(s)kip/(q)uit]: y
success: miscellaneous settings will be updated
Saving changes to: /etc/postgresql/12/main/postgresql.conf
```

If you are going to say yes to all you could also do `sudo timescaledb-tune --quiet --yes`. Now restart postpres

`sudo systemctl restart postgresql.service`

### Create a hypertable in `sensors` database

First connect to `sensors`

`sudo -u sensors psql`

Enable the TimescaleDB extension

```bash
sensors=# CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
WARNING:
WELCOME TO
 _____ _                               _     ____________
|_   _(_)                             | |    |  _  \ ___ \
  | |  _ _ __ ___   ___  ___  ___ __ _| | ___| | | | |_/ /
  | | | |  _ ` _ \ / _ \/ __|/ __/ _` | |/ _ \ | | | ___ \
  | | | | | | | | |  __/\__ \ (_| (_| | |  __/ |/ /| |_/ /
  |_| |_|_| |_| |_|\___||___/\___\__,_|_|\___|___/ \____/
               Running version 1.7.4
For more information on TimescaleDB, please visit the following links:

 1. Getting started: https://docs.timescale.com/getting-started
 2. API reference documentation: https://docs.timescale.com/api
 3. How TimescaleDB is designed: https://docs.timescale.com/introduction/architecture

Note: TimescaleDB collects anonymous reports to better understand and assist our users.
For more information and how to disable, please see our docs https://docs.timescaledb.com/using-timescaledb/telemetry.

CREATE EXTENSION
```

Disable telemetry (sending data to Timescale) and restart postgres

```bash
pink@thebeachlab:~$ sudo -u postgres psql
psql (12.4 (Ubuntu 12.4-0ubuntu0.20.04.1))
Type "help" for help.

postgres=# ALTER SYSTEM SET timescaledb.telemetry_level=off
postgres-# \q
pink@thebeachlab:~$ sudo systemctl restart postgresql.service
```



```sql
-- 1) Remove the old wide table
DROP TABLE IF EXISTS sensors;

-- 2) Create the narrow table
CREATE TABLE sensors (
  time        TIMESTAMPTZ NOT NULL,
  device_id   TEXT        NOT NULL,
  sensor_name TEXT        NOT NULL,
  value       DOUBLE PRECISION NOT NULL
);

-- 3) Make it a hypertable (pick chunk interval you like)
SELECT create_hypertable('sensors', 'time', chunk_time_interval => INTERVAL '1 day');

-- 4) Helpful indexes
CREATE INDEX ON sensors (device_id, sensor_name, time DESC);

-- (Optional) prevent exact duplicate points:
ALTER TABLE sensors ADD CONSTRAINT sensors_unique UNIQUE (time, device_id, sensor_name);

-- (Optional) compression/retention examples:
ALTER TABLE sensors SET (timescaledb.compress, timescaledb.compress_segmentby = 'device_id,sensor_name');
SELECT add_compression_policy('sensors', INTERVAL '7 days');
SELECT add_retention_policy('sensors', INTERVAL '365 days');
```

### Manually insert sensor data in the hypertable

You can enter data like this:

```sql 
INSERT INTO sensors (time, device_id, sensor_name, value)
VALUES (now(), 'pink', 'disk_usage_pct', 42.3);
```

### Automatic insert sensor data in the hypertable

`sudo nano /usr/local/bin/diskwatch_to_timescale.sh`

```bash
DEVICE_ID="pink"
SENSOR="disk_usage_pct"

PCT=$(df --output=pcent / | tail -n1 | tr -d ' %')

LAST=$(
  psql -Atc "SELECT value
             FROM sensors
             WHERE device_id='${DEVICE_ID}'
               AND sensor_name='${SENSOR}'
             ORDER BY time DESC
             LIMIT 1;"
)

if [ -z "$LAST" ] || [ "$PCT" != "$LAST" ]; then
  psql -XtAc "INSERT INTO sensors (time, device_id, sensor_name, value)
              VALUES (NOW(), '${DEVICE_ID}', '${SENSOR}', ${PCT});" >/dev/null
fi
```

Make it executable `sudo chmod +x /usr/local/bin/diskwatch_to_timescale.sh`

```bash
# Create /.pgpass with correct perms
sudo -u root sh -c 'umask 177 && cat > /root/.pgpass <<EOF
localhost:5432:sensors:sensors:password
EOF'
sudo chown root:root /root/.pgpass
```
and make sure the permissions are 600

`sudo chmod 600 /root/.pgpass`

check the write of data:

```bash
pink@thebeachlab$ sudo -u sensors psql
psql (18.0 (Ubuntu 18.0-1.pgdg22.04+3), server 17.6 (Ubuntu 17.6-2.pgdg22.04+1))
Type "help" for help.

sensors=# SELECT * 
FROM sensors
ORDER BY time DESC
LIMIT 20;
             time              | device_id |  sensor_name   | value 
-------------------------------+-----------+----------------+-------
 2025-10-14 09:55:01.294568+00 | pink      | disk_usage_pct |    61
(1 row)
```
### Add a Time series for the server internal sensors

This section sets up automatic collection of internal hardware metrics (CPU, GPU, disks, sensors) and stores them in TimescaleDB using Telegraf.

#### 1. Create the role and database
```bash
sudo -u postgres psql <<'SQL'
CREATE ROLE sensors LOGIN PASSWORD 'YOUR_PASSWORD';
CREATE DATABASE sensors OWNER sensors TEMPLATE template0 ENCODING 'UTF8';
\c sensors
CREATE EXTENSION IF NOT EXISTS timescaledb;
SQL
```

Ensure that `/etc/postgresql/*/main/pg_hba.conf` allows local password auth:
```
host    all    sensors    127.0.0.1/32    scram-sha-256
```
Then restart PostgreSQL.

#### 2. Install collectors
```bash
sudo apt update
sudo apt install -y telegraf lm-sensors smartmontools nvme-cli intel-gpu-tools
sudo sensors-detect --auto
```
Give Telegraf permission for SMART:
```bash
echo 'telegraf ALL=(root) NOPASSWD:/usr/sbin/smartctl' | sudo tee /etc/sudoers.d/telegraf-smart
```

#### 3. Configure Telegraf
Create `/etc/telegraf/telegraf.d/nuc-timescale.conf`:
```toml
[agent]
  interval = "30s"
  round_interval = true
  omit_hostname = false

[[inputs.cpu]] percpu=true totalcpu=true
[[inputs.mem]]
[[inputs.system]]

[[inputs.disk]]
  ignore_fs = ["tmpfs","devtmpfs","overlay","squashfs","aufs","nsfs","ramfs","bpf","cgroup2","tracefs","proc","sysfs"]
[[inputs.diskio]]

[[inputs.sensors]]
[[inputs.nvidia_smi]]
  bin_path = "/usr/bin/nvidia-smi"
  timeout = "5s"

[[inputs.smart]]
  use_sudo = true
  attributes = true
  nocheck = "standby"
  devices = ["/dev/nvme0","/dev/sda","/dev/sdb"]

[[outputs.sql]]
  driver = "pgx"
  data_source_name = "postgres://sensors:YOUR_PASSWORD@127.0.0.1:5432/sensors?sslmode=disable"
```

#### 4. Test and enable
```bash
sudo telegraf --config /etc/telegraf/telegraf.d/nuc-timescale.conf --test | head
sudo systemctl restart telegraf
sudo journalctl -u telegraf -n 50 --no-pager
```

#### 5. Verify in Timescale
```bash
sudo -u postgres psql sensors
\dt
SELECT time, host, util AS gpu_util, temperature_gpu AS gpu_temp FROM telegraf_nvidia_smi ORDER BY time DESC LIMIT 5;
SELECT time, host, feature, temp_input FROM telegraf_sensors ORDER BY time DESC LIMIT 5;
```

Convert tables to hypertables:
```sql
DO $$
DECLARE r record;
BEGIN
  FOR r IN SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename LIKE 'telegraf_%'
  LOOP
    EXECUTE format($f$SELECT create_hypertable('%I','time', if_not_exists => TRUE)$f$, r.tablename);
  END LOOP;
END$$;
```

Telegraf now continuously inserts CPU, GPU, temperature, and disk metrics into TimescaleDB.

### Push hypertable data to web server

Add a NOTIFY trigger in PostgreSQL

`sudo -u sensors psql`

```sql
-- 1) Create a function that NOTIFY’s a channel with a JSON payload
CREATE OR REPLACE FUNCTION public.sensors_notify()
RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE payload text;
BEGIN
  payload := json_build_object(
    'table','sensors',
    'op', TG_OP,
    'time', NEW.time,
    'device_id', NEW.device_id,
    'sensor_name', NEW.sensor_name,
    'value', NEW.value
  )::text;
  PERFORM pg_notify('sensors_changes', payload);
  RETURN NEW;
END; $$;
```

create a web_read role

```sql
CREATE ROLE web_read LOGIN PASSWORD 'webread_password';

-- read permissions
GRANT CONNECT ON DATABASE sensors TO web_read;
GRANT USAGE ON SCHEMA public TO web_read;
GRANT SELECT ON TABLE public.sensors TO web_read;
```

Install dependencies. Use a non-root service user and a virtualenv:

```bash
sudo adduser --system --group --home /opt/sse-bridge sse
sudo -u sse python3 -m venv /opt/sse-bridge/venv
sudo -u sse /opt/sse-bridge/venv/bin/pip install flask psycopg2-binary gunicorn
```

Create `sudo -u sse -H nano /opt/sse-bridge/sse.py`

```python
from flask import Flask, Response
import psycopg2, os, select, json, time

app = Flask(__name__)

def stream():
    conn = psycopg2.connect(
        host=os.getenv("PGHOST","localhost"),
        dbname=os.getenv("PGDATABASE","sensors"),
        user=os.getenv("PGUSER","web_read"),
        password=os.getenv("PGPASSWORD")
    )
    conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()
    cur.execute("LISTEN sensors_changes;")
    # keep-alive 25s for proxies
    last_ping = time.time()
    try:
        while True:
            if select.select([conn], [], [], 5)[0]:
                conn.poll()
                while conn.notifies:
                    n = conn.notifies.pop(0)
                    yield f"data: {n.payload}\n\n"
            if time.time() - last_ping > 25:
                yield ": keep-alive\n\n"
                last_ping = time.time()
    finally:
        cur.close(); conn.close()

@app.after_request
def sse_headers(resp):
    resp.headers["Cache-Control"] = "no-store"
    return resp

@app.get("/events")
def events():
    return Response(stream(), mimetype="text/event-stream")
```

Point nginx to it (reverse proxy)

```nginx
location /events {
    proxy_pass         http://127.0.0.1:5051/events;
    proxy_http_version 1.1;
    proxy_set_header   Host $host;
    proxy_set_header   X-Real-IP $remote_addr;
    proxy_buffering    off;
    proxy_cache        off;
    gzip               off;
    proxy_read_timeout 1h;
    add_header Cache-Control no-store;
}
```

`sudo nginx -t && sudo systemctl reload nginx`

Create a service

`sudo nano /etc/systemd/system/sse-bridge.service`

```bash
[Unit]
Description=SSE bridge for sensors
After=network.target

[Service]
User=sse
WorkingDirectory=/opt/sse-bridge
EnvironmentFile=/opt/sse-bridge/env.sh
ExecStart=/opt/sse-bridge/venv/bin/gunicorn -w 1 --threads 4 -b 127.0.0.1:5051 sse:app
Restart=always

[Install]
WantedBy=multi-user.target
```

Create the environment file:

```bash
# create env file
sudo -u sse -H nano /opt/sse-bridge/env.sh 

PGHOST=localhost
PGDATABASE=sensors
PGUSER=web_read
PGPASSWORD=password_for_webread

sudo -u sse -H chmod 600 /opt/sse-bridge/env.sh'
```

then

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now sse-bridge
sudo systemctl status sse-bridge
```

Check that data is pushed to the web server

```sql
sensors=# INSERT INTO public.sensors (time, device_id, sensor_name, value)
VALUES (now(), 'pink', 'disk_usage_pct', 60);
INSERT 0 1
sensors=# 
```

In the web server

```bash
pink@thebeachlab:~$ curl -i http://127.0.0.1:5051/events
HTTP/1.1 200 OK
Server: gunicorn
Date: Tue, 14 Oct 2025 14:07:49 GMT
Connection: keep-alive
Transfer-Encoding: chunked
Content-Type: text/event-stream; charset=utf-8
Cache-Control: no-store


data: {"table" : "sensors", "op" : "INSERT", "time" : "2025-10-14T14:09:10.324284+00:00", "device_id" : "pink", "sensor_name" : "disk_usage_pct", "value" : 60}
```

Catch the event with websocket






## Managing PostgreSQL with pgAdmin

### Install pgadmin4

```bash
#
# Setup the repository
#

# Install the public key for the repository (if not done previously):
sudo curl https://www.pgadmin.org/static/packages_pgadmin_org.pub | sudo apt-key add

# Create the repository configuration file:
sudo sh -c 'echo "deb https://ftp.postgresql.org/pub/pgadmin/pgadmin4/apt/$(lsb_release -cs) pgadmin4 main" > /etc/apt/sources.list.d/pgadmin4.list && apt update'

#
# Install pgAdmin
#
# Install for web mode only:
sudo apt install pgadmin4-web
```

### Apache and nginx together

To avoid both web servers listening to the same port change the default listening port from 80 to 5050 and 443 to 8090 in `/etc/apache2/ports.conf`

```apache
Listen 5050

<IfModule ssl_module>
        Listen 8090
</IfModule>

<IfModule mod_gnutls.c>
        Listen 8090
</IfModule>
```

and `sudo nano /etc/apache2/sites-available/000-default.conf` and set

```apache
<VirtualHost *:5050>
```

Then reload the service `sudo systemctl restart apache2` and verify Apache is listening to 8080 `sudo netstat -tlpn`

Also create the ufw rules `sudo ufw allow 5050 comment 'apache pgadmin'` and `sudo ufw reload`

pgadmin will be located at `http://server-address:5050/pgadmin4`

### Creating a subdomain (optional)

I created and enabled `/etc/nginx/sites-available/postgres.beachlab.org` with this content

```nginx
server {
        listen 80;
        listen [::]:80;
        server_name postgres.beachlab.org;
        return 301 http://beachlab.org:5050/pgadmin4;
}
```

If you don't require https that's all.

### Securing pgadmin with https (optional)

NOT WORKING YET. Check modules /etc/apache2/ports.conf and files in /etc/apache2/sites-enabled then change redisect in /etc/nginx/sites-available/postgres.beachlab.org (and remove ufw apache full rules?)

`sudo certbot certonly --standalone -d postgres.beachlab.org` which creates certificates in `/etc/letsencrypt/live/postgres.beachlab.org/`. Certificates will renew automatically.

Set

```bash
ServerName beachlab.org
ServerAlias postgres.beachlab.org
```

in `/etc/apache2/sites-available/000-default.conf`. Check syntax `sudo apache2ctl configtest` and `sudo systemctl reload apache2`

Install certbot apache plugin `sudo apt install certbot python3-certbot-apache` and run `sudo certbot --apache` but not redirect`


### Configure pgadmin

Run `/usr/pgadmin4/bin/setup-web.sh`

### Running pgadmin

Go to `http://server-ip:5050/pgadmin4`

### Reset pgadmin password
if you don't remember the credentials `mv /var/lib/pgadmin/pgadmin4.db /var/lib/pgadmin/pgadmin4.db.backup` and run `/usr/pgadmin4/bin/setup-web.sh` again.

Add a server and enter the connection details. You might have to connect to `sudo -u postgres psql` and `ALTER USER postgres PASSWORD 'mynewpassword';` if you don't remember your credentials.

### unlock pgadmin account
After 3 unsuccessful login attempts your account will be locked. Install `sudo apt install sqlite3` and run as root `sqlite3 pgadmin4.db "UPDATE USER SET LOCKED = false, LOGIN_ATTEMPTS = 0 WHERE USERNAME = 'user@domain.com';" ".exit"`

### pgadmin storage
ERD and other files are stored in `/var/lib/pgadmin/storage/email_account.org/`

## SQL Tips and tricks

### Create a readonly user

```sql
CREATE USER readonly WITH PASSWORD 'your_password';
\c air
GRANT CONNECT ON DATABASE air TO readonly;
GRANT USAGE ON SCHEMA public TO readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO readonly;
```

### For every table

- create a column named `id` with `bigint` or `int` datatype and IDENTITY. This will be the primary key. Enroll tables, also known as join tables will have more records than other records.
- create a column named `created` of `timestamp with timezone` datatype and default value `now()`
- create a column named `modified` of `timestamp with timezone` datatype and default value `now()`

Probably best to set all these in a table template.

### Autoupdate the modified timestamp when a record is updated

Using pgadmin query tool create a function `update_timestamp_modified_column()`

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

This function will appear under `trigger functions`. Now, for every table, we create a trigger for each table

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

Does not copy triggers. You will have to do this manually

### Add new column to existing table

Here adding a foreign key

```sql
ALTER TABLE interests ADD COLUMN IF NOT EXISTS interest_group_id INTEGER NOT NULL;
```

### Add one to many

Altered table has the many, select the foreign key. The reference table and (id) has the one

```sql
ALTER TABLE public.interests
    ADD FOREIGN KEY (interest_group_id)
    REFERENCES public.interest_group (id)
    NOT VALID;
```

### Create a JSON from a TABLE

```sql
SELECT json_agg(row_to_json(t))
FROM (
  SELECT *
  FROM your_table
) t
```

### Check the size of a TABLE

```sql
SELECT pg_size_pretty(pg_total_relation_size('table_name')) AS table_size;
```

### Create a unique constraint combination of 2 COLUMNS

```sql
-- Add a unique constraint on the combination of region_code and country_code
ALTER TABLE regions
ADD CONSTRAINT unique_region_country UNIQUE (region_code, country_code);
```

### Copy a TABLE from one DATABASE to another (same pg server)

```bash
sudo -u postgres pg_dump -d misc_data -t territories -f /tmp/territories.sql
sudo -u postgres psql -d air -f /tmp/territories.sql
```

### Delete ROWS
```sql
DELETE FROM countries WHERE alpha_2_code IS NULL;
```

### Create a VIEW with fallback values
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

### Get the definition that created a VIEW

Useful if you need to rename a column/recreate a view, etc.
```sql
SELECT view_definition
FROM information_schema.views
WHERE table_name = 'view_name';
```

## API and REST

### PostgREST

PostgREST is an open-source tool that automatically generates a RESTful API from a PostgreSQL database. Instead of writing backend code, you define your data model and permissions directly in the database, and PostgREST exposes them as secure, standards-compliant endpoints. This makes it easy to build scalable APIs quickly while leveraging PostgreSQL’s features like views, roles, and functions.

A RESTful API is an interface that allows systems to communicate over HTTP using the principles of Representational State Transfer (REST). It organizes resources into endpoints, typically accessed with standard HTTP methods like GET, POST, PUT, and DELETE, making interactions predictable and stateless. This approach simplifies integration, scalability, and flexibility across different platforms and clients.

Visit [PostgREST](postgrest.md) section

### FastAPI

FastAPI is a modern, high-performance web framework for building APIs with Python. It’s designed around Python type hints, which enable automatic validation, serialization, and interactive documentation. Known for its speed and ease of use, FastAPI makes it simple to create secure, production-ready APIs with minimal boilerplate code.

Install

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
```

Create the virtual environment (as pink)

```bash
mkdir -p ~/fastapi-app && cd ~/fastapi-app
python3 -m venv .venv
source .venv/bin/activate
```
Install dependencies

```bash
pip install --upgrade pip
pip install fastapi "uvicorn[standard]" gunicorn psycopg[binary]
```

Make a hello world app 

`/home/pink/fastapi-app/main.py`

```bash
from fastapi import FastAPI
app = FastAPI()
@app.get("/api/health")
def health(): return {"ok": True}
``` 

Create a system service

`sudo nano /etc/systemd/system/fastapi.service`

```bash
[Unit]
Description=FastAPI (pink)
After=network.target

[Service]
User=pink
Group=pink
WorkingDirectory=/home/pink/fastapi-app
Environment="PATH=/home/pink/fastapi-app/.venv/bin"
# (opcional) añade tus variables aquí:
# Environment="DATABASE_URL=postgres://api_ro:***@127.0.0.1:5432/tu_db"
ExecStart=/home/pink/fastapi-app/.venv/bin/gunicorn \
          -k uvicorn.workers.UvicornWorker -w 4 \
          -b 127.0.0.1:8000 main:app
Restart=always

[Install]
WantedBy=multi-user.target
```

and then

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now fastapi
```

For nginx reverse proxy, in the domain you desire add the following location

```nginx
location /api/ {
  proxy_pass http://127.0.0.1:8000/;
  proxy_set_header Host $host;
  proxy_set_header X-Forwarded-For $remote_addr;
}
```

and then

```bash
sudo nginx -t && sudo systemctl reload nginx
```




