"""Fail-closed validation for the offline cross-asset research program.

The module reads repository-owned contracts only. It has no exchange, network, database,
message-bus, runtime-signal, order, or position dependency.
"""

from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping, Sequence


STAGE_IDS = tuple(f"A{index}" for index in range(7))
STAGE_STATES = frozenset({"planned", "active", "passed", "rejected", "blocked", "skipped"})
TERMINAL_STATES = frozenset({"passed", "rejected", "skipped"})
FORBIDDEN_IMPORT_ROOTS = frozenset(
    {
        "ccxt",
        "fastapi",
        "httpx",
        "nats",
        "psycopg",
        "requests",
        "sqlalchemy",
        "trading_platform.bridge",
        "trading_platform.contracts",
        "trading_platform.db",
        "trading_platform.execution_model",
        "trading_platform.nats_support",
        "trading_platform.repository",
        "trading_platform.worker",
    }
)


class CrossAssetContextError(ValueError):
    """Raised when the cross-asset context is unsafe, stale, or inconsistent."""


def canonical_json(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True, separators=(",", ": ")
    ) + "\n"


def canonical_json_line(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def decision_digest(record: Mapping[str, Any]) -> str:
    payload = {key: value for key, value in record.items() if key != "record_digest"}
    return hashlib.sha256(canonical_json_line(payload).encode("utf-8")).hexdigest()


def _load_canonical(path: Path, label: str) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise CrossAssetContextError(f"cannot read {label}: {path}") from exc
    if not isinstance(payload, dict):
        raise CrossAssetContextError(f"{label} must be a JSON object")
    if raw != canonical_json(payload):
        raise CrossAssetContextError(f"{label} is not canonically serialized")
    return payload


def _repo_file(root: Path, raw: Any, label: str) -> Path:
    if not isinstance(raw, str) or not raw or Path(raw).is_absolute():
        raise CrossAssetContextError(f"{label} must be a repository-relative path")
    boundary = root.resolve(strict=True)
    try:
        candidate = (boundary / raw).resolve(strict=True)
        candidate.relative_to(boundary)
    except (OSError, ValueError) as exc:
        raise CrossAssetContextError(f"invalid {label}: {raw}") from exc
    if not candidate.is_file():
        raise CrossAssetContextError(f"{label} is not a regular file: {raw}")
    return candidate


def _utc(raw: Any, label: str) -> datetime:
    if not isinstance(raw, str) or not raw:
        raise CrossAssetContextError(f"{label} must be a UTC timestamp")
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CrossAssetContextError(f"invalid {label}: {raw}") from exc
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise CrossAssetContextError(f"{label} must use explicit UTC")
    return value


def _validate_program(payload: Mapping[str, Any]) -> tuple[str, dict[str, tuple[str, ...]]]:
    schema = payload.get("schema_version")
    if schema not in {
        "cross-asset-research-program-v1",
        "cross-asset-research-program-v2",
        "cross-asset-research-program-v3",
        "cross-asset-research-program-v4",
        "cross-asset-research-program-v5",
        "cross-asset-research-program-v6",
    }:
        raise CrossAssetContextError("unsupported cross-asset program schema")
    program_id = str(payload.get("program_id", ""))
    if program_id != "retail-cross-asset-multi-strategy-v1":
        raise CrossAssetContextError("unexpected cross-asset program_id")
    stages = payload.get("stages")
    if not isinstance(stages, list) or tuple(item.get("stage_id") for item in stages) != STAGE_IDS:
        raise CrossAssetContextError(f"program stages must be ordered exactly as {STAGE_IDS}")
    graph: dict[str, tuple[str, ...]] = {}
    for stage in stages:
        stage_id = str(stage["stage_id"])
        dependencies = tuple(str(value) for value in stage.get("dependencies", ()))
        if len(dependencies) != len(set(dependencies)):
            raise CrossAssetContextError(f"stage {stage_id} repeats a dependency")
        if any(value not in STAGE_IDS[: STAGE_IDS.index(stage_id)] for value in dependencies):
            raise CrossAssetContextError(f"stage {stage_id} has a non-prior dependency")
        if not all(stage.get(key) for key in ("objective", "pass_gate", "next_action")):
            raise CrossAssetContextError(f"stage {stage_id} is incomplete")
        graph[stage_id] = dependencies
    safety = payload.get("safety_boundaries", {})
    for key in (
        "bulk_market_data_download_allowed",
        "credentials_allowed",
        "database_access_allowed",
        "exchange_access_allowed",
        "live_trading_authorized",
        "message_bus_access_allowed",
        "order_intent_creation_allowed",
        "position_creation_allowed",
        "production_signal_creation_allowed",
        "running_soak_access_allowed",
        "strategy_evaluation_allowed_in_a0",
    ):
        if safety.get(key) is not False:
            raise CrossAssetContextError(f"A0 safety boundary must disable {key}")
    if safety.get("research_data_provider_api_tokens_allowed") is not True:
        raise CrossAssetContextError("the A1 provider-token exception must be explicit")
    if safety.get("actionable_arm_id") != "no_trade":
        raise CrossAssetContextError("A0 actionable arm must be no_trade")
    return program_id, graph


def _validate_mandate(payload: Mapping[str, Any]) -> None:
    schema = payload.get("schema_version")
    if schema not in {
        "cross-asset-research-mandate-v1",
        "cross-asset-research-mandate-v2",
        "cross-asset-research-mandate-v3",
        "cross-asset-research-mandate-v4",
        "cross-asset-research-mandate-v5",
        "cross-asset-research-mandate-v6",
        "cross-asset-research-mandate-v7",
    }:
        raise CrossAssetContextError("unsupported cross-asset mandate schema")
    if schema == "cross-asset-research-mandate-v1":
        if payload.get("mandate_id") != "retail-cross-asset-research-v1":
            raise CrossAssetContextError("unexpected mandate_id")
        if payload.get("status") != "frozen_a0_research_only":
            raise CrossAssetContextError("A0 mandate must be frozen research-only")
    elif schema == "cross-asset-research-mandate-v2":
        if payload.get("mandate_id") != "retail-cross-asset-research-v2":
            raise CrossAssetContextError("unexpected mandate_id")
        if payload.get("status") != "frozen_a1_data_access_only":
            raise CrossAssetContextError("A1 mandate must be frozen data-access-only")
        if payload.get("supersedes") != "retail-cross-asset-research-v1":
            raise CrossAssetContextError("A1 mandate must preserve v1 lineage")
    elif schema == "cross-asset-research-mandate-v3":
        if payload.get("mandate_id") != "retail-cross-asset-research-v3":
            raise CrossAssetContextError("unexpected mandate_id")
        if payload.get("status") != "frozen_a1_data_access_only":
            raise CrossAssetContextError("A1 mandate must be frozen data-access-only")
        if payload.get("supersedes") != "retail-cross-asset-research-v2":
            raise CrossAssetContextError("A1 mandate must preserve v2 lineage")
    elif schema == "cross-asset-research-mandate-v4":
        if payload.get("mandate_id") != "retail-cross-asset-research-v4":
            raise CrossAssetContextError("unexpected mandate_id")
        if payload.get("status") != "frozen_a1_data_access_and_derivatives_research_only":
            raise CrossAssetContextError("A1 v4 mandate must remain research-only")
        if payload.get("supersedes") != "retail-cross-asset-research-v3":
            raise CrossAssetContextError("A1 v4 mandate must preserve v3 lineage")
    elif schema == "cross-asset-research-mandate-v5":
        if payload.get("mandate_id") != "retail-cross-asset-research-v5":
            raise CrossAssetContextError("unexpected mandate_id")
        if payload.get("status") != "frozen_a1_oanda_read_only_data_qualification_only":
            raise CrossAssetContextError("A1 v5 mandate must remain OANDA research-only")
        if payload.get("supersedes") != "retail-cross-asset-research-v4":
            raise CrossAssetContextError("A1 v5 mandate must preserve v4 lineage")
    elif schema == "cross-asset-research-mandate-v6":
        if payload.get("mandate_id") != "retail-cross-asset-research-v6":
            raise CrossAssetContextError("unexpected mandate_id")
        if payload.get("status") != "frozen_a1_oanda_hourly_read_only_data_qualification_only":
            raise CrossAssetContextError("A1 v6 mandate must remain OANDA research-only")
        supersedes = payload.get("supersedes", {})
        if (
            supersedes.get("mandate_id") != "retail-cross-asset-research-v5"
            or supersedes.get("path") != "config/mandates/retail-cross-asset-research-v5.json"
            or supersedes.get("sha256")
            != "409efa04f45090e570c25d565d84e81eb6e7adba925822bf537f20de99b383b2"
        ):
            raise CrossAssetContextError("A1 v6 mandate must preserve v5 checksum lineage")
    else:
        if payload.get("mandate_id") != "retail-cross-asset-research-v7":
            raise CrossAssetContextError("unexpected mandate_id")
        if payload.get("status") != "frozen_a2_offline_strategy_research_and_conversion_data_only":
            raise CrossAssetContextError("A2 v7 mandate must remain offline research-only")
        supersedes = payload.get("supersedes", {})
        if (
            supersedes.get("mandate_id") != "retail-cross-asset-research-v6"
            or supersedes.get("path") != "config/mandates/retail-cross-asset-research-v6.json"
            or supersedes.get("sha256")
            != "789211dc38ca539b5d9a23d39848815fe4cb9087fddb33351f05fd9f42c9e957"
        ):
            raise CrossAssetContextError("A2 v7 mandate must preserve v6 checksum lineage")
    authority = payload.get("authority", {})
    if authority.get("live_trading_authorized") is not False:
        raise CrossAssetContextError("live trading must remain unauthorized")
    if authority.get("credentials_allowed") is not False:
        raise CrossAssetContextError("generic credentials must remain prohibited")
    if schema in {
        "cross-asset-research-mandate-v2",
        "cross-asset-research-mandate-v3",
        "cross-asset-research-mandate-v4",
        "cross-asset-research-mandate-v5",
        "cross-asset-research-mandate-v6",
        "cross-asset-research-mandate-v7",
    }:
        if authority.get("execution_credentials_allowed") is not False:
            raise CrossAssetContextError("execution credentials must remain prohibited")
        if authority.get("research_data_provider_api_tokens_allowed") is not True:
            raise CrossAssetContextError("A1 research-data token exception is missing")
        token_policy = payload.get("data_provider_token_policy", {})
        if schema in {
            "cross-asset-research-mandate-v5",
            "cross-asset-research-mandate-v6",
            "cross-asset-research-mandate-v7",
        }:
            if token_policy.get("allowed_environment_variables") != [
                "OANDA_ACCOUNT_ID",
                "OANDA_API_TOKEN",
                "OANDA_API_URL",
            ]:
                raise CrossAssetContextError("OANDA environment allowlist changed")
            if token_policy.get("allowed_http_method") != "GET":
                raise CrossAssetContextError("OANDA access must be GET-only")
            expected_purpose = (
                "offline_checksummed_oanda_a2_conversion_source_qualification_only"
                if schema == "cross-asset-research-mandate-v7"
                else "offline_checksummed_oanda_a1_source_qualification_only"
            )
            if token_policy.get("allowed_purpose") != expected_purpose:
                raise CrossAssetContextError("OANDA token purpose changed")
            expected_resources = (
                ["account_instrument_catalogue", "historical_instrument_candles"]
                if schema == "cross-asset-research-mandate-v5"
                else ["historical_instrument_candles"]
            )
            if token_policy.get("allowed_resource_classes") != expected_resources:
                raise CrossAssetContextError("OANDA resource allowlist changed")
            for key in (
                "broker_private_state_access_allowed",
                "database_or_message_bus_tokens_allowed",
                "may_be_logged_or_serialized",
                "order_or_order_preview_access_allowed",
                "repository_storage_allowed",
                "runtime_order_or_signal_access_allowed",
            ):
                if token_policy.get(key) is not False:
                    raise CrossAssetContextError(f"unsafe OANDA token policy: {key}")
        elif schema == "cross-asset-research-mandate-v2":
            expected_token = ["MARKETSTACK_API_KEY"]
            expected_purpose = "offline_checksummed_market_data_source_qualification_only"
        elif schema == "cross-asset-research-mandate-v3":
            expected_token = ["TWELVEDATA_API_KEY"]
            expected_purpose = "offline_checksummed_market_data_source_qualification_only"
        else:
            expected_token = [
                "CME_DATAMINE_API_ID",
                "CME_DATAMINE_API_PASSWORD",
                "DATABENTO_API_KEY",
                "TWELVEDATA_API_KEY",
            ]
            expected_purpose = "offline_checksummed_a1_source_qualification_only"
        if schema not in {
            "cross-asset-research-mandate-v5",
            "cross-asset-research-mandate-v6",
            "cross-asset-research-mandate-v7",
        }:
            if token_policy.get("allowed_environment_variables") != expected_token:
                raise CrossAssetContextError("A1 token environment allowlist changed")
            if token_policy.get("allowed_purpose") != expected_purpose:
                raise CrossAssetContextError("A1 token purpose changed")
            for key in (
                "broker_or_exchange_tokens_allowed",
                "database_or_message_bus_tokens_allowed",
                "may_be_logged_or_serialized",
                "repository_storage_allowed",
                "runtime_order_or_signal_access_allowed",
            ):
                if token_policy.get(key) is not False:
                    raise CrossAssetContextError(f"unsafe A1 token policy: {key}")
    if schema == "cross-asset-research-mandate-v4":
        scope = payload.get("execution_scope", {})
        if scope.get("listed_futures_data_research_authorized") is not True:
            raise CrossAssetContextError("v4 must explicitly authorize futures data research")
        if scope.get("derivatives_execution_authorized") is not False:
            raise CrossAssetContextError("v4 cannot authorize derivatives execution")
        if scope.get("approved_execution_instrument_ids") != []:
            raise CrossAssetContextError("v4 cannot approve execution instruments")
        if tuple(scope.get("candidate_futures", ())) != ("MES", "MGC", "MCL", "M6E", "MTN"):
            raise CrossAssetContextError("v4 futures candidate set changed")
    if schema == "cross-asset-research-mandate-v5":
        scope = payload.get("execution_scope", {})
        if tuple(scope.get("candidate_oanda_instruments", ())) != (
            "SPX500_USD",
            "XAU_USD",
            "WTICO_USD",
            "EUR_USD",
            "USB10Y_USD",
        ):
            raise CrossAssetContextError("v5 OANDA candidate set changed")
        if scope.get("oanda_data_research_authorized") is not True:
            raise CrossAssetContextError("v5 must authorize OANDA data research")
        if scope.get("oanda_execution_authorized") is not False:
            raise CrossAssetContextError("v5 cannot authorize OANDA execution")
        if scope.get("approved_execution_instrument_ids") != []:
            raise CrossAssetContextError("v5 cannot approve execution instruments")
    if schema == "cross-asset-research-mandate-v6":
        scope = payload.get("execution_scope", {})
        if tuple(scope.get("candidate_oanda_instruments", ())) != (
            "SPX500_USD",
            "NAS100_USD",
            "DE30_EUR",
            "UK100_GBP",
            "XAU_USD",
            "EUR_USD",
            "USD_JPY",
        ):
            raise CrossAssetContextError("v6 OANDA hourly candidate set changed")
        if scope.get("oanda_data_research_authorized") is not True:
            raise CrossAssetContextError("v6 must authorize OANDA data research")
        if scope.get("oanda_execution_authorized") is not False:
            raise CrossAssetContextError("v6 cannot authorize OANDA execution")
        if scope.get("approved_execution_instrument_ids") != []:
            raise CrossAssetContextError("v6 cannot approve execution instruments")
    if schema == "cross-asset-research-mandate-v7":
        scope = payload.get("execution_scope", {})
        if tuple(scope.get("research_candidate_oanda_instruments", ())) != (
            "SPX500_USD",
            "NAS100_USD",
            "DE30_EUR",
            "UK100_GBP",
            "XAU_USD",
            "EUR_USD",
            "USD_JPY",
        ):
            raise CrossAssetContextError("v7 OANDA strategy universe changed")
        if scope.get("conversion_only_oanda_instruments") != ["GBP_USD"]:
            raise CrossAssetContextError("v7 GBP conversion-only input changed")
        if scope.get("simulated_research_directions") != ["long", "short"]:
            raise CrossAssetContextError("v7 simulated research directions changed")
        if (
            scope.get("oanda_execution_authorized") is not False
            or scope.get("shorting_authorized_for_execution") is not False
            or scope.get("approved_execution_instrument_ids") != []
        ):
            raise CrossAssetContextError("v7 cannot authorize execution")
    if authority.get("maximum_live_allocation_gbp") != 0:
        raise CrossAssetContextError("maximum live allocation must be zero")
    capital = payload.get("capital", {})
    if capital.get("research_equity_gbp") != 20_000:
        raise CrossAssetContextError("research equity must be GBP 20,000")
    if capital.get("soft_drawdown_stop_fraction") != 0.12:
        raise CrossAssetContextError("soft drawdown stop must be 12 percent")
    if capital.get("hard_drawdown_ceiling_fraction") != 0.20:
        raise CrossAssetContextError("hard drawdown ceiling must be 20 percent")
    if capital.get("soft_equity_floor_gbp") != 17_600:
        raise CrossAssetContextError("soft equity floor must be GBP 17,600")
    if capital.get("hard_equity_floor_gbp") != 16_000:
        raise CrossAssetContextError("hard equity floor must be GBP 16,000")
    objective = payload.get("objective", {})
    if objective.get("stretch_annualized_return_fraction") != 0.50:
        raise CrossAssetContextError("the recorded stretch objective must be 50 percent")
    if objective.get("stretch_return_is_acceptance_gate") is not False:
        raise CrossAssetContextError("stretch return cannot be an acceptance gate")
    risk = payload.get("risk", {})
    if risk.get("minimum_planned_risk_per_position_fraction") != 0.0025:
        raise CrossAssetContextError("minimum planned position-risk bound changed")
    if risk.get("maximum_planned_risk_per_position_fraction") != 0.005:
        raise CrossAssetContextError("maximum planned position-risk bound changed")
    if risk.get("protective_exits_remain_enabled") is not True:
        raise CrossAssetContextError("protective exits must remain enabled")
    if schema != "cross-asset-research-mandate-v7" and risk.get("a0_maximum_gross_exposure_fraction") != 0:
        raise CrossAssetContextError("A0 gross exposure must remain zero")
    jurisdiction = payload.get("jurisdiction", {})
    if jurisdiction.get("planning_default") != "UK_retail":
        raise CrossAssetContextError("UK retail must remain the conservative planning default")
    if jurisdiction.get("residency_may_not_be_selected_to_bypass_rules") is not True:
        raise CrossAssetContextError("jurisdiction anti-bypass rule is required")


def _validate_access_matrix(payload: Mapping[str, Any]) -> None:
    schema = payload.get("schema_version")
    if schema == "cross-asset-instrument-access-v4":
        if payload.get("default_planning_jurisdiction") != "UK_retail":
            raise CrossAssetContextError("hourly instrument matrix must default to UK retail")
        if payload.get("approved_execution_instruments") != []:
            raise CrossAssetContextError("hourly A1 cannot approve execution instruments")
        if payload.get("jurisdiction_selection_policy", {}).get("anti_circumvention") is not True:
            raise CrossAssetContextError("hourly instrument matrix must prohibit circumvention")
        candidates = payload.get("research_candidates")
        expected = (
            "SPX500_USD",
            "NAS100_USD",
            "DE30_EUR",
            "UK100_GBP",
            "XAU_USD",
            "EUR_USD",
            "USD_JPY",
        )
        if not isinstance(candidates, list) or tuple(
            item.get("instrument_id") for item in candidates
        ) != expected:
            raise CrossAssetContextError("hourly A1 research candidates changed")
        if any(item.get("execution_state") != "conditional_unapproved" for item in candidates):
            raise CrossAssetContextError("hourly candidates cannot be execution-approved")
        if any(
            item.get("research_data_state") != "hourly_bid_ask_qualified_with_no_trade_mask"
            for item in candidates
        ):
            raise CrossAssetContextError("hourly candidate data state changed")
        return
    if schema == "cross-asset-instrument-access-v3":
        if payload.get("default_planning_jurisdiction") != "UK_retail":
            raise CrossAssetContextError("OANDA instrument matrix must default to UK retail")
        if payload.get("approved_execution_instruments") != []:
            raise CrossAssetContextError("OANDA A1 cannot approve execution instruments")
        if payload.get("jurisdiction_selection_policy", {}).get("anti_circumvention") is not True:
            raise CrossAssetContextError("OANDA instrument matrix must prohibit circumvention")
        candidates = payload.get("research_candidates")
        if not isinstance(candidates, list) or tuple(
            item.get("instrument_id") for item in candidates
        ) != ("SPX500_USD", "XAU_USD", "WTICO_USD", "EUR_USD", "USB10Y_USD"):
            raise CrossAssetContextError("OANDA A1 research candidates changed")
        if any(item.get("execution_state") != "conditional_unapproved" for item in candidates):
            raise CrossAssetContextError("OANDA candidates cannot be execution-approved")
        blocked = {
            item.get("instrument_id")
            for item in candidates
            if item.get("economic_evaluation_state")
            == "blocked_pending_historical_continuous_financing"
        }
        if blocked != {"WTICO_USD", "USB10Y_USD"}:
            raise CrossAssetContextError("OANDA continuous-financing blockers changed")
        return
    if schema == "cross-asset-instrument-access-v2":
        if payload.get("default_planning_jurisdiction") != "UK_retail":
            raise CrossAssetContextError("instrument matrix must default to UK retail")
        if payload.get("approved_execution_instruments") != []:
            raise CrossAssetContextError("A1 cannot approve execution instruments")
        if payload.get("jurisdiction_selection_policy", {}).get("anti_circumvention") is not True:
            raise CrossAssetContextError("instrument matrix must prohibit jurisdiction circumvention")
        candidates = payload.get("research_candidates")
        if not isinstance(candidates, list) or tuple(item.get("instrument_id") for item in candidates) != (
            "MES", "MGC", "MCL", "M6E", "MTN"
        ):
            raise CrossAssetContextError("A1 futures research candidates changed")
        if any(item.get("execution_state") != "conditional_unapproved" for item in candidates):
            raise CrossAssetContextError("futures candidates cannot be execution-approved")
        return
    if schema != "cross-asset-instrument-access-v1":
        raise CrossAssetContextError("unsupported instrument-access schema")
    if payload.get("default_planning_jurisdiction") != "UK_retail":
        raise CrossAssetContextError("instrument matrix must default to UK retail")
    if payload.get("approved_execution_instruments") != []:
        raise CrossAssetContextError("A0 must not approve execution instruments")
    jurisdictions = payload.get("jurisdictions")
    if not isinstance(jurisdictions, list) or {item.get("jurisdiction_id") for item in jurisdictions} != {
        "Malaysia_retail_alternative",
        "UK_retail",
    }:
        raise CrossAssetContextError("UK and Malaysia retail access records are required")
    for jurisdiction in jurisdictions:
        _utc(jurisdiction.get("observed_at"), "jurisdiction observed_at")
        products = jurisdiction.get("product_access")
        if not isinstance(products, list) or not products:
            raise CrossAssetContextError("each jurisdiction requires product access records")
        for product in products:
            if product.get("execution_state") not in {
                "blocked",
                "conditional_unapproved",
                "research_only",
            }:
                raise CrossAssetContextError("A0 product access cannot be approved")
            if product.get("product_family") == "crypto_derivatives" and product.get(
                "execution_state"
            ) != "blocked":
                raise CrossAssetContextError("retail crypto derivatives must remain blocked in A0")
    if payload.get("jurisdiction_selection_policy", {}).get("anti_circumvention") is not True:
        raise CrossAssetContextError("instrument matrix must prohibit jurisdiction circumvention")


def _validate_data_contract(payload: Mapping[str, Any]) -> None:
    schema = payload.get("schema_version")
    if schema == "cross-asset-data-contract-v6":
        if payload.get("contract_id") != "cross-asset-data-qualification-a3-v6":
            raise CrossAssetContextError("unexpected A3 data contract ID")
        if payload.get("bulk_download_authorized") is not False or payload.get(
            "strategy_evaluation_authorized"
        ) is not False:
            raise CrossAssetContextError("rejected A3 cannot authorize data or strategy work")
        a3 = payload.get("a3_result_policy", {})
        if (
            a3.get("result") != "rejected_do_not_tune_or_rerun"
            or a3.get("accepted_strategy_arms") != []
            or a3.get("prospective_partition_accessed") is not False
        ):
            raise CrossAssetContextError("A3 rejection boundary changed")
        boundary = payload.get("evidence_boundary", {})
        if (
            boundary.get("prospective_prices_available") is not False
            or boundary.get("genuinely_prospective_collection_not_started") is not True
            or boundary.get("genuinely_prospective_start") != "2026-08-31T00:00:00Z"
        ):
            raise CrossAssetContextError("A3 prospective boundary changed")
        next_family = payload.get("next_family_policy", {})
        if (
            next_family.get("a4_or_a5_activation_allowed") is not False
            or next_family.get("materially_new_hypothesis_and_experiment_id_required") is not True
            or next_family.get("program_amendment_and_user_authorization_required") is not True
            or next_family.get("rejected_family_regime_rescue_allowed") is not False
        ):
            raise CrossAssetContextError("post-A3 research boundary changed")
        if payload.get("gap_policy", {}).get("incomplete_session_window") != "no_trade":
            raise CrossAssetContextError("A3 incomplete windows must remain no_trade")
        return
    if schema == "cross-asset-data-contract-v5":
        if payload.get("contract_id") != "cross-asset-data-qualification-a2-v5":
            raise CrossAssetContextError("unexpected A2 data contract ID")
        if payload.get("bulk_download_authorized") is not False or payload.get(
            "strategy_evaluation_authorized"
        ) is not False:
            raise CrossAssetContextError("rejected A2 cannot authorize data or strategy work")
        sources = payload.get("accepted_sources")
        if not isinstance(sources, list) or tuple(item.get("qualification") for item in sources) != (
            "daily_bid_ask_context_only",
            "hourly_bid_ask_intraday_research_with_no_trade_masks",
            "gbp_conversion_only_never_a_strategy_instrument",
        ):
            raise CrossAssetContextError("A2 source lineage changed")
        result = payload.get("a2_result_policy", {})
        if (
            result.get("result") != "rejected_do_not_tune_or_rerun"
            or result.get("final_partition_clean_for_a2") is not False
            or result.get("final_partition_economic_metrics_computed") is not False
        ):
            raise CrossAssetContextError("A2 rejection or final-boundary policy changed")
        a3 = payload.get("a3_prerequisites", {})
        for key in (
            "genuinely_prospective_final_evidence_required",
            "new_experiment_id_required",
            "timestamp_only_prepartitioning_before_price_evaluation_required",
        ):
            if a3.get(key) is not True:
                raise CrossAssetContextError(f"A3 prerequisite missing: {key}")
        if a3.get("matching_a2_partitions_allowed") is not False:
            raise CrossAssetContextError("A3 cannot reuse the contaminated A2 partition rule")
        if payload.get("gap_policy", {}).get("incomplete_session_window") != "no_trade":
            raise CrossAssetContextError("A2/A3 incomplete windows must remain no_trade")
        if payload.get("timestamp_policy", {}).get("naive_timestamps") != "reject":
            raise CrossAssetContextError("A2/A3 timestamps must fail closed")
        return
    if schema == "cross-asset-data-contract-v4":
        if payload.get("contract_id") != "cross-asset-data-qualification-a1-v4":
            raise CrossAssetContextError("unexpected hourly A1 data contract ID")
        if payload.get("bulk_download_authorized") is not False:
            raise CrossAssetContextError("completed A1 cannot authorize another bulk download")
        if payload.get("strategy_evaluation_authorized") is not False:
            raise CrossAssetContextError("A1 cannot directly authorize strategy evaluation")
        if (
            payload.get(
                "strategy_evaluation_may_be_authorized_only_by_separately_frozen_a2_or_a3_contract"
            )
            is not True
        ):
            raise CrossAssetContextError("later strategy evaluation requires a frozen contract")
        sources = payload.get("accepted_sources")
        if not isinstance(sources, list) or tuple(
            item.get("qualification") for item in sources
        ) != (
            "daily_bid_ask_context_only",
            "hourly_bid_ask_intraday_research_with_no_trade_masks",
        ):
            raise CrossAssetContextError("hourly source qualification lineage changed")
        policy = payload.get("intraday_policy", {})
        if policy.get("availability_masks_required") is not True:
            raise CrossAssetContextError("hourly availability masks are required")
        if policy.get("positions_must_be_flat_before_17_00_America_New_York") is not True:
            raise CrossAssetContextError("hourly financing boundary is missing")
        if policy.get("commodity_and_bond_cfds_eligible_without_historical_financing") is not False:
            raise CrossAssetContextError("commodity/bond financing cannot be bypassed")
        if payload.get("gap_policy", {}).get("incomplete_session_window") != "no_trade":
            raise CrossAssetContextError("incomplete hourly windows must be no_trade")
        oanda = payload.get("oanda_source_policy", {})
        if oanda.get("hourly_bid_ask_source_qualification_passed") is not True:
            raise CrossAssetContextError("hourly source pass is missing")
        if oanda.get("oil_and_bond_economic_evaluation_allowed") is not False:
            raise CrossAssetContextError("oil and bond CFDs must remain excluded")
        if oanda.get("sealed_2026_price_accessed") is not False:
            raise CrossAssetContextError("sealed 2026 prices cannot be accessed")
        required = payload.get("required_fields_by_instrument_type", {})
        if set(required) != {"index_cfd", "spot_fx", "spot_metal"} or any(
            "availability_mask" not in fields for fields in required.values()
        ):
            raise CrossAssetContextError("hourly instrument data requirements changed")
        timestamps = payload.get("timestamp_policy", {})
        if timestamps.get("timezone") != "UTC" or timestamps.get("naive_timestamps") != "reject":
            raise CrossAssetContextError("hourly data timestamps must be explicit UTC")
        return
    if schema == "cross-asset-data-contract-v3":
        if payload.get("contract_id") != "cross-asset-data-qualification-a1-v3":
            raise CrossAssetContextError("unexpected OANDA A1 data contract ID")
        if payload.get("bulk_download_authorized") is not False:
            raise CrossAssetContextError("OANDA A1 cannot authorize an unfrozen bulk download")
        if payload.get("strategy_evaluation_authorized") is not False:
            raise CrossAssetContextError("OANDA A1 cannot authorize strategy evaluation")
        sources = payload.get("accepted_sources")
        if not isinstance(sources, list) or len(sources) != 1:
            raise CrossAssetContextError("OANDA daily source qualification is missing")
        if sources[0].get("qualification") != "daily_bid_ask_source_pilot_only":
            raise CrossAssetContextError("OANDA source qualification was overstated")
        policy = payload.get("intraday_successor_policy", {})
        if policy.get("positions_must_be_flat_before_17_00_America_New_York") is not True:
            raise CrossAssetContextError("OANDA intraday financing boundary is missing")
        if policy.get("commodity_and_bond_cfds_eligible_without_historical_financing") is not False:
            raise CrossAssetContextError("OANDA commodity/bond financing cannot be bypassed")
        if policy.get("historical_hourly_bid_ask_pilot_required") is not True:
            raise CrossAssetContextError("OANDA hourly source pilot is required")
        oanda = payload.get("oanda_source_policy", {})
        if oanda.get("broker_native_prices_may_be_relabelled_as_exchange_futures") is not False:
            raise CrossAssetContextError("OANDA prices cannot be relabelled as futures")
        if oanda.get("historical_financing_series_available") is not False:
            raise CrossAssetContextError("unavailable OANDA financing history was invented")
        required = payload.get("required_fields_by_instrument_type", {})
        if set(required) != {"bond_cfd", "commodity_cfd", "index_cfd", "spot_fx", "spot_metal"}:
            raise CrossAssetContextError("OANDA instrument data requirements changed")
        timestamps = payload.get("timestamp_policy", {})
        if timestamps.get("timezone") != "UTC" or timestamps.get("naive_timestamps") != "reject":
            raise CrossAssetContextError("OANDA data timestamps must be explicit UTC")
        return
    if schema == "cross-asset-data-contract-v2":
        if payload.get("contract_id") != "cross-asset-data-qualification-a1-v2":
            raise CrossAssetContextError("unexpected A1 data contract ID")
        if payload.get("accepted_sources") != [] or payload.get("bulk_download_authorized") is not False:
            raise CrossAssetContextError("A1 v2 cannot pre-accept a source or bulk download")
        if payload.get("strategy_evaluation_authorized") is not False:
            raise CrossAssetContextError("A1 v2 cannot authorize strategy evaluation")
        required = payload.get("required_fields_by_instrument_type", {})
        if set(required) != {"cash", "future", "listed_fund"} or any(not value for value in required.values()):
            raise CrossAssetContextError("A1 v2 instrument data requirements changed")
        futures = payload.get("futures_policy", {})
        for key in (
            "exact_expiry_rows_required",
            "parent_history_is_mechanism_evidence_only",
            "roll_uses_prior_completed_session_only",
        ):
            if futures.get(key) is not True:
                raise CrossAssetContextError(f"missing futures data gate: {key}")
        for key in ("parent_history_may_prove_micro_execution", "vendor_adjusted_continuous_series_allowed"):
            if futures.get(key) is not False:
                raise CrossAssetContextError(f"unsafe futures data policy: {key}")
        if futures.get("forced_roll_sessions_before_delivery_risk") != 5:
            raise CrossAssetContextError("futures delivery buffer changed")
        if payload.get("cost_and_cashflow_policy", {}).get("round_trip_implicit_cost_bps") != [10, 30, 80]:
            raise CrossAssetContextError("A1 v2 cost scenarios changed")
        timestamps = payload.get("timestamp_policy", {})
        if timestamps.get("timezone") != "UTC" or timestamps.get("naive_timestamps") != "reject":
            raise CrossAssetContextError("data timestamps must be explicit UTC and fail closed")
        return
    if schema != "cross-asset-data-contract-v1":
        raise CrossAssetContextError("unsupported cross-asset data schema")
    if payload.get("contract_id") != "cross-asset-data-feasibility-a0-v1":
        raise CrossAssetContextError("unexpected data contract ID")
    if payload.get("accepted_sources") != []:
        raise CrossAssetContextError("A0 cannot accept a market-data source")
    if payload.get("bulk_download_authorized") is not False:
        raise CrossAssetContextError("A0 cannot authorize bulk downloads")
    if payload.get("strategy_evaluation_authorized") is not False:
        raise CrossAssetContextError("A0 cannot authorize strategy evaluation")
    requirements = payload.get("required_fields_by_instrument_type")
    if not isinstance(requirements, dict):
        raise CrossAssetContextError("instrument-specific data requirements are missing")
    for key in ("cash", "crypto_spot", "listed_fund", "fx", "future", "perpetual"):
        if key not in requirements or not requirements[key]:
            raise CrossAssetContextError(f"missing data requirements for {key}")
    timestamps = payload.get("timestamp_policy", {})
    if timestamps.get("timezone") != "UTC" or timestamps.get("naive_timestamps") != "reject":
        raise CrossAssetContextError("data timestamps must be explicit UTC and fail closed")
    if payload.get("point_in_time_universe", {}).get("current_survivors_as_history") != "reject":
        raise CrossAssetContextError("current-survivor universes must be rejected")


def _validate_futures_specs(payload: Mapping[str, Any]) -> None:
    if payload.get("schema_version") != "cross-asset-futures-spec-registry-v1":
        raise CrossAssetContextError("unsupported futures-spec registry schema")
    if payload.get("status") != "incomplete_no_instrument_qualified":
        raise CrossAssetContextError("futures-spec registry cannot imply qualification")
    if payload.get("approved_execution_instruments") != []:
        raise CrossAssetContextError("futures-spec registry cannot approve execution")
    instruments = payload.get("instruments")
    expected = (
        ("MES", "ES", "2019-05-06", "2009-10-05", "2025-12-31", "XCME"),
        ("MGC", "GC", "2010-10-04", "2009-10-05", "2025-12-31", "XCEC"),
        ("MCL", "CL", "2021-07-12", "2009-10-05", "2025-12-31", "XNYM"),
        ("M6E", "6E", "2009-10-05", "2009-10-05", "2025-12-31", "XCME"),
        ("MTN", "TN", "2024-03-25", "2016-01-11", "2025-12-31", "XCBT"),
    )
    if not isinstance(instruments, list) or tuple(
        (
            item.get("micro_root"),
            item.get("parent_root"),
            item.get("micro_usable_start"),
            item.get("parent_usable_start"),
            item.get("usable_end"),
            item.get("venue_mic"),
        )
        for item in instruments
    ) != expected:
        raise CrossAssetContextError("futures-spec registry universe or boundary changed")
    if any(item.get("execution_state") != "conditional_unapproved" for item in instruments):
        raise CrossAssetContextError("futures-spec registry cannot approve a candidate")
    if any(
        not str(item.get("contract_terms_state", "")).startswith(
            ("qualified_", "blocked_", "pending_")
        )
        for item in instruments
    ):
        raise CrossAssetContextError("futures contract-term state is invalid")
    bridge = payload.get("parent_bridge_policy", {})
    if bridge != {
        "exact_micro_history_required_for_executable_evaluation": True,
        "parent_history_is_mechanism_evidence_only": True,
        "parent_history_may_prove_micro_execution": False,
    }:
        raise CrossAssetContextError("unsafe parent-to-micro bridge policy")


def _validate_futures_source_comparison(payload: Mapping[str, Any]) -> None:
    if payload.get("schema_version") != "cross-asset-futures-source-comparison-v1":
        raise CrossAssetContextError("unsupported futures-source comparison schema")
    if payload.get("status") != "blocked_pending_exact_quotes":
        raise CrossAssetContextError("futures-source comparison must remain quote-blocked")
    if payload.get("selected_provider_id") is not None:
        raise CrossAssetContextError("a futures provider cannot be selected before exact quotes")
    if payload.get("automatic_purchase_allowed") is not False:
        raise CrossAssetContextError("automatic futures-data purchase is prohibited")
    if payload.get("user_approval_required_before_purchase") is not True:
        raise CrossAssetContextError("futures-data purchase requires user approval")
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or tuple(item.get("provider_id") for item in candidates) != (
        "cme_datamine",
        "databento",
    ):
        raise CrossAssetContextError("futures-source candidates changed")
    if any(
        item.get("coverage_quote_state") != "pending_exact_quote"
        or item.get("gate_results") != {}
        or item.get("twelve_month_tco") is not None
        for item in candidates
    ):
        raise CrossAssetContextError("unverified futures-source result was recorded")
    if payload.get("required_gates") != [
        "authorized_distribution",
        "contract_definitions",
        "exact_boundary_coverage",
        "final_settlements",
        "private_research_retention",
        "publication_timestamps",
        "reproducible_retrieval",
    ]:
        raise CrossAssetContextError("futures-source gates changed")
    rule = payload.get("selection_rule", {})
    if rule.get("databento_discount_must_exceed_fraction") != "0.10":
        raise CrossAssetContextError("futures-source tie threshold changed")
    if rule.get("every_gate_must_pass") is not True:
        raise CrossAssetContextError("futures-source gates cannot be bypassed")


def _validate_a1_contract(payload: Mapping[str, Any]) -> None:
    if payload.get("schema_version") == "cross-asset-a1-oanda-hourly-history-amendment-v1":
        if (
            payload.get("experiment_id") != "cross-asset-a1-oanda-hourly-history-v2"
            or payload.get("supersedes") != "cross-asset-a1-oanda-hourly-history-v1"
            or payload.get("status") != "frozen"
        ):
            raise CrossAssetContextError("unexpected or unfrozen hourly OANDA successor")
        if payload.get("changes_from_predecessor") != {
            "candidate_pass_requires_complete_session_days_at_least": 3000,
            "candidate_pass_requires_history_edges_and_no_gap_over_hours": 168,
            "every_incomplete_session_date_disposition": "no_trade",
            "incomplete_session_fraction_is_reported_not_a_source_rejection_gate": True,
            "new_provider_requests_allowed": False,
            "output_artifact_root": "artifacts/agent-level-experiment/cross-asset/a1-oanda-hourly-history-v2",
            "price_rows_may_be_changed_or_filled": False,
            "raw_and_normalized_predecessor_reuse_required": True,
        }:
            raise CrossAssetContextError("hourly OANDA successor changes are not minimal")
        if set(payload.get("frozen_predecessor_evidence", {})) != {
            "audit_report",
            "evidence_manifest",
            "source_manifest",
        }:
            raise CrossAssetContextError("hourly OANDA successor lineage is incomplete")
        return
    if payload.get("schema_version") == "cross-asset-a1-oanda-source-pilot-amendment-v1":
        if payload.get("experiment_id") != "cross-asset-a1-oanda-source-pilot-v2":
            raise CrossAssetContextError("unexpected OANDA successor experiment")
        if payload.get("supersedes") != "cross-asset-a1-oanda-source-pilot-v1":
            raise CrossAssetContextError("OANDA successor lineage changed")
        if payload.get("status") != "frozen":
            raise CrossAssetContextError("OANDA successor must be frozen")
        changes = payload.get("changes_from_predecessor", {})
        if changes != {
            "new_provider_requests_allowed": False,
            "output_artifact_root": "artifacts/agent-level-experiment/cross-asset/a1-oanda-source-pilot-v2",
            "raw_source_reuse_required": True,
            "wtico_excluded_presegment_end": "2005-11-27T22:00:00Z",
            "wtico_usable_segment_start_inclusive": "2005-11-27T22:00:00Z",
        }:
            raise CrossAssetContextError("OANDA successor changes are not minimal")
        evidence = payload.get("frozen_predecessor_evidence", {})
        if set(evidence) != {"audit_report", "evidence_manifest", "source_manifest"}:
            raise CrossAssetContextError("OANDA successor evidence lineage is incomplete")
        return
    if payload.get("schema_version") == "cross-asset-a1-lse-futures-expansion-contract-v1":
        if payload.get("experiment_id") != "cross-asset-a1-lse-futures-expansion-v1" or payload.get("status") != "frozen":
            raise CrossAssetContextError("unexpected or unfrozen A1 expansion contract")
        if tuple(item.get("symbol") for item in payload.get("listed_funds", ())) != ("SWDA", "VAGS", "SGLN", "COMM"):
            raise CrossAssetContextError("A1 expansion LSE universe changed")
        if tuple(item.get("micro_root") for item in payload.get("listed_futures", ())) != ("MES", "MGC", "MCL", "M6E", "MTN"):
            raise CrossAssetContextError("A1 expansion futures universe changed")
        if payload.get("futures_source_comparison", {}).get("automatic_purchase_allowed") is not False:
            raise CrossAssetContextError("A1 expansion cannot purchase data automatically")
        for key, value in payload.get("prohibitions", {}).items():
            if value is not False:
                raise CrossAssetContextError(f"unsafe A1 expansion permission: {key}")
        return
    if (
        payload.get("schema_version")
        == "cross-asset-a1-exact-lse-boundary-clarification-contract-v1"
    ):
        if (
            payload.get("review_id") != "cross-asset-a1-executable-universe-feasibility-v2"
            or payload.get("status") != "frozen"
        ):
            raise CrossAssetContextError("unexpected or unfrozen LSE boundary clarification")
        expected = (
            ("SWDA", "SWDA:LSE", "IE00B4L5Y983", "XLON", "GBp", "0.01"),
            ("VAGS", "VAGS:LSE", "IE00BG47K971", "XLON", "GBP", "1"),
            ("SGLN", "SGLN:LSE", "IE00B4ND3602", "XLON", "GBp", "0.01"),
            ("COMM", "COMM:LSE", "IE00BDFL4P12", "XLON", "GBp", "0.01"),
        )
        instruments = payload.get("expected_instruments")
        if not isinstance(instruments, list) or tuple(
            (
                item.get("symbol"),
                item.get("provider_symbol"),
                item.get("expected_isin"),
                item.get("expected_mic"),
                item.get("expected_currency"),
                item.get("price_to_gbp_multiplier"),
            )
            for item in instruments
        ) != expected:
            raise CrossAssetContextError("LSE boundary-clarification universe changed")
        plan = payload.get("request_plan", {})
        if (
            plan.get("maximum_requests"),
            plan.get("maximum_weighted_credits"),
            plan.get("minute_credit_ceiling"),
            plan.get("start_date_inclusive"),
            plan.get("end_date_exclusive"),
        ) != (4, 4, 55, "2025-02-03", "2025-03-01"):
            raise CrossAssetContextError("LSE boundary-clarification request boundary changed")
        boundary = payload.get("evidence_boundary", {})
        if boundary.get("preceding_evidence") != {
            "path": "artifacts/agent-level-experiment/cross-asset/a1-executable-universe-feasibility-v1/evidence-manifest.json",
            "sha256": "eb4608c913843167f9a0e54482e509dda56238ea3131727fc631276c045f7d78",
        }:
            raise CrossAssetContextError("LSE boundary-clarification evidence lineage changed")
        if boundary.get("sealed_2026_partition_accessed") is not False:
            raise CrossAssetContextError("LSE boundary clarification cannot access sealed 2026")
        reuse = payload.get("reuse_policy", {})
        if (
            reuse.get("allowed_endpoints")
            != ["dividends", "earliest_timestamp", "splits"]
            or reuse.get("raw_bytes_may_be_modified") is not False
        ):
            raise CrossAssetContextError("LSE boundary-clarification reuse policy changed")
        for key, value in payload.get("prohibitions", {}).items():
            if value is not False:
                raise CrossAssetContextError(
                    f"unsafe LSE boundary-clarification permission: {key}"
                )
        return
    if (
        payload.get("schema_version")
        == "cross-asset-a1-executable-universe-feasibility-contract-v1"
    ):
        if (
            payload.get("review_id") != "cross-asset-a1-executable-universe-feasibility-v1"
            or payload.get("status") != "frozen"
        ):
            raise CrossAssetContextError("unexpected or unfrozen executable-universe review")
        cash = payload.get("candidate_paths", {}).get("exact_lse_cash", {})
        expected = (
            ("SWDA", "SWDA:LSE", "IE00B4L5Y983", "XLON", "GBp", "0.01"),
            ("VAGS", "VAGS:LSE", "IE00BG47K971", "XLON", "GBP", "1"),
            ("SGLN", "SGLN:LSE", "IE00B4ND3602", "XLON", "GBp", "0.01"),
            ("COMM", "COMM:LSE", "IE00BDFL4P12", "XLON", "GBp", "0.01"),
        )
        instruments = cash.get("expected_instruments")
        if not isinstance(instruments, list) or tuple(
            (
                item.get("symbol"),
                item.get("provider_symbol"),
                item.get("expected_isin"),
                item.get("expected_mic"),
                item.get("expected_currency"),
                item.get("price_to_gbp_multiplier"),
            )
            for item in instruments
        ) != expected:
            raise CrossAssetContextError("executable-universe exact LSE set changed")
        plan = cash.get("request_plan", {})
        if (
            plan.get("maximum_requests"),
            plan.get("maximum_weighted_credits"),
            plan.get("minute_credit_ceiling"),
        ) != (16, 168, 55):
            raise CrossAssetContextError("executable-universe request budget changed")
        derivative_symbols = tuple(
            item.get("symbol")
            for item in payload.get("candidate_paths", {})
            .get("broader_derivatives_and_fx", {})
            .get("candidates", ())
        )
        if derivative_symbols != ("MES", "MGC", "MCL", "GBP/USD", "EUR/USD", "BTC-ETH"):
            raise CrossAssetContextError("broader feasibility candidate set changed")
        rules = payload.get("decision_rules", {})
        if rules.get("active_subscription_use_is_sufficient_for_current_research") is not True:
            raise CrossAssetContextError("active-subscription research rule is missing")
        for key in (
            "cash_path_failure_automatically_accepts_derivatives",
            "economic_proxy_can_replace_exact_execution_line",
            "full_history_download_authorized_by_this_review",
            "headline_return_can_select_universe",
            "strategy_evaluation_authorized",
        ):
            if rules.get(key) is not False:
                raise CrossAssetContextError(f"unsafe executable-universe rule: {key}")
        boundary = payload.get("evidence_boundary", {})
        if boundary.get("preceding_evidence") != {
            "path": "artifacts/agent-level-experiment/cross-asset/a1-ibkr-contract-details-public-review-v1/evidence-manifest.json",
            "sha256": "91af46ef7afa3f0f4fb2332f22cd0ab0cb8dffcbac8daf023b5cea2bb2f7471a",
        }:
            raise CrossAssetContextError("executable-universe evidence lineage changed")
        if boundary.get("sealed_2026_partition_accessed") is not False:
            raise CrossAssetContextError("executable-universe review cannot access sealed 2026")
        for key, value in payload.get("prohibitions", {}).items():
            if value is not False:
                raise CrossAssetContextError(f"unsafe executable-universe permission: {key}")
        return
    if (
        payload.get("schema_version")
        == "cross-asset-a1-ibkr-contract-details-public-review-contract-v1"
    ):
        if (
            payload.get("review_id")
            != "cross-asset-a1-ibkr-contract-details-public-review-v1"
            or payload.get("status") != "frozen"
        ):
            raise CrossAssetContextError("unexpected or unfrozen IBKR contract-details review")
        expected = (
            ("SWDA", "IE00B4L5Y983", "XLON", "GBX"),
            ("VAGS", "IE00BG47K971", "XLON", "GBP"),
            ("SGLN", "IE00B4ND3602", "XLON", "GBX"),
            ("COMM", "IE00BDFL4P12", "XLON", "GBX"),
        )
        instruments = payload.get("expected_instruments")
        if not isinstance(instruments, list) or tuple(
            (item.get("symbol"), item.get("isin"), item.get("mic"), item.get("trading_currency"))
            for item in instruments
        ) != expected:
            raise CrossAssetContextError("IBKR contract-details universe changed")
        boundary = payload.get("evidence_boundary", {})
        if boundary.get("account_verification") != {
            "path": "artifacts/agent-level-experiment/cross-asset/a1-account-instrument-verification-v1/evidence-manifest.json",
            "sha256": "ecbafc21e6678b50a4c564f201153f04cb6bbf4c18305f1f68d7c92b2d878883",
        }:
            raise CrossAssetContextError("IBKR contract-details evidence lineage changed")
        if boundary.get("sealed_2026_partition_accessed") is not False:
            raise CrossAssetContextError("IBKR contract-details review cannot access sealed 2026")
        rules = payload.get("decision_rules", {})
        for key in (
            "economic_similarity_can_replace_exact_instrument",
            "public_source_can_approve_account_access_without_authenticated_evidence",
            "strategy_or_price_evidence_can_repair_identity_failure",
        ):
            if rules.get(key) is not False:
                raise CrossAssetContextError(f"unsafe IBKR contract-details rule: {key}")
        for key in (
            "account_result_plus_official_lineage_can_verify_exact_line",
            "gbp_or_gbpence_display_normalization_requires_official_support",
            "ibkr_lseetf_to_xlon_mapping_requires_official_support",
        ):
            if rules.get(key) is not True:
                raise CrossAssetContextError(f"missing IBKR contract-details gate: {key}")
        if set(payload.get("gates", {})) != {
            "broker_exchange_mapping",
            "currency",
            "issuer_identity",
            "listing_identity",
        }:
            raise CrossAssetContextError("IBKR contract-details gates changed")
        for key, value in payload.get("prohibitions", {}).items():
            if value is not False:
                raise CrossAssetContextError(f"unsafe IBKR contract-details permission: {key}")
        return
    if payload.get("schema_version") == "cross-asset-a1-account-instrument-verification-contract-v1":
        if (
            payload.get("experiment_id")
            != "cross-asset-a1-account-instrument-verification-v1"
            or payload.get("status") != "frozen"
        ):
            raise CrossAssetContextError("unexpected or unfrozen A1 account verification")
        expected_instruments = (
            ("SWDA", "IE00B4L5Y983", "XLON", "GBX"),
            ("VAGS", "IE00BG47K971", "XLON", "GBP"),
            ("SGLN", "IE00B4ND3602", "XLON", "GBX"),
            ("COMM", "IE00BDFL4P12", "XLON", "GBX"),
        )
        instruments = payload.get("candidate_instruments")
        if not isinstance(instruments, list) or tuple(
            (item.get("symbol"), item.get("isin"), item.get("mic"), item.get("trading_currency"))
            for item in instruments
        ) != expected_instruments:
            raise CrossAssetContextError("A1 account-verification universe changed")
        brokers = payload.get("brokers")
        if not isinstance(brokers, list) or tuple(item.get("broker_id") for item in brokers) != (
            "trading_212_uk",
            "interactive_brokers_uk",
        ):
            raise CrossAssetContextError("A1 account-verification broker scope changed")
        allowed = payload.get("allowed_operations", {})
        for key in (
            "existing_authenticated_browser_session_allowed",
            "exact_instrument_search_allowed",
            "interactive_login_allowed_if_user_completes_authentication",
            "read_only_account_metadata_allowed",
        ):
            if allowed.get(key) is not True:
                raise CrossAssetContextError(f"A1 account verification omits permission: {key}")
        boundary = payload.get("evidence_boundary", {})
        if boundary.get("completion_review") != {
            "path": "artifacts/agent-level-experiment/cross-asset/a1-completion-review-v1/evidence-manifest.json",
            "sha256": "5c9e13ef4a7de7daca9a4778c6332e67039687ea905951ebd643189dc631fc3c",
        }:
            raise CrossAssetContextError("A1 account-verification lineage changed")
        if boundary.get("sealed_2026_partition_accessed") is not False:
            raise CrossAssetContextError("A1 account verification cannot access sealed 2026")
        rules = payload.get("decision_rules", {})
        for key in (
            "availability_on_one_broker_implies_availability_on_another",
            "economic_similarity_can_replace_exact_isin",
            "instrument_search_presence_is_execution_approval",
            "public_catalog_can_replace_account_check",
            "quoted_price_or_performance_is_evidence",
        ):
            if rules.get(key) is not False:
                raise CrossAssetContextError(f"unsafe A1 account-verification rule: {key}")
        if rules.get("broker_result_is_independent_per_exact_instrument") is not True:
            raise CrossAssetContextError("A1 account results must remain instrument-specific")
        for key, value in payload.get("prohibitions", {}).items():
            if value is not False:
                raise CrossAssetContextError(f"unsafe A1 account-verification permission: {key}")
        return
    if payload.get("schema_version") == "cross-asset-a1-completion-review-contract-v1":
        if (
            payload.get("review_id") != "cross-asset-a1-completion-review-v1"
            or payload.get("status") != "frozen"
        ):
            raise CrossAssetContextError("unexpected or unfrozen A1 completion review")
        expected = ("SPY", "EFA", "IEF", "TLT", "GLD", "DBC", "BIL", "GBP/USD")
        instruments = payload.get("instruments")
        if not isinstance(instruments, list) or tuple(
            item.get("symbol") for item in instruments
        ) != expected:
            raise CrossAssetContextError("A1 completion-review universe changed")
        boundary = payload.get("evidence_boundary", {})
        if boundary.get("accepted_recovery_evidence") != {
            "path": "artifacts/agent-level-experiment/cross-asset/a1-twelvedata-recovery-v3/evidence-manifest.json",
            "sha256": "72dca315d92feced97442d502db46775f634dc7b4363764dd6dbf4c14bb61c98",
        }:
            raise CrossAssetContextError("A1 completion-review evidence lineage changed")
        if boundary.get("sealed_2026_partition_accessed") is not False:
            raise CrossAssetContextError("A1 completion review cannot access sealed 2026")
        rules = payload.get("decision_rules", {})
        if rules.get("a1_pass_requires_all_gates") is not True:
            raise CrossAssetContextError("A1 completion review must require every gate")
        if rules.get("public_catalog_presence_is_execution_approval") is not False:
            raise CrossAssetContextError("public catalog cannot approve execution")
        if rules.get("economically_similar_product_is_exact_mapping") is not False:
            raise CrossAssetContextError("economic similarity cannot imply exact mapping")
        required_gates = {"archival_use", "corporate_actions", "cost_model", "executable_mapping"}
        if set(payload.get("gates", {})) != required_gates:
            raise CrossAssetContextError("A1 completion-review gates changed")
        for key, value in payload.get("prohibitions", {}).items():
            if value is not False:
                raise CrossAssetContextError(f"unsafe A1 completion-review permission: {key}")
        return
    if payload.get("schema_version") == "cross-asset-a1-twelvedata-recovery-contract-v1":
        if payload.get("experiment_id") != "cross-asset-a1-twelvedata-recovery-v3" or payload.get("status") != "frozen":
            raise CrossAssetContextError("unexpected or unfrozen Twelve Data recovery contract")
        if tuple(payload.get("instruments", ())) != ("SPY", "EFA", "EEM", "IEF", "TLT", "GLD", "DBC", "BIL", "GBP/USD"):
            raise CrossAssetContextError("Twelve Data recovery universe changed")
        base = payload.get("base_contract", {})
        if base != {"path": "config/experiments/cross-asset-a1-twelvedata-full-history-v2.json", "sha256": "0e648b0d3349ffb8a944f76bccbef550bbb6704fff773569db99e26a4acdf901"}:
            raise CrossAssetContextError("Twelve Data recovery base lineage changed")
        evidence = payload.get("frozen_v2_evidence", {})
        if evidence != {"path": "artifacts/agent-level-experiment/cross-asset/a1-twelvedata-full-history-v2/evidence-manifest.json", "sha256": "550a78799913afeda9c1bba3645a12065d9ac340eb20599fa069aa2ca3a650ab"}:
            raise CrossAssetContextError("Twelve Data recovery evidence lineage changed")
        calendar = payload.get("boundaries", {}).get("calendar", {})
        if calendar != {"path": "config/research/cross-asset-a1-calendars-2008-2025-v2.json", "sha256": "1458a26e587bdf2dbbc3ba8e9b0c5d072990ceb82c967db27a906f80c29230cd"}:
            raise CrossAssetContextError("Twelve Data corrected calendar changed")
        request = payload.get("request_plan", {})
        if (request.get("maximum_requests"), request.get("maximum_weighted_credits"), request.get("minute_credit_ceiling"), request.get("phase_count")) != (51, 507, 55, 13):
            raise CrossAssetContextError("Twelve Data recovery request budget changed")
        if payload.get("decision_rule", {}).get("instrument_decisions_are_independent") is not True or payload.get("decision_rule", {}).get("a1_stage_passed_by_recovery") is not False:
            raise CrossAssetContextError("Twelve Data recovery decision boundary changed")
        for key, value in payload.get("prohibitions", {}).items():
            if value is not False:
                raise CrossAssetContextError(f"unsafe Twelve Data recovery permission: {key}")
        return
    if payload.get("schema_version") == "cross-asset-a1-twelvedata-full-history-amendment-v1":
        if payload.get("experiment_id") != "cross-asset-a1-twelvedata-full-history-v2":
            raise CrossAssetContextError("unexpected Twelve Data history successor ID")
        if payload.get("supersedes") != "cross-asset-a1-twelvedata-full-history-v1":
            raise CrossAssetContextError("Twelve Data history successor lineage changed")
        if payload.get("status") != "frozen" or payload.get("no_other_contract_field_changes") is not True:
            raise CrossAssetContextError("Twelve Data history successor must be frozen and minimal")
        base = payload.get("base_contract", {})
        if base.get("path") != "config/experiments/cross-asset-a1-twelvedata-full-history-v1.json":
            raise CrossAssetContextError("Twelve Data history successor base path changed")
        if base.get("sha256") != "fe8bd4353dedc117049e482bdab74451c14cd4ab403f2c122b5d0f5e284639e6":
            raise CrossAssetContextError("Twelve Data history successor base digest changed")
        failure = payload.get("frozen_interruption_evidence", {})
        if failure.get("path") != "artifacts/agent-level-experiment/cross-asset/a1-twelvedata-full-history-v1/failure-report.json":
            raise CrossAssetContextError("Twelve Data history interruption path changed")
        if failure.get("sha256") != "e02a9793cf0c786f053d1db0ac770d0b7a5fd2a89db97f6d693e441ead6d7898":
            raise CrossAssetContextError("Twelve Data history interruption digest changed")
        if payload.get("changes_from_predecessor") != {
            "output_artifact_root": "artifacts/agent-level-experiment/cross-asset/a1-twelvedata-full-history-v2"
        }:
            raise CrossAssetContextError("Twelve Data history successor changes are not minimal")
        return
    if payload.get("schema_version") == "cross-asset-a1-twelvedata-full-history-contract-v1":
        if payload.get("experiment_id") != "cross-asset-a1-twelvedata-full-history-v1":
            raise CrossAssetContextError("unexpected Twelve Data history experiment ID")
        if payload.get("status") != "frozen":
            raise CrossAssetContextError("Twelve Data history contract must be frozen")
        if tuple(payload.get("instruments", ())) != (
            "SPY", "EFA", "EEM", "IEF", "TLT", "GLD", "DBC", "BIL", "GBP/USD"
        ):
            raise CrossAssetContextError("Twelve Data history universe changed")
        prohibitions = payload.get("prohibitions", {})
        for key in (
            "adjusted_price_use_allowed",
            "economic_metrics_allowed",
            "execution_approval_allowed",
            "execution_credentials_allowed",
            "feature_generation_allowed",
            "partial_ob0_access_allowed",
            "pnl_allowed",
            "protected_service_access_allowed",
            "return_calculation_allowed",
            "sealed_2026_access_allowed",
            "strategy_parameters_allowed",
            "strategy_signals_allowed",
        ):
            if prohibitions.get(key) is not False:
                raise CrossAssetContextError(f"Twelve Data history must disable {key}")
        boundaries = payload.get("boundaries", {})
        if boundaries.get("development_start_inclusive") != "2008-01-02":
            raise CrossAssetContextError("Twelve Data history start changed")
        if boundaries.get("development_end_inclusive") != "2025-12-31":
            raise CrossAssetContextError("Twelve Data history end changed")
        if boundaries.get("sealed_2026_partition_accessed") is not False:
            raise CrossAssetContextError("Twelve Data history cannot access 2026")
        calendar = boundaries.get("expected_calendar", {})
        if calendar.get("path") != "config/research/cross-asset-a1-calendars-2008-2025-v1.json":
            raise CrossAssetContextError("Twelve Data history calendar path changed")
        if calendar.get("sha256") != "85bb13a34457acccf980bfc0e623b75bc532146422f3a51fd402dd3103ce8da2":
            raise CrossAssetContextError("Twelve Data history calendar digest changed")
        if (calendar.get("us_session_count"), calendar.get("fx_session_count")) != (4529, 4671):
            raise CrossAssetContextError("Twelve Data history calendar count changed")
        request = payload.get("request_plan", {})
        if (request.get("maximum_requests"), request.get("maximum_weighted_credits")) != (25, 329):
            raise CrossAssetContextError("Twelve Data history request budget changed")
        if request.get("minute_credit_ceiling") != 55:
            raise CrossAssetContextError("Twelve Data history minute limit changed")
        query = request.get("time_series_query", {})
        if query.get("adjust") != "none" or query.get("outputsize") != "5000":
            raise CrossAssetContextError("Twelve Data history price semantics changed")
        access = payload.get("source_access", {})
        if access.get("api_token_environment_variable") != "TWELVEDATA_API_KEY":
            raise CrossAssetContextError("Twelve Data history token variable changed")
        if access.get("api_token_may_be_logged_or_serialized") is not False:
            raise CrossAssetContextError("Twelve Data history token serialization is unsafe")
        if payload.get("decision_rule", {}).get("a1_stage_passed_by_history_contract") is not False:
            raise CrossAssetContextError("history contract cannot pass A1")
        return
    if payload.get("schema_version") == "cross-asset-a1-twelvedata-source-pilot-amendment-v1":
        if payload.get("pilot_id") != "cross-asset-a1-twelvedata-economic-proxy-pilot-v2":
            raise CrossAssetContextError("unexpected Twelve Data successor ID")
        if payload.get("supersedes") != "cross-asset-a1-twelvedata-economic-proxy-pilot-v1":
            raise CrossAssetContextError("Twelve Data successor lineage changed")
        if payload.get("status") != "frozen" or payload.get("no_other_contract_field_changes") is not True:
            raise CrossAssetContextError("Twelve Data successor must be frozen and minimal")
        base = payload.get("base_contract", {})
        if base.get("path") != "config/experiments/cross-asset-a1-twelvedata-economic-proxy-pilot-v1.json":
            raise CrossAssetContextError("Twelve Data successor base path changed")
        if base.get("sha256") != "6fba0c1d57f2c496435812e7ce13aedd3de8d81a059a7595387808f2a3c42f36":
            raise CrossAssetContextError("Twelve Data successor base digest changed")
        failure = payload.get("frozen_failure_evidence", {})
        if failure.get("path") != "artifacts/agent-level-experiment/cross-asset/a1-twelvedata-economic-proxy-pilot-v1/evidence-manifest.json":
            raise CrossAssetContextError("Twelve Data successor failure lineage changed")
        if failure.get("sha256") != "503d9be184796263273140aecfcc3e7a96c9b2e4181966ae32afc444a17c95c2":
            raise CrossAssetContextError("Twelve Data successor failure digest changed")
        changes = payload.get("changes_from_predecessor", {})
        if changes.get("time_series_query_boundary") != {
            "end_date": "2025-03-03",
            "start_date": "2025-01-31",
        }:
            raise CrossAssetContextError("Twelve Data successor query buffer changed")
        if changes.get("output_artifact_root") != "artifacts/agent-level-experiment/cross-asset/a1-twelvedata-economic-proxy-pilot-v2":
            raise CrossAssetContextError("Twelve Data successor artifact root changed")
        return
    if payload.get("schema_version") == "cross-asset-a1-twelvedata-source-pilot-contract-v1":
        _validate_twelvedata_a1_contract(payload)
        return
    if payload.get("schema_version") == "cross-asset-a1-marketstack-source-pilot-eod-identity-amendment-v1":
        if payload.get("pilot_id") != "cross-asset-a1-marketstack-free-source-pilot-v3":
            raise CrossAssetContextError("unexpected final Marketstack pilot ID")
        if payload.get("supersedes") != "cross-asset-a1-marketstack-free-source-pilot-v2":
            raise CrossAssetContextError("final Marketstack pilot lineage changed")
        if payload.get("status") != "frozen" or payload.get("no_other_contract_field_changes") is not True:
            raise CrossAssetContextError("final Marketstack pilot must be frozen and minimal")
        base = payload.get("base_contract", {})
        if base.get("path") != "config/experiments/cross-asset-a1-marketstack-free-source-pilot-v1.json":
            raise CrossAssetContextError("final Marketstack base path changed")
        if base.get("sha256") != "623e11b4f555dd67db529fd1dc7f841b878c9d1837c7f12628d07ec1ec6d8ce7":
            raise CrossAssetContextError("final Marketstack base digest changed")
        changes = payload.get("changes_from_predecessor", {})
        if changes.get("request_endpoints") != ["eod", "splits", "dividends"]:
            raise CrossAssetContextError("final Marketstack endpoint set changed")
        if changes.get("total_planned_requests") != 12:
            raise CrossAssetContextError("final Marketstack request count changed")
        if changes.get("output_artifact_root") != "artifacts/agent-level-experiment/cross-asset/a1-marketstack-free-source-pilot-v3":
            raise CrossAssetContextError("final Marketstack artifact root changed")
        if changes.get("identity_source") != "eod_name_symbol_exchange_price_currency_plus_checksummed_issuer_control":
            raise CrossAssetContextError("final Marketstack identity source changed")
        failure = payload.get("frozen_failure_evidence", {})
        if failure.get("path") != "artifacts/agent-level-experiment/cross-asset/a1-marketstack-free-source-pilot-v2/failure-report.json":
            raise CrossAssetContextError("final Marketstack failure lineage changed")
        if failure.get("sha256") != "5d9cf8c5ab81cc128ffaaca6f6cb1aae20e8b85ffe28ad46a271259d8a93b335":
            raise CrossAssetContextError("final Marketstack failure digest changed")
        return
    if payload.get("schema_version") == "cross-asset-a1-marketstack-source-pilot-amendment-v1":
        if payload.get("pilot_id") != "cross-asset-a1-marketstack-free-source-pilot-v2":
            raise CrossAssetContextError("unexpected Marketstack successor pilot ID")
        if payload.get("supersedes") != "cross-asset-a1-marketstack-free-source-pilot-v1":
            raise CrossAssetContextError("Marketstack successor lineage changed")
        if payload.get("status") != "frozen" or payload.get("no_other_contract_field_changes") is not True:
            raise CrossAssetContextError("Marketstack successor must be frozen and minimal")
        base = payload.get("base_contract", {})
        if base.get("path") != "config/experiments/cross-asset-a1-marketstack-free-source-pilot-v1.json":
            raise CrossAssetContextError("Marketstack successor base path changed")
        if base.get("sha256") != "623e11b4f555dd67db529fd1dc7f841b878c9d1837c7f12628d07ec1ec6d8ce7":
            raise CrossAssetContextError("Marketstack successor base digest changed")
        changes = payload.get("changes_from_predecessor", {})
        if changes.get("endpoint_paths") != {"tickers": "/tickers/{symbol}"}:
            raise CrossAssetContextError("Marketstack successor endpoint change is not exact")
        if changes.get("output_artifact_root") != "artifacts/agent-level-experiment/cross-asset/a1-marketstack-free-source-pilot-v2":
            raise CrossAssetContextError("Marketstack successor artifact root changed")
        failure = payload.get("frozen_failure_evidence", {})
        if failure.get("path") != "artifacts/agent-level-experiment/cross-asset/a1-marketstack-free-source-pilot-v1/failure-report.json":
            raise CrossAssetContextError("Marketstack successor failure lineage changed")
        if failure.get("sha256") != "abb918d4d09bcceabe7d020cf3b408febbe95e597c80a6a89eb1c92b7ee7e3d2":
            raise CrossAssetContextError("Marketstack successor failure digest changed")
        return
    if payload.get("schema_version") == "cross-asset-a1-marketstack-source-pilot-contract-v1":
        _validate_marketstack_a1_contract(payload)
        return
    if payload.get("schema_version") != "cross-asset-a1-source-pilot-contract-v1":
        raise CrossAssetContextError("unsupported A1 source-pilot schema")
    if payload.get("pilot_id") != "cross-asset-a1-lse-source-pilot-v1":
        raise CrossAssetContextError("unexpected A1 source-pilot ID")
    if payload.get("status") != "frozen":
        raise CrossAssetContextError("A1 source pilot must be frozen")
    if payload.get("strategy_evaluation_authorized") is not False:
        raise CrossAssetContextError("A1 cannot authorize strategy evaluation")
    prohibitions = payload.get("prohibitions", {})
    for key in (
        "bulk_download_allowed",
        "credentials_allowed",
        "economic_metrics_allowed",
        "execution_approval_allowed",
        "partial_ob0_access_allowed",
        "pnl_allowed",
        "protected_service_access_allowed",
        "strategy_parameters_allowed",
        "strategy_signals_allowed",
    ):
        if prohibitions.get(key) is not False:
            raise CrossAssetContextError(f"A1 safety boundary must disable {key}")
    if payload.get("jurisdiction", {}).get("execution_access_approved") is not False:
        raise CrossAssetContextError("A1 cannot approve instrument execution")
    instruments = payload.get("instruments")
    expected = ("SWDA", "VAGS", "SGLN", "COMM")
    if not isinstance(instruments, list) or tuple(item.get("ticker") for item in instruments) != expected:
        raise CrossAssetContextError("A1 exact GBP LSE universe changed")
    for instrument in instruments:
        if instrument.get("exchange") != "London Stock Exchange":
            raise CrossAssetContextError("A1 instrument must be an LSE listing")
        if instrument.get("listing_currency") != "GBP":
            raise CrossAssetContextError("A1 instrument must use its GBP trading line")
        if not all(instrument.get(key) for key in ("instrument_id", "isin", "sedol", "ric")):
            raise CrossAssetContextError("A1 instrument identity is incomplete")
    boundaries = payload.get("boundaries", {})
    sessions = boundaries.get("expected_lse_sessions")
    if not isinstance(sessions, list) or len(sessions) != 22 or len(set(sessions)) != 22:
        raise CrossAssetContextError("A1 pilot must freeze 22 unique expected sessions")
    source = payload.get("sources", {}).get("stooq_daily_csv", {})
    if source.get("maximum_requests") != 4 or source.get("accepted_before_pilot") is not False:
        raise CrossAssetContextError("A1 candidate-source request boundary changed")
    if payload.get("decision_rule", {}).get("technical_csv_success_is_source_acceptance") is not False:
        raise CrossAssetContextError("technical CSV success cannot imply source acceptance")


def _validate_twelvedata_a1_contract(payload: Mapping[str, Any]) -> None:
    if payload.get("pilot_id") != "cross-asset-a1-twelvedata-economic-proxy-pilot-v1":
        raise CrossAssetContextError("unexpected Twelve Data A1 pilot ID")
    if payload.get("status") != "frozen" or payload.get("strategy_evaluation_authorized") is not False:
        raise CrossAssetContextError("Twelve Data A1 pilot must be frozen and source-only")
    prohibitions = payload.get("prohibitions", {})
    for key in (
        "bulk_download_allowed",
        "derivative_data_allowed",
        "economic_metrics_allowed",
        "execution_approval_allowed",
        "execution_credentials_allowed",
        "partial_ob0_access_allowed",
        "pnl_allowed",
        "protected_service_access_allowed",
        "strategy_parameters_allowed",
        "strategy_signals_allowed",
    ):
        if prohibitions.get(key) is not False:
            raise CrossAssetContextError(f"Twelve Data A1 safety boundary must disable {key}")
    access = payload.get("source_access", {})
    if access.get("api_token_environment_variable") != "TWELVEDATA_API_KEY":
        raise CrossAssetContextError("Twelve Data token environment variable changed")
    if access.get("research_data_provider_api_token_allowed") is not True:
        raise CrossAssetContextError("Twelve Data research token must be explicitly allowed")
    if access.get("existing_paid_subscription_use_authorized") is not True:
        raise CrossAssetContextError("existing Twelve Data subscription use is not authorized")
    for key in (
        "api_token_may_be_logged_or_serialized",
        "broker_or_exchange_credentials_allowed",
        "further_paid_upgrade_authorized",
    ):
        if access.get(key) is not False:
            raise CrossAssetContextError(f"unsafe Twelve Data access setting: {key}")
    expected = ("SPY", "EFA", "EEM", "IEF", "TLT", "GLD", "DBC", "BIL", "GBP/USD")
    instruments = payload.get("instruments")
    if not isinstance(instruments, list) or tuple(item.get("symbol") for item in instruments) != expected:
        raise CrossAssetContextError("Twelve Data exact economic-proxy universe changed")
    if len({item.get("instrument_id") for item in instruments}) != len(expected):
        raise CrossAssetContextError("Twelve Data instrument identities are incomplete or duplicated")
    boundaries = payload.get("boundaries", {})
    etf_sessions = boundaries.get("expected_us_etf_sessions")
    fx_sessions = boundaries.get("expected_fx_sessions")
    if not isinstance(etf_sessions, list) or len(etf_sessions) != 19 or etf_sessions != sorted(set(etf_sessions)):
        raise CrossAssetContextError("Twelve Data pilot must freeze 19 US ETF sessions")
    if not isinstance(fx_sessions, list) or len(fx_sessions) != 20 or fx_sessions != sorted(set(fx_sessions)):
        raise CrossAssetContextError("Twelve Data pilot must freeze 20 FX sessions")
    source = payload.get("sources", {}).get("twelvedata_grow", {})
    if source.get("api_base_url") != "https://api.twelvedata.com":
        raise CrossAssetContextError("Twelve Data host changed")
    if source.get("adjustment_mode") != "none":
        raise CrossAssetContextError("Twelve Data pilot must remain unadjusted")
    if source.get("maximum_requests") != 20 or source.get("maximum_weighted_credits") != 58:
        raise CrossAssetContextError("Twelve Data request budget changed")
    if source.get("minute_credit_ceiling") != 55 or source.get("maximum_symbols") != 9:
        raise CrossAssetContextError("Twelve Data plan boundary changed")
    if payload.get("decision_rule", {}).get("a1_stage_passed_by_pilot") is not False:
        raise CrossAssetContextError("Twelve Data source pilot cannot pass A1")
    if payload.get("jurisdiction", {}).get("execution_access_approved") is not False:
        raise CrossAssetContextError("Twelve Data pilot cannot approve execution instruments")


def _validate_marketstack_a1_contract(payload: Mapping[str, Any]) -> None:
    if payload.get("pilot_id") != "cross-asset-a1-marketstack-free-source-pilot-v1":
        raise CrossAssetContextError("unexpected Marketstack A1 pilot ID")
    if payload.get("status") != "frozen":
        raise CrossAssetContextError("Marketstack A1 pilot must be frozen")
    if payload.get("strategy_evaluation_authorized") is not False:
        raise CrossAssetContextError("Marketstack A1 cannot authorize strategy evaluation")
    prohibitions = payload.get("prohibitions", {})
    for key in (
        "bulk_download_allowed",
        "derivative_data_allowed",
        "economic_metrics_allowed",
        "execution_approval_allowed",
        "execution_credentials_allowed",
        "partial_ob0_access_allowed",
        "pnl_allowed",
        "protected_service_access_allowed",
        "strategy_parameters_allowed",
        "strategy_signals_allowed",
    ):
        if prohibitions.get(key) is not False:
            raise CrossAssetContextError(f"Marketstack A1 safety boundary must disable {key}")
    access = payload.get("source_access", {})
    if access.get("api_token_environment_variable") != "MARKETSTACK_API_KEY":
        raise CrossAssetContextError("Marketstack token environment variable changed")
    if access.get("research_data_provider_api_token_allowed") is not True:
        raise CrossAssetContextError("Marketstack research token must be explicitly allowed")
    for key in (
        "api_token_may_be_logged_or_serialized",
        "broker_or_exchange_credentials_allowed",
        "paid_upgrade_authorized",
    ):
        if access.get(key) is not False:
            raise CrossAssetContextError(f"unsafe Marketstack access setting: {key}")
    if access.get("free_account_only") is not True:
        raise CrossAssetContextError("Marketstack pilot must remain free-only")
    instruments = payload.get("instruments")
    expected = ("SWDA", "VAGS", "SGLN", "COMM")
    expected_isins = {
        "SWDA": "IE00B4L5Y983",
        "VAGS": "IE00BG47K971",
        "SGLN": "IE00B4ND3602",
        "COMM": "IE00BDFL4P12",
    }
    expected_units = {"SWDA": ("GBX", "0.01"), "VAGS": ("GBP", "1"), "SGLN": ("GBX", "0.01"), "COMM": ("GBX", "0.01")}
    if not isinstance(instruments, list) or tuple(item.get("ticker") for item in instruments) != expected:
        raise CrossAssetContextError("Marketstack A1 exact universe changed")
    for instrument in instruments:
        ticker = instrument["ticker"]
        if instrument.get("isin") != expected_isins[ticker]:
            raise CrossAssetContextError(f"Marketstack A1 ISIN changed for {ticker}")
        if instrument.get("expected_vendor_exchange_code") != "XLON":
            raise CrossAssetContextError(f"Marketstack A1 exchange changed for {ticker}")
        if (
            instrument.get("expected_vendor_quote_unit"),
            instrument.get("price_to_gbp_multiplier"),
        ) != expected_units[ticker]:
            raise CrossAssetContextError(f"Marketstack A1 quote conversion changed for {ticker}")
    sessions = payload.get("boundaries", {}).get("expected_lse_sessions")
    if not isinstance(sessions, list) or len(sessions) != 22 or sessions != sorted(set(sessions)):
        raise CrossAssetContextError("Marketstack A1 must freeze 22 ordered sessions")
    source = payload.get("sources", {}).get("marketstack_free", {})
    if source.get("api_base_url") != "https://api.marketstack.com/v2":
        raise CrossAssetContextError("Marketstack A1 API boundary changed")
    if source.get("maximum_requests") != 20 or source.get("maximum_symbols") != 4:
        raise CrossAssetContextError("Marketstack A1 request boundary changed")
    if source.get("plan") != "free" or source.get("accepted_before_pilot") is not False:
        raise CrossAssetContextError("Marketstack must remain an unaccepted free candidate")
    if source.get("adjusted_fields_eligible_for_research") is not False:
        raise CrossAssetContextError("Marketstack adjusted fields must remain ineligible")
    if source.get("raw_plus_separate_corporate_actions_policy_frozen") is not True:
        raise CrossAssetContextError("Marketstack raw-price policy is missing")
    if source.get("availability_fallback_frozen") is not True:
        raise CrossAssetContextError("Marketstack availability fallback is missing")
    terms = source.get("research_reuse_terms", {})
    if source.get("research_reuse_terms_documented") is not True:
        raise CrossAssetContextError("Marketstack private source-qualification terms are missing")
    if terms.get("private_source_qualification_while_account_active_documented") is not True:
        raise CrossAssetContextError("Marketstack private source-qualification use is unresolved")
    if terms.get("archival_use_after_account_termination_resolved") is not False:
        raise CrossAssetContextError("Marketstack archival-use uncertainty must remain explicit")
    if terms.get("service_agreement_url") != "https://marketstack.com/agreement":
        raise CrossAssetContextError("Marketstack terms source changed")
    _utc(terms.get("observed_at"), "Marketstack terms observed_at")
    controls = payload.get("sources", {}).get("issuer_identity", {}).get("checksummed_controls")
    if not isinstance(controls, list) or tuple(item.get("ticker") for item in controls) != expected:
        raise CrossAssetContextError("Marketstack issuer controls are incomplete")
    if payload.get("decision_rule", {}).get("technical_json_success_is_source_acceptance") is not False:
        raise CrossAssetContextError("technical JSON success cannot imply source acceptance")


def _validate_a1_evidence(root: Path, payload: Mapping[str, Any], state: str) -> None:
    schema = payload.get("schema_version")
    if schema not in {
        "cross-asset-a1-evidence-manifest-v1",
        "cross-asset-a1-marketstack-evidence-manifest-v1",
        "cross-asset-a1-twelvedata-evidence-manifest-v1",
        "cross-asset-a1-twelvedata-full-history-evidence-manifest-v1",
        "cross-asset-a1-twelvedata-recovery-evidence-manifest-v1",
        "cross-asset-a1-completion-evidence-manifest-v1",
        "cross-asset-a1-account-verification-evidence-manifest-v1",
        "cross-asset-a1-executable-universe-feasibility-evidence-manifest-v1",
        "cross-asset-a1-exact-lse-boundary-clarification-evidence-manifest-v1",
        "cross-asset-a1-ibkr-public-review-evidence-manifest-v1",
        "cross-asset-a1-lse-futures-expansion-evidence-manifest-v1",
        "cross-asset-a1-exact-xlon-history-failure-evidence-v1",
        "cross-asset-a1-oanda-source-successor-evidence-v1",
        "cross-asset-a1-oanda-hourly-successor-evidence-v1",
    }:
        raise CrossAssetContextError("unsupported A1 evidence-manifest schema")
    if schema == "cross-asset-a1-oanda-hourly-successor-evidence-v1":
        if payload.get("experiment_id") != "cross-asset-a1-oanda-hourly-history-v2":
            raise CrossAssetContextError("hourly OANDA successor evidence ID changed")
        if payload.get("decision") != "a1_hourly_source_qualification_passed_with_no_trade_masks":
            raise CrossAssetContextError("hourly OANDA successor decision changed")
        for key in ("a1_stage_passed", "qualified_for_strategy_evaluation"):
            if payload.get(key) is not True:
                raise CrossAssetContextError(f"hourly OANDA successor pass field changed: {key}")
        for key in (
            "price_rows_changed_or_filled",
            "returns_or_pnl_computed",
            "sealed_2026_price_accessed",
        ):
            if payload.get(key) is not False:
                raise CrossAssetContextError(f"hourly OANDA successor safety field changed: {key}")
        if (
            payload.get("new_provider_requests") != 0
            or payload.get("accepted_strategy_arms") != []
            or payload.get("approved_execution_instruments") != []
            or payload.get("actionable_arm_id") != "no_trade"
        ):
            raise CrossAssetContextError("hourly OANDA successor authority changed")
        artifacts = payload.get("artifacts")
        _validate_artifacts(root, artifacts)
        masks = [item for item in artifacts if "/availability/" in str(item.get("path", ""))]
        if len(masks) != 7:
            raise CrossAssetContextError("hourly OANDA successor availability masks are incomplete")
        report_record = next(
            (item for item in artifacts if str(item.get("path", "")).endswith("/audit-report.json")),
            None,
        )
        if report_record is None:
            raise CrossAssetContextError("hourly OANDA successor report is missing")
        report = _load_canonical(
            _repo_file(root, report_record["path"], "hourly OANDA successor report"),
            "hourly OANDA successor report",
        )
        if (
            report.get("decision") != payload.get("decision")
            or report.get("experiment_id") != payload.get("experiment_id")
            or report.get("a1_stage_passed") is not True
            or report.get("passed_candidate_count") != 7
            or report.get("returns_or_pnl_computed") is not False
            or report.get("price_rows_changed_or_filled") is not False
        ):
            raise CrossAssetContextError("hourly OANDA successor report changed")
        results = report.get("instrument_results")
        if not isinstance(results, list) or tuple(item.get("instrument_id") for item in results) != (
            "SPX500_USD",
            "NAS100_USD",
            "DE30_EUR",
            "UK100_GBP",
            "XAU_USD",
            "EUR_USD",
            "USD_JPY",
        ):
            raise CrossAssetContextError("hourly OANDA successor result universe changed")
        if any(
            item.get("decision") != "candidate_pass_with_incomplete_sessions_no_trade"
            or item.get("complete_session_days", 0) < 3000
            or item.get("outage_gaps") != []
            for item in results
        ):
            raise CrossAssetContextError("hourly OANDA successor candidate gate changed")
        if state != "passed":
            raise CrossAssetContextError("hourly OANDA successor evidence requires A1 passed status")
        return
    if schema == "cross-asset-a1-oanda-source-successor-evidence-v1":
        if payload.get("experiment_id") != "cross-asset-a1-oanda-source-pilot-v2":
            raise CrossAssetContextError("OANDA successor evidence ID changed")
        if payload.get("decision") != "oanda_source_pilot_passed_for_successor_cost_and_semantics_qualification":
            raise CrossAssetContextError("OANDA successor evidence decision changed")
        if payload.get("a1_stage_passed") is not False:
            raise CrossAssetContextError("OANDA source pilot cannot pass A1")
        if payload.get("source_pilot_passed") is not True:
            raise CrossAssetContextError("OANDA successor source pass is missing")
        if payload.get("qualified_for_strategy_evaluation") is not False:
            raise CrossAssetContextError("OANDA source pilot cannot authorize a strategy")
        if payload.get("new_provider_requests") != 0:
            raise CrossAssetContextError("OANDA successor may not make provider requests")
        artifacts = payload.get("artifacts")
        _validate_artifacts(root, artifacts)
        report_record = next(
            (item for item in artifacts if str(item.get("path", "")).endswith("/audit-report.json")),
            None,
        )
        if report_record is None:
            raise CrossAssetContextError("OANDA successor evidence omits the audit report")
        report = _load_canonical(
            _repo_file(root, report_record["path"], "OANDA successor audit report"),
            "OANDA successor audit report",
        )
        if (
            report.get("experiment_id") != payload.get("experiment_id")
            or report.get("decision") != payload.get("decision")
            or report.get("a1_stage_passed") is not False
            or report.get("source_pilot_passed") is not True
            or report.get("qualified_for_strategy_evaluation") is not False
            or report.get("new_provider_requests") != 0
        ):
            raise CrossAssetContextError("OANDA successor report lineage changed")
        if report.get("passed_candidate_count") != 5:
            raise CrossAssetContextError("OANDA successor candidate result changed")
        oil = next(
            (
                item
                for item in report.get("instrument_results", ())
                if item.get("instrument_id") == "WTICO_USD"
            ),
            None,
        )
        if not isinstance(oil, Mapping) or oil.get("first_candle_at") != "2005-11-27T22:00:00Z":
            raise CrossAssetContextError("OANDA oil segment boundary changed")
        if state == "passed":
            raise CrossAssetContextError("OANDA source pilot cannot pass all of A1")
        return
    if schema == "cross-asset-a1-exact-xlon-history-failure-evidence-v1":
        if payload.get("experiment_id") != "cross-asset-a1-lse-futures-expansion-v1":
            raise CrossAssetContextError("exact XLON history failure evidence ID mismatch")
        if payload.get("decision") != "exact_lse_full_history_rejected":
            raise CrossAssetContextError("exact XLON history failure decision changed")
        artifacts = payload.get("artifacts")
        _validate_artifacts(root, artifacts)
        report_record = next(
            (item for item in artifacts if str(item.get("path", "")).endswith("/failure-report.json")),
            None,
        )
        inventory_record = next(
            (item for item in artifacts if str(item.get("path", "")).endswith("/quality-inventory.json")),
            None,
        )
        if report_record is None or inventory_record is None:
            raise CrossAssetContextError("exact XLON history failure evidence is incomplete")
        report = _load_canonical(
            _repo_file(root, report_record["path"], "exact XLON history failure report"),
            "exact XLON history failure report",
        )
        inventory = _load_canonical(
            _repo_file(root, inventory_record["path"], "exact XLON history quality inventory"),
            "exact XLON history quality inventory",
        )
        if (
            report.get("decision") != payload.get("decision")
            or report.get("a1_stage_passed") is not False
            or report.get("approved_execution_instruments") != []
            or report.get("accepted_strategy_arms") != []
            or report.get("quality_inventory_sha256") != inventory_record.get("sha256")
        ):
            raise CrossAssetContextError("exact XLON history failure report changed")
        expected = (("SWDA", 1, 9), ("VAGS", 0, 0), ("SGLN", 1, 8), ("COMM", 169, 38))
        if tuple(
            (item.get("symbol"), item.get("duplicate_session_count"), len(item.get("missing_sessions", ())))
            for item in inventory.get("instruments", ())
        ) != expected:
            raise CrossAssetContextError("exact XLON history quality result changed")
        if state == "passed":
            raise CrossAssetContextError("rejected exact XLON history cannot pass A1")
        return
    if schema == "cross-asset-a1-lse-futures-expansion-evidence-manifest-v1":
        if payload.get("experiment_id") != "cross-asset-a1-lse-futures-expansion-v1":
            raise CrossAssetContextError("A1 expansion evidence ID mismatch")
        if payload.get("decision") != "a1_expansion_frozen_pending_acquisition":
            raise CrossAssetContextError("A1 expansion evidence decision changed")
        artifacts = payload.get("artifacts")
        _validate_artifacts(root, artifacts)
        report_record = next(
            (item for item in artifacts if str(item.get("path", "")).endswith("/freeze-report.json")),
            None,
        )
        if report_record is None:
            raise CrossAssetContextError("A1 expansion evidence omits freeze report")
        report = _load_canonical(
            _repo_file(root, report_record["path"], "A1 expansion freeze report"),
            "A1 expansion freeze report",
        )
        if (
            report.get("experiment_id") != payload.get("experiment_id")
            or report.get("decision") != payload.get("decision")
            or report.get("a1_stage_passed") is not False
            or report.get("approved_execution_instruments") != []
            or report.get("accepted_strategy_arms") != []
        ):
            raise CrossAssetContextError("A1 expansion freeze report changed")
        for key, value in report.get("safety", {}).items():
            if value is not False:
                raise CrossAssetContextError(f"A1 expansion violates safety field: {key}")
        if state == "passed":
            raise CrossAssetContextError("a frozen acquisition plan cannot pass A1")
        return
    if schema == "cross-asset-a1-exact-lse-boundary-clarification-evidence-manifest-v1":
        if payload.get("review_id") != "cross-asset-a1-executable-universe-feasibility-v2":
            raise CrossAssetContextError("LSE clarification evidence ID mismatch")
        if payload.get("decision") not in {
            "exact_lse_source_clarification_passed",
            "exact_lse_source_clarification_rejected",
        }:
            raise CrossAssetContextError("LSE clarification evidence decision is invalid")
        artifacts = payload.get("artifacts")
        _validate_artifacts(root, artifacts)
        reused = payload.get("reused_artifacts")
        _validate_artifacts(root, reused)
        report_record = next(
            (item for item in artifacts if str(item.get("path", "")).endswith("/audit-report.json")),
            None,
        )
        if report_record is None:
            raise CrossAssetContextError("LSE clarification evidence omits audit report")
        report = _load_canonical(
            _repo_file(root, report_record["path"], "LSE clarification audit report"),
            "LSE clarification audit report",
        )
        if (
            report.get("review_id") != payload.get("review_id")
            or report.get("decision") != payload.get("decision")
            or report.get("a1_stage_passed") is not False
            or report.get("approved_execution_instruments") != []
            or report.get("accepted_strategy_arms") != []
        ):
            raise CrossAssetContextError("LSE clarification report lineage changed")
        for key in (
            "economic_metrics_computed",
            "pnl_computed",
            "returns_computed",
            "sealed_2026_partition_accessed",
            "strategy_signals_generated",
        ):
            if report.get(key) is not False:
                raise CrossAssetContextError(
                    f"LSE clarification report violates safety field: {key}"
                )
        expected_pass = payload.get("decision") == "exact_lse_source_clarification_passed"
        if report.get("exact_lse_source_clarification_passed") is not expected_pass:
            raise CrossAssetContextError("LSE clarification pass flag conflicts with decision")
        if state == "passed":
            raise CrossAssetContextError("source clarification evidence cannot pass A1")
        return
    if schema == "cross-asset-a1-executable-universe-feasibility-evidence-manifest-v1":
        if payload.get("review_id") != "cross-asset-a1-executable-universe-feasibility-v1":
            raise CrossAssetContextError("executable-universe evidence ID mismatch")
        if payload.get("decision") not in {
            "exact_lse_source_pilot_passed",
            "exact_lse_source_pilot_rejected",
        }:
            raise CrossAssetContextError("executable-universe evidence decision is invalid")
        artifacts = payload.get("artifacts")
        _validate_artifacts(root, artifacts)
        report_record = next(
            (item for item in artifacts if str(item.get("path", "")).endswith("/audit-report.json")),
            None,
        )
        facts_record = next(
            (
                item
                for item in artifacts
                if str(item.get("path", "")).endswith("/public-feasibility-facts.json")
            ),
            None,
        )
        source_record = next(
            (item for item in artifacts if str(item.get("path", "")).endswith("/source-manifest.json")),
            None,
        )
        if report_record is None or facts_record is None or source_record is None:
            raise CrossAssetContextError("executable-universe evidence is incomplete")
        report = _load_canonical(
            _repo_file(root, report_record["path"], "executable-universe audit report"),
            "executable-universe audit report",
        )
        facts_path = _repo_file(
            root, facts_record["path"], "executable-universe public facts"
        )
        facts = _load_canonical(facts_path, "executable-universe public facts")
        if (
            report.get("review_id") != payload.get("review_id")
            or report.get("decision") != payload.get("decision")
            or report.get("a1_stage_passed") is not False
            or report.get("approved_execution_instruments") != []
            or report.get("accepted_strategy_arms") != []
        ):
            raise CrossAssetContextError("executable-universe report lineage changed")
        for key in (
            "economic_metrics_computed",
            "pnl_computed",
            "returns_computed",
            "sealed_2026_partition_accessed",
            "strategy_signals_generated",
        ):
            if report.get(key) is not False:
                raise CrossAssetContextError(
                    f"executable-universe report violates safety field: {key}"
                )
        if (
            facts.get("review_id") != payload.get("review_id")
            or facts.get("decision") != "public_feasibility_only_no_universe_selected"
            or facts.get("universe_selected") is not False
            or facts.get("strategy_evaluation_performed") is not False
            or facts.get("sealed_2026_partition_accessed") is not False
            or report.get("public_feasibility_facts_sha256") != _sha256(facts_path)
        ):
            raise CrossAssetContextError("executable-universe public facts changed")
        if state == "passed":
            raise CrossAssetContextError("source feasibility evidence cannot pass A1")
        if (
            state in {"blocked", "rejected"}
            and report.get("exact_lse_source_pilot_passed") is not False
        ):
            raise CrossAssetContextError("failed A1 state conflicts with source feasibility")
        return
    if schema == "cross-asset-a1-ibkr-public-review-evidence-manifest-v1":
        if payload.get("review_id") != "cross-asset-a1-ibkr-contract-details-public-review-v1":
            raise CrossAssetContextError("IBKR public-review evidence ID mismatch")
        if payload.get("decision") != "ibkr_public_lineage_partially_resolved":
            raise CrossAssetContextError("IBKR public-review decision is invalid")
        artifacts = payload.get("artifacts")
        _validate_artifacts(root, artifacts)
        report_record = next(
            (item for item in artifacts if str(item.get("path", "")).endswith("/audit-report.json")),
            None,
        )
        facts_record = next(
            (item for item in artifacts if str(item.get("path", "")).endswith("/source-facts.json")),
            None,
        )
        if report_record is None or facts_record is None:
            raise CrossAssetContextError("IBKR public-review evidence is incomplete")
        report = _load_canonical(
            _repo_file(root, report_record["path"], "IBKR public-review report"),
            "IBKR public-review report",
        )
        facts = _load_canonical(
            _repo_file(root, facts_record["path"], "IBKR public source facts"),
            "IBKR public source facts",
        )
        if (
            report.get("review_id") != payload.get("review_id")
            or report.get("decision") != payload.get("decision")
            or report.get("a1_stage_passed") is not False
        ):
            raise CrossAssetContextError("IBKR public-review report lineage mismatch")
        if report.get("approved_execution_instruments") != []:
            raise CrossAssetContextError("IBKR public review cannot approve instruments")
        if report.get("accepted_strategy_arms") != []:
            raise CrossAssetContextError("IBKR public review cannot accept strategies")
        if report.get("exact_account_lines_verified_for_identity_only") != ["VAGS"]:
            raise CrossAssetContextError("IBKR public-review exact-line result changed")
        for key, value in report.get("safety", {}).items():
            if value is not False:
                raise CrossAssetContextError(f"IBKR public review violates safety field: {key}")
        if (
            facts.get("review_id") != payload.get("review_id")
            or facts.get("broker_exchange_mapping", {}).get("mapping_supported") is not True
            or facts.get("currency_notation_review", {}).get("exact_literal_mapping_supported")
            is not False
        ):
            raise CrossAssetContextError("IBKR public source facts changed")
        _utc(facts.get("observed_at"), "IBKR public source observed_at")
        results = facts.get("instrument_results")
        expected_results = (
            ("SWDA", True, True, True, False, False),
            ("VAGS", True, True, True, True, True),
            ("SGLN", True, True, True, False, False),
            ("COMM", True, True, True, False, False),
        )
        if not isinstance(results, list) or tuple(
            (
                item.get("symbol"),
                item.get("issuer_identity_passed"),
                item.get("listing_identity_passed"),
                item.get("broker_exchange_mapping_passed"),
                item.get("currency_gate_passed"),
                item.get("exact_account_line_verified"),
            )
            for item in results
        ) != expected_results:
            raise CrossAssetContextError("IBKR public-review instrument results changed")
        retention = facts.get("retention_policy", {})
        if retention.get("normalized_identity_fields_only") is not True:
            raise CrossAssetContextError("IBKR public review must retain identity fields only")
        for key in (
            "live_or_delayed_quotes_retained",
            "market_prices_retained",
            "performance_fields_retained",
            "raw_page_snapshots_retained",
            "search_snippets_used_as_final_evidence",
        ):
            if retention.get(key) is not False:
                raise CrossAssetContextError(f"unsafe IBKR public-review retention: {key}")
        if state == "passed":
            raise CrossAssetContextError("partial IBKR public review cannot pass A1")
        return
    if schema == "cross-asset-a1-account-verification-evidence-manifest-v1":
        if payload.get("experiment_id") != "cross-asset-a1-account-instrument-verification-v1":
            raise CrossAssetContextError("A1 account-verification evidence ID mismatch")
        if payload.get("decision") != "a1_account_verification_incomplete":
            raise CrossAssetContextError("A1 account-verification decision is invalid")
        artifacts = payload.get("artifacts")
        _validate_artifacts(root, artifacts)
        report_record = next(
            (
                item
                for item in artifacts
                if str(item.get("path", "")).endswith("/audit-report.json")
            ),
            None,
        )
        if report_record is None:
            raise CrossAssetContextError("A1 account-verification evidence omits audit report")
        report = _load_canonical(
            _repo_file(root, report_record["path"], "A1 account-verification report"),
            "A1 account-verification report",
        )
        if (
            report.get("experiment_id") != payload.get("experiment_id")
            or report.get("decision") != payload.get("decision")
            or report.get("a1_stage_passed") is not False
        ):
            raise CrossAssetContextError("A1 account-verification report lineage mismatch")
        if report.get("approved_execution_instruments") != []:
            raise CrossAssetContextError("A1 account verification cannot approve instruments")
        if report.get("accepted_strategy_arms") != []:
            raise CrossAssetContextError("A1 account verification cannot accept strategies")
        for key, value in report.get("safety", {}).items():
            if value is not False:
                raise CrossAssetContextError(
                    f"A1 account verification violates safety field: {key}"
                )
        if state == "passed":
            raise CrossAssetContextError("incomplete account verification cannot pass A1")
        return
    if schema == "cross-asset-a1-completion-evidence-manifest-v1":
        if payload.get("review_id") != "cross-asset-a1-completion-review-v1":
            raise CrossAssetContextError("A1 completion evidence ID mismatch")
        if payload.get("decision") != "a1_blocked_completion_gates":
            raise CrossAssetContextError("A1 completion evidence decision is invalid")
        artifacts = payload.get("artifacts")
        _validate_artifacts(root, artifacts)
        report_record = next(
            (
                item
                for item in artifacts
                if str(item.get("path", "")).endswith("/audit-report.json")
            ),
            None,
        )
        if report_record is None:
            raise CrossAssetContextError("A1 completion evidence omits audit report")
        report = _load_canonical(
            _repo_file(root, report_record["path"], "A1 completion report"),
            "A1 completion report",
        )
        if (
            report.get("review_id") != payload.get("review_id")
            or report.get("decision") != payload.get("decision")
            or report.get("a1_stage_passed") is not False
        ):
            raise CrossAssetContextError("A1 completion report lineage or decision mismatch")
        if report.get("approved_execution_instruments") != []:
            raise CrossAssetContextError("A1 completion cannot approve execution instruments")
        if report.get("accepted_strategy_arms") != []:
            raise CrossAssetContextError("A1 completion cannot accept strategy arms")
        for key, value in report.get("safety", {}).items():
            if value is not False:
                raise CrossAssetContextError(f"A1 completion violates safety field: {key}")
        if state == "passed":
            raise CrossAssetContextError("failed A1 completion evidence cannot pass A1")
        return
    if schema == "cross-asset-a1-twelvedata-recovery-evidence-manifest-v1":
        if payload.get("experiment_id") != "cross-asset-a1-twelvedata-recovery-v3":
            raise CrossAssetContextError("Twelve Data recovery evidence ID mismatch")
        if payload.get("decision") not in {"recovery_accepted_for_A1_subset_review", "recovery_rejected_missing_essential_role"}:
            raise CrossAssetContextError("Twelve Data recovery evidence decision is invalid")
        artifacts = payload.get("artifacts")
        _validate_artifacts(root, artifacts)
        report_record = next((item for item in artifacts if str(item.get("path", "")).endswith("/audit-report.json")), None)
        if report_record is None:
            raise CrossAssetContextError("recovery evidence omits audit report")
        report = _load_canonical(_repo_file(root, report_record["path"], "recovery audit report"), "recovery audit report")
        if report.get("experiment_id") != payload.get("experiment_id") or report.get("decision") != payload.get("decision") or report.get("a1_stage_passed") is not False:
            raise CrossAssetContextError("recovery report lineage or A1 boundary mismatch")
        for key in ("economic_metrics_computed", "feature_observations_generated", "pnl_computed", "returns_computed", "sealed_2026_partition_accessed", "strategy_signals_generated"):
            if report.get(key) is not False:
                raise CrossAssetContextError(f"recovery report violates safety field: {key}")
        return
    if schema == "cross-asset-a1-twelvedata-full-history-evidence-manifest-v1":
        if payload.get("experiment_id") not in {
            "cross-asset-a1-twelvedata-full-history-v1",
            "cross-asset-a1-twelvedata-full-history-v2",
        }:
            raise CrossAssetContextError("Twelve Data history evidence ID mismatch")
        if payload.get("decision") not in {
            "full_history_accepted_for_A1_review",
            "full_history_rejected",
        }:
            raise CrossAssetContextError("Twelve Data history evidence decision is invalid")
        artifacts = payload.get("artifacts")
        _validate_artifacts(root, artifacts)
        report_record = next(
            (
                item
                for item in artifacts
                if str(item.get("path", "")).endswith("/audit-report.json")
            ),
            None,
        )
        if report_record is None:
            raise CrossAssetContextError("history evidence omits the audit report")
        report_path = _repo_file(root, report_record["path"], "history audit report")
        report = _load_canonical(report_path, "history audit report")
        if (
            report.get("experiment_id") != payload.get("experiment_id")
            or report.get("decision") != payload.get("decision")
        ):
            raise CrossAssetContextError("history report and evidence mismatch")
        for key in (
            "a1_stage_passed",
            "economic_metrics_computed",
            "feature_observations_generated",
            "pnl_computed",
            "returns_computed",
            "sealed_2026_partition_accessed",
            "strategy_signals_generated",
        ):
            if report.get(key) is not False:
                raise CrossAssetContextError(f"history report violates safety field: {key}")
        if state in {"blocked", "rejected"} and report.get("history_accepted") is not False:
            raise CrossAssetContextError("failed A1 state conflicts with accepted history")
        return
    if schema == "cross-asset-a1-marketstack-evidence-manifest-v1":
        expected_pilots = {
            "cross-asset-a1-marketstack-free-source-pilot-v1",
            "cross-asset-a1-marketstack-free-source-pilot-v2",
            "cross-asset-a1-marketstack-free-source-pilot-v3",
        }
    elif schema == "cross-asset-a1-twelvedata-evidence-manifest-v1":
        expected_pilots = {
            "cross-asset-a1-twelvedata-economic-proxy-pilot-v1",
            "cross-asset-a1-twelvedata-economic-proxy-pilot-v2",
        }
    else:
        expected_pilots = {"cross-asset-a1-lse-source-pilot-v1"}
    if payload.get("pilot_id") not in expected_pilots:
        raise CrossAssetContextError("A1 evidence pilot ID mismatch")
    if payload.get("decision") not in {
        "candidate_source_accepted_for_full_history_contract",
        "candidate_source_rejected_for_full_history_contract",
    }:
        raise CrossAssetContextError("A1 evidence has an invalid decision")
    artifacts = payload.get("artifacts")
    _validate_artifacts(root, artifacts)
    report_record = next(
        (
            item
            for item in artifacts
            if str(item.get("path", "")).endswith("/audit-report.json")
        ),
        None,
    )
    if report_record is None:
        raise CrossAssetContextError("A1 evidence omits the audit report")
    report_path = _repo_file(root, report_record["path"], "A1 audit report")
    report = _load_canonical(report_path, "A1 audit report")
    if report.get("pilot_id") != payload.get("pilot_id") or report.get("decision") != payload.get("decision"):
        raise CrossAssetContextError("A1 report and evidence decision mismatch")
    for key in (
        "a1_stage_passed",
        "bulk_download_authorized",
        "economic_metrics_computed",
        "pnl_computed",
        "sealed_partition_accessed",
        "strategy_signals_generated",
    ):
        if report.get(key) is not False:
            raise CrossAssetContextError(f"A1 report violates safety field: {key}")
    if state == "passed" and report.get("source_accepted") is not True:
        raise CrossAssetContextError("A1 cannot pass without an accepted source")
    if state in {"blocked", "rejected"} and report.get("source_accepted") is not False:
        raise CrossAssetContextError("failed A1 status conflicts with accepted source evidence")


def _validate_a2_contract(payload: Mapping[str, Any]) -> None:
    if (
        payload.get("schema_version") != "cross-asset-a2-session-breakout-contract-v1"
        or payload.get("experiment_id") != "cross-asset-a2-session-breakout-continuation-v1"
        or payload.get("status") != "frozen"
    ):
        raise CrossAssetContextError("unexpected or unfrozen A2 strategy contract")
    if tuple(payload.get("instrument_universe", ())) != (
        "SPX500_USD",
        "NAS100_USD",
        "DE30_EUR",
        "UK100_GBP",
        "XAU_USD",
        "EUR_USD",
        "USD_JPY",
    ):
        raise CrossAssetContextError("A2 strategy universe changed")
    if payload.get("partitions", {}).get("initial_run_may_read_final_sealed_values") is not False:
        raise CrossAssetContextError("A2 contract cannot authorize final-period access")
    if payload.get("costs", {}).get("additional_round_trip_slippage_bps") != [0, 5, 15]:
        raise CrossAssetContextError("A2 cost scenarios changed")
    if payload.get("accounting", {}).get("no_leverage") is not True:
        raise CrossAssetContextError("A2 leverage prohibition changed")
    for key, value in payload.get("prohibitions", {}).items():
        if value is not False:
            raise CrossAssetContextError(f"unsafe A2 permission: {key}")


def _validate_a3_hypothesis(payload: Mapping[str, Any]) -> None:
    if (
        payload.get("schema_version") != "cross-asset-a3-hypothesis-contract-v1"
        or payload.get("experiment_id") != "cross-asset-a3-overnight-gap-reversion-v1"
        or payload.get("status") != "frozen_hypothesis_only_unimplemented"
    ):
        raise CrossAssetContextError("unexpected A3 frozen hypothesis")
    if payload.get("activation_rule", {}).get("a2_result_may_change_this_hypothesis") is not False:
        raise CrossAssetContextError("A2 results cannot change the frozen A3 hypothesis")
    if payload.get("signal_outline", {}).get("lookback_complete_sessions") != 20:
        raise CrossAssetContextError("A3 hypothesis parameters changed")


def _validate_a3_prepartition_evidence(root: Path, payload: Mapping[str, Any]) -> None:
    if (
        payload.get("schema_version") != "cross-asset-a3-timestamp-prepartition-evidence-v1"
        or payload.get("experiment_id") != "cross-asset-a3-timestamp-prepartition-v1"
        or payload.get("decision") != "a3_timestamp_prepartition_passed"
        or payload.get("price_fields_deserialized") is not False
        or payload.get("prospective_price_rows_present") is not False
        or payload.get("economic_metrics_computed") is not False
        or payload.get("strategy_features_or_signals_computed") is not False
    ):
        raise CrossAssetContextError("A3 timestamp-prepartition evidence changed")
    artifacts = payload.get("artifacts")
    _validate_artifacts(root, artifacts)
    partition_files = [
        item for item in artifacts if "/development/" in item.get("path", "") or "/validation/" in item.get("path", "")
    ]
    if len(partition_files) != 30:
        raise CrossAssetContextError("A3 prepartition must bind exactly thirty partition files")


def _validate_a3_contract(payload: Mapping[str, Any]) -> None:
    if (
        payload.get("schema_version") != "cross-asset-a3-overnight-gap-reversion-contract-v2"
        or payload.get("experiment_id") != "cross-asset-a3-overnight-gap-reversion-v2"
        or payload.get("status") != "frozen"
    ):
        raise CrossAssetContextError("unexpected or unfrozen A3 replacement contract")
    if tuple(payload.get("instrument_universe", ())) != (
        "SPX500_USD",
        "NAS100_USD",
        "DE30_EUR",
        "UK100_GBP",
        "XAU_USD",
        "EUR_USD",
        "USD_JPY",
    ):
        raise CrossAssetContextError("A3 strategy universe changed")
    if payload.get("predecessor_hypothesis", {}).get("mechanism_may_change") is not False:
        raise CrossAssetContextError("A3 replacement cannot change the frozen mechanism")
    if payload.get("data_bindings", {}).get("source_files_outside_prepartitions_may_be_read") is not False:
        raise CrossAssetContextError("A3 replacement must use prepartitions only")
    if payload.get("historical_result_policy", {}).get("historical_result_can_accept_strategy_arm") is not False:
        raise CrossAssetContextError("A3 historical evidence cannot accept an arm")
    if payload.get("partitions", {}).get("prospective_final", {}).get("price_data_available_to_this_run") is not False:
        raise CrossAssetContextError("A3 prospective prices must remain unavailable")
    if payload.get("costs", {}).get("additional_round_trip_slippage_bps") != [0, 5, 15]:
        raise CrossAssetContextError("A3 cost scenarios changed")
    if payload.get("robustness", {}).get("primary_lookback_complete_sessions") != 20:
        raise CrossAssetContextError("A3 lookback changed")
    if payload.get("robustness", {}).get("primary_gap_threshold_multiplier") != "0.75":
        raise CrossAssetContextError("A3 gap threshold changed")
    if len(payload.get("acceptance_gates", {})) != 17:
        raise CrossAssetContextError("A3 historical gate set changed")
    for key, value in payload.get("prohibitions", {}).items():
        if value is not False:
            raise CrossAssetContextError(f"unsafe A3 permission: {key}")


def _validate_a3_evidence(root: Path, payload: Mapping[str, Any]) -> None:
    if (
        payload.get("schema_version") != "cross-asset-a3-overnight-gap-reversion-evidence-v2"
        or payload.get("experiment_id") != "cross-asset-a3-overnight-gap-reversion-v2"
        or payload.get("decision") != "a3_rejected_do_not_tune"
        or payload.get("accepted_strategy_arms") != []
        or payload.get("actionable_arm_id") != "no_trade"
        or payload.get("prospective_partition_accessed") is not False
    ):
        raise CrossAssetContextError("unexpected A3 rejection evidence")
    artifacts = payload.get("artifacts")
    _validate_artifacts(root, artifacts)
    result_record = next(
        (item for item in artifacts if str(item.get("path", "")).endswith("/result.json")), None
    )
    if result_record is None:
        raise CrossAssetContextError("A3 rejection evidence omits the result")
    result = _load_canonical(_repo_file(root, result_record["path"], "A3 result"), "A3 result")
    if (
        result.get("decision") != "a3_rejected_do_not_tune"
        or result.get("accepted_strategy_arms") != []
        or result.get("prospective_partition_accessed") is not False
    ):
        raise CrossAssetContextError("A3 result decision changed")
    gates = result.get("gate_results", {})
    if len(gates) != 17 or sum(value is False for value in gates.values()) != 12:
        raise CrossAssetContextError("A3 rejection gates changed")
    validation = result.get("partitions", {}).get("validation", {}).get("cost_scenarios", {}).get("5", {})
    development = result.get("partitions", {}).get("development", {}).get("cost_scenarios", {}).get("5", {})
    if (
        validation.get("filled_trades") != 848
        or validation.get("net_return_fraction") != -0.036408957003693065
        or validation.get("profit_factor") != 0.8045721207407776
        or development.get("net_return_fraction") != -0.11966105364005675
    ):
        raise CrossAssetContextError("A3 primary result changed")


def _validate_a2_evidence(root: Path, payload: Mapping[str, Any]) -> None:
    if (
        payload.get("schema_version") != "cross-asset-a2-session-breakout-evidence-v1"
        or payload.get("experiment_id") != "cross-asset-a2-session-breakout-continuation-v1"
        or payload.get("decision") != "a2_rejected_final_remains_sealed"
        or payload.get("accepted_strategy_arms") != []
        or payload.get("actionable_arm_id") != "no_trade"
    ):
        raise CrossAssetContextError("unexpected A2 rejection evidence")
    artifacts = payload.get("artifacts")
    _validate_artifacts(root, artifacts)
    result_record = next(
        (item for item in artifacts if str(item.get("path", "")).endswith("/result.json")), None
    )
    if result_record is None:
        raise CrossAssetContextError("A2 rejection evidence omits the result")
    result = _load_canonical(
        _repo_file(root, result_record["path"], "A2 result"), "A2 result"
    )
    if result.get("decision") != payload.get("decision") or result.get("accepted_strategy_arms") != []:
        raise CrossAssetContextError("A2 result decision changed")
    gates = result.get("gate_results", {})
    if len(gates) != 13 or sum(value is False for value in gates.values()) != 10:
        raise CrossAssetContextError("A2 rejection gates changed")
    validation = result.get("partitions", {}).get("validation", {}).get("cost_scenarios", {}).get("5", {})
    if (
        validation.get("filled_trades") != 1099
        or validation.get("net_return_fraction") != -0.05349669492962361
        or validation.get("profit_factor") != 0.8260721836540638
    ):
        raise CrossAssetContextError("A2 primary validation result changed")


def _validate_a2_integrity_evidence(root: Path, payload: Mapping[str, Any]) -> None:
    if (
        payload.get("schema_version") != "cross-asset-a2-integrity-review-evidence-v1"
        or payload.get("experiment_id") != "cross-asset-a2-session-breakout-integrity-review-v1"
        or payload.get("decision") != "a2_final_partition_access_claim_rejected"
        or payload.get("final_partition_clean_for_a2") is not False
        or payload.get("economic_metrics_computed_from_final_partition") is not False
    ):
        raise CrossAssetContextError("A2 boundary-integrity evidence changed")
    _validate_artifacts(root, payload.get("artifacts"))


def _validate_status(
    payload: Mapping[str, Any], program_id: str, graph: Mapping[str, tuple[str, ...]]
) -> tuple[str, str, str | None]:
    if payload.get("schema_version") not in {
        "cross-asset-program-status-v1",
        "cross-asset-program-status-v2",
        "cross-asset-program-status-v3",
        "cross-asset-program-status-v4",
        "cross-asset-program-status-v5",
        "cross-asset-program-status-v6",
        "cross-asset-program-status-v7",
    }:
        raise CrossAssetContextError("unsupported cross-asset status schema")
    if payload.get("program_id") != program_id:
        raise CrossAssetContextError("status program_id mismatch")
    records = payload.get("stages")
    if not isinstance(records, list) or tuple(item.get("stage_id") for item in records) != STAGE_IDS:
        raise CrossAssetContextError("status must contain every stage in order")
    states: dict[str, str] = {}
    for record in records:
        state = str(record.get("state", ""))
        if state not in STAGE_STATES:
            raise CrossAssetContextError(f"invalid state for {record.get('stage_id')}: {state}")
        states[str(record["stage_id"])] = state
    active = [stage_id for stage_id, state in states.items() if state == "active"]
    if len(active) > 1:
        raise CrossAssetContextError("only one cross-asset stage may be active")
    for stage_id, state in states.items():
        if state in TERMINAL_STATES or state == "active":
            missing = [dep for dep in graph[stage_id] if states.get(dep) != "passed"]
            if missing:
                raise CrossAssetContextError(f"stage {stage_id} has unsatisfied prerequisites: {missing}")
    current = str(payload.get("current_stage", ""))
    if current not in states or payload.get("current_state") != states[current]:
        raise CrossAssetContextError("current stage/state mismatch")
    if payload.get("actionable_arm_id") != "no_trade":
        raise CrossAssetContextError("actionable arm must remain no_trade")
    if payload.get("accepted_strategy_arms") != []:
        raise CrossAssetContextError("the research program cannot yet accept a strategy arm")
    if payload.get("approved_execution_instruments") != []:
        raise CrossAssetContextError("the research program cannot approve execution instruments")
    return current, states[current], active[0] if active else None


def _validate_decisions(path: Path) -> int:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise CrossAssetContextError(f"cannot read decision log: {path}") from exc
    if not lines:
        raise CrossAssetContextError("decision log is empty")
    previous: str | None = None
    for expected_sequence, line in enumerate(lines, start=1):
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CrossAssetContextError("invalid decision log JSON") from exc
        if line != canonical_json_line(record):
            raise CrossAssetContextError("decision log line is not canonical")
        if record.get("sequence") != expected_sequence:
            raise CrossAssetContextError("decision log sequence is not contiguous")
        if record.get("stage_id") not in STAGE_IDS:
            raise CrossAssetContextError("decision log references an unknown stage")
        if record.get("previous_record_digest") != previous:
            raise CrossAssetContextError("decision log chain is broken")
        _utc(record.get("recorded_at"), "decision recorded_at")
        if record.get("record_digest") != decision_digest(record):
            raise CrossAssetContextError("decision log digest mismatch")
        previous = str(record["record_digest"])
    return len(lines)


def _validate_artifacts(root: Path, artifacts: Any) -> set[str]:
    if not isinstance(artifacts, list) or not artifacts:
        raise CrossAssetContextError("status has no checksummed context artifacts")
    seen: set[str] = set()
    for item in artifacts:
        if not isinstance(item, dict):
            raise CrossAssetContextError("artifact record must be an object")
        raw_path = str(item.get("path", ""))
        if raw_path in seen:
            raise CrossAssetContextError(f"duplicate artifact path: {raw_path}")
        path = _repo_file(root, raw_path, "context artifact")
        if item.get("sha256") != sha256_file(path):
            raise CrossAssetContextError(f"context artifact checksum mismatch: {raw_path}")
        seen.add(raw_path)
    return seen


def _validate_module_isolation(path: Path) -> None:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError) as exc:
        raise CrossAssetContextError(f"cannot inspect isolated module: {path}") from exc
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module)
    forbidden = sorted(
        root
        for root in roots
        if any(root == blocked or root.startswith(f"{blocked}.") for blocked in FORBIDDEN_IMPORT_ROOTS)
    )
    if forbidden:
        raise CrossAssetContextError(f"isolated module imports forbidden dependencies: {forbidden}")


@dataclass(frozen=True, slots=True)
class CrossAssetValidation:
    program_id: str
    current_stage: str
    current_state: str
    active_stage: str | None
    artifact_count: int
    decision_records: int
    accepted_strategy_arms: int
    approved_execution_instruments: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "accepted_strategy_arms": self.accepted_strategy_arms,
            "active_stage": self.active_stage,
            "approved_execution_instruments": self.approved_execution_instruments,
            "artifact_count": self.artifact_count,
            "current_stage": self.current_stage,
            "current_state": self.current_state,
            "decision_records": self.decision_records,
            "program_id": self.program_id,
        }


def validate_cross_asset_context(
    repo_root: Path,
    program_path: Path,
    mandate_path: Path,
    access_path: Path,
    data_path: Path,
    status_path: Path,
) -> CrossAssetValidation:
    root = repo_root.resolve(strict=True)
    program = _load_canonical(program_path, "program contract")
    program_id, graph = _validate_program(program)
    _validate_mandate(_load_canonical(mandate_path, "research mandate"))
    _validate_access_matrix(_load_canonical(access_path, "instrument access matrix"))
    _validate_data_contract(_load_canonical(data_path, "data contract"))
    if program.get("schema_version") == "cross-asset-research-program-v2":
        _validate_futures_specs(
            _load_canonical(
                _repo_file(
                    root,
                    "config/research/cross-asset-futures-specs-v1.json",
                    "futures-spec registry",
                ),
                "futures-spec registry",
            )
        )
        _validate_futures_source_comparison(
            _load_canonical(
                _repo_file(
                    root,
                    "config/research/cross-asset-futures-source-comparison-v1.json",
                    "futures-source comparison",
                ),
                "futures-source comparison",
            )
        )
    status = _load_canonical(status_path, "program status")
    current, state, active = _validate_status(status, program_id, graph)
    if current != "A0":
        a1_path = _repo_file(root, status.get("a1_contract_path"), "A1 contract")
        _validate_a1_contract(_load_canonical(a1_path, "A1 source-pilot contract"))
        evidence_raw = status.get("a1_evidence_manifest_path")
        evidence_candidate = root / str(evidence_raw)
        if state in {"blocked", "passed", "rejected"} or evidence_candidate.is_file():
            evidence_path = _repo_file(
                root, status.get("a1_evidence_manifest_path"), "A1 evidence manifest"
            )
            evidence = _load_canonical(evidence_path, "A1 evidence manifest")
            if evidence.get("schema_version") in {
                "cross-asset-a1-oanda-source-successor-evidence-v1",
                "cross-asset-a1-oanda-hourly-successor-evidence-v1",
            }:
                contract_record = next(
                    (
                        item
                        for item in evidence.get("artifacts", ())
                        if item.get("path") == str(a1_path.relative_to(root))
                    ),
                    None,
                )
                if not isinstance(contract_record, Mapping) or contract_record.get(
                    "sha256"
                ) != sha256_file(a1_path):
                    raise CrossAssetContextError("OANDA evidence contract checksum mismatch")
            elif evidence.get("contract_sha256") != sha256_file(a1_path):
                raise CrossAssetContextError("A1 evidence contract checksum mismatch")
            a1_state = next(
                item.get("state") for item in status.get("stages", ()) if item.get("stage_id") == "A1"
            )
            _validate_a1_evidence(root, evidence, str(a1_state))
    if current in {"A2", "A3", "A4", "A5", "A6"}:
        a2_contract_path = _repo_file(root, status.get("a2_contract_path"), "A2 contract")
        _validate_a2_contract(_load_canonical(a2_contract_path, "A2 contract"))
        a2_evidence_path = _repo_file(
            root, status.get("a2_evidence_manifest_path"), "A2 evidence manifest"
        )
        a2_evidence = _load_canonical(a2_evidence_path, "A2 evidence manifest")
        contract_record = next(
            (
                item
                for item in a2_evidence.get("artifacts", ())
                if item.get("path") == str(a2_contract_path.relative_to(root))
            ),
            None,
        )
        if not isinstance(contract_record, Mapping) or contract_record.get("sha256") != sha256_file(
            a2_contract_path
        ):
            raise CrossAssetContextError("A2 evidence contract checksum mismatch")
        _validate_a2_evidence(root, a2_evidence)
        integrity_path = _repo_file(
            root,
            status.get("a2_integrity_evidence_manifest_path"),
            "A2 integrity evidence manifest",
        )
        _validate_a2_integrity_evidence(
            root, _load_canonical(integrity_path, "A2 integrity evidence manifest")
        )
        a3_path = _repo_file(root, status.get("a3_hypothesis_contract_path"), "A3 hypothesis")
        _validate_a3_hypothesis(_load_canonical(a3_path, "A3 hypothesis"))
    if current in {"A3", "A4", "A5", "A6"} and status.get("a3_contract_path"):
        prepartition_path = _repo_file(
            root,
            status.get("a3_prepartition_evidence_manifest_path"),
            "A3 prepartition evidence manifest",
        )
        prepartition = _load_canonical(prepartition_path, "A3 prepartition evidence manifest")
        _validate_a3_prepartition_evidence(root, prepartition)
        a3_contract_path = _repo_file(root, status.get("a3_contract_path"), "A3 contract")
        a3_contract = _load_canonical(a3_contract_path, "A3 contract")
        _validate_a3_contract(a3_contract)
        contract_record = next(
            (
                item
                for item in status.get("context_artifacts", ())
                if item.get("path") == str(a3_contract_path.relative_to(root))
            ),
            None,
        )
        if not isinstance(contract_record, Mapping) or contract_record.get("sha256") != sha256_file(
            a3_contract_path
        ):
            raise CrossAssetContextError("A3 status contract checksum mismatch")
        if status.get("a3_evidence_manifest_path"):
            a3_evidence_path = _repo_file(
                root, status.get("a3_evidence_manifest_path"), "A3 evidence manifest"
            )
            a3_evidence = _load_canonical(a3_evidence_path, "A3 evidence manifest")
            _validate_a3_evidence(root, a3_evidence)
            evidence_contract_record = next(
                (
                    item
                    for item in a3_evidence.get("artifacts", ())
                    if item.get("path") == str(a3_contract_path.relative_to(root))
                ),
                None,
            )
            if not isinstance(evidence_contract_record, Mapping) or evidence_contract_record.get(
                "sha256"
            ) != sha256_file(a3_contract_path):
                raise CrossAssetContextError("A3 evidence contract checksum mismatch")
    artifacts = _validate_artifacts(root, status.get("context_artifacts"))
    required = set(program.get("required_session_start_paths", ()))
    implicit = {
        str(program_path.resolve(strict=True).relative_to(root)),
        str(mandate_path.resolve(strict=True).relative_to(root)),
        str(access_path.resolve(strict=True).relative_to(root)),
        str(data_path.resolve(strict=True).relative_to(root)),
        str(status_path.resolve(strict=True).relative_to(root)),
    }
    missing = sorted(required - artifacts - implicit)
    if missing:
        raise CrossAssetContextError(f"status omits session-start artifacts: {missing}")
    decision_path = _repo_file(root, status.get("decision_log_path"), "decision log")
    decision_count = _validate_decisions(decision_path)
    if status.get("latest_decision_digest") != json.loads(
        decision_path.read_text(encoding="utf-8").splitlines()[-1]
    )["record_digest"]:
        raise CrossAssetContextError("status latest decision digest is stale")
    for raw_path in status.get("isolated_module_paths", ()):
        _validate_module_isolation(_repo_file(root, raw_path, "isolated module"))
    return CrossAssetValidation(
        program_id=program_id,
        current_stage=current,
        current_state=state,
        active_stage=active,
        artifact_count=len(artifacts),
        decision_records=decision_count,
        accepted_strategy_arms=len(status["accepted_strategy_arms"]),
        approved_execution_instruments=len(status["approved_execution_instruments"]),
    )


def validate_artifact_lineage(repo_root: Path, artifacts: Sequence[Mapping[str, Any]]) -> None:
    """Public fixture helper used by tests to prove changed artifacts fail closed."""

    _validate_artifacts(repo_root.resolve(strict=True), list(artifacts))
