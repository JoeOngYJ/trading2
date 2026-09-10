#!/usr/bin/env python3
"""Validate the frozen, offline-only Tardis raw-pilot contract."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from trading_platform.research_program import canonical_json


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = REPO_ROOT / "config/experiments/btc-order-book-tardis-raw-pilot-v1.json"


class TardisPilotContractError(ValueError):
    """Raised when the frozen provider-pilot boundary is stale or unsafe."""


def validate_contract(path: Path = CONTRACT_PATH) -> dict:
    raw = path.read_text(encoding="utf-8")
    payload = json.loads(raw)
    if raw != canonical_json(payload):
        raise TardisPilotContractError("contract is not deterministically serialized")
    if payload.get("schema_version") != "btc-order-book-provider-raw-pilot-contract-v1":
        raise TardisPilotContractError("unsupported contract schema")
    if payload.get("status") != "frozen":
        raise TardisPilotContractError("contract must remain frozen")

    boundaries = payload.get("boundaries", {})
    dates = boundaries.get("exact_partition_dates")
    if dates != ["2019-12-01", "2022-12-01", "2025-12-01"]:
        raise TardisPilotContractError("pilot dates changed")
    if any(date.fromisoformat(value).year >= 2026 for value in dates):
        raise TardisPilotContractError("sealed or future partition requested")
    if boundaries.get("sealed_2026_access_allowed") is not False:
        raise TardisPilotContractError("sealed 2026 access must remain disabled")

    inputs = payload.get("inputs", {})
    if inputs.get("allowed_host") != "api.tardis.dev":
        raise TardisPilotContractError("unexpected provider host")
    if inputs.get("allowed_path") != "/v1/data-feeds/binance":
        raise TardisPilotContractError("unexpected provider path")
    if inputs.get("channels") != ["aggTrade", "depth", "depthSnapshot"]:
        raise TardisPilotContractError("native channel set changed")
    if inputs.get("format") != "exchange_native_ndjson_with_local_timestamp":
        raise TardisPilotContractError("normalized data cannot satisfy this contract")
    for url in inputs.get("provider_documentation", []):
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != "docs.tardis.dev":
            raise TardisPilotContractError("provider reference escapes the official host")

    prerequisite = payload.get("execution_prerequisites", {})
    if prerequisite.get("state") != "blocked_pending_final_ob0_acceptance_and_provider_access":
        raise TardisPilotContractError("pilot execution must remain blocked")
    if prerequisite.get("final_ob0_acceptance_required") is not True:
        raise TardisPilotContractError("final OB0 acceptance gate is missing")
    if prerequisite.get("active_ob0_may_be_inspected_to_decide_readiness") is not False:
        raise TardisPilotContractError("partial OB0 inspection is prohibited")

    safety = payload.get("isolation", {})
    required_false = (
        "active_or_partial_ob0_access_allowed",
        "database_access_allowed",
        "economic_or_predictive_analysis_allowed",
        "exchange_api_access_allowed",
        "live_trading_authorized",
        "message_bus_access_allowed",
        "production_signal_or_order_access_allowed",
        "running_service_or_container_access_allowed",
    )
    if any(safety.get(key) is not False for key in required_false):
        raise TardisPilotContractError("offline safety boundary changed")
    if payload.get("access_and_budget", {}).get("purchase_authorized") is not False:
        raise TardisPilotContractError("contract cannot authorize a purchase")
    if payload.get("decision_rule", {}).get("normalized_csv_can_satisfy_raw_contract") is not False:
        raise TardisPilotContractError("normalized CSV must fail closed")

    return {
        "audit_id": payload["audit_id"],
        "decision": "contract_valid_execution_blocked",
        "exact_partition_dates": dates,
        "purchase_authorized": False,
        "sealed_2026_access_allowed": False,
    }


def main() -> None:
    print(json.dumps(validate_contract(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
