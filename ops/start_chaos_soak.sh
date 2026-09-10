#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "usage: $0 (--runs N | --duration-hours N) --report-dir PATH [--unit NAME]" >&2
  exit 2
}

mode=""
amount=""
report_dir=""
unit_name=""
while (($#)); do
  case "$1" in
    --runs|--duration-hours)
      [[ -z "${mode}" && $# -ge 2 ]] || usage
      mode="${1#--}"
      amount="$2"
      shift 2
      ;;
    --report-dir)
      (($# >= 2)) || usage
      report_dir="$2"
      shift 2
      ;;
    --unit)
      (($# >= 2)) || usage
      unit_name="$2"
      shift 2
      ;;
    *) usage ;;
  esac
done

[[ -n "${mode}" && -n "${report_dir}" && "${amount}" =~ ^[1-9][0-9]*$ ]] || usage
: "${TEST_POSTGRES_URL:?TEST_POSTGRES_URL is required}"
: "${TEST_POSTGRES_CONTAINER:?TEST_POSTGRES_CONTAINER is required}"
: "${TEST_NATS_URL:?TEST_NATS_URL is required}"
: "${TEST_NATS_CONTAINER:?TEST_NATS_CONTAINER is required}"
: "${CHAOS_ACKNOWLEDGE_ISOLATED:?CHAOS_ACKNOWLEDGE_ISOLATED=1 is required}"
[[ "${CHAOS_ACKNOWLEDGE_ISOLATED}" == "1" ]] || usage

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ "${report_dir}" != /* ]]; then
  report_dir="${project_root}/${report_dir}"
fi
if [[ -e "${report_dir}" ]] && find "${report_dir}" -mindepth 1 -print -quit | grep -q .; then
  echo "Report directory is not empty: ${report_dir}" >&2
  exit 2
fi
mkdir -p "${report_dir}"

if [[ -z "${unit_name}" ]]; then
  unit_name="trading-chaos-$(date -u +%Y%m%dT%H%M%SZ)"
fi
[[ "${unit_name}" =~ ^[A-Za-z0-9_.@-]+$ ]] || usage
echo "${unit_name}" >"${report_dir}/systemd-unit"

systemd-run --user --unit="${unit_name}" --property=Type=exec \
  --property="WorkingDirectory=${project_root}" \
  --setenv="CHAOS_ACKNOWLEDGE_ISOLATED=1" \
  --setenv="TEST_POSTGRES_URL=${TEST_POSTGRES_URL}" \
  --setenv="TEST_POSTGRES_CONTAINER=${TEST_POSTGRES_CONTAINER}" \
  --setenv="TEST_NATS_URL=${TEST_NATS_URL}" \
  --setenv="TEST_NATS_CONTAINER=${TEST_NATS_CONTAINER}" \
  "${project_root}/ops/chaos_soak_supervisor.sh" "${mode}" "${amount}" "${report_dir}"

deadline=$((SECONDS + 10))
while [[ ! -s "${report_dir}/supervisor-heartbeat.json" && ${SECONDS} -lt ${deadline} ]]; do
  sleep 0.1
done
if [[ ! -s "${report_dir}/supervisor-heartbeat.json" ]]; then
  systemctl --user status "${unit_name}" --no-pager >&2 || true
  exit 1
fi
echo "Started ${unit_name}; report directory: ${report_dir}"
