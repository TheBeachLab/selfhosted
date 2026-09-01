#!/usr/bin/env bash
set -Eeuo pipefail

readonly REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly SCRIPT="${REPO_ROOT}/services/openclaw-maintenance-update"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

assert_contains() {
  file=$1
  expected=$2
  grep -Fq -- "${expected}" "${file}" || fail "${file} does not contain: ${expected}"
}

assert_not_contains() {
  file=$1
  unexpected=$2
  ! grep -Fq -- "${unexpected}" "${file}" || fail "${file} unexpectedly contains: ${unexpected}"
}

make_fake() {
  path=$1
  shift
  cat >"${path}" <<EOF
#!/usr/bin/env bash
set -Eeuo pipefail
$*
EOF
  chmod +x "${path}"
}

setup_case() {
  case_dir=$(mktemp -d)
  home_dir="${case_dir}/home"
  state_dir="${home_dir}/.openclaw"
  fake_bin="${case_dir}/bin"
  command_log="${case_dir}/commands.log"
  installed_file="${case_dir}/installed-version"
  target_file="${case_dir}/target-version"
  systemd_state="${case_dir}/systemd-state"
  tmux_state="${case_dir}/tmux-state"
  doctor_rc_file="${case_dir}/doctor-rc"
  rpc_mode_file="${case_dir}/rpc-mode"
  mkdir -p "${state_dir}/state" "${state_dir}/agents/main/sessions" "${fake_bin}" "${home_dir}/backups"
  printf '{}\n' >"${state_dir}/openclaw.json"
  printf 'sqlite fixture\n' >"${state_dir}/state/openclaw.sqlite"
  printf '{}\n' >"${state_dir}/agents/main/sessions/sessions.json"
  printf '1.0.0\n' >"${installed_file}"
  printf '2.0.0\n' >"${target_file}"
  printf 'active\n' >"${systemd_state}"
  printf '0\n' >"${doctor_rc_file}"
  printf 'ready\n' >"${rpc_mode_file}"
  : >"${command_log}"

  make_fake "${fake_bin}/openclaw" '
echo "openclaw $*" >>"${TEST_COMMAND_LOG}"
case "${1:-}" in
  --version) printf "OpenClaw %s (test)\n" "$(<"${TEST_INSTALLED_FILE}")" ;;
  doctor) exit "$(<"${TEST_DOCTOR_RC_FILE}")" ;;
  config) exit 0 ;;
  gateway)
    case "${2:-}" in
      status)
        if [[ "$(<"${TEST_RPC_MODE_FILE}")" == ready ]]; then
          printf "Gateway version: %s\nConnectivity probe: ok\n" "$(<"${TEST_TARGET_FILE}")"
        else
          printf "Connectivity probe: failed\n"
          exit 1
        fi
        ;;
      install) exit 0 ;;
    esac
    ;;
  channels) exit 0 ;;
esac'

  make_fake "${fake_bin}/npm" '
echo "npm $*" >>"${TEST_COMMAND_LOG}"
if [[ "${1:-}" == view ]]; then
  cat "${TEST_TARGET_FILE}"
elif [[ "${1:-}" == install ]]; then
  cat "${TEST_TARGET_FILE}" >"${TEST_INSTALLED_FILE}"
fi'

  make_fake "${fake_bin}/sudo" '
echo "sudo $*" >>"${TEST_COMMAND_LOG}"
[[ "${1:-}" != -n ]] || shift
exec "$@"'

  make_fake "${fake_bin}/systemctl" '
echo "systemctl $*" >>"${TEST_COMMAND_LOG}"
[[ "${1:-}" != --user ]] || shift
case "${1:-}" in
  is-active) cat "${TEST_SYSTEMD_STATE}" ;;
  stop) printf "inactive\n" >"${TEST_SYSTEMD_STATE}" ;;
  start|restart) printf "active\n" >"${TEST_SYSTEMD_STATE}" ;;
esac'

  make_fake "${fake_bin}/tmux" '
echo "tmux $*" >>"${TEST_COMMAND_LOG}"
case "${1:-}" in
  has-session) [[ -f "${TEST_TMUX_STATE}" ]] ;;
  kill-session) rm -f "${TEST_TMUX_STATE}" ;;
  new-session) touch "${TEST_TMUX_STATE}" ;;
esac'

  make_fake "${fake_bin}/sqlite3" '
echo "sqlite3 $*" >>"${TEST_COMMAND_LOG}"
last="${*: -1}"
if [[ "${last}" == *quick_check* ]]; then
  if [[ "$(<"${TEST_SYSTEMD_STATE}")" == active ]]; then
    echo "database is locked" >&2
    exit 5
  fi
  echo ok
elif [[ "${last}" == .backup* ]]; then
  destination=${last#*.backup }
  destination=${destination:1:${#destination}-2}
  cp "$3" "${destination}"
fi'

  make_fake "${fake_bin}/lsof" 'exit 1'
  make_fake "${fake_bin}/flock" 'exit 0'
  make_fake "${fake_bin}/timeout" 'shift; exec "$@"'
  make_fake "${fake_bin}/sleep" 'exit 0'
  make_fake "${fake_bin}/sha256sum" '
for file in "$@"; do printf "testhash  %s\n" "${file}"; done'
}

run_case() {
  set +e
  HOME="${home_dir}" \
  USER="$(id -un)" \
  LOGNAME="$(id -un)" \
  XDG_RUNTIME_DIR="${case_dir}/run" \
  TEST_COMMAND_LOG="${command_log}" \
  TEST_INSTALLED_FILE="${installed_file}" \
  TEST_TARGET_FILE="${target_file}" \
  TEST_SYSTEMD_STATE="${systemd_state}" \
  TEST_TMUX_STATE="${tmux_state}" \
  TEST_DOCTOR_RC_FILE="${doctor_rc_file}" \
  TEST_RPC_MODE_FILE="${rpc_mode_file}" \
  OPENCLAW_MAINTENANCE_EXPECTED_USER="$(id -un)" \
  OPENCLAW_MAINTENANCE_STATE_DIR="${state_dir}" \
  OPENCLAW_MAINTENANCE_BACKUP_ROOT="${home_dir}/backups" \
  OPENCLAW_MAINTENANCE_LOCK_FILE="${case_dir}/run/update.lock" \
  OPENCLAW_MAINTENANCE_OPENCLAW_BIN="${fake_bin}/openclaw" \
  OPENCLAW_MAINTENANCE_NPM_BIN="${fake_bin}/npm" \
  OPENCLAW_MAINTENANCE_SUDO_BIN="${fake_bin}/sudo" \
  OPENCLAW_MAINTENANCE_SYSTEMCTL_BIN="${fake_bin}/systemctl" \
  OPENCLAW_MAINTENANCE_TMUX_BIN="${fake_bin}/tmux" \
  OPENCLAW_MAINTENANCE_SQLITE3_BIN="${fake_bin}/sqlite3" \
  OPENCLAW_MAINTENANCE_LSOF_BIN="${fake_bin}/lsof" \
  OPENCLAW_MAINTENANCE_FLOCK_BIN="${fake_bin}/flock" \
  OPENCLAW_MAINTENANCE_SHA256SUM_BIN="${fake_bin}/sha256sum" \
  OPENCLAW_MAINTENANCE_TIMEOUT_BIN="${fake_bin}/timeout" \
  OPENCLAW_MAINTENANCE_SLEEP_BIN="${fake_bin}/sleep" \
  OPENCLAW_MAINTENANCE_RPC_ATTEMPTS=2 \
  OPENCLAW_MAINTENANCE_RPC_INTERVAL_SECONDS=0 \
  "${SCRIPT}" >"${case_dir}/stdout" 2>"${case_dir}/stderr"
  case_rc=$?
  set -e
}

test_no_update_is_non_mutating() {
  setup_case
  cp "${installed_file}" "${target_file}"
  run_case
  [[ "${case_rc}" -eq 0 ]] || fail "no-update case returned ${case_rc}"
  assert_not_contains "${command_log}" "systemctl --user stop"
  assert_not_contains "${command_log}" "openclaw doctor"
  rm -rf "${case_dir}"
}

test_successful_update_orders_maintenance() {
  setup_case
  touch "${tmux_state}"
  run_case
  [[ "${case_rc}" -eq 0 ]] || fail "success case returned ${case_rc}: $(<"${case_dir}/stderr")"
  assert_contains "${command_log}" "tmux kill-session -t watson"
  assert_contains "${command_log}" "systemctl --user stop openclaw-gateway.service"
  assert_contains "${command_log}" "openclaw plugins install @openclaw/whatsapp@2.0.0 --force --pin --accept-capabilities"
  assert_contains "${command_log}" "openclaw doctor --fix --non-interactive --yes"
  assert_contains "${command_log}" "openclaw gateway install --force"
  assert_contains "${command_log}" "systemctl --user restart openclaw-gateway.service"
  assert_contains "${command_log}" "tmux new-session -d -s watson"
  find "${home_dir}/backups" -name SHA256SUMS -type f | grep -q . || fail "backup manifest missing"
  rm -rf "${case_dir}"
}

test_doctor_failure_keeps_gateway_stopped() {
  setup_case
  touch "${tmux_state}"
  printf '7\n' >"${doctor_rc_file}"
  run_case
  [[ "${case_rc}" -ne 0 ]] || fail "doctor failure unexpectedly succeeded"
  assert_contains "${command_log}" "openclaw doctor --fix --non-interactive --yes"
  assert_not_contains "${command_log}" "systemctl --user restart openclaw-gateway.service"
  assert_not_contains "${command_log}" "tmux new-session -d -s watson"
  [[ "$(<"${systemd_state}")" == inactive ]] || fail "gateway was not left stopped"
  rm -rf "${case_dir}"
}

test_rpc_failure_stops_gateway_and_skips_tui() {
  setup_case
  touch "${tmux_state}"
  printf 'failed\n' >"${rpc_mode_file}"
  run_case
  [[ "${case_rc}" -ne 0 ]] || fail "RPC failure unexpectedly succeeded"
  assert_contains "${command_log}" "systemctl --user restart openclaw-gateway.service"
  assert_not_contains "${command_log}" "tmux new-session -d -s watson"
  [[ "$(<"${systemd_state}")" == inactive ]] || fail "gateway was not stopped after RPC failure"
  rm -rf "${case_dir}"
}

bash -n "${SCRIPT}"
test_no_update_is_non_mutating
test_successful_update_orders_maintenance
test_doctor_failure_keeps_gateway_stopped
test_rpc_failure_stops_gateway_and_skips_tui
echo "PASS: OpenClaw maintenance updater tests"
