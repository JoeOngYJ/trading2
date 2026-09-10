"""Fail-closed context validation for the offline cash-ETF research successor.

This module owns repository context only.  It intentionally has no network, broker,
database, message-bus, runtime-signal, order, or position dependency.
"""

from __future__ import annotations

import ast
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping


PROGRAM_ID = "retail-cash-etf-multi-strategy-v1"
STAGE_IDS = tuple(f"C{index}" for index in range(8))
STAGE_STATES = frozenset({"planned", "active", "passed", "rejected", "blocked", "skipped"})
TERMINAL_STATES = frozenset({"passed", "rejected", "blocked", "skipped"})
PROXY_SYMBOLS = ("BIL", "DBC", "EFA", "GBP/USD", "GLD", "IEF", "SPY", "TLT")
RISKY_PROXY_SYMBOLS = ("DBC", "EFA", "GLD", "IEF", "SPY", "TLT")
EXACT_UK_SYMBOLS = ("AGCP", "IGLT", "SGLN", "SWDA")
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


class CashEtfContextError(ValueError):
    """Raised when the cash-ETF context is unsafe, stale, or inconsistent."""


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
        raise CashEtfContextError(f"cannot read {label}: {path}") from exc
    if not isinstance(payload, dict) or raw != canonical_json(payload):
        raise CashEtfContextError(f"{label} must be a canonical JSON object")
    return payload


def _repo_file(root: Path, raw: Any, label: str) -> Path:
    if not isinstance(raw, str) or not raw or Path(raw).is_absolute():
        raise CashEtfContextError(f"{label} must be a repository-relative path")
    boundary = root.resolve(strict=True)
    try:
        candidate = (boundary / raw).resolve(strict=True)
        candidate.relative_to(boundary)
    except (OSError, ValueError) as exc:
        raise CashEtfContextError(f"invalid {label}: {raw}") from exc
    if not candidate.is_file():
        raise CashEtfContextError(f"{label} is not a regular file: {raw}")
    return candidate


def _utc(raw: Any, label: str) -> datetime:
    if not isinstance(raw, str) or not raw.endswith("Z"):
        raise CashEtfContextError(f"{label} must use explicit UTC Z")
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CashEtfContextError(f"invalid {label}: {raw}") from exc
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise CashEtfContextError(f"{label} must use UTC")
    return value


def _validate_mandate(payload: Mapping[str, Any]) -> None:
    if (
        payload.get("schema_version") != "cash-etf-research-mandate-v1"
        or payload.get("mandate_id") != "retail-cash-etf-research-v1"
        or payload.get("status") != "frozen_offline_research_only"
    ):
        raise CashEtfContextError("unexpected cash-ETF mandate")
    authority = payload.get("authority", {})
    required_false = (
        "broker_private_state_access_allowed",
        "execution_credentials_allowed",
        "live_trading_authorized",
        "order_submission_allowed",
        "paper_trading_authorized",
    )
    if any(authority.get(key) is not False for key in required_false):
        raise CashEtfContextError("cash-ETF mandate grants unsafe authority")
    boundary = payload.get("instrument_boundary", {})
    if boundary.get("direct_futures_allowed") is not False:
        raise CashEtfContextError("direct futures must be prohibited")
    if boundary.get("initial_direction") != "long_or_flat" or boundary.get("leverage_allowed") is not False:
        raise CashEtfContextError("initial cash-ETF direction or leverage changed")
    if payload.get("capital", {}).get("research_equity_gbp") != 20000:
        raise CashEtfContextError("research capital changed")
    if payload.get("capital", {}).get("hard_drawdown_ceiling_fraction") != 0.2:
        raise CashEtfContextError("hard drawdown ceiling changed")


def _validate_program(payload: Mapping[str, Any]) -> dict[str, tuple[str, ...]]:
    if payload.get("schema_version") != "cash-etf-research-program-v1":
        raise CashEtfContextError("unsupported cash-ETF program schema")
    if payload.get("program_id") != PROGRAM_ID:
        raise CashEtfContextError("unexpected cash-ETF program ID")
    stages = payload.get("stages")
    if not isinstance(stages, list) or tuple(row.get("stage_id") for row in stages) != STAGE_IDS:
        raise CashEtfContextError("cash-ETF stages must be ordered C0 through C7")
    graph: dict[str, tuple[str, ...]] = {}
    for row in stages:
        stage_id = str(row["stage_id"])
        dependencies = tuple(str(value) for value in row.get("dependencies", ()))
        if len(dependencies) != len(set(dependencies)):
            raise CashEtfContextError(f"stage {stage_id} repeats a dependency")
        if any(value not in STAGE_IDS[: STAGE_IDS.index(stage_id)] for value in dependencies):
            raise CashEtfContextError(f"stage {stage_id} has a non-prior dependency")
        if not all(row.get(key) for key in ("objective", "pass_gate", "next_action")):
            raise CashEtfContextError(f"stage {stage_id} is incomplete")
        graph[stage_id] = dependencies
    safety = payload.get("safety_boundaries", {})
    for key in (
        "database_access_allowed",
        "direct_futures_data_allowed",
        "exchange_access_allowed",
        "live_trading_authorized",
        "message_bus_access_allowed",
        "order_intent_creation_allowed",
        "position_creation_allowed",
        "production_signal_creation_allowed",
        "running_soak_access_allowed",
    ):
        if safety.get(key) is not False:
            raise CashEtfContextError(f"unsafe program permission: {key}")
    if safety.get("actionable_arm_id") != "no_trade":
        raise CashEtfContextError("actionable arm must remain no_trade")
    return graph


def _validate_registry(payload: Mapping[str, Any]) -> None:
    if payload.get("schema_version") != "cash-etf-proxy-registry-v1":
        raise CashEtfContextError("unsupported cash-ETF proxy registry")
    proxies = payload.get("proxy_instruments", [])
    if tuple(sorted(row.get("symbol") for row in proxies)) != PROXY_SYMBOLS:
        raise CashEtfContextError("proxy universe changed")
    if any(row.get("execution_eligible") is not False for row in proxies):
        raise CashEtfContextError("a proxy instrument became execution eligible")
    if any(row.get("evidence_status") != "proxy_only" for row in proxies):
        raise CashEtfContextError("proxy evidence status changed")
    exact = payload.get("precommitted_exact_uk_candidates", [])
    if tuple(sorted(row.get("symbol") for row in exact)) != EXACT_UK_SYMBOLS:
        raise CashEtfContextError("exact UK candidate set changed")
    if any(row.get("execution_state") != "conditional_unapproved" for row in exact):
        raise CashEtfContextError("an exact UK line became approved")
    if payload.get("actionable_arm_id") != "no_trade":
        raise CashEtfContextError("registry actionable arm changed")


def _validate_boundaries(payload: Mapping[str, Any]) -> None:
    if payload.get("schema_version") != "cash-etf-evidence-boundaries-v1":
        raise CashEtfContextError("unsupported evidence-boundary schema")
    if payload.get("strategy_families_frozen_before_economics") != [
        "cash_etf_slow_trend",
        "cash_etf_turn_of_month",
    ]:
        raise CashEtfContextError("strategy family freeze changed")
    expected = (
        ("development", "2009-01-02T00:00:00Z", "2019-01-01T00:00:00Z", "open"),
        ("validation", "2019-01-01T00:00:00Z", "2024-01-01T00:00:00Z", "locked"),
        ("historical_confirmation", "2024-01-01T00:00:00Z", "2026-01-01T00:00:00Z", "locked"),
        ("excluded_2026", "2026-01-01T00:00:00Z", "2027-01-01T00:00:00Z", "excluded"),
    )
    observed = tuple(
        (row.get("partition_id"), row.get("start_inclusive"), row.get("end_exclusive"), row.get("state"))
        for row in payload.get("partitions", ())
    )
    if observed != expected:
        raise CashEtfContextError("cash-ETF evidence boundaries changed")
    for _, start, end, _ in expected:
        if _utc(start, "partition start") >= _utc(end, "partition end"):
            raise CashEtfContextError("reversed evidence partition")


def _validate_strategy_contract(payload: Mapping[str, Any], experiment_id: str) -> None:
    if payload.get("schema_version") != "cash-etf-proxy-strategy-contract-v1":
        raise CashEtfContextError("unsupported proxy strategy contract")
    if payload.get("experiment_id") != experiment_id or payload.get("status") != "frozen":
        raise CashEtfContextError("unexpected or unfrozen proxy strategy contract")
    if payload.get("economic_results_read_before_freeze") is not False:
        raise CashEtfContextError("strategy was not frozen price-blind")
    if payload.get("actionable_arm_id") != "no_trade" or payload.get("proxy_only") is not True:
        raise CashEtfContextError("proxy strategy escaped the counterfactual boundary")
    if payload.get("cost_scenarios_round_trip_bps") != [10, 25, 50]:
        raise CashEtfContextError("strategy cost grid changed")
    if payload.get("primary_cost_round_trip_bps") != 25:
        raise CashEtfContextError("primary strategy cost changed")
    if experiment_id == "cash-etf-slow-trend-proxy-v1":
        rule = payload.get("rule", {})
        if rule.get("lookback_sessions") != 252 or rule.get("allocation_per_risky_proxy") != "0.1666666666666666666666666667":
            raise CashEtfContextError("slow-trend rule changed")
        if tuple(sorted(rule.get("risky_proxy_symbols", ()))) != RISKY_PROXY_SYMBOLS:
            raise CashEtfContextError("slow-trend proxy universe changed")
    else:
        rule = payload.get("rule", {})
        if rule.get("symbols") != ["EFA", "SPY"] or rule.get("entry_session") != "final_us_session_open":
            raise CashEtfContextError("turn-of-month rule changed")
        if rule.get("exit_session") != "fourth_us_session_next_month_open":
            raise CashEtfContextError("turn-of-month exit changed")


def _validate_decisions(path: Path) -> tuple[int, str]:
    previous: str | None = None
    count = 0
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            record = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CashEtfContextError(f"invalid decision log line {line_number}") from exc
        if raw != canonical_json_line(record):
            raise CashEtfContextError("decision log is not canonical JSONL")
        if record.get("program_id") != PROGRAM_ID or record.get("previous_record_digest") != previous:
            raise CashEtfContextError("decision log chain changed")
        if decision_digest(record) != record.get("record_digest"):
            raise CashEtfContextError("decision record digest mismatch")
        _utc(record.get("decided_at"), "decision timestamp")
        previous = str(record["record_digest"])
        count += 1
    if count == 0 or previous is None:
        raise CashEtfContextError("decision log cannot be empty")
    return count, previous


def _validate_imports(root: Path, paths: list[str]) -> None:
    for raw in paths:
        path = _repo_file(root, raw, "isolated module")
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if any(name == root_name or name.startswith(root_name + ".") for root_name in FORBIDDEN_IMPORT_ROOTS):
                    raise CashEtfContextError(f"forbidden import in {raw}: {name}")


def _validate_c1_blocked(root: Path, status: Mapping[str, Any]) -> None:
    path = _repo_file(root, status.get("c1_evidence_manifest_path"), "C1 evidence manifest")
    evidence = _load_canonical(path, "C1 evidence manifest")
    if evidence.get("schema_version") != "cash-etf-c1-prepartition-evidence-v1":
        raise CashEtfContextError("unsupported C1 evidence schema")
    if evidence.get("experiment_id") != "cash-etf-c1-prepartition-v1":
        raise CashEtfContextError("unexpected C1 experiment")
    if evidence.get("decision") != "timestamp_prepartition_passed_source_qualification_blocked":
        raise CashEtfContextError("C1 blocked decision changed")
    if evidence.get("source_qualification_blocker") != "complete_issuer_action_reconciliation_missing":
        raise CashEtfContextError("C1 source blocker changed")
    for key in (
        "economic_metrics_computed",
        "numeric_fields_deserialized",
        "strategy_features_or_signals_computed",
    ):
        if evidence.get(key) is not False:
            raise CashEtfContextError(f"C1 unsafe evidence claim: {key}")
    for record in evidence.get("artifacts", ()):
        artifact = _repo_file(root, record.get("path"), "C1 evidence artifact")
        if sha256_file(artifact) != record.get("sha256"):
            raise CashEtfContextError(f"C1 artifact checksum changed: {record.get('path')}")

    action_path = _repo_file(
        root,
        status.get("c1_official_action_evidence_path"),
        "C1 official-action evidence manifest",
    )
    action_evidence = _load_canonical(action_path, "C1 official-action evidence manifest")
    if (
        action_evidence.get("schema_version")
        != "cash-etf-c1-issuer-action-ledger-source-evidence-v1"
        or action_evidence.get("experiment_id")
        != "cash-etf-c1-issuer-action-ledger-source-v2"
        or action_evidence.get("decision") != "issuer_action_source_gate_blocked"
    ):
        raise CashEtfContextError("unexpected C1 official-action evidence")
    for key in (
        "economic_metrics_computed",
        "forbidden_market_data_preserved",
        "numeric_ledger_built",
        "strategy_evaluation_run",
    ):
        if action_evidence.get(key) is not False:
            raise CashEtfContextError(f"C1 unsafe official-action claim: {key}")
    action_artifacts: dict[str, Path] = {}
    for record in action_evidence.get("artifacts", ()):
        artifact = _repo_file(root, record.get("path"), "C1 official-action artifact")
        if sha256_file(artifact) != record.get("sha256"):
            raise CashEtfContextError(
                f"C1 official-action checksum changed: {record.get('path')}"
            )
        action_artifacts[str(record.get("path"))] = artifact
    report_key = (
        "artifacts/agent-level-experiment/cash-etf/"
        "c1-issuer-action-ledger-source-v2/reconciliation-report.json"
    )
    report = _load_canonical(action_artifacts.get(report_key, Path("missing")), "C1 action report")
    if (
        report.get("decision") != "blocked"
        or report.get("actionable_arm_id") != "no_trade"
        or report.get("approved_execution_instruments") != []
        or any(row.get("instrument_passed") is not False for row in report.get("instrument_results", ()))
    ):
        raise CashEtfContextError("C1 action report escaped the blocked/no-trade boundary")
    by_symbol = {row.get("symbol"): row for row in report.get("instrument_results", ())}
    if (
        report.get("historical_nyse_arca_rule_verified") is not True
        or report.get("source_failures") != 0
        or by_symbol.get("DBC", {}).get("distribution_status") != "passed"
        or by_symbol.get("GLD", {}).get("distribution_status") != "unresolved"
        or any(
            by_symbol.get(symbol, {}).get("split_status") != "unresolved"
            for symbol in ("SPY", "EFA", "IEF", "TLT", "GLD", "DBC")
        )
        or by_symbol.get("BIL", {}).get("split_status") != "passed"
    ):
        raise CashEtfContextError("C1 issuer-action findings changed")

    availability_path = _repo_file(
        root,
        status.get("c1_archive_availability_evidence_path"),
        "C1 archive-availability evidence manifest",
    )
    availability_evidence = _load_canonical(
        availability_path, "C1 archive-availability evidence manifest"
    )
    if (
        availability_evidence.get("schema_version")
        != "cash-etf-c1-corporate-action-archive-availability-evidence-v1"
        or availability_evidence.get("experiment_id")
        != "cash-etf-c1-corporate-action-archive-availability-v1"
        or availability_evidence.get("decision")
        != "blocked_no_purchase_eligible_candidate"
    ):
        raise CashEtfContextError("unexpected C1 archive-availability evidence")
    for key in (
        "data_purchase_authorized",
        "economic_metrics_computed",
        "numeric_ledger_built",
        "strategy_evaluation_run",
    ):
        if availability_evidence.get(key) is not False:
            raise CashEtfContextError(f"C1 unsafe archive-availability claim: {key}")
    if (
        availability_evidence.get("actionable_arm_id") != "no_trade"
        or availability_evidence.get("approved_execution_instruments") != []
        or availability_evidence.get("purchase_eligible_candidates") != []
    ):
        raise CashEtfContextError("C1 archive availability escaped the blocked boundary")
    availability_artifacts: dict[str, Path] = {}
    for record in availability_evidence.get("artifacts", ()):
        artifact = _repo_file(root, record.get("path"), "C1 archive-availability artifact")
        if sha256_file(artifact) != record.get("sha256"):
            raise CashEtfContextError(
                f"C1 archive-availability checksum changed: {record.get('path')}"
            )
        availability_artifacts[str(record.get("path"))] = artifact

    availability_root = (
        "artifacts/agent-level-experiment/cash-etf/"
        "c1-corporate-action-archive-availability-v1/"
    )
    availability_report = _load_canonical(
        availability_artifacts.get(availability_root + "availability-report.json", Path("missing")),
        "C1 archive-availability report",
    )
    expected_candidate_decisions = {
        "eodhd_corporate_actions_api": "rejected",
        "factset_corporate_actions": "contact_required",
        "ice_corporate_actions": "contact_required",
        "lseg_corporate_actions": "contact_required",
        "massive_corporate_actions_api": "rejected",
        "nyse_group_corporate_actions": "contact_required",
    }
    observed_candidate_decisions = {
        str(row.get("candidate_id")): str(row.get("decision"))
        for row in availability_report.get("candidate_results", ())
    }
    if (
        availability_report.get("decision") != "blocked_no_purchase_eligible_candidate"
        or availability_report.get("whole_gate_passed") is not False
        or availability_report.get("data_purchase_authorized") is not False
        or availability_report.get("purchase_eligible_candidates") != []
        or availability_report.get("approved_execution_instruments") != []
        or availability_report.get("accepted_strategy_arms") != []
        or availability_report.get("actionable_arm_id") != "no_trade"
        or observed_candidate_decisions != expected_candidate_decisions
    ):
        raise CashEtfContextError("C1 archive-availability findings changed")
    eodhd = next(
        row
        for row in availability_report["candidate_results"]
        if row["candidate_id"] == "eodhd_corporate_actions_api"
    )
    massive = next(
        row
        for row in availability_report["candidate_results"]
        if row["candidate_id"] == "massive_corporate_actions_api"
    )
    if (
        eodhd.get("findings", {}).get("archive_retention")
        != "failed_delete_within_one_month_after_subscription"
        or massive.get("findings", {}).get("archive_retention")
        != "failed_public_terms_grant_display_use_only_absent_separate_agreement"
    ):
        raise CashEtfContextError("C1 archive-retention findings changed")

    source_manifest = _load_canonical(
        availability_artifacts.get(availability_root + "source-manifest.json", Path("missing")),
        "C1 archive source manifest",
    )
    if (
        source_manifest.get("schema_version") != "cash-etf-c1-archive-source-manifest-v1"
        or source_manifest.get("response_count") != 15
        or len(source_manifest.get("sources", ())) != 15
        or source_manifest.get("full_commercial_pages_preserved") is not False
    ):
        raise CashEtfContextError("C1 archive source manifest changed")
    if any(
        row.get("http_status") != 200
        or not isinstance(row.get("response_sha256"), str)
        or len(row["response_sha256"]) != 64
        for row in source_manifest["sources"]
    ):
        raise CashEtfContextError("C1 archive source response invalid")


def _validate_c1_passed(root: Path, status: Mapping[str, Any]) -> None:
    path = _repo_file(
        root, status.get("c1_pragmatic_ledger_evidence_path"), "C1 pragmatic ledger evidence"
    )
    evidence = _load_canonical(path, "C1 pragmatic ledger evidence")
    if (
        evidence.get("schema_version") != "cash-etf-c1-pragmatic-action-ledger-evidence-v2"
        or evidence.get("experiment_id") != "cash-etf-c1-pragmatic-action-ledger-v5"
        or evidence.get("decision") != "pragmatic_action_ledger_passed"
        or evidence.get("numeric_total_return_ledger_built") is not True
        or evidence.get("strategy_evaluation_run") is not False
        or evidence.get("actionable_arm_id") != "no_trade"
        or evidence.get("accepted_strategy_arms") != []
        or evidence.get("approved_execution_instruments") != []
    ):
        raise CashEtfContextError("unexpected C1 pragmatic ledger evidence")
    artifacts: dict[str, Path] = {}
    for record in evidence.get("artifacts", ()):
        artifact = _repo_file(root, record.get("path"), "C1 pragmatic ledger artifact")
        if sha256_file(artifact) != record.get("sha256"):
            raise CashEtfContextError(f"C1 pragmatic checksum changed: {record.get('path')}")
        artifacts[str(record.get("path"))] = artifact
    report_key = (
        "artifacts/agent-level-experiment/cash-etf/"
        "c1-pragmatic-action-ledger-v5/ledger-report.json"
    )
    report = _load_canonical(artifacts.get(report_key, Path("missing")), "C1 pragmatic report")
    results = report.get("instrument_results", ())
    if (
        report.get("decision") != "passed"
        or report.get("whole_universe_gate_passed") is not True
        or report.get("numeric_locked_partitions_deserialized") is not False
        or report.get("fx_post_boundary_rows_deserialized") != 0
        or report.get("official_fx_patch_observation_count") != 4
        or report.get("provider_dividends_used_for_cash_credit") is not False
        or report.get("strategy_evaluation_run") is not False
        or report.get("approved_execution_instruments") != []
        or len(results) != 7
        or any(
            row.get("instrument_passed") is not True
            or row.get("ledger_currency") != "GBP"
            or row.get("row_count") != 2516
            or row.get("start_session") != "2009-01-02"
            or row.get("end_session") != "2018-12-31"
            or row.get("post_boundary_rows_deserialized") != 0
            for row in results
        )
    ):
        raise CashEtfContextError("C1 pragmatic ledger findings changed")


def validate_context(repo_root: Path) -> dict[str, Any]:
    root = repo_root.resolve(strict=True)
    program = _load_canonical(root / "config/research/cash-etf-program-v1.json", "program")
    mandate = _load_canonical(root / "config/mandates/retail-cash-etf-research-v1.json", "mandate")
    registry = _load_canonical(root / "config/research/cash-etf-proxy-registry-v1.json", "registry")
    boundaries = _load_canonical(root / "config/research/cash-etf-evidence-boundaries-v1.json", "boundaries")
    status = _load_canonical(root / "config/research/cash-etf-status-v1.json", "status")
    graph = _validate_program(program)
    _validate_mandate(mandate)
    _validate_registry(registry)
    _validate_boundaries(boundaries)
    _validate_strategy_contract(
        _load_canonical(root / "config/experiments/cash-etf-slow-trend-proxy-v1.json", "slow trend"),
        "cash-etf-slow-trend-proxy-v1",
    )
    _validate_strategy_contract(
        _load_canonical(root / "config/experiments/cash-etf-turn-of-month-proxy-v1.json", "turn of month"),
        "cash-etf-turn-of-month-proxy-v1",
    )
    if status.get("schema_version") != "cash-etf-program-status-v1" or status.get("program_id") != PROGRAM_ID:
        raise CashEtfContextError("unexpected cash-ETF status")
    states = {str(row.get("stage_id")): str(row.get("state")) for row in status.get("stages", ())}
    if tuple(states) != STAGE_IDS or any(value not in STAGE_STATES for value in states.values()):
        raise CashEtfContextError("invalid cash-ETF stage states")
    active = [stage_id for stage_id, state in states.items() if state == "active"]
    if len(active) > 1:
        raise CashEtfContextError("only one cash-ETF stage may be active")
    for stage_id, state in states.items():
        if state in TERMINAL_STATES or state == "active":
            if any(states[dependency] != "passed" for dependency in graph[stage_id]):
                raise CashEtfContextError(f"stage {stage_id} skipped a prerequisite")
    current = str(status.get("current_stage"))
    if current not in states or status.get("current_state") != states[current]:
        raise CashEtfContextError("current cash-ETF status is inconsistent")
    if active and active != [current]:
        raise CashEtfContextError("current stage must be the active stage")
    if status.get("actionable_arm_id") != "no_trade" or status.get("accepted_strategy_arms") != []:
        raise CashEtfContextError("cash-ETF status claims actionable or accepted alpha")
    if status.get("approved_execution_instruments") != []:
        raise CashEtfContextError("cash-ETF status claims an approved execution instrument")
    if states.get("C1") == "blocked":
        _validate_c1_blocked(root, status)
    elif states.get("C1") == "passed":
        _validate_c1_passed(root, status)
    decisions_path = _repo_file(root, status.get("decision_log_path"), "decision log")
    decision_count, latest_digest = _validate_decisions(decisions_path)
    if status.get("latest_decision_digest") != latest_digest:
        raise CashEtfContextError("status does not bind the latest decision")
    for record in status.get("context_artifacts", ()):
        path = _repo_file(root, record.get("path"), "context artifact")
        if sha256_file(path) != record.get("sha256"):
            raise CashEtfContextError(f"context checksum changed: {record.get('path')}")
    _validate_imports(root, list(status.get("isolated_module_paths", ())))
    return {
        "accepted_strategy_arms": 0,
        "active_stage": active[0] if active else None,
        "approved_execution_instruments": 0,
        "artifact_count": len(status.get("context_artifacts", ())),
        "current_stage": current,
        "current_state": states[current],
        "decision": "context_valid",
        "decision_records": decision_count,
        "program_id": PROGRAM_ID,
    }
