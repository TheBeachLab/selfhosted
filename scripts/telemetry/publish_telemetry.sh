#!/usr/bin/env bash
set -uo pipefail

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

OPENMETEO_CACHE="$SCRIPT_DIR/openmeteo_cache.json"
OPENMETEO_URL="https://api.open-meteo.com/v1/forecast?latitude=41.2369&longitude=1.8119&current=temperature_2m,relative_humidity_2m,surface_pressure,uv_index,wind_speed_10m&daily=sunrise,sunset&timezone=Europe%2FMadrid&forecast_days=1"
OPENMETEO_TTL=900  # 15 minutes

iso_ts="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
host="$(hostname)"

cpu_usage() {
  # /proc/stat includes iowait, irq, softirq and steal. Guest time is already
  # included in user/nice and must not be counted twice.
  local first second
  first=$(awk '/^cpu / {print $2+$3+$4+$5+$6+$7+$8+$9, $5+$6; exit}' /proc/stat)
  sleep 1
  second=$(awk '/^cpu / {print $2+$3+$4+$5+$6+$7+$8+$9, $5+$6; exit}' /proc/stat)
  awk -v a="$first" -v b="$second" 'BEGIN {split(a,x); split(b,y); dt=y[1]-x[1]; if(dt<=0) print "null"; else printf "%.1f",100*(1-(y[2]-x[2])/dt)}'
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
  if [ -x /usr/local/bin/nvidia-smi-safe.sh ]; then
    /usr/local/bin/nvidia-smi-safe.sh --query-gpu=name,temperature.gpu,utilization.gpu,memory.used,memory.total,power.draw --format=csv,noheader,nounits 2>/dev/null \
      | sed 's/\[[^]]*\]/null/g' \
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

# Validate JSON — returns null if value is not valid JSON
validate_json() {
  local val="$1"
  if echo "$val" | jq -e . >/dev/null 2>&1; then
    echo "$val"
  else
    echo "null"
  fi
}

# Fetch Open-Meteo with 15-minute cache
openmeteo_fetch() {
  local now cache_age=99999
  now=$(date +%s)
  if [ -f "$OPENMETEO_CACHE" ]; then
    local cache_time
    cache_time=$(stat -c %Y "$OPENMETEO_CACHE" 2>/dev/null || echo 0)
    cache_age=$((now - cache_time))
  fi
  if [ "$cache_age" -ge "$OPENMETEO_TTL" ]; then
    local raw
    raw=$(curl -sf --max-time 10 "$OPENMETEO_URL" 2>/dev/null) || true
    if echo "$raw" | jq -e . >/dev/null 2>&1; then
      local temporary
      temporary=$(mktemp "${OPENMETEO_CACHE}.XXXXXX")
      printf '%s\n' "$raw" > "$temporary" && mv "$temporary" "$OPENMETEO_CACHE"
    fi
  fi
  if [ -f "$OPENMETEO_CACHE" ]; then
    cat "$OPENMETEO_CACHE"
  else
    echo "null"
  fi
}

env_json() {
  local meteo
  meteo="$(openmeteo_fetch)"

  local temp humidity pressure uv wind sr ss
  temp="$(echo "$meteo"     | jq '.current.temperature_2m      // null' 2>/dev/null || echo "null")"
  humidity="$(echo "$meteo" | jq '.current.relative_humidity_2m // null' 2>/dev/null || echo "null")"
  pressure="$(echo "$meteo" | jq '.current.surface_pressure      // null' 2>/dev/null || echo "null")"
  uv="$(echo "$meteo"       | jq '.current.uv_index              // null' 2>/dev/null || echo "null")"
  wind="$(echo "$meteo"     | jq '.current.wind_speed_10m        // null' 2>/dev/null || echo "null")"
  sr="$(echo "$meteo"       | jq -r '(.daily.sunrise // [null])[0] // "null"' 2>/dev/null || echo "null")"
  ss="$(echo "$meteo"       | jq -r '(.daily.sunset  // [null])[0] // "null"' 2>/dev/null || echo "null")"

  # Strip date prefix: "2026-03-04T07:30" → "07:30"
  [ "$sr" != "null" ] && sr="$(echo "$sr" | sed 's/.*T//')"
  [ "$ss" != "null" ] && ss="$(echo "$ss" | sed 's/.*T//')"

  local observed date_label
  # Open-Meteo current.time is local time plus an explicit UTC offset.
  observed=$(echo "$meteo" | jq -r 'if .current.time then (((.current.time + "Z") | fromdateiso8601?) // ((.current.time + ":00Z") | fromdateiso8601?)) - (.utc_offset_seconds // 0) | todateiso8601 else null end' 2>/dev/null || echo null)
  date_label=$(echo "$meteo" | jq -r '.daily.time[0] // ""' 2>/dev/null || true)
  jq -nc \
    --arg observed "$observed" \
    --arg date_label "$date_label" \
    --argjson temp     "$temp" \
    --argjson humidity "$humidity" \
    --argjson pressure "$pressure" \
    --argjson uv       "$uv" \
    --argjson wind     "$wind" \
    --arg     sr       "$sr" \
    --arg     ss       "$ss" \
    '{
      source: { name: "Open-Meteo", timestamp: (if $observed == "null" or $observed == "" then null else $observed end), date: $date_label },
      building: { temp: $temp, humidity: $humidity, pressure: $pressure, co2: null },
      outdoor:  { uv_index: $uv, wind_kph: $wind, sunrise: $sr, sunset: $ss }
    }'
}

uptime_s="$(cut -d' ' -f1 /proc/uptime | awk '{printf "%d", $1}')"
cpu_p="$(cpu_usage 2>/dev/null || echo 0)"
cpu_t="$(validate_json "$(cpu_temp 2>/dev/null || echo null)")"
gpu="$(validate_json "$(gpu_json 2>/dev/null || echo null)")"
mem="$(validate_json "$(mem_json 2>/dev/null || echo null)")"
disk="$(validate_json "$(disk_json 2>/dev/null || echo null)")"
load="$(validate_json "$(load_json 2>/dev/null || echo null)")"
env="$(validate_json "$(env_json 2>/dev/null || echo null)")"

speedtest_summary="null"
if [ -f "$SCRIPT_DIR/last_speedtest.json" ]; then
  speedtest_summary="$(validate_json "$(jq -c '{
    timestamp:(.speedtest?.timestamp // .timestamp // null),
    ping_ms:(.speedtest?.ping?.latency // null),
    down_mbps:((.speedtest?.download?.bandwidth? // null) | if . == null then null else (. * 8 / 1000000) end),
    up_mbps:((.speedtest?.upload?.bandwidth? // null) | if . == null then null else (. * 8 / 1000000) end),
    packet_loss:(.speedtest?.packetLoss // null),
    error:(.error // null)
  }' "$SCRIPT_DIR/last_speedtest.json" 2>/dev/null || echo null)")"
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
  --argjson env "$env" \
  '{timestamp:$ts,host:$host,cpu:{usage_percent:$cpu_usage,temp_c:$cpu_temp},memory:$mem,disk:$disk,loadavg:$load,gpu:$gpu,uptime_s:$uptime_s,speedtest:$speedtest,env:$env}'
)"

args=(-h "$BROKER_HOST" -p "$BROKER_PORT" -q "$QOS" -t "$TOPIC" -m "$payload")
if [ -n "$MQTT_USERNAME" ]; then
  args+=( -u "$MQTT_USERNAME" )
fi
if [ -n "$MQTT_PASSWORD" ]; then
  args+=( -P "$MQTT_PASSWORD" )
fi
if [ "$RETAIN" = "true" ]; then args+=( -r ); fi

# Abort silently if payload is not valid JSON
if ! echo "$payload" | jq -e . >/dev/null 2>&1; then
  echo "publish_telemetry: invalid payload, skipping" >&2
  exit 1
fi

if [ "$DRY_RUN" = "true" ]; then
  echo "$payload"
else
  mosquitto_pub "${args[@]}"
fi
