#!/usr/bin/env python3
"""Validate the BTC unified backtest E0 specification without reading market data."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "research/btc/contracts/btc-unified-backtest-engine-e0-v1.json"
PLAN = ROOT / "research/btc/reports/BTC_UNIFIED_BACKTEST_ENGINE_E0_PLAN.md"
REVIEW = ROOT / "research/btc/reports/BTC_UNIFIED_BACKTEST_ENGINE_E0_REVIEW.md"
QUALIFICATION_ID = "btc-unified-backtest-engine-e0-v1"


class E0ValidationError(ValueError):
    pass


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise E0ValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def canonical_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"


def canonical_line(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def load_contract(path: Path = CONTRACT) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
        value = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise E0ValidationError(f"cannot parse contract: {path}") from exc
    if not isinstance(value, dict) or raw != canonical_json(value):
        raise E0ValidationError("contract is not canonical sorted UTF-8 JSON")
    return value


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise E0ValidationError(message)


def validate_contract(contract: dict[str, Any]) -> dict[str, bool]:
    action = contract.get("action_boundary", {})
    _require(contract.get("qualification_id") == QUALIFICATION_ID, "wrong qualification ID")
    _require(
        contract.get("status") == "frozen_before_E1_implementation", "contract is not frozen"
    )
    _require(action.get("actionable_arm_id") == "no_trade", "action boundary is not no_trade")
    _require(action.get("accepted_strategy_arms") == [], "a strategy arm was accepted")
    _require(
        action.get("historical_strategy_return_access_allowed_in_E0_E1_E2") is False,
        "historical return access is not prohibited",
    )
    _require(
        action.get("production_SignalPayload_OrderIntent_position_or_route_allowed") is False,
        "production actions are not prohibited",
    )

    required_authorities = {
        "config/execution_scenarios.json",
        "config/mandates/retail-btc-delta-neutral-research-v1.json",
        "config/mandates/retail-btc-directional-perpetual-research-v1.json",
        "config/retail_mandate.json",
        "docs/BTC_DERIVATIVES_RESEARCH_MANDATE.md",
        "docs/BTC_DIRECTIONAL_PERPETUAL_RESEARCH_MANDATE.md",
        "docs/EXECUTION_COST_MODEL.md",
        "docs/RETAIL_TRADING_MANDATE.md",
        "docs/STRATEGY_RESEARCH_STANDARD.md",
        "research/btc/BTC_EVIDENCE_CATALOG.json",
        "research/btc/contracts/btc-only-program-v1.json",
    }
    authorities = contract.get("bound_authorities", [])
    paths = {item.get("path") for item in authorities}
    _require(paths == required_authorities, "bound authority set is incomplete or unexpected")
    for item in authorities:
        path = ROOT / item["path"]
        _require(path.is_file(), f"missing authority: {item['path']}")
        _require(sha256_path(path) == item.get("sha256"), f"changed authority: {item['path']}")

    phases = contract.get("event_order", {}).get("phases", [])
    _require([item.get("phase") for item in phases] == list(range(1, 10)), "invalid event phases")
    phase_text = " ".join(str(item.get("name", "")) for item in phases)
    for token in ("liquidation", "protective", "funding", "strategy", "adverse", "reconcile"):
        _require(token in phase_text, f"event order omits {token}")

    accounting = contract.get("accounting_contract", {})
    _require("liabilities" in accounting.get("identities", {}).get("nav", ""), "NAV omits liabilities")
    _require("fee_asset" in accounting.get("identities", {}).get("nav", ""), "NAV omits fee assets")
    _require("memo" in accounting.get("memo_vs_balance", ""), "memo/balance split is missing")
    _require(
        "never_both" in accounting.get("cost_treatment", {}).get("no_double_count", ""),
        "cost double-count protection is missing",
    )

    margin = contract.get("margin_contract", {})
    _require("terminal_evaluation_invalidation" in margin.get("liquidation_treatment", ""), "observed liquidation is not terminal")
    _require("planning_buffer_breach_only" in margin.get("response", ""), "planning and liquidation breaches are conflated")

    adapter = contract.get("execution_adapter_capabilities", {})
    _require("all_or_none" in adapter.get("candle_OHLC", ""), "candle adapter permits partial fills")
    _require("synthetic" in adapter.get("partial_fill", "") and "L2" in adapter.get("partial_fill", ""), "partial-fill evidence boundary missing")

    serialization = contract.get("serialization_and_digest_contract", {})
    _require(
        "reject_during_parse" in serialization.get("duplicate_object_keys", ""),
        "duplicate keys not rejected",
    )
    _require("excluding_only" in serialization.get("row_digest", ""), "row digest domain missing")
    _require(
        "signed_zero_normalized_to_0"
        in accounting.get("decimal_policy", {}).get("canonical_decimal_string", ""),
        "negative-zero normalization missing",
    )

    output = contract.get("output_contract", {})
    for ledger_name in (
        "decision_ledger",
        "order_ledger",
        "fill_ledger",
        "funding_ledger",
        "hourly_account_ledger",
        "closed_episode_ledger",
    ):
        fields = output.get(ledger_name, [])
        _require("row_digest" in fields, f"{ledger_name} omits row_digest")
        if ledger_name != "closed_episode_ledger":
            _require("event_sequence" in fields, f"{ledger_name} omits event_sequence")
            _require("before_state_digest" in fields, f"{ledger_name} omits before state")
            _require("after_state_digest" in fields, f"{ledger_name} omits after state")
    common_fields = set(output.get("common_economic_row_fields", []))
    _require(
        {"event_sequence", "before_state_digest", "after_state_digest", "row_digest"}
        <= common_fields,
        "common economic row lineage is incomplete",
    )

    fixtures = set(contract.get("synthetic_fixture_requirements_for_E1_E2", []))
    required_fixtures = {
        "same_timestamp_funding_and_entry_membership",
        "same_timestamp_funding_and_exit_membership",
        "funding_caused_margin_breach",
        "gap_through_observed_liquidation_with_fee_and_deficit",
        "zero_position_price_and_funding_invariance",
        "unchanged_price_round_trip_loses_exactly_equity_affecting_costs",
        "mirrored_long_and_short_price_paths",
        "duplicate_and_permuted_same_sequence_events_reject",
        "unsupported_or_unavailable_fee_currency_rejects",
        "candle_adapter_cannot_emit_partial_fill",
    }
    _require(required_fixtures <= fixtures, "synthetic fixture matrix is incomplete")

    independence = contract.get("subsequent_phase_boundary", {}).get("E2_independence", "")
    for token in ("PortfolioLedger", "dataclasses", "AST", "transitive", "every_event_row"):
        _require(token in independence, f"oracle independence omits {token}")

    prohibited = " ".join(contract.get("prohibited", []))
    for token in ("historical", "2026", "OB0", "network", "database", "NATS", "Freqtrade"):
        _require(token in prohibited, f"prohibited scope omits {token}")

    return {
        "accounting_semantics_complete": True,
        "action_boundary_fail_closed": True,
        "authority_hashes_verified": True,
        "canonical_contract_verified": True,
        "event_and_liquidation_order_complete": True,
        "oracle_independence_frozen": True,
        "output_lineage_complete": True,
        "synthetic_fixture_matrix_complete": True,
    }


def qualify(output: Path) -> dict[str, Any]:
    output = output.resolve()
    contract = load_contract()
    gates = validate_contract(contract)
    _require(PLAN.is_file(), "missing E0 plan")
    _require(REVIEW.is_file(), "missing independent E0 review")
    _require(not output.exists(), "output path must not already exist")
    output.mkdir(parents=True)

    report: dict[str, Any] = {
        "actionable_arm_id": "no_trade",
        "bound_authority_count": len(contract["bound_authorities"]),
        "contract_sha256": sha256_path(CONTRACT),
        "decision": "e0_specification_passed_e1_synthetic_only_permitted",
        "gates": gates,
        "historical_market_rows_accessed": 0,
        "historical_strategy_return_accessed": False,
        "next_permitted_phase": "E1_synthetic_Decimal_accounting_kernel_only",
        "plan_sha256": sha256_path(PLAN),
        "production_or_external_service_accessed": False,
        "qualification_id": QUALIFICATION_ID,
        "review_sha256": sha256_path(REVIEW),
        "sealed_2026_or_partial_OB0_accessed": False,
    }
    report_path = output / "qualification-report.json"
    report_path.write_text(canonical_json(report), encoding="utf-8")

    artifacts = []
    for path, role in (
        (CONTRACT, "frozen_contract"),
        (PLAN, "human_plan"),
        (REVIEW, "independent_review"),
        (Path(__file__), "validator"),
        (ROOT / "research/btc/tests/test_unified_engine_e0.py", "tests"),
        (report_path, "qualification_report"),
    ):
        artifacts.append(
            {
                "path": str(path.relative_to(ROOT)),
                "role": role,
                "sha256": sha256_path(path),
                "size_bytes": path.stat().st_size,
            }
        )
    manifest = {
        "actionable_arm_id": "no_trade",
        "artifacts": artifacts,
        "decision": report["decision"],
        "qualification_id": QUALIFICATION_ID,
    }
    (output / "evidence-manifest.json").write_text(canonical_json(manifest), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(canonical_line(qualify(args.output)))


if __name__ == "__main__":
    main()
