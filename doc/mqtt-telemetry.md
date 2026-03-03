# MQTT Telemetry (alpha/stats)

**Author:** Mr. Watson 🦄
**Date:** 2026-02-07

<!-- vim-markdown-toc GFM -->

- [Goal](#goal)
- [Quick checks](#quick-checks)
- [Final Topic Design](#final-topic-design)
- [What is included in `alpha/stats`](#what-is-included-in-alphastats)
- [Scripts created](#scripts-created)
- [Scheduler (cron)](#scheduler-cron)
- [Broker access model](#broker-access-model)
- [Notes on speedtest reliability](#notes-on-speedtest-reliability)
- [Minimal frontend subscription](#minimal-frontend-subscription)
- [Code snippets (sanitized, self-contained)](#code-snippets-sanitized-self-contained)
- [Security reminder](#security-reminder)

<!-- vim-markdown-toc -->

## Goal

Publish server telemetry for dashboards using MQTT, with public read-only consumption and authenticated publishing.

## Quick checks

```bash
mosquitto_sub -h 127.0.0.1 -t alpha/stats -C 1 -v
crontab -l | grep -E 'publish_telemetry|publish_speedtest'
tail -n 50 /tmp/telemetry.log
```

## Final Topic Design

- `alpha/stats` → retained live payload (includes latest speedtest summary)
- `alpha/stats/speedtest` → full speedtest payload (also retained)

For a website, subscribing to `alpha/stats` is enough.

## What is included in `alpha/stats`

- timestamp, host
- CPU usage + temperature
- memory usage
- disk usage (`/`)
- load average
- NVIDIA GPU stats (if available)
- uptime
- `speedtest` summary block (latest known value)

## Scripts created

- `scripts/publish_telemetry.sh`
- `scripts/publish_speedtest.sh`
- `scripts/install_telemetry_cron.sh`
- `scripts/telemetry.env` (local config)
- `scripts/telemetry.env.example`
- `scripts/last_speedtest.json` (cache for latest speedtest result)

## Scheduler (cron)

Installed jobs:

```cron
* * * * * /home/pink/.openclaw/workspace/scripts/publish_telemetry.sh >/tmp/telemetry.log 2>&1
17 */6 * * * /home/pink/.openclaw/workspace/scripts/publish_speedtest.sh >/tmp/telemetry-speedtest.log 2>&1
```

- live telemetry every minute
- speedtest every 6 hours at minute 17

## Broker access model

Mosquitto configured for **public read only** on alpha stats:

- anonymous: read `alpha/stats` and `alpha/stats/#`
- authenticated publisher user: write `alpha/stats` and `alpha/stats/#`

This allows dashboards/websites to subscribe without credentials while keeping write access controlled.

## Notes on speedtest reliability

The speedtest script:

1. tries Ookla CLI (`speedtest`)
2. falls back to `speedtest-cli` if needed
3. caches last result to `scripts/last_speedtest.json`
4. injects a normalized `speedtest` summary into `alpha/stats`

If speedtest times out, summary includes an `error` field instead of values.

## Minimal frontend subscription

Subscribe to:

- `alpha/stats`

Expect a retained JSON payload, so clients receive last known value immediately upon connect.

## Code snippets (sanitized, self-contained)

### `scripts/telemetry.env` (sanitized)

```bash
BROKER_HOST=127.0.0.1
BROKER_PORT=1883
MQTT_USERNAME='YOUR_PUBLISH_USER'
MQTT_PASSWORD='YOUR_PUBLISH_PASSWORD'
QOS=1
RETAIN=true
LIVE_TOPIC='alpha/stats'
# Optional:
# SPEEDTEST_TOPIC='alpha/stats/speedtest'
```

### `scripts/publish_telemetry.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
[ -f "$SCRIPT_DIR/telemetry.env" ] && source "$SCRIPT_DIR/telemetry.env"

BROKER_HOST="${BROKER_HOST:-127.0.0.1}"
BROKER_PORT="${BROKER_PORT:-1883}"
TOPIC="${LIVE_TOPIC:-${TOPIC:-alpha/stats/live}}"
QOS="${QOS:-1}"
RETAIN="${RETAIN:-false}"
MQTT_USERNAME="${MQTT_USERNAME:-}"
MQTT_PASSWORD="${MQTT_PASSWORD:-}"
DRY_RUN="${DRY_RUN:-false}"

iso_ts="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
host="$(hostname)"

cpu_usage() {
  local cpu a b c idle1 total1 idle2 total2 diff_idle diff_total
  read -r cpu a b c idle1 _ < /proc/stat
  total1=$((a+b+c+idle1))
  sleep 1
  read -r cpu a b c idle2 _ < /proc/stat
  total2=$((a+b+c+idle2))
  diff_idle=$((idle2-idle1))
  diff_total=$((total2-total1))
  if [ "$diff_total" -le 0 ]; then echo "0"; return; fi
  awk -v di="$diff_idle" -v dt="$diff_total" 'BEGIN{printf "%.1f", (1 - di/dt)*100}'
}

cpu_temp() {
  if sensors -j >/dev/null 2>&1; then
    sensors -j 2>/dev/null | jq -r '
      .. | objects | to_entries[]? | select(.key|test("temp[0-9]+_input")) | .value
    ' 2>/dev/null | awk 'NR==1{printf "%.1f", $1; found=1} END{if(!found) print "null"}'
  else
    echo "null"
  fi
}

gpu_json() {
  if command -v nvidia-smi >/dev/null 2>&1; then
    nvidia-smi --query-gpu=name,temperature.gpu,utilization.gpu,memory.used,memory.total,power.draw --format=csv,noheader,nounits 2>/dev/null \
      | awk -F', *' 'NR==1 {printf "{\"name\":\"%s\",\"temp_c\":%s,\"util_percent\":%s,\"mem_used_mb\":%s,\"mem_total_mb\":%s,\"power_w\":%s}", $1,$2,$3,$4,$5,$6; found=1} END{if(!found) printf "null"}'
  else
    echo "null"
  fi
}

mem_json() {
  free -m | awk '/^Mem:/ {printf "{\"total_mb\":%d,\"used_mb\":%d,\"free_mb\":%d,\"used_percent\":%.1f}", $2,$3,$4,($3/$2)*100}'
}

disk_json() {
  df -P / | awk 'NR==2 {gsub("%","",$5); printf "{\"mount\":\"/\",\"used_percent\":%d,\"used_gb\":%.2f,\"avail_gb\":%.2f}", $5,$3/1048576,$4/1048576}'
}

load_json() {
  local l1 l5 l15
  read -r l1 l5 l15 _ < /proc/loadavg
  echo "{\"l1\":$l1,\"l5\":$l5,\"l15\":$l15}"
}

uptime_s="$(cut -d' ' -f1 /proc/uptime | awk '{printf "%d", $1}')"
cpu_p="$(cpu_usage)"
cpu_t="$(cpu_temp)"
gpu="$(gpu_json)"
mem="$(mem_json)"
disk="$(disk_json)"
load="$(load_json)"

speedtest_summary="null"
if [ -f "$SCRIPT_DIR/last_speedtest.json" ]; then
  speedtest_summary="$(jq -c '{
    timestamp:(.speedtest?.timestamp // .timestamp // null),
    ping_ms:(.speedtest?.ping?.latency // null),
    down_mbps:((.speedtest?.download?.bandwidth? // null) | if . == null then null else (. * 8 / 1000000) end),
    up_mbps:((.speedtest?.upload?.bandwidth? // null) | if . == null then null else (. * 8 / 1000000) end),
    packet_loss:(.speedtest?.packetLoss // null),
    error:(.error // null)
  }' "$SCRIPT_DIR/last_speedtest.json" 2>/dev/null || echo null)"
fi

payload="$(jq -nc \
  --arg ts "$iso_ts" \
  --arg host "$host" \
  --argjson cpu_usage "$cpu_p" \
  --argjson cpu_temp "$cpu_t" \
  --argjson uptime_s "$uptime_s" \
  --argjson mem "$mem" \
  --argjson disk "$disk" \
  --argjson load "$load" \
  --argjson gpu "$gpu" \
  --argjson speedtest "$speedtest_summary" \
  '{timestamp:$ts,host:$host,cpu:{usage_percent:$cpu_usage,temp_c:$cpu_temp},memory:$mem,disk:$disk,loadavg:$load,gpu:$gpu,uptime_s:$uptime_s,speedtest:$speedtest}'
)"

args=(-h "$BROKER_HOST" -p "$BROKER_PORT" -q "$QOS" -t "$TOPIC" -m "$payload")
if [ -n "$MQTT_USERNAME" ]; then args+=( -u "$MQTT_USERNAME" ); fi
if [ -n "$MQTT_PASSWORD" ]; then args+=( -P "$MQTT_PASSWORD" ); fi
if [ "$RETAIN" = "true" ]; then args+=( -r ); fi

if [ "$DRY_RUN" = "true" ]; then
  echo "$payload"
else
  mosquitto_pub "${args[@]}"
fi
```

### `scripts/publish_speedtest.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
[ -f "$SCRIPT_DIR/telemetry.env" ] && source "$SCRIPT_DIR/telemetry.env"

BROKER_HOST="${BROKER_HOST:-127.0.0.1}"
BROKER_PORT="${BROKER_PORT:-1883}"
TOPIC="${SPEEDTEST_TOPIC:-${TOPIC:-alpha/stats/speedtest}}"
QOS="${QOS:-1}"
TIMEOUT_S="${TIMEOUT_S:-300}"
RETAIN="${RETAIN:-true}"
CACHE_FILE="${CACHE_FILE:-$SCRIPT_DIR/last_speedtest.json}"
MQTT_USERNAME="${MQTT_USERNAME:-}"
MQTT_PASSWORD="${MQTT_PASSWORD:-}"
DRY_RUN="${DRY_RUN:-false}"

iso_ts="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
host="$(hostname)"

raw="$(timeout "$TIMEOUT_S" speedtest --accept-license --accept-gdpr --format=json 2>/dev/null || true)"

if [ -z "$raw" ] && command -v speedtest-cli >/dev/null 2>&1; then
  legacy="$(timeout "$TIMEOUT_S" speedtest-cli --json 2>/dev/null || true)"
  if [ -n "$legacy" ]; then
    payload="$(jq -nc --arg ts "$iso_ts" --arg host "$host" --argjson s "$legacy" '{timestamp:$ts,host:$host,speedtest:{timestamp:$ts,ping:{latency:($s.ping//null)},download:{bandwidth:(($s.download//0)/8)},upload:{bandwidth:(($s.upload//0)/8)},packetLoss:null,server:{name:($s.server.name//null),id:($s.server.id//null),location:($s.server.name//null)}}}')"
  else
    payload="$(jq -nc --arg ts "$iso_ts" --arg host "$host" '{timestamp:$ts,host:$host,error:"speedtest_failed_or_timed_out"}')"
  fi
elif [ -z "$raw" ]; then
  payload="$(jq -nc --arg ts "$iso_ts" --arg host "$host" '{timestamp:$ts,host:$host,error:"speedtest_failed_or_timed_out"}')"
else
  payload="$(jq -nc --arg ts "$iso_ts" --arg host "$host" --argjson s "$raw" '{timestamp:$ts,host:$host,speedtest:$s}')"
fi

echo "$payload" > "$CACHE_FILE"

args=(-h "$BROKER_HOST" -p "$BROKER_PORT" -q "$QOS" -t "$TOPIC" -m "$payload")
if [ -n "$MQTT_USERNAME" ]; then args+=( -u "$MQTT_USERNAME" ); fi
if [ -n "$MQTT_PASSWORD" ]; then args+=( -P "$MQTT_PASSWORD" ); fi
if [ "$RETAIN" = "true" ]; then args+=( -r ); fi

if [ "$DRY_RUN" = "true" ]; then
  echo "$payload"
else
  mosquitto_pub "${args[@]}"
fi
```

### Cron entries (final)

```cron
* * * * * /home/pink/.openclaw/workspace/scripts/publish_telemetry.sh >/tmp/telemetry.log 2>&1
17 */6 * * * /home/pink/.openclaw/workspace/scripts/publish_speedtest.sh >/tmp/telemetry-speedtest.log 2>&1
```

### Mosquitto ACL snippet (public read, restricted writes)

```conf
# Anonymous public read (dashboard)
topic read alpha/stats
topic read alpha/stats/#

user door
topic write alpha/stats
topic read alpha/stats
topic write alpha/stats/#
topic read alpha/stats/#
```

## Security reminder

Do **not** publish credentials in repo/docs. Keep credentials in local runtime config only.

## Sensor robustness (`validate_json`)

When a hardware sensor fails (e.g. GPU in ERR! state returning `[GPU requires reset]` instead of a number), passing that value to `jq --argjson` produces invalid JSON and the whole script aborts — no MQTT message is published, DB goes stale.

### Fix applied (2026-03-03)

Added a `validate_json()` helper that sanitizes each sensor output before it reaches `jq`:

```bash
# Returns the value if it is valid JSON, otherwise returns "null"
validate_json() {
  local val="$1"
  if echo "$val" | jq -e . >/dev/null 2>&1; then
    echo "$val"
  else
    echo "null"
  fi
}
```

All sensor variables are wrapped:

```bash
cpu_t="$(validate_json "$(cpu_temp 2>/dev/null || echo null)")"
gpu="$(validate_json  "$(gpu_json  2>/dev/null || echo null)")"
mem="$(validate_json  "$(mem_json  2>/dev/null || echo null)")"
disk="$(validate_json "$(disk_json 2>/dev/null || echo null)")"
load="$(validate_json "$(load_json 2>/dev/null || echo null)")"
```

Additional hardening in `gpu_json()` — NVIDIA fields like `[GPU requires reset]` and `[N/A]` are sanitized via `sed` before building the JSON object:

```bash
nvidia-smi ... 2>/dev/null \
  | sed 's/\[[^]]*\]/null/g' \
  | awk -F', *' '...'
```

Final guard — abort silently if the assembled payload is still invalid:

```bash
if ! echo "$payload" | jq -e . >/dev/null 2>&1; then
  echo "publish_telemetry: invalid payload, skipping" >&2
  exit 1
fi
```

Result: if any sensor breaks, that field becomes `null` in the dashboard; all other metrics continue flowing normally.

## Adding physical sensors (BME280 + K30 CO2)

Physical sensors publish to `alpha/sensors/<device_id>` via MQTT. The server subscribes and writes each reading to the `sensors` table, which triggers the SSE bridge for real-time frontend updates.

### MQTT payload format

Each device publishes a JSON object to `alpha/sensors/<device_id>`:

```json
{
  "device_id": "room1",
  "timestamp": "2026-03-03T10:00:00Z",
  "readings": {
    "temperature_c":  23.4,
    "humidity_pct":   61.2,
    "pressure_hpa":  1013.1,
    "co2_ppm":        812
  }
}
```

The ingest script expands each key in `readings` into one row in `sensors(time, device_id, sensor_name, value)`.

### BME280 (I2C — temperature, humidity, pressure)

**Wiring (Raspberry Pi):**

| BME280 | RPi pin |
|--------|---------|
| VCC    | 3.3V (pin 1) |
| GND    | GND (pin 6) |
| SDA    | GPIO 2 / SDA (pin 3) |
| SCL    | GPIO 3 / SCL (pin 5) |

Default I2C address: `0x76` (SDO to GND) or `0x77` (SDO to VCC).

**Enable I2C on Raspberry Pi:**

```bash
sudo raspi-config  # Interface Options → I2C → Enable
# or:
sudo sed -i 's/#dtparam=i2c_arm=on/dtparam=i2c_arm=on/' /boot/config.txt
echo "i2c-dev" | sudo tee -a /etc/modules
sudo reboot
# verify:
i2cdetect -y 1   # should show 0x76 or 0x77
```

**Install deps:**

```bash
sudo apt install python3-smbus python3-pip mosquitto-clients
pip3 install smbus2 bme280 paho-mqtt
```

**Reading script (`read_bme280.py`):**

```python
#!/usr/bin/env python3
import json, time
from datetime import datetime, timezone
import smbus2, bme280
import paho.mqtt.client as mqtt

DEVICE_ID   = "room1"         # change per location
MQTT_HOST   = "YOUR_SERVER_IP"
MQTT_PORT   = 1883
MQTT_TOPIC  = f"alpha/sensors/{DEVICE_ID}"
MQTT_USER   = "YOUR_PUBLISH_USER"
MQTT_PASS   = "YOUR_PUBLISH_PASSWORD"
I2C_PORT    = 1
I2C_ADDRESS = 0x76
INTERVAL_S  = 60

bus = smbus2.SMBus(I2C_PORT)
calibration = bme280.load_calibration_params(bus, I2C_ADDRESS)
client = mqtt.Client()
client.username_pw_set(MQTT_USER, MQTT_PASS)
client.connect(MQTT_HOST, MQTT_PORT)
client.loop_start()

while True:
    data = bme280.sample(bus, I2C_ADDRESS, calibration)
    payload = json.dumps({
        "device_id": DEVICE_ID,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "readings": {
            "temperature_c": round(data.temperature, 2),
            "humidity_pct":  round(data.humidity, 2),
            "pressure_hpa":  round(data.pressure, 2),
        }
    })
    client.publish(MQTT_TOPIC, payload, qos=1, retain=True)
    time.sleep(INTERVAL_S)
```

Run as a service or via cron every minute.

### K30 CO2 sensor (UART)

The SenseAir K30 uses UART at 9600 baud, 8N1. Connect via a USB-UART adapter or directly to the Raspberry Pi UART pins (disable serial console first).

**Wiring (USB-UART adapter):**

| K30      | Adapter |
|----------|---------|
| G+  (Tx) | RX      |
| G0  (Rx) | TX      |
| G+  (5V) | 5V      |
| GND      | GND     |

Find the device: `ls /dev/ttyUSB*` or `/dev/ttyS0` for native UART.

**Install deps:**

```bash
pip3 install pyserial paho-mqtt
```

**Reading script (`read_k30.py`):**

```python
#!/usr/bin/env python3
import json, time, serial
from datetime import datetime, timezone
import paho.mqtt.client as mqtt

DEVICE_ID  = "room1"
MQTT_HOST  = "YOUR_SERVER_IP"
MQTT_PORT  = 1883
MQTT_TOPIC = f"alpha/sensors/{DEVICE_ID}"
MQTT_USER  = "YOUR_PUBLISH_USER"
MQTT_PASS  = "YOUR_PUBLISH_PASSWORD"
SERIAL_DEV = "/dev/ttyUSB0"
INTERVAL_S = 60

# K30 read CO2 command (Modbus-style)
CMD = bytes([0xFE, 0x44, 0x00, 0x08, 0x02, 0x9F, 0x25])

def read_co2(ser):
    ser.write(CMD)
    time.sleep(0.5)
    resp = ser.read(7)
    if len(resp) < 7 or resp[0] != 0xFE:
        return None
    return (resp[3] << 8) | resp[4]

client = mqtt.Client()
client.username_pw_set(MQTT_USER, MQTT_PASS)
client.connect(MQTT_HOST, MQTT_PORT)
client.loop_start()

with serial.Serial(SERIAL_DEV, 9600, timeout=1) as ser:
    while True:
        ppm = read_co2(ser)
        if ppm is not None:
            payload = json.dumps({
                "device_id": DEVICE_ID,
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "readings": {"co2_ppm": ppm}
            })
            client.publish(MQTT_TOPIC, payload, qos=1, retain=True)
        time.sleep(INTERVAL_S)
```

**Combine both sensors** by merging `readings` dicts and publishing one payload per device.

### Server-side ingest

Add a subscriber to `mqtt_to_timescale.py` (or a separate script) that handles `alpha/sensors/#` and writes to the `sensors` table:

```python
SENSOR_INSERT = """
INSERT INTO public.sensors (time, device_id, sensor_name, value)
VALUES (%s, %s, %s, %s)
ON CONFLICT (time, device_id, sensor_name) DO NOTHING;
"""

def on_sensor_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload)
        ts   = parse_time(data.get("timestamp"))
        did  = data.get("device_id", msg.topic.split("/")[-1])
        for name, val in (data.get("readings") or {}).items():
            if val is not None:
                with conn.cursor() as cur:
                    cur.execute(SENSOR_INSERT, (ts, did, name, float(val)))
    except Exception as e:
        log.exception("sensor ingest error: %s", e)
```

Subscribe to the additional topic in `on_connect`:

```python
client.subscribe("alpha/sensors/#", qos=1)
```

Update Mosquitto ACL to allow reads from `alpha/sensors/#`:

```conf
topic read alpha/sensors/#
```

### Quick test

From the server, verify a sensor is publishing:

```bash
mosquitto_sub -h 127.0.0.1 -t "alpha/sensors/#" -C 1 -v
```

Check the last inserted reading:

```sql
SELECT time, device_id, sensor_name, value
FROM sensors
ORDER BY time DESC
LIMIT 10;
```
