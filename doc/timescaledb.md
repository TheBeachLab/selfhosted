# TimescaleDB

IoT stores huge time series data. Relational databases can be used to store the data but processing can be slow. TimescaleDB is an NoSQL database optimized to store time-series data. It is implemented as an extension of PostgreSQL combining the ease of use of relational databases and the speed of NoSQL databases.

- [TimescaleDB](#timescaledb)
  - [Install](#install)
  - [Configure and optimize](#configure-and-optimize)
  - [Convert existing `sensors` database into hypertable](#convert-existing-sensors-database-into-hypertable)
  - [Manually insert sensor data in the hypertable](#manually-insert-sensor-data-in-the-hypertable)
  - [Automatic insert sensor data in the hypertable](#automatic-insert-sensor-data-in-the-hypertable)
  - [Push hypertable data to web server](#push-hypertable-data-to-web-server)
  - [Catch the event with SSE](#catch-the-event-with-sse)
  - [Add a Time series for the server internal sensors](#add-a-time-series-for-the-server-internal-sensors)
    - [1. Create the role and database](#1-create-the-role-and-database)
    - [2. Install collectors](#2-install-collectors)
    - [3. Configure Telegraf](#3-configure-telegraf)
    - [4. Test and enable](#4-test-and-enable)
    - [5. Verify in Timescale](#5-verify-in-timescale)


## Install

```bash
sudo add-apt-repository ppa:timescale/timescaledb-ppa
sudo apt update
sudo apt install timescaledb-postgresql-12
```

## Configure and optimize

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

## Convert existing `sensors` database into hypertable

First execute psql as `sensors` user

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

## Manually insert sensor data in the hypertable

You can enter data like this:

```sql 
INSERT INTO sensors (time, device_id, sensor_name, value)
VALUES (now(), 'pink', 'disk_usage_pct', 42.3);
```

## Automatic insert sensor data in the hypertable

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

## Push hypertable data to web server

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

## Catch the event with SSE

And update your website

```html
<table id="readings">
  <thead>
    <tr><th>Device</th><th>Sensor</th><th>Value</th><th>Time</th></tr>
  </thead>
  <tbody></tbody>
</table>

<script>
  // Open the SSE stream
  const es = new EventSource('/events');
  es.onmessage = (ev) => updateDashboard(JSON.parse(ev.data));

  // Paint/update the UI with the newest reading
  function updateDashboard(msg) {
    // Try to be flexible with field names coming from your backend
    const device = msg.device_id || msg.device || 'unknown';
    const sensor = msg.sensor_name || msg.sensor || msg.table || 'reading';
    const value  = msg.value ?? msg.val ?? msg.reading ?? '—';
    const ts     = msg.ts || msg.time || msg.timestamp || new Date().toISOString();

    // Use (device,sensor) as a stable row key
    const key = `${device}:${sensor}`;
    const tbody = document.querySelector('#readings tbody');
    let row = tbody.querySelector(`tr[data-key="${key}"]`);

    if (!row) {
      // Create row if first time we see this (device,sensor)
      row = document.createElement('tr');
      row.setAttribute('data-key', key);
      row.innerHTML = `
        <td class="c-device"></td>
        <td class="c-sensor"></td>
        <td class="c-value"></td>
        <td class="c-time"></td>
      `;
      tbody.appendChild(row);
    }

    // Update the cells
    row.querySelector('.c-device').textContent = device;
    row.querySelector('.c-sensor').textContent = sensor;
    row.querySelector('.c-value').textContent  = String(value);
    row.querySelector('.c-time').textContent   = new Date(ts).toLocaleString();

    // Optional: quick highlight effect when a value changes
    row.classList.add('updated');
    setTimeout(() => row.classList.remove('updated'), 400);
  }
</script>

<style>
  /* Optional: tiny highlight so you "see" live updates */
  tr.updated { transition: background 0.4s; background: rgba(255, 230, 150, 0.6); }
  table { border-collapse: collapse; width: 100%; }
  th, td { border-bottom: 1px solid #ddd; padding: 6px 8px; text-align: left; }
</style>
```



## Add a Time series for the server internal sensors

This section sets up automatic collection of internal hardware metrics (CPU, GPU, disks, sensors) and stores them in TimescaleDB using Telegraf.

### 1. Create the role and database
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

### 2. Install collectors
```bash
sudo apt update
sudo apt install -y telegraf lm-sensors smartmontools nvme-cli intel-gpu-tools
sudo sensors-detect --auto
```
Give Telegraf permission for SMART:
```bash
echo 'telegraf ALL=(root) NOPASSWD:/usr/sbin/smartctl' | sudo tee /etc/sudoers.d/telegraf-smart
```

### 3. Configure Telegraf
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

### 4. Test and enable
```bash
sudo telegraf --config /etc/telegraf/telegraf.d/nuc-timescale.conf --test | head
sudo systemctl restart telegraf
sudo journalctl -u telegraf -n 50 --no-pager
```

### 5. Verify in Timescale
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
