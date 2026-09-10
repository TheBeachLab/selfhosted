#!/usr/bin/env bash
# Manage intentional eGPU sessions on thebeachlab.
# The NUC hard-hangs after long periods with the Razer Core X attached
# (even at idle). Treat the eGPU as a job session, not always-on hardware.
set -euo pipefail

SESSION_FILE="${EGPU_SESSION_FILE:-/var/tmp/egpu-session.state}"
EXPECTED_NAME="${EGPU_NAME:-Razer Core X}"

notify() {
  if [ -x /usr/local/bin/notify.sh ]; then
    /usr/local/bin/notify.sh "$1" "${2:-}" "${3:-5}" || true
  fi
}

bolt_state() {
  boltctl list 2>/dev/null | awk -v n="$EXPECTED_NAME" '
    $0 ~ n {found=1}
    found && /status:/ {
      for (i = 1; i <= NF; i++) if ($i ~ /status:/) { print $(i+1); exit 0 }
    }
  '
}

has_nvidia_pci() {
  lspci -nn 2>/dev/null | grep -qi nvidia
}

has_nvidiactl() {
  [ -e /dev/nvidiactl ]
}

gpu_ok() {
  has_nvidia_pci && has_nvidiactl
}

smi_ok() {
  command -v nvidia-smi >/dev/null 2>&1 || return 1
  nvidia-smi -L >/dev/null 2>&1
}

session_age_seconds() {
  local started now
  if [ ! -f "$SESSION_FILE" ]; then
    echo ""
    return 0
  fi
  # shellcheck disable=SC1090
  . "$SESSION_FILE"
  if [ -z "${STARTED_EPOCH:-}" ]; then
    echo ""
    return 0
  fi
  now=$(date +%s)
  echo $((now - STARTED_EPOCH))
}

cmd_status() {
  local bs age age_h smi
  bs="$(bolt_state || true)"
  bs="${bs:-unknown}"
  age="$(session_age_seconds)"
  smi="no"
  smi_ok && smi="yes"

  echo "bolt_status=${bs}"
  echo "nvidia_pci=$(has_nvidia_pci && echo yes || echo no)"
  echo "nvidiactl=$(has_nvidiactl && echo yes || echo no)"
  echo "nvidia_smi=${smi}"
  if [ -f "$SESSION_FILE" ]; then
    # shellcheck disable=SC1090
    . "$SESSION_FILE"
    echo "session=active"
    echo "session_started_utc=${STARTED_UTC:-unknown}"
    if [ -n "$age" ]; then
      age_h=$(awk -v s="$age" 'BEGIN { printf "%.1f", s/3600 }')
      echo "session_age_h=${age_h}"
    fi
    echo "session_note=${NOTE:-}"
  else
    echo "session=inactive"
  fi

  if gpu_ok; then
    if [ ! -f "$SESSION_FILE" ]; then
      echo "hint=eGPU is live but no session is recorded; run: egpu-session start"
    fi
  else
    echo "hint=Core X off or not enumerated. Power it on, cold-boot the NUC with the cable attached, then: egpu-session start"
  fi
}

cmd_start() {
  if ! gpu_ok; then
    echo "error: NVIDIA device not ready (bolt=$(bolt_state || echo unknown))" >&2
    echo "Power on the Razer Core X, keep the Thunderbolt cable attached, cold-boot the NUC, then retry." >&2
    return 1
  fi
  if ! smi_ok; then
    echo "warning: /dev/nvidiactl exists but nvidia-smi failed; driver may be unhealthy" >&2
  fi

  local now_e now_u
  now_e=$(date +%s)
  now_u=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
  cat >"$SESSION_FILE" <<EOF
STARTED_EPOCH=${now_e}
STARTED_UTC=${now_u}
NOTE=${1:-manual}
EOF
  chmod 644 "$SESSION_FILE" 2>/dev/null || true

  systemctl start nvidia-persistenced 2>/dev/null || true

  echo "eGPU session started at ${now_u}"
  echo "Do GPU jobs now. Prefer ending the session within ~6 hours."
  echo "When done: egpu-session end"
  notify "eGPU session started on $(hostname)" "started_at=${now_u} note=${1:-manual}. Plan to end within ~6h." 5
}

cmd_end() {
  local reboot_flag=0
  if [ "${1:-}" = "--reboot" ]; then
    reboot_flag=1
  fi

  systemctl stop comfyui 2>/dev/null || true
  systemctl stop rag-library-ingest 2>/dev/null || true

  if [ -f "$SESSION_FILE" ]; then
    rm -f "$SESSION_FILE"
  fi

  cat <<'EOF'
eGPU session ended (local state cleared).

Safe teardown (required for host stability):
  1. Stop active GPU jobs (ComfyUI/RAG already stopped if they were running).
  2. Power OFF the Razer Core X (do not hot-unplug the TB cable while the NUC is up).
  3. Reboot the NUC to clear Thunderbolt/PCIe state:
       sudo systemctl reboot

Whisper/TTS frontends stay up; they only load CUDA when a job arrives and a GPU is present.
EOF

  notify "eGPU session ended on $(hostname)" "Power off Core X, then reboot the NUC for a clean PCIe state." 5

  if [ "$reboot_flag" -eq 1 ]; then
    echo "Rebooting in 5 seconds..."
    sleep 5
    systemctl reboot
  fi
}

cmd_doctor() {
  echo "=== egpu-session doctor ==="
  cmd_status
  echo
  echo "=== uname / cmdline ==="
  uname -r
  cat /proc/cmdline
  echo
  echo "=== nvidia module options (files) ==="
  grep -rh . /etc/modprobe.d/*nvidia* 2>/dev/null || true
  echo
  echo "=== recent heartbeat (last 5) ==="
  tail -n 5 /var/log/host-heartbeat.log 2>/dev/null || echo "no heartbeat log"
  echo
  echo "=== kernel GPU/TB lines this boot (tail) ==="
  journalctl -k -b --no-pager 2>/dev/null | grep -iE 'NVRM|Xid|fallen|thunderbolt|pciehp|Link Down' | tail -n 20 || true
}

usage() {
  cat <<'EOF'
Usage: egpu-session <status|start|end|doctor> [args]

  status          Show bolt/NVIDIA/session state
  start [note]    Record a session when the GPU is ready
  end [--reboot]  Clear session, stop ComfyUI/RAG; optional reboot
  doctor          Diagnostics for support/debugging

Operational model:
  Always-on Core X has hard-hung this NUC after ~12–22 h even at idle.
  Power Core X only for job sessions, then power it off and reboot.
EOF
}

main() {
  case "${1:-}" in
    status|"") cmd_status ;;
    start) shift; cmd_start "${1:-manual}" ;;
    end) shift; cmd_end "${1:-}" ;;
    doctor) cmd_doctor ;;
    -h|--help|help) usage ;;
    *) usage >&2; return 2 ;;
  esac
}

main "$@"
