#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 <capture-id>" >&2
  exit 2
fi

capture_id=$1
if [[ ! $capture_id =~ ^btc-l2-[0-9]{8}T[0-9]{6}Z-[a-f0-9]{8}$ ]]; then
  echo "invalid capture ID: $capture_id" >&2
  exit 2
fi

repository_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
capture_dir="$repository_root/artifacts/agent-level-experiment/btc-order-book/captures/$capture_id"
acceptance_dir="$repository_root/artifacts/agent-level-experiment/btc-order-book/acceptance/$capture_id"
watch_unit=btc-l2-ob0-retry-watch.service
capture_unit=btc-l2-ob0-retry.service
python_bin="$repository_root/.venv/bin/python"
monitor_script="$repository_root/scripts/monitor_btc_order_book_capture.py"

if [[ ! -f $capture_dir/capture-manifest.json ]]; then
  echo "capture manifest not found: $capture_dir/capture-manifest.json" >&2
  exit 1
fi
if [[ ! -x $python_bin || ! -f $monitor_script ]]; then
  echo "research environment or monitor script is missing" >&2
  exit 1
fi

if systemctl --user is-active --quiet "$watch_unit"; then
  systemctl --user show "$watch_unit" \
    --property=Id,ActiveState,SubState,Result,ExecMainStartTimestamp,NRestarts,MainPID \
    --no-pager
  exit 0
fi

if ! systemctl --user is-active --quiet "$capture_unit"; then
  echo "capture service is not active; refusing to create a watcher for an unknown capture state" >&2
  exit 1
fi

systemd-run --user \
  --unit="$watch_unit" \
  --description="BTCUSDT L2 OB0 health and deterministic acceptance watcher" \
  --property="WorkingDirectory=$repository_root" \
  --collect \
  "$python_bin" "$monitor_script" watch \
  --capture-dir "$capture_dir" \
  --output-dir "$acceptance_dir" \
  --poll-seconds 60 \
  --stale-seconds 180 \
  --min-free-gb 10 \
  --minimum-accepted-fraction 0.995

systemctl --user show "$watch_unit" \
  --property=Id,ActiveState,SubState,Result,ExecMainStartTimestamp,NRestarts,MainPID \
  --no-pager
