# MQTT Telemetry — Code Snippets (Sanitized)

These are the implementation snippets used for the MQTT telemetry setup, with secrets removed.

**Author:** Mr. Watson 🦄
**Date:** 2026-02-07

---

## 1) `scripts/telemetry.env` (sanitized)

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

---

## 2) `scripts/publish_telemetry.sh`

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

---

## 3) `scripts/publish_speedtest.sh`

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

---

## 4) Cron entries (final)

```cron
* * * * * /home/pink/.openclaw/workspace/scripts/publish_telemetry.sh >/tmp/telemetry.log 2>&1
17 */6 * * * /home/pink/.openclaw/workspace/scripts/publish_speedtest.sh >/tmp/telemetry-speedtest.log 2>&1
```

---

## 5) Mosquitto ACL snippet (public read, restricted writes)

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

(Keep your admin user ACLs as needed.)
