#!/usr/bin/env bash
set -euo pipefail

mode="${1:?mode is required}"
amount="${2:?amount is required}"
report_dir="${3:?absolute report directory is required}"
project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

mkdir -p "${report_dir}"
echo "$$" >"${report_dir}/supervisor.pid"
runner_pid=""

write_heartbeat() {
  local state="$1"
  local temporary="${report_dir}/.supervisor-heartbeat.json.$$"
  printf '{"state":"%s","supervisor_pid":%s,"runner_pid":%s,"observed_at":"%s"}\n' \
    "${state}" "$$" "${runner_pid:-null}" "$(date -u +%FT%TZ)" >"${temporary}"
  mv "${temporary}" "${report_dir}/supervisor-heartbeat.json"
}

write_completion() {
  local status="$1"
  local temporary="${report_dir}/.completion.json.$$"
  printf '{"exit_code":%s,"completed":%s,"finished_at":"%s"}\n' \
    "${status}" "$([[ "${status}" -eq 0 ]] && echo true || echo false)" \
    "$(date -u +%FT%TZ)" >"${temporary}"
  mv "${temporary}" "${report_dir}/completion.json"
}

terminate() {
  write_heartbeat "terminating"
  if [[ -n "${runner_pid}" ]] && kill -0 "${runner_pid}" 2>/dev/null; then
    kill -TERM "${runner_pid}" 2>/dev/null || true
    wait "${runner_pid}" || true
  fi
  write_completion 143
  exit 143
}
trap terminate INT TERM

# A restarted supervisor must never append to an interrupted formal soak. Preserve the evidence,
# mark it incomplete, and exit successfully so the container restart policy does not loop.
if [[ -f "${report_dir}/completion.json" ]]; then
  write_heartbeat "existing_completion"
  exit 0
fi
if [[ -s "${report_dir}/runs.jsonl" ]]; then
  write_heartbeat "interrupted_before_restart"
  write_completion 125
  exit 0
fi

case "${mode}" in
  runs) runner_args=(--runs "${amount}") ;;
  duration-hours) runner_args=(--duration-hours "${amount}") ;;
  *) echo "unsupported supervisor mode: ${mode}" >&2; exit 2 ;;
esac

(
  cd "${project_root}"
  exec "${project_root}/ops/run_chaos_matrix.sh" \
    "${runner_args[@]}" --report-dir "${report_dir}"
) >>"${report_dir}/master.log" 2>&1 &
runner_pid=$!
echo "${runner_pid}" >"${report_dir}/runner.pid"

while kill -0 "${runner_pid}" 2>/dev/null; do
  write_heartbeat "running"
  sleep 30 &
  wait $! || true
done

set +e
wait "${runner_pid}"
status=$?
set -e
write_heartbeat "$([[ "${status}" -eq 0 ]] && echo completed || echo failed)"
write_completion "${status}"
exit "${status}"
