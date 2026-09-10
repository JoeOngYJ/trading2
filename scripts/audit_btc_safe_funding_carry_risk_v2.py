#!/usr/bin/env python3
"""Independently audit and close the safe BTC carry-risk v2 experiment."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for _entry in (str(ROOT), str(SRC)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from scripts.backtest_btc_safe_funding_carry_risk_v2 import canonical_bytes, sha256_path


DEFAULT_PRIMARY = (
    ROOT / "artifacts/agent-level-experiment/btc-focused/safe-delta-neutral-funding-carry-v2"
)
DEFAULT_REPLAY = (
    ROOT
    / "artifacts/agent-level-experiment/btc-focused/safe-delta-neutral-funding-carry-v2-replay"
)


def _relative(path: Path) -> str:
    return str(path.resolve(strict=False).relative_to(ROOT))


def _write_json(path: Path, value: dict[str, Any]) -> str:
    if path.exists():
        raise ValueError(f"refusing to overwrite safe carry audit evidence: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(value))
    return sha256_path(path)


def _load_canonical(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    value = json.loads(raw)
    if raw != canonical_bytes(value):
        raise ValueError(f"non-canonical safe carry evidence: {path}")
    return value


def _normalize(value: Any, output: Path) -> Any:
    prefix = _relative(output)
    if isinstance(value, str):
        return "$OUTPUT" + value[len(prefix) :] if value.startswith(prefix) else value
    if isinstance(value, list):
        return [_normalize(item, output) for item in value]
    if isinstance(value, dict):
        return {key: _normalize(item, output) for key, item in value.items()}
    return value


def _validate_manifest(output: Path, report_sha: str, trades_sha: str) -> dict[str, Any]:
    manifest = _load_canonical(output / "evidence-manifest.json")
    if (
        manifest.get("experiment_id") != "btc-safe-delta-neutral-funding-carry-v2"
        or manifest.get("actionable_arm_id") != "no_trade"
        or manifest.get("no_strategy_arm_accepted_or_actionable") is not True
    ):
        raise ValueError("safe carry evidence manifest identity changed")
    expected = {
        _relative(output / "report.json"): report_sha,
        _relative(output / "evaluation-primary-trades.jsonl"): trades_sha,
    }
    observed = {item.get("path"): item.get("sha256") for item in manifest.get("artifacts", [])}
    if observed != expected:
        raise ValueError("safe carry evidence manifest artifact set changed")
    for item in manifest.get("implementation", []):
        path = ROOT / item["path"]
        if not path.is_file() or sha256_path(path) != item["sha256"]:
            raise ValueError(f"safe carry implementation changed: {item['path']}")
    contract = manifest.get("bound_contract", {})
    contract_path = ROOT / str(contract.get("path"))
    if not contract_path.is_file() or sha256_path(contract_path) != contract.get("sha256"):
        raise ValueError("safe carry bound contract changed")
    return manifest


def audit(primary: Path, replay: Path) -> dict[str, Any]:
    primary = primary.resolve(strict=True)
    replay = replay.resolve(strict=True)
    primary_report_path = primary / "report.json"
    replay_report_path = replay / "report.json"
    primary_trades_path = primary / "evaluation-primary-trades.jsonl"
    replay_trades_path = replay / "evaluation-primary-trades.jsonl"
    primary_report_sha = sha256_path(primary_report_path)
    replay_report_sha = sha256_path(replay_report_path)
    primary_trades_sha = sha256_path(primary_trades_path)
    replay_trades_sha = sha256_path(replay_trades_path)
    primary_report = _load_canonical(primary_report_path)
    replay_report = _load_canonical(replay_report_path)
    primary_manifest = _validate_manifest(primary, primary_report_sha, primary_trades_sha)
    replay_manifest = _validate_manifest(replay, replay_report_sha, replay_trades_sha)

    primary_result = primary_report["results"]["evaluation"][
        "candle-primary-30bps-rt-v1"
    ]
    severe_result = primary_report["results"]["evaluation"][
        "candle-severe-80bps-rt-v1"
    ]
    always_on = primary_report["controls"][
        "always_on_matched_carry_same_25pct_primary"
    ]
    checks = {
        "accepted_strategy_arms_empty": primary_report.get("accepted_strategy_arms") == [],
        "actionable_arm_no_trade": primary_report.get("actionable_arm_id") == "no_trade",
        "always_on_no_observed_or_shock_breach": always_on["counts"]["margin_breaches"]
        == 0
        and always_on["counts"]["shock_margin_breaches"] == 0,
        "always_on_same_exposure_is_more_efficient": always_on["metrics"][
            "return_per_exposed_day"
        ]
        > primary_result["metrics"]["return_per_exposed_day"],
        "decision_exact": primary_report.get("decision")
        == "risk_implementation_passed_timing_alpha_rejected",
        "manifest_semantic_replay_identical": _normalize(primary_manifest, primary)
        == _normalize(replay_manifest, replay),
        "primary_and_severe_positive": primary_result["metrics"]["net_return"] > 0
        and severe_result["metrics"]["net_return"] > 0,
        "primary_counts_exact": primary_result["metrics"]["trade_count"] == 6
        and primary_result["counts"]["margin_breaches"] == 0
        and primary_result["counts"]["shock_margin_breaches"] == 0
        and primary_result["counts"]["risk_exits"] == 0
        and primary_result["counts"]["entry_shocked_ratio_rejections"] == 0,
        "primary_margin_ratio_above_frozen_minimum": primary_result[
            "margin_diagnostics"
        ]["minimum_shocked_margin_equity_to_maintenance_ratio"]
        >= 2.0,
        "report_byte_identical": primary_report_sha == replay_report_sha,
        "risk_gates_all_pass": all(primary_report.get("risk_gates", {}).values()),
        "risk_implementation_passed": primary_report.get("risk_implementation_passed")
        is True,
        "sizing_not_presented_as_alpha": abs(
            primary_report["sizing_attribution"][
                "v2_primary_net_return_per_unit_leg_fraction"
            ]
            - primary_report["sizing_attribution"][
                "legacy_v1_primary_net_return_per_unit_leg_fraction"
            ]
        )
        < 0.002,
        "timing_alpha_rejected": primary_report.get("timing_alpha_passed") is False
        and not any(primary_report.get("timing_gates", {}).values()),
        "trades_byte_identical": primary_trades_sha == replay_trades_sha,
        "year_2026_unread": primary_report.get("data_audit", {}).get("year_2026_accessed")
        is False,
        "zero_live_credentials_orders_ob0_or_protected_services": primary_report.get(
            "zero_live_capital_credentials_orders_2026_ob0_or_protected_services"
        )
        is True,
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise ValueError(f"safe carry v2 independent audit failed: {failed}")

    report = {
        "actionable_arm_id": "no_trade",
        "checks": checks,
        "decision": "safe_carry_v2_risk_pass_timing_rejection_independently_reproduced",
        "experiment_id": "btc-safe-delta-neutral-funding-carry-v2",
        "primary_result": {
            "maximum_drawdown": primary_result["metrics"]["maximum_drawdown"],
            "minimum_shocked_margin_ratio": primary_result["margin_diagnostics"][
                "minimum_shocked_margin_equity_to_maintenance_ratio"
            ],
            "net_return": primary_result["metrics"]["net_return"],
            "return_per_exposed_day": primary_result["metrics"][
                "return_per_exposed_day"
            ],
            "trade_count": primary_result["metrics"]["trade_count"],
        },
        "replay": {
            "manifest": _relative(replay / "evidence-manifest.json"),
            "manifest_sha256": sha256_path(replay / "evidence-manifest.json"),
            "report": _relative(replay_report_path),
            "report_sha256": replay_report_sha,
            "trades": _relative(replay_trades_path),
            "trades_sha256": replay_trades_sha,
        },
        "same_exposure_always_on": {
            "minimum_shocked_margin_ratio": always_on["margin_diagnostics"][
                "minimum_shocked_margin_equity_to_maintenance_ratio"
            ],
            "net_return": always_on["metrics"]["net_return"],
            "return_per_exposed_day": always_on["metrics"]["return_per_exposed_day"],
        },
        "strategy_arm_accepted": False,
    }
    audit_directory = primary / "audit"
    report_path = audit_directory / "audit-report.json"
    report_sha = _write_json(report_path, report)
    manifest = {
        "actionable_arm_id": "no_trade",
        "artifacts": [
            {"path": _relative(primary_report_path), "sha256": primary_report_sha},
            {"path": _relative(primary_trades_path), "sha256": primary_trades_sha},
            {
                "path": _relative(primary / "evidence-manifest.json"),
                "sha256": sha256_path(primary / "evidence-manifest.json"),
            },
            {"path": _relative(replay_report_path), "sha256": replay_report_sha},
            {"path": _relative(replay_trades_path), "sha256": replay_trades_sha},
            {
                "path": _relative(replay / "evidence-manifest.json"),
                "sha256": sha256_path(replay / "evidence-manifest.json"),
            },
            {"path": _relative(report_path), "sha256": report_sha},
        ],
        "audit_implementation": {
            "path": _relative(Path(__file__)),
            "sha256": sha256_path(Path(__file__)),
        },
        "decision": "risk_implementation_passed_timing_alpha_rejected_and_closed",
        "experiment_id": "btc-safe-delta-neutral-funding-carry-v2",
        "no_strategy_arm_accepted_or_actionable": True,
        "schema_version": "btc-safe-funding-carry-risk-v2-audit-manifest-v1",
    }
    manifest_path = audit_directory / "evidence-manifest.json"
    manifest_sha = _write_json(manifest_path, manifest)
    return {
        **report,
        "audit_manifest": _relative(manifest_path),
        "audit_manifest_sha256": manifest_sha,
        "audit_report": _relative(report_path),
        "audit_report_sha256": report_sha,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--primary", type=Path, default=DEFAULT_PRIMARY)
    parser.add_argument("--replay", type=Path, default=DEFAULT_REPLAY)
    args = parser.parse_args()
    result = audit(args.primary, args.replay)
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))


if __name__ == "__main__":
    main()
