# MQTT → TimescaleDB + PostgREST (Telemetry History)

**Author:** Mr. Watson 🦄
**Date:** 2026-02-07

<!-- vim-markdown-toc GFM -->

- [Goal](#goal)
- [Architecture](#architecture)
- [Quick checks](#quick-checks)
- [SQL setup (Timescale + table + retention + API roles)](#sql-setup-timescale--table--retention--api-roles)
- [Ingestor script (`mqtt_to_timescale.py`)](#ingestor-script-mqtt_to_timescalepy)
- [Ingestor env + systemd](#ingestor-env--systemd)
- [PostgREST config + systemd](#postgrest-config--systemd)
- [Nginx website route (history API)](#nginx-website-route-history-api)
- [Useful API calls](#useful-api-calls)
- [Ops checks](#ops-checks)

<!-- vim-markdown-toc -->

## Goal

Store historical telemetry from MQTT in TimescaleDB and expose it safely via PostgREST for dashboard charts.

## Architecture

- Source: MQTT topic `alpha/stats` (retained JSON)
- Ingestor: `telemetry-ingest.service`
- Storage: TimescaleDB hypertable in DB `sensors`
- API: PostgREST on `127.0.0.1:3010`

Flow:

- live card from MQTT (`alpha/stats`)
- history from PostgREST (`telemetry_stats` / `telemetry_latest`)

## Quick checks

```bash
systemctl status telemetry-ingest postgrest
curl -s http://127.0.0.1:3010/telemetry_latest?limit=1
journalctl -u telemetry-ingest -n 80 --no-pager
```

## SQL setup (Timescale + table + retention + API roles)

Run in database `sensors` as superuser (`postgres`).

```sql
CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS public.telemetry_stats (
  time timestamptz NOT NULL,
  host text NOT NULL,
  cpu_usage_percent double precision,
  cpu_temp_c double precision,
  memory_used_percent double precision,
  disk_used_percent double precision,
  load1 double precision,
  load5 double precision,
  load15 double precision,
  gpu_util_percent double precision,
  gpu_temp_c double precision,
  uptime_s bigint,
  speedtest_ping_ms double precision,
  speedtest_down_mbps double precision,
  speedtest_up_mbps double precision,
  speedtest_error text,
  payload jsonb NOT NULL
);

SELECT create_hypertable(
  'public.telemetry_stats',
  'time',
  if_not_exists => TRUE,
  chunk_time_interval => interval '1 day'
);

ALTER TABLE public.telemetry_stats
  ADD CONSTRAINT telemetry_stats_host_time_unique UNIQUE (host, time);

CREATE INDEX IF NOT EXISTS telemetry_stats_time_desc_idx
  ON public.telemetry_stats (time DESC);

CREATE INDEX IF NOT EXISTS telemetry_stats_host_time_desc_idx
  ON public.telemetry_stats (host, time DESC);

ALTER TABLE public.telemetry_stats
  SET (timescaledb.compress, timescaledb.compress_segmentby = 'host');

SELECT add_compression_policy('public.telemetry_stats', INTERVAL '7 days', if_not_exists => TRUE);
SELECT add_retention_policy('public.telemetry_stats', INTERVAL '32 days', if_not_exists => TRUE);

CREATE OR REPLACE VIEW public.telemetry_latest AS
SELECT DISTINCT ON (host)
  time, host,
  cpu_usage_percent, cpu_temp_c,
  memory_used_percent,
  disk_used_percent,
  load1, load5, load15,
  gpu_util_percent, gpu_temp_c,
  uptime_s,
  speedtest_ping_ms, speedtest_down_mbps, speedtest_up_mbps, speedtest_error,
  payload
FROM public.telemetry_stats
ORDER BY host, time DESC;
```

### Roles and grants (example placeholders)

```sql
-- Replace passwords with your own
CREATE ROLE telemetry_ingest LOGIN PASSWORD 'REPLACE_WITH_STRONG_PASSWORD';
CREATE ROLE web_anon NOLOGIN;
CREATE ROLE telemetry_api LOGIN PASSWORD 'REPLACE_WITH_STRONG_PASSWORD';
GRANT web_anon TO telemetry_api;

GRANT CONNECT ON DATABASE sensors TO telemetry_ingest, telemetry_api;
GRANT USAGE ON SCHEMA public TO telemetry_ingest, web_anon;
GRANT INSERT ON TABLE public.telemetry_stats TO telemetry_ingest;
GRANT SELECT ON TABLE public.telemetry_stats TO web_anon;
GRANT SELECT ON TABLE public.telemetry_latest TO web_anon;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO web_anon;
```

## Ingestor script (`mqtt_to_timescale.py`)

```python
#!/usr/bin/env python3
import json
import logging
import os
import signal
import sys
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
import psycopg

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("mqtt-to-timescale")

DB_DSN = os.environ["DB_DSN"]
MQTT_HOST = os.getenv("MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "alpha/stats")
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "")

INSERT_SQL = """
INSERT INTO public.telemetry_stats (
  time, host,
  cpu_usage_percent, cpu_temp_c,
  memory_used_percent,
  disk_used_percent,
  load1, load5, load15,
  gpu_util_percent, gpu_temp_c,
  uptime_s,
  speedtest_ping_ms, speedtest_down_mbps, speedtest_up_mbps, speedtest_error,
  payload
) VALUES (
  %(time)s, %(host)s,
  %(cpu_usage)s, %(cpu_temp)s,
  %(mem_used)s,
  %(disk_used)s,
  %(l1)s, %(l5)s, %(l15)s,
  %(gpu_util)s, %(gpu_temp)s,
  %(uptime)s,
  %(sp_ping)s, %(sp_down)s, %(sp_up)s, %(sp_error)s,
  %(payload)s::jsonb
)
ON CONFLICT (host, time) DO NOTHING;
"""

conn = psycopg.connect(DB_DSN)
conn.autocommit = True


def parse_time(ts: str):
    if not ts:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return datetime.now(timezone.utc)


def to_float(v):
    try:
        if v is None:
            return None
        return float(v)
    except Exception:
        return None


def to_int(v):
    try:
        if v is None:
            return None
        return int(v)
    except Exception:
        return None


def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        log.info("Connected to MQTT %s:%s, subscribing to %s", MQTT_HOST, MQTT_PORT, MQTT_TOPIC)
        client.subscribe(MQTT_TOPIC, qos=1)
    else:
        log.error("MQTT connect failed with rc=%s", rc)


def on_message(client, userdata, msg):
    try:
        raw = msg.payload.decode("utf-8", errors="replace")
        data = json.loads(raw)

        speedtest = data.get("speedtest") or {}

        payload = {
            "time": parse_time(data.get("timestamp")),
            "host": data.get("host") or "unknown",
            "cpu_usage": to_float((data.get("cpu") or {}).get("usage_percent")),
            "cpu_temp": to_float((data.get("cpu") or {}).get("temp_c")),
            "mem_used": to_float((data.get("memory") or {}).get("used_percent")),
            "disk_used": to_float((data.get("disk") or {}).get("used_percent")),
            "l1": to_float((data.get("loadavg") or {}).get("l1")),
            "l5": to_float((data.get("loadavg") or {}).get("l5")),
            "l15": to_float((data.get("loadavg") or {}).get("l15")),
            "gpu_util": to_float((data.get("gpu") or {}).get("util_percent")),
            "gpu_temp": to_float((data.get("gpu") or {}).get("temp_c")),
            "uptime": to_int(data.get("uptime_s")),
            "sp_ping": to_float(speedtest.get("ping_ms")),
            "sp_down": to_float(speedtest.get("down_mbps")),
            "sp_up": to_float(speedtest.get("up_mbps")),
            "sp_error": speedtest.get("error"),
            "payload": json.dumps(data, separators=(",", ":")),
        }

        with conn.cursor() as cur:
            cur.execute(INSERT_SQL, payload)

    except Exception as e:
        log.exception("Failed to process message on %s: %s", msg.topic, e)


def shutdown(signum, frame):
    log.info("Shutting down (signal %s)", signum)
    try:
        client.disconnect()
    except Exception:
        pass
    try:
        conn.close()
    except Exception:
        pass
    sys.exit(0)


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
if MQTT_USERNAME:
    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
client.on_connect = on_connect
client.on_message = on_message

signal.signal(signal.SIGINT, shutdown)
signal.signal(signal.SIGTERM, shutdown)

client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
client.loop_forever()
```

## Ingestor env + systemd

### `/etc/telemetry-ingest.env` (example)

```bash
DB_DSN=postgresql://telemetry_ingest:REPLACE_WITH_STRONG_PASSWORD@127.0.0.1:5432/sensors
MQTT_HOST=127.0.0.1
MQTT_PORT=1883
MQTT_TOPIC=alpha/stats
# Optional when broker requires auth for subscribe:
# MQTT_USERNAME=your_user
# MQTT_PASSWORD=your_password
LOG_LEVEL=INFO
```

### `/etc/systemd/system/telemetry-ingest.service`

```ini
[Unit]
Description=MQTT to TimescaleDB ingestor (alpha/stats)
After=network-online.target postgresql.service mosquitto.service
Wants=network-online.target

[Service]
Type=simple
User=pink
Group=pink
EnvironmentFile=/etc/telemetry-ingest.env
ExecStart=/opt/telemetry-ingest/.venv/bin/python /home/pink/.openclaw/workspace/scripts/mqtt_to_timescale.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

## PostgREST config + systemd

### `/etc/postgrest-telemetry.conf` (example)

```ini
db-uri = "postgres://telemetry_api:REPLACE_WITH_STRONG_PASSWORD@127.0.0.1:5432/sensors"
db-schemas = "public"
db-anon-role = "web_anon"
server-host = "127.0.0.1"
server-port = 3010
openapi-mode = "follow-privileges"
```

### `/etc/systemd/system/postgrest-telemetry.service`

```ini
[Unit]
Description=PostgREST for telemetry (sensors DB)
After=network.target postgresql.service

[Service]
Type=simple
ExecStart=/usr/local/bin/postgrest /etc/postgrest-telemetry.conf
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
```

## Nginx website route (history API)

Added to `beachlab.org` vhost so website code can query history under the same domain:

```nginx
# Telemetry history API (PostgREST -> TimescaleDB)
location /api/telemetry/ {
    proxy_pass http://127.0.0.1:3010/;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $remote_addr;
}
```

This maps:

- `https://beachlab.org/api/telemetry/telemetry_latest` → `http://127.0.0.1:3010/telemetry_latest`
- `https://beachlab.org/api/telemetry/telemetry_stats` → `http://127.0.0.1:3010/telemetry_stats`

## Useful API calls

```bash
# Latest row per host
curl 'http://127.0.0.1:3010/telemetry_latest?select=time,host,cpu_usage_percent,disk_used_percent,speedtest_down_mbps,speedtest_error'

# Same via website route
curl 'https://beachlab.org/api/telemetry/telemetry_latest?select=time,host,cpu_usage_percent,disk_used_percent,speedtest_down_mbps,speedtest_error'

# Recent history
curl 'http://127.0.0.1:3010/telemetry_stats?select=time,host,cpu_usage_percent,memory_used_percent,disk_used_percent&order=time.desc&limit=200'

# Last 24h only
curl 'http://127.0.0.1:3010/telemetry_stats?time=gte.2026-02-06T12:00:00Z&select=time,host,cpu_usage_percent&order=time.asc'
```

## Ops checks

```bash
# Services
systemctl status telemetry-ingest
systemctl status postgrest-telemetry

# Ingest logs
journalctl -u telemetry-ingest -n 100 --no-pager

# PostgREST logs
journalctl -u postgrest-telemetry -n 100 --no-pager

# Row count
sudo -u postgres psql -d sensors -c "SELECT count(*) FROM public.telemetry_stats;"
```

---

## Updates (2026-03-11)

### Indefinite retention + compression

Removed the 32-day retention policy. Data is now kept forever. TimescaleDB compression (already configured) compresses chunks older than 7 days (~10-20x ratio, ~10-20 MB/year).

```bash
# Remove retention
sudo -u postgres psql -d sensors -c "SELECT remove_retention_policy('telemetry_stats');"

# Verify compression policy still active
sudo -u postgres psql -d sensors -c "SELECT * FROM timescaledb_information.jobs WHERE hypertable_name = 'telemetry_stats';"

# Check table size
sudo -u postgres psql -d sensors -c "SELECT pg_size_pretty(hypertable_size('telemetry_stats')) AS total_size, (SELECT count(*) FROM telemetry_stats) AS rows, (SELECT min(time) FROM telemetry_stats) AS oldest;"
```

### Auto-reconnect in mqtt_to_timescale.py

The ingestor used a module-level DB connection that was never re-established after a PostgreSQL restart or timeout. Added `get_conn()` helper that checks if the connection is alive and reconnects if closed. Symptom: no new rows in `telemetry_stats` despite cron running normally.

```bash
# If telemetry stops flowing, check logs first:
journalctl -u telemetry-ingest -n 30 --no-pager

# Restart to recover (now also self-heals on next message):
sudo systemctl restart telemetry-ingest
```

### Environment data (building sensors + Open-Meteo)

`telemetry_stats` and `telemetry_latest` now include environment columns:

| Column | Source | Notes |
|---|---|---|
| `temp` | Open-Meteo `temperature_2m` | Replace with physical sensor when available |
| `humidity` | Open-Meteo `relative_humidity_2m` | Replace with physical sensor |
| `pressure` | Open-Meteo `surface_pressure` | Replace with physical sensor |
| `co2` | — | NULL until physical sensor |
| `uv_index` | Open-Meteo | Outdoor, always from API |
| `wind_kph` | Open-Meteo `wind_speed_10m` | Outdoor |
| `sunrise` | Open-Meteo daily | HH:MM format |
| `sunset` | Open-Meteo daily | HH:MM format |

Location: Sitges, Barcelona (`41.2369, 1.8119`, `Europe/Madrid`). Open-Meteo is fetched every 15 min and cached at `scripts/openmeteo_cache.json`. NULL is stored (never 0) if a value is unavailable — the frontend shows `-` for null.

```bash
# Force fresh Open-Meteo fetch:
rm /home/pink/.openclaw/workspace/scripts/openmeteo_cache.json
```
