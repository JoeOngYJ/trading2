#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path


CHAOS_MODULES = {
    "test_worker_kill_integration",
    "test_jetstream_outbox_integration",
    "test_bridge_chaos_integration",
    "test_postgres_recovery_integration",
    "test_freqtrade_execution_boundary",
}


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)]


def main(report_dir: Path) -> int:
    runs_path = report_dir / "runs.jsonl"
    runs = [json.loads(line) for line in runs_path.read_text().splitlines() if line.strip()]
    scenario_times: dict[str, list[float]] = defaultdict(list)
    test_failures = 0
    test_errors = 0
    test_skips = 0
    test_executions = 0
    for junit_path in sorted((report_dir / "junit").glob("run-*.xml")):
        root = ET.parse(junit_path).getroot()
        suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
        for suite in suites:
            test_failures += int(suite.attrib.get("failures", 0))
            test_errors += int(suite.attrib.get("errors", 0))
            test_skips += int(suite.attrib.get("skipped", 0))
        for case in root.iter("testcase"):
            test_executions += 1
            classname = case.attrib.get("classname", "")
            module = classname.rsplit(".", 1)[-1]
            if module in CHAOS_MODULES:
                scenario_times[f"{module}.{case.attrib['name']}"] .append(
                    float(case.attrib.get("time", 0.0))
                )

    durations = [run["duration_ms"] / 1000 for run in runs]
    scenarios = {
        name: {
            "executions": len(values),
            "p50_seconds": percentile(values, 0.50),
            "p95_seconds": percentile(values, 0.95),
            "p99_seconds": percentile(values, 0.99),
            "max_seconds": max(values),
        }
        for name, values in sorted(scenario_times.items())
    }
    summary = {
        "runs_completed": len(runs),
        "runs_passed": sum(run["status"] == "passed" for run in runs),
        "runs_failed": sum(run["status"] == "failed" for run in runs),
        "test_executions": test_executions,
        "test_failures": test_failures,
        "test_errors": test_errors,
        "test_skips": test_skips,
        "matrix_duration_seconds": {
            "p50": percentile(durations, 0.50),
            "p95": percentile(durations, 0.95),
            "p99": percentile(durations, 0.99),
            "max": max(durations) if durations else None,
        },
        "scenario_duration_seconds": scenarios,
        "measurement_note": (
            "Scenario duration includes test setup, fault injection, recovery, and assertions; "
            "it is a conservative convergence measurement, not exchange order latency."
        ),
    }
    target = report_dir / "summary.json"
    target.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if summary["runs_failed"] else 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(f"usage: {sys.argv[0]} REPORT_DIR")
    raise SystemExit(main(Path(sys.argv[1])))
