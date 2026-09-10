#!/usr/bin/env python3
"""Run the frozen safe-exposure BTC funding carry risk v2 experiment offline."""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal, ROUND_DOWN
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for _entry in (str(ROOT), str(SRC)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from scripts.backtest_btc_positive_funding_carry import (
    B2_SOURCE,
    RECOVERY_SOURCE,
    _gate_number,
    load_archive_bars,
    load_funding,
    load_scenarios,
    load_spot_hourly,
    merge_recovery_mark,
)
from trading_platform.btc_carry import CarryCostScenario, CarryParameters, HourBar, utc_ms
from trading_platform.btc_carry_risk_v2 import run_safe_carry_backtest


CONTRACT_PATH = ROOT / "research/btc/contracts/btc-safe-delta-neutral-funding-carry-v2.json"
DEFAULT_OUTPUT = (
    ROOT / "artifacts/agent-level-experiment/btc-focused/safe-delta-neutral-funding-carry-v2"
)
LEGACY_REPORT = (
    ROOT / "artifacts/agent-level-experiment/btc-focused/positive-funding-carry-v1/report.json"
)


def canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode()


def sha256_path(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_contract(contract: dict[str, Any]) -> None:
    if (
        contract.get("status") != "frozen_before_any_v2_return_calculation"
        or contract.get("experiment_id") != "btc-safe-delta-neutral-funding-carry-v2"
        or contract.get("action_boundary", {}).get("actionable_arm_id") != "no_trade"
    ):
        raise ValueError("safe carry v2 contract is not frozen and fail-closed")
    if any(
        contract.get("action_boundary", {}).get(key) is not False
        for key in (
            "credentials_allowed",
            "live_or_exchange_paper_orders_allowed",
            "partial_ob0_access_allowed",
            "position_or_order_intent_creation_allowed",
            "production_signal_creation_allowed",
            "protected_service_access_allowed",
            "year_2026_access_allowed",
        )
    ):
        raise ValueError("safe carry v2 action boundary changed")
    for item in contract["bound_inputs"]:
        path = ROOT / item["path"]
        if not path.is_file() or sha256_path(path) != item["sha256"]:
            raise ValueError(f"missing or changed safe carry v2 input: {item['path']}")


def _spot_control(
    spot: dict[int, HourBar],
    start: int,
    end: int,
    scenario: CarryCostScenario,
    leg_fraction: Decimal,
) -> dict[str, Any]:
    first = min(timestamp for timestamp in spot if timestamp >= start)
    last = max(timestamp for timestamp in spot if timestamp <= end)
    quantity = (
        Decimal("1000") * leg_fraction / spot[first].open
    ).quantize(Decimal("0.00001"), rounding=ROUND_DOWN)
    buy = spot[first].open * (
        Decimal("1") + scenario.implicit_bps_per_fill / Decimal("10000")
    )
    sell = spot[last].open * (
        Decimal("1") - scenario.implicit_bps_per_fill / Decimal("10000")
    )
    fees = quantity * (buy + sell) * scenario.fee_bps_per_fill / Decimal("10000")
    pnl = quantity * (sell - buy) - fees
    return {
        "entry_ms": first,
        "exit_ms": last,
        "leg_fraction": float(leg_fraction),
        "net_return": float(pnl / Decimal("1000")),
        "pnl_quote": str(pnl),
    }


def _concentration_pass(value: Any, maximum: float) -> bool:
    return value is not None and float(value) <= maximum


def run(output: Path, contract_path: Path = CONTRACT_PATH) -> dict[str, Any]:
    contract_path = contract_path.resolve(strict=True)
    contract_path.relative_to(ROOT)
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    verify_contract(contract)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite immutable safe carry output: {output}")
    output.mkdir(parents=True)

    b2 = json.loads(B2_SOURCE.read_text(encoding="utf-8"))
    archive_records = b2["archive_records"]
    future = load_archive_bars(
        [item for item in archive_records if item["series"] == "klines"], "klines"
    )
    mark = load_archive_bars(
        [item for item in archive_records if item["series"] == "markPriceKlines"],
        "markPriceKlines",
    )
    funding = load_funding(
        [item for item in archive_records if item["series"] == "fundingRate"]
    )
    recovery = json.loads(RECOVERY_SOURCE.read_text(encoding="utf-8"))
    merge_recovery_mark(mark, recovery)
    spot, spot_audit = load_spot_hourly()
    if len(future) != 52608 or len(mark) != 52608 or len(funding) != 6576:
        raise ValueError("safe carry v2 requires complete frozen derivatives ledgers")

    scenarios = load_scenarios()
    params = CarryParameters(leg_fraction=Decimal("0.25"))
    minimum_ratio = Decimal("2")
    partitions = {
        "development": (
            utc_ms("2020-02-03T00:00:00Z"),
            utc_ms("2023-12-31T23:00:00Z"),
        ),
        "evaluation": (
            utc_ms("2024-01-01T00:00:00Z"),
            utc_ms("2025-12-31T23:00:00Z"),
        ),
    }
    results: dict[str, Any] = {}
    for partition, (start, end) in partitions.items():
        results[partition] = {}
        for scenario_id, scenario in scenarios.items():
            results[partition][scenario_id] = run_safe_carry_backtest(
                spot=spot,
                future=future,
                mark=mark,
                funding=funding,
                start_ms=start,
                end_ms=end,
                scenario=scenario,
                params=params,
                minimum_shocked_margin_ratio=minimum_ratio,
            )

    primary_id = "candle-primary-30bps-rt-v1"
    severe_id = "candle-severe-80bps-rt-v1"
    evaluation_start, evaluation_end = partitions["evaluation"]
    primary = results["evaluation"][primary_id]
    severe = results["evaluation"][severe_id]
    always_on = run_safe_carry_backtest(
        spot=spot,
        future=future,
        mark=mark,
        funding=funding,
        start_ms=evaluation_start,
        end_ms=evaluation_end,
        scenario=scenarios[primary_id],
        params=params,
        minimum_shocked_margin_ratio=minimum_ratio,
        mode="always_on",
    )
    no_funding = run_safe_carry_backtest(
        spot=spot,
        future=future,
        mark=mark,
        funding=funding,
        start_ms=evaluation_start,
        end_ms=evaluation_end,
        scenario=scenarios[primary_id],
        params=params,
        minimum_shocked_margin_ratio=minimum_ratio,
        include_funding=False,
    )
    return_per_exposure_increment = (
        primary["metrics"]["return_per_exposed_day"]
        - always_on["metrics"]["return_per_exposed_day"]
    )
    years_positive = sum(
        value > 0 for value in primary["metrics"]["annual_returns"].values()
    )
    maximum_concentration = contract["frozen_gates"][
        "best_three_month_positive_pnl_fraction_max"
    ]
    risk_gates = {
        "best_three_month_concentration": _concentration_pass(
            primary["concentration"]["best_three_month_positive_pnl_fraction"],
            maximum_concentration,
        ),
        "best_trade_concentration": _concentration_pass(
            primary["concentration"]["best_trade_positive_pnl_fraction"],
            contract["frozen_gates"]["best_trade_positive_pnl_fraction_max"],
        ),
        "data_causality_matched_quantity_and_no_2026": (
            primary["counts"]["notional_mismatch_rejections"] == 0
            and spot_audit["source_sha256"]
            == "3d37dadf416469cef7ce57fb009a1796658b7cf098c1e451045f85436eab46ab"
        ),
        "entry_shocked_ratio_rejections_zero": primary["counts"][
            "entry_shocked_ratio_rejections"
        ]
        == 0,
        "funding_cashflow_positive": Decimal(primary["attribution"]["funding_cashflow"])
        > 0,
        "minimum_trades": primary["metrics"]["trade_count"]
        >= contract["frozen_gates"]["minimum_closed_trades"],
        "no_observed_margin_breach": primary["counts"]["margin_breaches"] == 0,
        "no_shocked_margin_breach": primary["counts"]["shock_margin_breaches"] == 0,
        "primary_drawdown": primary["metrics"]["maximum_drawdown"]
        <= contract["frozen_gates"]["primary_maximum_drawdown_max"],
        "primary_net_positive": primary["metrics"]["net_return"] > 0,
        "severe_net_positive": severe["metrics"]["net_return"] > 0,
        "validation_years_positive": years_positive
        == contract["frozen_gates"]["strictly_positive_evaluation_years_required"],
    }
    timing_gates = {
        "return_per_exposed_day_beats_same_exposure_always_on": (
            return_per_exposure_increment > 0
        )
    }
    risk_passed = all(risk_gates.values())
    timing_passed = all(timing_gates.values())
    if risk_passed and timing_passed:
        decision = "development_candidate_passed_not_promotable"
    elif risk_passed:
        decision = "risk_implementation_passed_timing_alpha_rejected"
    else:
        decision = "risk_implementation_rejected"

    legacy = json.loads(LEGACY_REPORT.read_text(encoding="utf-8"))
    legacy_primary = legacy["results"]["validation"][primary_id]["metrics"]
    controls = {
        "always_on_matched_carry_same_25pct_primary": always_on,
        "btc_spot_buy_and_hold_same_25pct_primary": _spot_control(
            spot,
            evaluation_start,
            evaluation_end,
            scenarios[primary_id],
            params.leg_fraction,
        ),
        "flat": {"net_return": 0.0},
        "rejected_v1_49pct_primary_metrics": legacy_primary,
        "signal_windows_funding_only_same_25pct_primary": {
            "net_return": float(
                (
                    Decimal(primary["attribution"]["funding_cashflow"])
                    - Decimal(primary["attribution"]["explicit_fees"])
                    - Decimal(primary["attribution"]["implicit_cost"])
                )
                / Decimal("1000")
            )
        },
        "signal_windows_without_funding_same_25pct_primary": no_funding,
    }
    report = {
        "accepted_strategy_arms": [],
        "actionable_arm_id": "no_trade",
        "controls": controls,
        "data_audit": {
            "funding_events": len(funding),
            "futures_hours": len(future),
            "mark_hours": len(mark),
            "premium_index_consumed": False,
            "spot": spot_audit,
            "year_2026_accessed": False,
        },
        "decision": decision,
        "experiment_id": contract["experiment_id"],
        "promotion_evidence": False,
        "results": results,
        "return_per_exposed_day_increment_vs_same_exposure_always_on": (
            return_per_exposure_increment
        ),
        "risk_gates": risk_gates,
        "risk_implementation_passed": risk_passed,
        "sizing_attribution": {
            "legacy_v1_leg_fraction": 0.49,
            "legacy_v1_primary_net_return": legacy_primary["net_return"],
            "legacy_v1_primary_net_return_per_unit_leg_fraction": (
                legacy_primary["net_return"] / 0.49
            ),
            "v2_leg_fraction": 0.25,
            "v2_primary_net_return": primary["metrics"]["net_return"],
            "v2_primary_net_return_per_unit_leg_fraction": primary["metrics"][
                "net_return_per_unit_leg_fraction"
            ],
        },
        "strategy_passed_frozen_development_gates": risk_passed and timing_passed,
        "timing_alpha_passed": timing_passed,
        "timing_gates": timing_gates,
        "v1_signal_parameters_unchanged": True,
        "zero_live_capital_credentials_orders_2026_ob0_or_protected_services": True,
    }

    report_path = output / "report.json"
    report_path.write_bytes(canonical_bytes(report))
    trades_path = output / "evaluation-primary-trades.jsonl"
    with trades_path.open("wb") as handle:
        for trade in primary["trades"]:
            handle.write(canonical_bytes(trade))
    implementation = [
        ROOT / "src/trading_platform/btc_carry.py",
        ROOT / "src/trading_platform/btc_carry_risk_v2.py",
        ROOT / "scripts/backtest_btc_positive_funding_carry.py",
        ROOT / "scripts/backtest_btc_safe_funding_carry_risk_v2.py",
        ROOT / "tests/test_btc_carry.py",
        ROOT / "tests/test_btc_carry_risk_v2.py",
    ]
    evidence = {
        "actionable_arm_id": "no_trade",
        "artifacts": [
            {"path": str(report_path.relative_to(ROOT)), "sha256": sha256_path(report_path)},
            {"path": str(trades_path.relative_to(ROOT)), "sha256": sha256_path(trades_path)},
        ],
        "bound_contract": {
            "path": str(contract_path.relative_to(ROOT)),
            "sha256": sha256_path(contract_path),
        },
        "decision": decision,
        "experiment_id": contract["experiment_id"],
        "implementation": [
            {"path": str(path.relative_to(ROOT)), "sha256": sha256_path(path)}
            for path in implementation
        ],
        "no_strategy_arm_accepted_or_actionable": True,
        "schema_version": "btc-safe-funding-carry-risk-v2-evidence-manifest-v1",
    }
    manifest_path = output / "evidence-manifest.json"
    manifest_path.write_bytes(canonical_bytes(evidence))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=CONTRACT_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    contract = args.contract if args.contract.is_absolute() else ROOT / args.contract
    report = run(output, contract)
    primary = report["results"]["evaluation"]["candle-primary-30bps-rt-v1"]
    severe = report["results"]["evaluation"]["candle-severe-80bps-rt-v1"]
    summary = {
        "decision": report["decision"],
        "primary_counts": primary["counts"],
        "primary_metrics": primary["metrics"],
        "risk_gates": report["risk_gates"],
        "severe_metrics": severe["metrics"],
        "timing_gates": report["timing_gates"],
    }
    print(json.dumps(summary, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
