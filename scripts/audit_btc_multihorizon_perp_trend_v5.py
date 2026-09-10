#!/usr/bin/env python3
"""Independent replay and result audit for BTC multi-horizon perpetual trend v5."""

import hashlib
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRIMARY = ROOT / "artifacts/agent-level-experiment/btc-focused/multihorizon-perp-trend-v5"
REPLAY = ROOT / "artifacts/agent-level-experiment/btc-focused/multihorizon-perp-trend-v5-replay"
AUDIT = PRIMARY / "audit"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


if AUDIT.exists() or REPLAY.exists():
    raise FileExistsError("refusing to overwrite immutable audit/replay")
spec = importlib.util.spec_from_file_location("trend_v5_replay", ROOT / "scripts/run_btc_multihorizon_perp_trend_v5.py")
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)
module.OUTPUT = REPLAY
replayed = module.run()
primary_report = json.loads((PRIMARY / "report.json").read_text())
checks = {
    "byte_identical_report": digest(PRIMARY / "report.json") == digest(REPLAY / "report.json"),
    "rejected": primary_report["decision"] == "rejected_frozen_gates",
    "all_controls_present": all(set(primary_report["results"][p]["candle-primary-30bps-rt-v1"]) == {"candidate_fixed", "candidate_ewma", "simple_28d", "always_long", "random"} for p in primary_report["results"]),
    "development_positive_but_stability_negative": primary_report["results"]["development"]["candle-primary-30bps-rt-v1"]["candidate_fixed"]["metrics"]["net_return"] > 0 and primary_report["results"]["consumed_stability"]["candle-primary-30bps-rt-v1"]["candidate_fixed"]["metrics"]["net_return"] < 0,
    "simple_control_beats_candidate_in_development": primary_report["results"]["development"]["candle-primary-30bps-rt-v1"]["simple_28d"]["metrics"]["net_return"] > primary_report["results"]["development"]["candle-primary-30bps-rt-v1"]["candidate_fixed"]["metrics"]["net_return"],
    "no_arm_or_action": primary_report["accepted_strategy_arms"] == [] and primary_report["actionable_arm_id"] == "no_trade",
    "no_2026": primary_report["year_2026_accessed"] is False,
}
AUDIT.mkdir(parents=True)
audit_report = {"actionable_arm_id": "no_trade", "checks": checks, "decision": "audit_passed_rejection_confirmed" if all(checks.values()) else "audit_failed", "experiment_id": "btc-multihorizon-perp-trend-v5"}
audit_path = AUDIT / "audit-report.json"; audit_path.write_bytes(canonical(audit_report))
manifest = {"actionable_arm_id": "no_trade", "artifacts": [{"path": str(audit_path.relative_to(ROOT)), "sha256": digest(audit_path)}, {"path": str(REPLAY / "report.json"), "sha256": digest(REPLAY / "report.json")}], "experiment_id": "btc-multihorizon-perp-trend-v5", "primary_report_sha256": digest(PRIMARY / "report.json"), "schema_version": "btc-multihorizon-perp-trend-v5-audit-manifest-v1"}
(AUDIT / "evidence-manifest.json").write_bytes(canonical(manifest))
print(json.dumps(audit_report, indent=2, sort_keys=True))
