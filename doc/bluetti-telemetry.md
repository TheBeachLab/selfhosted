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

### OBD2

| Topic | Type | Notes |
|---|---|---|
| `obd_rpm` | float | Engine RPM |
| `obd_speed_kmh` | float | Vehicle speed (km/h) |
| `obd_throttle_pct` | float | Throttle position (%) |
| `obd_engine_load_pct` | float | Calculated engine load (%) |
| `obd_boost_kpa` | float | Turbo boost pressure (kPa) |
| `obd_coolant_temp_c` | float | Coolant temperature (C) |
| `obd_intake_temp_c` | float | Intake air temperature (C) |
| `obd_oil_temp_c` | float | Oil temperature (C) |
| `obd_fuel_level_pct` | float | Fuel level (%) |
| `obd_fuel_rail_pressure_kpa` | float | Fuel rail pressure (kPa) |
| `obd_maf_gps` | float | Mass air flow (g/s) |
| `obd_runtime_s` | int | Engine runtime (s) |
| `obd_voltage_v` | float | OBD adapter voltage (V) |
| `obd_dtc_count` | int | Diagnostic trouble code count |
| `obd_connected` | string | `true`/`false` → boolean |

### Combined JSON topics (not ingested to DB)

- `environment` — co2, temp, humidity, pressure, altitude_m, baro_altitude_m
- `gps` — combined GPS JSON
- `imu` — combined IMU JSON (includes raw accel/gyro)
- `navigation` — lat, lon, speed, heading, altitude, pitch, roll, yaw_rate
- `starlink` — full JSON with all Starlink fields
- `obd` — combined OBD JSON
- `obd_engine` — engine-specific OBD JSON
- `obd_status` — OBD connection status JSON
- `obd_dtcs` — diagnostic trouble codes JSON array

### Event topics

- `bluetti/events/<device_id>/starlink` — Starlink state changes (published by starlink-watcher, 5s poll)
- `bluetti/events/<device_id>/wifi` — WiFi network changes (published by NM dispatcher)

## Database schema

Database: `sensors`. Table: `public.bluetti_stats` (TimescaleDB hypertable, 1-day chunks).

58 columns total: 2 keys + 10 power + 4 environment + 12 GPS/IMU + 14 Starlink + 1 extra (`starlink_ping_ms_avg`) + 15 OBD2.

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
  imu_yaw_rate_dps  real,
  -- OBD2
  obd_rpm               real,
  obd_speed_kmh         real,
  obd_throttle_pct      real,
  obd_engine_load_pct   real,
  obd_boost_kpa         real,
  obd_coolant_temp_c    real,
  obd_intake_temp_c     real,
  obd_oil_temp_c        real,
  obd_fuel_level_pct    real,
  obd_fuel_rail_pressure_kpa real,
  obd_maf_gps           real,
  obd_runtime_s         integer,
  obd_voltage_v         real,
  obd_dtc_count         integer,
  obd_connected         boolean
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
  imu_pitch_deg, imu_roll_deg, imu_yaw_rate_dps,
  obd_rpm, obd_speed_kmh, obd_throttle_pct, obd_engine_load_pct,
  obd_boost_kpa, obd_coolant_temp_c, obd_intake_temp_c, obd_oil_temp_c,
  obd_fuel_level_pct, obd_fuel_rail_pressure_kpa, obd_maf_gps,
  obd_runtime_s, obd_voltage_v, obd_dtc_count, obd_connected
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

- **2026-04-02:** Added 15 OBD-II telemetry columns. A dedicated collector publishes scalar vehicle diagnostics through an ELM327-compatible adapter; the public runbook intentionally omits vehicle and device identifiers.
- **2026-03-29:** Added 12 GPS/IMU columns (gps_lat, gps_lon, gps_speed_kmh, gps_altitude_m, gps_satellites, gps_fix, heading_deg, altitude_m, baro_altitude_m, imu_pitch_deg, imu_roll_deg, imu_yaw_rate_dps). RPi now publishes IMU at 2–5 Hz with 100-sample averaging, GPS rounded to 2 decimals for privacy, IMU reset via MQTT command.
- **2026-03-28:** Added sensor columns (co2_ppm, temperature_c, humidity_pct, pressure_hpa) and 14 Starlink columns. Starlink watcher service + WiFi auto-reconnect on RPi.
- **2026-03-25:** Initial pipeline — Bluetti power fields, ingest script, hypertable, PostgREST exposure.

## Field freshness and website instruments (2026-09-12)

The old ingestor wrote its in-memory state every 30 seconds with the current
clock, even without new MQTT deliveries. On September 12, a 24-hour query had
2,879 rows but just one distinct pitch value; the observed public snapshot
combined `Unreachable` Starlink with cached throughput and repeated -31°/-26.7°
attitude. An eight-second non-retained subscription received no message. These
observations establish repeated stored state, not the vehicle's actual attitude.
The Pi SSH endpoint also timed out; its physical power/connection state remains
unverified.

The versioned replacement is `scripts/mobile-lab/bluetti_ingest.py`, with pure
state handling in `observation_state.py`. It ignores retained replay without a
trusted source time, expires each field after five minutes, and timestamps each
row with the last accepted delivery rather than the flush clock. Repeated
snapshots use the same unique key, so they cannot manufacture new history. Empty
state continues scheduling (the previous early return stopped the timer).
`001-field-freshness.sql` adds nullable `field_received_at` JSONB and appends it
to the existing view, preserving old rows and grants. Old rows with no metadata
must never establish sensor freshness.

Supported inputs are legacy `bluetti/state/<id>/<field>`, upstream
`bluetti/<id>/state/<field>`, and whitelisted `gml/nav`, `gml/cabin`, and
`gml/starlink` fields for this vehicle. These mappings were checked against
`bluetti-starlink-mqtt/pibot-sensors/sensor_mqtt.py` on 2026-09-12. They are code
compatibility, not evidence that the updated Pi publisher is running. Broker
permissions are unchanged. Public coordinates remain rounded to two decimals;
combined raw messages, private fields and command topics are not stored.

A `gml/nav` source timestamp older than five minutes is rejected (including
old outbox traffic). Untimestamped non-retained fields have receipt provenance,
not a guaranteed sensor sampling time; the UI says "received" accordingly.
Future producer work should timestamp every group before outbox enqueue.

The website uses independently aged field values. It hides stale attitude,
withholds Starlink throughput when the dish is disconnected, requires a recent
GPS fix, uses GPS altitude rather than silently substituting barometric altitude,
and marks suspect CO2 as "Check sensor". The CO2 250–10,000 ppm range is a UI
sanity check, not an air-quality standard or a safety classification.

The W463 drawings are based on the owner's supplied photographs. The vehicle
and perpendicular needle rotate together against a stationary signed scale;
roll has no horizontal reference line. Positive pitch raises the right-facing
nose; positive roll lowers the vehicle's right side in the front view. These
are display conventions. Vehicle mounting alignment has not been verified and
no IMU zero/reset command was sent. Missing readings show no angle or needle.

Deploy the additive migration first, then install `bluetti_ingest.py` and
`observation_state.py` beside the existing runtime script and restart only
`bluetti-ingest`. Keep a private backup of the previous script and view definition.
Rollback the service by restoring the prior script; leave the additive metadata
column intact. Validate imports in the runtime venv, run
`python3 -m unittest discover -s scripts/mobile-lab -p 'test_*.py'`, and verify
that retained replay alone produces no new rows. Never seed test telemetry on
the production broker; instrument test readings belong in a local preview.
