#!/usr/bin/env bash
# eGPU watchdog: loss/recovery alerts, light auto-recovery, session max-age warnings.
# Does not auto-reboot. Hard hangs cannot be recovered in software once the host freezes.
set -euo pipefail

EXPECTED_NAME="${EGPU_NAME:-Razer Core X}"
RECOVER_BACKOFF_S="${RECOVER_BACKOFF_S:-${COOLDOWN_S:-1800}}"
# Alert when NVIDIA has been continuously present this long (seconds).
# Host hard-hangs were observed around 12h and 22h of continuous attach (idle).
WARN_S="${EGPU_WARN_S:-21600}"       # 6h
CRITICAL_S="${EGPU_CRITICAL_S:-36000}" # 10h
STATE_FILE="/var/tmp/egpu-watchdog.state"
LAST_RECOVER_FILE="/var/tmp/egpu-watchdog.last_recover"

notify() {
  /usr/local/bin/notify.sh "$1" "${2:-}" "${3:-5}" || true
}

has_nvidia() {
  lspci -nn | grep -qi nvidia
}

bolt_state() {
  boltctl list 2>/dev/null | awk -v n="$EXPECTED_NAME" '
    $0 ~ n {found=1}
    found && /status:/ {
      for (i = 1; i <= NF; i++) if ($i ~ /status:/) { print $(i+1); exit 0 }
    }
  '
}

recover_once() {
  local bs="${1:-}"
  local now last
  # Intentionally powered-off enclosure: do not thrash bolt/pci.
  if [ "$bs" = "disconnected" ]; then
    return 0
  fi
  now=$(date +%s)
  last=0
  [ -f "$LAST_RECOVER_FILE" ] && last=$(cat "$LAST_RECOVER_FILE" 2>/dev/null || echo 0)
  if [ $((now - last)) -lt "$RECOVER_BACKOFF_S" ]; then
    return 0
  fi
  echo "$now" >"$LAST_RECOVER_FILE"
  systemctl restart bolt || true
  echo 1 >/sys/bus/pci/rescan || true
  modprobe nvidia || true
  modprobe nvidia_uvm || true
  modprobe nvidia_modeset || true
  sleep 3
}

load_state() {
  PREV_STATUS="unknown"
  LAST_OK_TS=""
  FIRST_MISSING_TS=""
  FIRST_OK_EPOCH=""
  AGE_ALERT_LEVEL="none"

  if [ -f "$STATE_FILE" ]; then
    if grep -q '^PREV_STATUS=' "$STATE_FILE" 2>/dev/null; then
      # shellcheck disable=SC1090
      . "$STATE_FILE"
    else
      PREV_STATUS="$(cat "$STATE_FILE" 2>/dev/null || echo unknown)"
    fi
  fi
}

save_state() {
  cat >"$STATE_FILE" <<EOF
PREV_STATUS=${CURRENT_STATUS}
LAST_OK_TS=${LAST_OK_TS}
FIRST_MISSING_TS=${FIRST_MISSING_TS}
FIRST_OK_EPOCH=${FIRST_OK_EPOCH}
AGE_ALERT_LEVEL=${AGE_ALERT_LEVEL}
EOF
}

hours_fmt() {
  awk -v s="$1" 'BEGIN { printf "%.1f", s/3600 }'
}

check_session_age() {
  local now age age_h
  now=$(date +%s)

  if [ "$CURRENT_STATUS" != "ok" ] && [ "$CURRENT_STATUS" != "recovered" ]; then
    FIRST_OK_EPOCH=""
    AGE_ALERT_LEVEL="none"
    return 0
  fi

  if [ -z "${FIRST_OK_EPOCH:-}" ]; then
    FIRST_OK_EPOCH="$now"
  fi

  age=$((now - FIRST_OK_EPOCH))
  age_h="$(hours_fmt "$age")"

  if [ "$age" -ge "$CRITICAL_S" ] && [ "${AGE_ALERT_LEVEL}" != "critical" ]; then
    AGE_ALERT_LEVEL="critical"
    notify "eGPU attached ${age_h}h on $(hostname) — end session soon" \
      "Continuous NVIDIA presence ${age_h}h. Previous unclean hangs occurred near 12–22h even at idle. Run: egpu-session end  then power off Core X and reboot." \
      8
  elif [ "$age" -ge "$WARN_S" ] && [ "${AGE_ALERT_LEVEL}" = "none" ]; then
    AGE_ALERT_LEVEL="warn"
    notify "eGPU session ${age_h}h on $(hostname)" \
      "Core X has been live ~${age_h}h. Prefer ending the session (egpu-session end, power off Core X, reboot) before a multi-hour overnight attach." \
      6
  fi
}

CURRENT_STATUS="ok"
reason=""
load_state

bs=$(bolt_state || true)
if ! has_nvidia; then
  CURRENT_STATUS="missing"
  reason="NVIDIA not present in PCI; bolt status for '$EXPECTED_NAME' is '${bs:-unknown}'"
fi

if [ "$CURRENT_STATUS" = "missing" ]; then
  recover_once "${bs:-}"

  bs2=$(bolt_state || true)
  if has_nvidia; then
    CURRENT_STATUS="recovered"
    reason="recovered after automatic rescan/restart (bolt=${bs2:-unknown})"
  fi
fi

NOW_UTC="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
if [ "$CURRENT_STATUS" = "missing" ]; then
  if [ "$PREV_STATUS" != "missing" ]; then
    FIRST_MISSING_TS="$NOW_UTC"
    FIRST_OK_EPOCH=""
    AGE_ALERT_LEVEL="none"
    notify "eGPU lost on $(hostname) at ${NOW_UTC}" "${reason}" 7
  fi
elif [ "$CURRENT_STATUS" = "recovered" ] || { [ "$CURRENT_STATUS" = "ok" ] && [ "$PREV_STATUS" = "missing" ]; }; then
  LAST_OK_TS="$NOW_UTC"
  FIRST_MISSING_DESC="${FIRST_MISSING_TS:-unknown}"
  FIRST_OK_EPOCH="$(date +%s)"
  AGE_ALERT_LEVEL="none"
  notify "eGPU recovered on $(hostname) at ${NOW_UTC}" \
    "NVIDIA visible again (missing_since=${FIRST_MISSING_DESC}). Start a session with: egpu-session start" \
    5
else
  LAST_OK_TS="$NOW_UTC"
  FIRST_MISSING_TS=""
fi

check_session_age

if [ "$CURRENT_STATUS" = "recovered" ]; then
  CURRENT_STATUS="ok"
fi
save_state

if [ "${1:-}" = "--verbose" ]; then
  echo "state=$CURRENT_STATUS reason=$reason"
  echo "prev_state=${PREV_STATUS}"
  echo "last_ok_ts=${LAST_OK_TS:-}"
  echo "first_missing_ts=${FIRST_MISSING_TS:-}"
  echo "first_ok_epoch=${FIRST_OK_EPOCH:-}"
  echo "age_alert_level=${AGE_ALERT_LEVEL:-none}"
  echo "bolt_state=${bs:-unknown}"
  has_nvidia && echo "nvidia=yes" || echo "nvidia=no"
fi
