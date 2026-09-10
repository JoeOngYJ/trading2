#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "usage: $0 (--runs N | --duration-hours N) [--report-dir PATH]" >&2
  exit 2
}

runs=""
duration_hours=""
report_dir=""
while (($#)); do
  case "$1" in
    --runs)
      (($# >= 2)) || usage
      runs="$2"
      shift 2
      ;;
    --duration-hours)
      (($# >= 2)) || usage
      duration_hours="$2"
      shift 2
      ;;
    --report-dir)
      (($# >= 2)) || usage
      report_dir="$2"
      shift 2
      ;;
    *) usage ;;
  esac
done

if [[ -n "${runs}" && -n "${duration_hours}" ]] || [[ -z "${runs}" && -z "${duration_hours}" ]]; then
  usage
fi
[[ -z "${runs}" || "${runs}" =~ ^[1-9][0-9]*$ ]] || usage
[[ -z "${duration_hours}" || "${duration_hours}" =~ ^[1-9][0-9]*$ ]] || usage

: "${TEST_POSTGRES_URL:?TEST_POSTGRES_URL is required}"
: "${TEST_POSTGRES_CONTAINER:?TEST_POSTGRES_CONTAINER is required}"
: "${TEST_NATS_URL:?TEST_NATS_URL is required}"
: "${TEST_NATS_CONTAINER:?TEST_NATS_CONTAINER is required}"
: "${CHAOS_ACKNOWLEDGE_ISOLATED:?Set CHAOS_ACKNOWLEDGE_ISOLATED=1 after verifying test-only targets}"
if [[ "${CHAOS_ACKNOWLEDGE_ISOLATED}" != "1" ]]; then
  echo "CHAOS_ACKNOWLEDGE_ISOLATED must equal 1" >&2
  exit 2
fi
if [[ "${TEST_POSTGRES_CONTAINER}" == *production* || "${TEST_NATS_CONTAINER}" == *production* ]]; then
  echo "Refusing container names containing 'production'" >&2
  exit 2
fi

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="${project_root}/.venv/bin/python"
[[ -x "${python_bin}" ]] || { echo "Missing ${python_bin}" >&2; exit 2; }
command -v docker >/dev/null

if [[ -z "${report_dir}" ]]; then
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  report_dir="${project_root}/artifacts/chaos/${stamp}"
elif [[ "${report_dir}" != /* ]]; then
  report_dir="${project_root}/${report_dir}"
fi
mkdir -p "${report_dir}/junit" "${report_dir}/logs"
results_file="${report_dir}/runs.jsonl"
if [[ -s "${results_file}" ]] || compgen -G "${report_dir}/junit/run-*.xml" >/dev/null; then
  echo "Report directory already contains run results: ${report_dir}" >&2
  exit 2
fi
touch "${results_file}"

postgres_was_running="$(docker inspect -f '{{.State.Running}}' "${TEST_POSTGRES_CONTAINER}")"
nats_was_running="$(docker inspect -f '{{.State.Running}}' "${TEST_NATS_CONTAINER}")"
cleanup() {
  if [[ "${CHAOS_LEAVE_CONTAINERS_RUNNING:-0}" != "1" ]]; then
    [[ "${postgres_was_running}" == "true" ]] || docker stop "${TEST_POSTGRES_CONTAINER}" >/dev/null 2>&1 || true
    [[ "${nats_was_running}" == "true" ]] || docker stop "${TEST_NATS_CONTAINER}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

docker start "${TEST_POSTGRES_CONTAINER}" "${TEST_NATS_CONTAINER}" >/dev/null
"${python_bin}" - "${TEST_POSTGRES_URL}" "${TEST_NATS_URL}" <<'PY'
import socket
import sys
import time
from urllib.parse import urlparse

for raw in sys.argv[1:]:
    parsed = urlparse(raw)
    port = parsed.port or (5432 if parsed.scheme.startswith("postgres") else 4222)
    deadline = time.monotonic() + 30
    while True:
        try:
            with socket.create_connection((parsed.hostname, port), timeout=0.5):
                break
        except OSError:
            if time.monotonic() >= deadline:
                raise SystemExit(f"dependency did not become reachable: {parsed.hostname}:{port}")
            time.sleep(0.1)
PY

manifest_path="${report_dir}/release-manifest.json"
"${python_bin}" "${project_root}/ops/release_manifest.py" create "${manifest_path}" \
  >"${report_dir}/release-fingerprint.txt"

started_epoch="$(date +%s)"
deadline_epoch=0
[[ -z "${duration_hours}" ]] || deadline_epoch=$((started_epoch + duration_hours * 3600))
iteration=0

while true; do
  if [[ -n "${runs}" && ${iteration} -ge ${runs} ]]; then
    break
  fi
  if [[ ${deadline_epoch} -gt 0 && ${iteration} -gt 0 && $(date +%s) -ge ${deadline_epoch} ]]; then
    break
  fi
  iteration=$((iteration + 1))
  run_id="$(printf '%04d' "${iteration}")"
  junit_path="${report_dir}/junit/run-${run_id}.xml"
  log_path="${report_dir}/logs/run-${run_id}.log"
  run_started_ns="$(date +%s%N)"
  echo "chaos matrix run ${iteration} started at $(date -u +%FT%TZ)"
  "${python_bin}" "${project_root}/ops/release_manifest.py" verify "${manifest_path}"

  set +e
  (
    cd "${project_root}"
    CHAOS_RUN_ID="${run_id}" \
      TEST_POSTGRES_URL="${TEST_POSTGRES_URL}" \
      TEST_POSTGRES_CONTAINER="${TEST_POSTGRES_CONTAINER}" \
      TEST_NATS_URL="${TEST_NATS_URL}" \
      TEST_NATS_CONTAINER="${TEST_NATS_CONTAINER}" \
      "${python_bin}" -m pytest -q --junitxml="${junit_path}"
  ) 2>&1 | tee "${log_path}"
  status=${PIPESTATUS[0]}
  set -e

  run_finished_ns="$(date +%s%N)"
  duration_ms=$(((run_finished_ns - run_started_ns) / 1000000))
  if [[ ${status} -eq 0 ]]; then
    disposition="passed"
  else
    disposition="failed"
  fi
  "${python_bin}" - "${results_file}" "${iteration}" "${disposition}" "${status}" "${duration_ms}" <<'PY'
import datetime
import json
import sys

path, iteration, disposition, status, duration_ms = sys.argv[1:]
record = {
    "iteration": int(iteration),
    "status": disposition,
    "exit_code": int(status),
    "duration_ms": int(duration_ms),
    "finished_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
}
with open(path, "a", encoding="utf-8") as handle:
    handle.write(json.dumps(record, separators=(",", ":")) + "\n")
PY
  "${python_bin}" "${project_root}/ops/summarize_chaos_results.py" "${report_dir}" >/dev/null
  if [[ ${status} -ne 0 ]]; then
    echo "chaos matrix stopped after failure in run ${iteration}; see ${log_path}" >&2
    exit "${status}"
  fi
done

"${python_bin}" "${project_root}/ops/summarize_chaos_results.py" "${report_dir}"
