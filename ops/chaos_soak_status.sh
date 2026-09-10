#!/usr/bin/env bash
set -euo pipefail

report_dir="${1:?usage: $0 REPORT_DIR}"
project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[[ "${report_dir}" == /* ]] || report_dir="${project_root}/${report_dir}"

"${project_root}/.venv/bin/python" - "${report_dir}" <<'PY'
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

root = Path(sys.argv[1])
heartbeat_path = root / "supervisor-heartbeat.json"
runs_path = root / "runs.jsonl"
heartbeat = json.loads(heartbeat_path.read_text()) if heartbeat_path.exists() else None
runs = [json.loads(line) for line in runs_path.read_text().splitlines()] if runs_path.exists() else []
completion_path = root / "completion.json"
completion = json.loads(completion_path.read_text()) if completion_path.exists() else None
age = None
if heartbeat:
    observed = datetime.fromisoformat(heartbeat["observed_at"].replace("Z", "+00:00"))
    age = (datetime.now(timezone.utc) - observed).total_seconds()
print(json.dumps({
    "report_dir": str(root),
    "unit": (root / "systemd-unit").read_text().strip() if (root / "systemd-unit").exists() else None,
    "container": (root / "docker-container").read_text().strip() if (root / "docker-container").exists() else None,
    "heartbeat": heartbeat,
    "heartbeat_age_seconds": age,
    "runs_completed": len(runs),
    "runs_passed": sum(row.get("status") == "passed" for row in runs),
    "runs_failed": sum(row.get("status") == "failed" for row in runs),
    "last_run": runs[-1] if runs else None,
    "completion": completion,
}, indent=2))
PY
