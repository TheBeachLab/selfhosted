# Bluetti Mobile Lab Telemetry Pipeline

**Author:** Mr. Watson
**Date:** 2026-03-29

<!-- vim-markdown-toc GFM -->

- [Overview](#overview)
- [Architecture](#architecture)
- [Quick checks](#quick-checks)
- [MQTT topics](#mqtt-topics)
- [Database schema](#database-schema)
- [Ingest script](#ingest-script)
- [Ingest systemd](#ingest-systemd)
- [API access](#api-access)
- [MQTT WebSocket (live data)](#mqtt-websocket-live-data)
- [Privacy](#privacy)
- [Ops](#ops)
- [Changelog](#changelog)

<!-- vim-markdown-toc -->

## Overview

The G Mobile Lab is a Bluetti AC200M portable power station with sensors mounted on a Raspberry Pi 5 (pibot1). The RPi publishes telemetry to the server's Mosquitto broker via MQTT. A Python ingestor writes 30-second snapshots to TimescaleDB. PostgREST exposes the latest row via API. For real-time IMU/GPS visualization, browsers connect directly to MQTT over WebSocket.

## Architecture

```
RPi (pibot1)
  bluetti-mqtt ── BLE ── AC200M ──┐
  pibot-sensors ── I2C sensors ───┤  MQTT (bluetti/state/#)
  pibot-sensors ── GPS NEO-6M ────┤─────────────────────────► Mosquitto
  pibot-sensors ── IMU MPU-6050 ──┤                             │
  starlink-watcher ── gRPC ───────┘                             │
                                                    ┌───────────┴──────────┐
                                                    │                      │
                                             bluetti-ingest          WSS :8083
                                             (30s flush)          (live to browser)
                                                    │
                                              TimescaleDB
                                           (bluetti_stats)
                                                    │
                                               PostgREST
                                            (:3010 → Nginx)
                                                    │
                                          /api/telemetry/bluetti_latest
```

Two data paths:

- **DB path (30s):** MQTT → ingest script → `bluetti_stats` → `bluetti_latest` view → PostgREST → API poll from dashboard. Used for power, environment sensors, Starlink, GPS position.
- **Live path (2–5 Hz):** MQTT → Mosquitto WSS → browser MQTT.js client. Used for IMU attitude (pitch/roll/yaw) and speed/heading — too fast for DB storage.

## Quick checks

```bash
systemctl status bluetti-ingest postgrest-telemetry
curl -s https://api.beachlab.org/telemetry/public/bluetti_latest | python3 -m json.tool
journalctl -u bluetti-ingest -n 30 --no-pager
```

## MQTT topics

All under `bluetti/state/<device_id>/` where device_id is `AC200M-2241000242252`.

### Power (from bluetti-mqtt, BLE)

| Topic | Type | Notes |
|---|---|---|
| `total_battery_percent` | float | Mapped to `battery_percent` in DB |
| `dc_input_power` | float | Solar input (W) |
| `ac_input_power` | float | AC charger input (W) |
| `ac_output_power` | float | AC output (W) |
| `dc_output_power` | float | DC output (W) |
| `power_generation` | float | Total generation (W) |
| `ac_output_on` | string | `ON`/`OFF` → boolean |
| `dc_output_on` | string | `ON`/`OFF` → boolean |
| `ac_output_mode` | string | AC output mode |
| `internal_ac_voltage` | float | Internal AC voltage (V) |
| `internal_dc_input_voltage` | float | Internal DC input voltage (V) |
| `internal_dc_input_power` | float | Internal DC input power (W) |
| `auto_sleep_mode` | string | Auto sleep mode |
| `pack_details1` | JSON | Battery pack 1 details |
| `pack_details2` | JSON | Battery pack 2 details |

### Environment sensors (from pibot-sensors, I2C)

| Topic | Type | Notes |
|---|---|---|
| `co2_ppm` | float | K30 CO2 (ppm) |
| `temperature_c` | float | BME280 (°C) |
| `humidity_pct` | float | BME280 (%) |
| `pressure_hpa` | float | BME280 (hPa) |

### GPS (from pibot-sensors, NEO-6M)

| Topic | Type | Notes |
|---|---|---|
| `gps_lat` | float | Latitude, rounded to 2 decimals (~1 km) |
| `gps_lon` | float | Longitude, rounded to 2 decimals (~1 km) |
| `gps_speed_kmh` | float | Speed over ground (km/h) |
| `gps_altitude_m` | float | GPS altitude MSL (m) |
| `gps_satellites` | int | Number of satellites |
| `gps_fix` | int | 0=none, 1=GPS, 2=DGPS |
| `heading_deg` | float | Course over ground (°), valid when moving |

### Altitude (fused)

| Topic | Type | Notes |
|---|---|---|
| `altitude_m` | float | Fused GPS + barometric altitude (m) |
| `baro_altitude_m` | float | Barometric altitude from BME280 pressure (m) |

### IMU (from pibot-sensors, MPU-6050)

| Topic | Type | Notes |
|---|---|---|
| `imu_pitch_deg` | float | Pitch angle (°), 100-sample averaged |
| `imu_roll_deg` | float | Roll angle (°), 100-sample averaged |
| `imu_yaw_rate_dps` | float | Yaw rate (°/s), 100-sample averaged |

IMU topics publish at 2–5 Hz (fast path for live visualization). The 30s ingest cycle captures one snapshot for DB storage.

IMU reset: publish any message to `bluetti/cmd/<device_id>/imu_reset` to zero the current pitch/roll as the new flat reference. Calibration saved to `/opt/pibot-sensors/imu_calibration.json` on the RPi.

### Starlink (from pibot-sensors, gRPC)

| Topic | Type | Notes |
|---|---|---|
| `starlink_state` | string | CONNECTED, SEARCHING, BOOTING, STOWED, UNREACHABLE, etc. |
| `starlink_downlink_mbps` | float | Current download (Mbps) |
| `starlink_uplink_mbps` | float | Current upload (Mbps) |
| `starlink_ping_ms` | float | Latency (ms) |
| `starlink_ping_drop_rate` | float | Packet loss (0.0–1.0) |
| `starlink_uptime_s` | int | Dish uptime (s) |
| `starlink_obstructed` | bool | Currently obstructed? |
| `starlink_obstruction_pct` | float | Sky obstruction (%) |
| `starlink_gps_sats` | int | Dish GPS satellites |
| `starlink_country` | string | Country code (rough ~10 km) |
| `starlink_azimuth_deg` | float | Dish boresight azimuth (°) |
| `starlink_elevation_deg` | float | Dish boresight elevation (°) |
| `starlink_tilt_deg` | float | Physical tilt (°) |
| `starlink_alerts` | string | Comma-separated alerts, or `none` |

### Combined JSON topics (not ingested to DB)

- `environment` — co2, temp, humidity, pressure, altitude_m, baro_altitude_m
- `gps` — combined GPS JSON
- `imu` — combined IMU JSON (includes raw accel/gyro)
- `navigation` — lat, lon, speed, heading, altitude, pitch, roll, yaw_rate
- `starlink` — full JSON with all Starlink fields

### Event topics

- `bluetti/events/<device_id>/starlink` — Starlink state changes (published by starlink-watcher, 5s poll)
- `bluetti/events/<device_id>/wifi` — WiFi network changes (published by NM dispatcher)

## Database schema

Database: `sensors`. Table: `public.bluetti_stats` (TimescaleDB hypertable, 1-day chunks).

43 columns total: 2 keys + 10 power + 4 environment + 12 GPS/IMU + 14 Starlink + 1 extra (`starlink_ping_ms_avg`).

```sql
-- Current schema (2026-03-29)
CREATE TABLE public.bluetti_stats (
  time            timestamptz NOT NULL,
  device_id       text NOT NULL,
  -- Power
  battery_percent   double precision,
  dc_input_power    double precision,
  ac_input_power    double precision,
  ac_output_power   double precision,
  dc_output_power   double precision,
  power_generation  double precision,
  ac_output_on      boolean,
  dc_output_on      boolean,
  pack_details1     jsonb,
  pack_details2     jsonb,
  -- Environment (I2C sensors)
  co2_ppm           double precision,
  temperature_c     double precision,
  humidity_pct      double precision,
  pressure_hpa      double precision,
  -- Starlink
  starlink_state           text,
  starlink_downlink_mbps   double precision,
  starlink_uplink_mbps     double precision,
  starlink_ping_ms         double precision,
  starlink_ping_drop_rate  double precision,
  starlink_uptime_s        integer,
  starlink_obstructed      boolean,
  starlink_obstruction_pct double precision,
  starlink_gps_sats        integer,
  starlink_country         text,
  starlink_ping_ms_avg     double precision,
  starlink_azimuth_deg     double precision,
  starlink_elevation_deg   double precision,
  starlink_tilt_deg        double precision,
  starlink_alerts          text,
  -- GPS
  gps_lat           double precision,
  gps_lon           double precision,
  gps_speed_kmh     real,
  gps_altitude_m    real,
  gps_satellites    smallint,
  gps_fix           smallint,
  heading_deg       real,
  -- Altitude (fused)
  altitude_m        real,
  baro_altitude_m   real,
  -- IMU
  imu_pitch_deg     real,
  imu_roll_deg      real,
  imu_yaw_rate_dps  real
);

SELECT create_hypertable('bluetti_stats', 'time',
  if_not_exists => TRUE, chunk_time_interval => interval '1 day');

ALTER TABLE bluetti_stats
  ADD CONSTRAINT bluetti_stats_device_time_unique UNIQUE (device_id, time);

ALTER TABLE bluetti_stats
  SET (timescaledb.compress, timescaledb.compress_segmentby = 'device_id');

SELECT add_compression_policy('bluetti_stats', INTERVAL '7 days', if_not_exists => TRUE);
```

View:

```sql
CREATE OR REPLACE VIEW public.bluetti_latest AS
SELECT DISTINCT ON (device_id)
  time, device_id,
  battery_percent, dc_input_power, ac_input_power,
  ac_output_power, dc_output_power, power_generation,
  ac_output_on, dc_output_on,
  pack_details1, pack_details2,
  co2_ppm, temperature_c, humidity_pct, pressure_hpa,
  starlink_state, starlink_downlink_mbps, starlink_uplink_mbps,
  starlink_ping_ms, starlink_ping_drop_rate, starlink_uptime_s,
  starlink_obstructed, starlink_obstruction_pct,
  starlink_gps_sats, starlink_country,
  starlink_ping_ms_avg,
  starlink_azimuth_deg, starlink_elevation_deg, starlink_tilt_deg,
  starlink_alerts,
  gps_lat, gps_lon, gps_speed_kmh, gps_altitude_m,
  gps_satellites, gps_fix, heading_deg,
  altitude_m, baro_altitude_m,
  imu_pitch_deg, imu_roll_deg, imu_yaw_rate_dps
FROM bluetti_stats
ORDER BY device_id, time DESC;

GRANT SELECT ON public.bluetti_latest TO web_anon;
```

### Grants

```sql
GRANT SELECT        ON public.bluetti_stats  TO web_anon, telemetry_api;
GRANT SELECT        ON public.bluetti_latest TO web_anon, telemetry_api;
GRANT INSERT,SELECT ON public.bluetti_stats  TO telemetry_ingest;
```

> **Note:** `ON CONFLICT ... DO NOTHING` requires SELECT in addition to INSERT. Grant both to the ingest role.

Data retention: indefinite (compression after 7 days). As of 2026-03-29: ~12k rows, ~10 MB, oldest row 2026-03-25.

## Ingest script

Location: `/home/pink/.openclaw/workspace/scripts/bluetti_ingest.py`

- Subscribes to `bluetti/state/#` (QoS 1)
- Parses topic as `bluetti/state/<device_id>/<field>`
- Stores all fields in `state[device_id]` dict (thread-safe with Lock)
- Flushes a snapshot row per device every 30 seconds
- Auto-reconnects to DB on connection loss

Key functions:

- `on_message()` — captures any MQTT field into state dict
- `flush()` — builds row dict from state, executes INSERT, schedules next flush
- `to_float()`, `to_int()`, `to_bool()`, `to_json()` — type coercers (None-safe)

## Ingest systemd

### `/etc/systemd/system/bluetti-ingest.service`

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

Uses the same env file and venv as `telemetry-ingest.service`.

## API access

PostgREST exposes `bluetti_latest` via the existing telemetry API route:

```bash
# Latest row (all fields)
curl -s https://api.beachlab.org/telemetry/public/bluetti_latest

# Select specific fields
curl -s 'https://api.beachlab.org/telemetry/public/bluetti_latest?select=time,battery_percent,gps_lat,gps_lon,imu_pitch_deg,imu_roll_deg'

# History (last 24h)
curl -s 'https://api.beachlab.org/telemetry/public/bluetti_stats?time=gte.2026-03-28T00:00:00Z&order=time.asc&limit=500'
```

Nginx route (same as server telemetry):

```nginx
location /api/telemetry/ {
    proxy_pass http://127.0.0.1:3010/;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $remote_addr;
}
```

## MQTT WebSocket (live data)

For real-time IMU/GPS visualization, browsers connect directly to Mosquitto over WSS.

- **Endpoint:** `wss://mosquitto.beachlab.org:8083/`
- **Auth:** anonymous (no credentials needed)
- **ACL:** read-only access to `bluetti/#`
- **Port 8083:** open in firewall, TLS with Let's Encrypt cert
- **Client library:** MQTT.js (browser build)

### Mosquitto ACL

File: `/etc/mosquitto/aclfile`

```
# Bluetti / Home Assistant (vehicle pibot1)
user door
topic readwrite bluetti/#
topic readwrite homeassistant/#

# Anonymous read for Bluetti telemetry
topic read bluetti/#
```

Fast topics (2–5 Hz): `imu_pitch_deg`, `imu_roll_deg`, `imu_yaw_rate_dps`, `heading_deg`, `gps_speed_kmh`, `altitude_m`.

All other topics publish at 30s intervals and are better consumed via API polling.

## Privacy

GPS coordinates are **rounded at the sensor level** (RPi) to 2 decimal places before MQTT publish. This gives ~1.1 km precision — enough for a map dot without revealing exact location. Full-precision coordinates never leave the RPi.

The public API (`bluetti_latest`) only ever contains the rounded values. The D3 wireframe map on the dashboard further obscures location due to its low-detail coastline rendering.

## Ops

```bash
# Service status
systemctl status bluetti-ingest

# Recent ingest logs
journalctl -u bluetti-ingest -n 30 --no-pager

# Restart after script changes
sudo systemctl restart bluetti-ingest

# Reload PostgREST schema (after view/table changes)
sudo -u postgres psql -d sensors -c "NOTIFY pgrst, 'reload schema';"

# Note: PostgREST does not support config reload — always use restart after config changes:
# sudo systemctl restart postgrest-telemetry

# Row count and size
sudo -u postgres psql -d sensors -c "SELECT pg_size_pretty(hypertable_size('bluetti_stats')) AS size, count(*) AS rows FROM bluetti_stats;"

# IMU calibration reset
mosquitto_pub -h 127.0.0.1 -t 'bluetti/cmd/AC200M-2241000242252/imu_reset' -m 'reset'

# Quick MQTT check (10 messages, 5s timeout)
mosquitto_sub -t 'bluetti/state/#' -C 10 -W 5

# Check MQTT topics live (continuous)
mosquitto_sub -h 127.0.0.1 -t 'bluetti/state/#' -v
```

### Adding new columns

When new sensors are added to pibot1:

1. `ALTER TABLE bluetti_stats ADD COLUMN <name> <type>;`
2. Add column to INSERT_SQL and flush() row dict in `bluetti_ingest.py`
3. `DROP VIEW bluetti_latest; CREATE VIEW ...` with the new column
4. `GRANT SELECT ON public.bluetti_latest TO web_anon;`
5. `sudo systemctl restart bluetti-ingest`
6. `NOTIFY pgrst, 'reload schema';`

### Troubleshooting

- **Rows stop appearing:** check `journalctl -u bluetti-ingest` — likely DB reconnect or MQTT disconnect. Service auto-restarts.
- **API returns old data:** check if `bluetti-ingest` is running. If view was recreated, run `NOTIFY pgrst, 'reload schema'`.
- **New columns return NULL:** the RPi may not be publishing the topic yet, or the MQTT field name in the ingest script doesn't match the topic suffix.
- **IMU values noisy:** verify the RPi is averaging samples (check pibot-sensors logs). If still noisy, increase sample count.

## Changelog

- **2026-03-29:** Added 12 GPS/IMU columns (gps_lat, gps_lon, gps_speed_kmh, gps_altitude_m, gps_satellites, gps_fix, heading_deg, altitude_m, baro_altitude_m, imu_pitch_deg, imu_roll_deg, imu_yaw_rate_dps). RPi now publishes IMU at 2–5 Hz with 100-sample averaging, GPS rounded to 2 decimals for privacy, IMU reset via MQTT command.
- **2026-03-28:** Added sensor columns (co2_ppm, temperature_c, humidity_pct, pressure_hpa) and 14 Starlink columns. Starlink watcher service + WiFi auto-reconnect on RPi.
- **2026-03-25:** Initial pipeline — Bluetti power fields, ingest script, hypertable, PostgREST exposure.
