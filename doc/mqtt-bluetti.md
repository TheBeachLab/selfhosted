# Bluetti AC200M — MQTT Ingest to TimescaleDB

**Author:** Mr. Watson 🦄
**Date:** 2026-03-25

<!-- vim-markdown-toc GFM -->

- [Goal](#goal)
- [Architecture](#architecture)
- [MQTT Topics](#mqtt-topics)
- [Mosquitto ACL](#mosquitto-acl)
- [Database](#database)
- [Ingest Service](#ingest-service)
- [PostgREST API](#postgrest-api)
- [Ops checks](#ops-checks)

<!-- vim-markdown-toc -->

## Goal

Persist live power station data from a vehicle-mounted Bluetti AC200M (via a Raspberry Pi 5, `pibot1`) into TimescaleDB and expose it via PostgREST. Data flows when the vehicle has internet (Starlink).

## Architecture

```
Bluetti AC200M
    └─► pibot1 (Raspberry Pi 5)
            └─► MQTT broker (mosquitto) — topics: bluetti/state/<device_id>/<field>
                    └─► bluetti-ingest.service (Python)
                            └─► TimescaleDB (sensors DB)
                                    └─► PostgREST → /api/telemetry/bluetti_latest
```

Each field is published as a plain string on its own topic, updated every few seconds. The ingest service aggregates all fields for a device and writes one row every 30 seconds.

## MQTT Topics

**Base:** `bluetti/state/<device_id>/<field_name>`

Device: `AC200M-2241000242252`

| Field | Type | Notes |
|---|---|---|
| `total_battery_percent` | float | State of charge % |
| `dc_input_power` | float | W |
| `ac_input_power` | float | W |
| `ac_output_power` | float | W |
| `dc_output_power` | float | W |
| `power_generation` | float | W |
| `ac_output_on` | ON/OFF | AC output state |
| `dc_output_on` | ON/OFF | DC output state |
| `ac_output_mode` | string | |
| `internal_ac_voltage` | float | V |
| `internal_dc_input_voltage` | float | V |
| `internal_dc_input_power` | float | W |
| `auto_sleep_mode` | string | |
| `pack_details1` | JSON | Cell voltages, pack 1 |
| `pack_details2` | JSON | Cell voltages, pack 2 |

### Quick check

```bash
mosquitto_sub -t 'bluetti/state/#' -C 10 -W 5
```

## Mosquitto ACL

File: `/etc/mosquitto/aclfile`

```
# Bluetti / Home Assistant (vehicle pibot1)
user door
topic readwrite bluetti/#
topic readwrite homeassistant/#

# Anonymous read for Bluetti telemetry
topic read bluetti/#
```

## Database

Database: `sensors`

### Table: `bluetti_stats`

```sql
CREATE TABLE public.bluetti_stats (
  time              TIMESTAMPTZ      NOT NULL,
  device_id         TEXT             NOT NULL,
  battery_percent   DOUBLE PRECISION,
  dc_input_power    DOUBLE PRECISION,
  ac_input_power    DOUBLE PRECISION,
  ac_output_power   DOUBLE PRECISION,
  dc_output_power   DOUBLE PRECISION,
  power_generation  DOUBLE PRECISION,
  ac_output_on      BOOLEAN,
  dc_output_on      BOOLEAN,
  pack_details1     JSONB,
  pack_details2     JSONB
);

SELECT create_hypertable('public.bluetti_stats', 'time');

CREATE UNIQUE INDEX bluetti_stats_device_time_idx
  ON public.bluetti_stats (device_id, time DESC);

-- Compress chunks older than 7 days
ALTER TABLE public.bluetti_stats SET (
  timescaledb.compress,
  timescaledb.compress_segmentby = 'device_id',
  timescaledb.compress_orderby   = 'time DESC'
);
SELECT add_compression_policy('public.bluetti_stats', INTERVAL '7 days');
```

### View: `bluetti_latest`

```sql
CREATE VIEW public.bluetti_latest AS
SELECT DISTINCT ON (device_id)
  time, device_id,
  battery_percent,
  dc_input_power, ac_input_power,
  ac_output_power, dc_output_power,
  power_generation,
  ac_output_on, dc_output_on,
  pack_details1, pack_details2
FROM public.bluetti_stats
ORDER BY device_id, time DESC;
```

### Grants

```sql
GRANT SELECT        ON public.bluetti_stats  TO web_anon, telemetry_api;
GRANT SELECT        ON public.bluetti_latest TO web_anon, telemetry_api;
GRANT INSERT,SELECT ON public.bluetti_stats  TO telemetry_ingest;
```

> **Note:** `ON CONFLICT … DO NOTHING` requires SELECT in addition to INSERT. Grant both to the ingest role.

## Ingest Service

Script: `/home/pink/.openclaw/workspace/scripts/bluetti_ingest.py`

- Subscribes to `bluetti/state/#`
- Collects individual field messages per device in memory
- Flushes one row per device to DB every 30 seconds (`FLUSH_INTERVAL`)
- Auto-reconnects to PostgreSQL if connection drops
- Uses same venv and env file as `telemetry-ingest`

### Service file: `/etc/systemd/system/bluetti-ingest.service`

```ini
[Unit]
Description=Bluetti MQTT to TimescaleDB ingestor
After=network-online.target postgresql.service mosquitto.service
Wants=network-online.target

[Service]
Type=simple
User=pink
Group=pink
EnvironmentFile=/etc/telemetry-ingest.env
ExecStart=/opt/telemetry-ingest/.venv/bin/python /home/pink/.openclaw/workspace/scripts/bluetti_ingest.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### Service management

```bash
sudo systemctl status bluetti-ingest
sudo systemctl restart bluetti-ingest
journalctl -u bluetti-ingest -n 50 --no-pager
```

## PostgREST API

PostgREST instance: `postgrest-telemetry` (port 3010, `db-anon-role = web_anon`)

> **Note:** PostgREST does not support config reload — always use `restart` after schema changes.

```bash
sudo systemctl restart postgrest-telemetry
```

### Endpoints

```bash
# Latest reading per device
curl 'http://127.0.0.1:3010/bluetti_latest'

# Via public API
curl 'https://beachlab.org/api/telemetry/bluetti_latest'

# History (last 24h)
ISO=$(date -u -d '24 hours ago' +%Y-%m-%dT%H:%M:%SZ)
curl "http://127.0.0.1:3010/bluetti_stats?time=gte.${ISO}&order=time.desc"

# Specific device
curl 'http://127.0.0.1:3010/bluetti_latest?device_id=eq.AC200M-2241000242252'
```

## Ops checks

```bash
# Is data flowing?
sudo -u postgres psql -d sensors -c \
  "SELECT time, device_id, battery_percent, ac_output_on, dc_input_power \
   FROM bluetti_stats ORDER BY time DESC LIMIT 5;"

# Table size
sudo -u postgres psql -d sensors -c \
  "SELECT pg_size_pretty(hypertable_size('bluetti_stats')) AS size, \
   count(*) AS rows FROM bluetti_stats;"

# Service logs
journalctl -u bluetti-ingest -n 30 --no-pager

# Live MQTT check
mosquitto_sub -t 'bluetti/state/#' -C 5 -W 10
```
