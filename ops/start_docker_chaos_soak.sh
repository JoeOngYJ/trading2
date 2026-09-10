#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "usage: $0 (--runs N | --duration-hours N) --report-dir PATH --container NAME" >&2
  exit 2
}

mode=""
amount=""
report_dir=""
container_name=""
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
    --container)
      (($# >= 2)) || usage
      container_name="$2"
      shift 2
      ;;
    *) usage ;;
  esac
done

[[ -n "${mode}" && -n "${report_dir}" && -n "${container_name}" ]] || usage
[[ "${amount}" =~ ^[1-9][0-9]*$ ]] || usage
[[ "${container_name}" =~ ^[A-Za-z0-9_.-]+$ ]] || usage
: "${TEST_POSTGRES_URL:?TEST_POSTGRES_URL is required}"
: "${TEST_POSTGRES_CONTAINER:?TEST_POSTGRES_CONTAINER is required}"
: "${TEST_NATS_URL:?TEST_NATS_URL is required}"
: "${TEST_NATS_CONTAINER:?TEST_NATS_CONTAINER is required}"
: "${CHAOS_DOCKER_NETWORK:?CHAOS_DOCKER_NETWORK is required}"
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
echo "${container_name}" >"${report_dir}/docker-container"

python_store="/home/joe/.local/share/uv/python"
python_runtime="$(readlink -f "${project_root}/.venv/bin/python")"
host_uid="$(id -u)"
host_gid="$(id -g)"
docker_gid="$(stat -c '%g' /var/run/docker.sock)"
[[ "${python_runtime}" == "${python_store}/"* ]] || {
  echo "Unexpected Python runtime path: ${python_runtime}" >&2
  exit 2
}

docker run --detach \
  --name "${container_name}" \
  --restart "on-failure:3" \
  --user "${host_uid}:${host_gid}" \
  --group-add "${docker_gid}" \
  --network "${CHAOS_DOCKER_NETWORK}" \
  --workdir "${project_root}" \
  --volume "${project_root}:${project_root}" \
  --volume "${python_store}:${python_store}:ro" \
  --volume "/usr/bin/docker:/usr/bin/docker:ro" \
  --volume "/var/run/docker.sock:/var/run/docker.sock" \
  --env "CHAOS_ACKNOWLEDGE_ISOLATED=1" \
  --env "TEST_POSTGRES_URL=${TEST_POSTGRES_URL}" \
  --env "TEST_POSTGRES_CONTAINER=${TEST_POSTGRES_CONTAINER}" \
  --env "TEST_NATS_URL=${TEST_NATS_URL}" \
  --env "TEST_NATS_CONTAINER=${TEST_NATS_CONTAINER}" \
  python:3.12-slim \
  "${project_root}/ops/chaos_soak_supervisor.sh" "${mode}" "${amount}" "${report_dir}" \
  >"${report_dir}/docker-id"

inhibitor_unit="${container_name}-sleep-inhibitor.service"
if ! systemd-run --user \
  --unit "${inhibitor_unit%.service}" \
  --property "Restart=on-failure" \
  --property "RestartSec=5s" \
  --collect \
  /usr/bin/systemd-inhibit \
    --what=sleep \
    --who="${container_name}" \
    --why="Continuous chaos soak is running" \
    --mode=block \
    /usr/bin/docker wait "${container_name}"; then
  echo "Could not establish the host sleep inhibitor; stopping ${container_name}" >&2
  docker stop "${container_name}" >/dev/null
  exit 1
fi
echo "${inhibitor_unit}" >"${report_dir}/inhibitor-unit"

deadline=$((SECONDS + 15))
while [[ ! -s "${report_dir}/supervisor-heartbeat.json" && ${SECONDS} -lt ${deadline} ]]; do
  sleep 0.1
done
if [[ ! -s "${report_dir}/supervisor-heartbeat.json" ]]; then
  echo "Docker supervisor did not produce a heartbeat; inspect ${container_name}" >&2
  exit 1
fi
echo "Started ${container_name}; report directory: ${report_dir}"
