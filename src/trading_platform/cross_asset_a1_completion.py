from __future__ import annotations

import hashlib
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping


class A1CompletionError(ValueError):
    """Raised when completion-review evidence is invalid or unsafe."""


ALLOWED_SOURCE_HOSTS = {
    "helpcentre.trading212.com",
    "support.twelvedata.com",
    "twelvedata.com",
    "www.interactivebrokers.co.uk",
    "www.interactivebrokers.com",
    "www.ishares.com",
    "www.sec.gov",
}

NORMALIZED_ACTION_FILES = {
    "EFA": "artifacts/agent-level-experiment/cross-asset/a1-twelvedata-recovery-v3/normalized/efa-dividends.jsonl",
    "IEF": "artifacts/agent-level-experiment/cross-asset/a1-twelvedata-recovery-v3/normalized/ief-dividends.jsonl",
    "TLT": "artifacts/agent-level-experiment/cross-asset/a1-twelvedata-recovery-v3/normalized/tlt-dividends.jsonl",
}


def canonical_json(payload: Any) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        indent=2,
        separators=(",", ": "),
        ensure_ascii=False,
        allow_nan=False,
    )


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_canonical(path: Path, label: str) -> Mapping[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
        payload = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise A1CompletionError(f"cannot read {label}") from exc
    if not isinstance(payload, dict):
        raise A1CompletionError(f"{label} must be an object")
    if raw != f"{canonical_json(payload)}\n" and raw != json.dumps(
        payload, sort_keys=True, indent=2, ensure_ascii=False
    ) + "\n":
        raise A1CompletionError(f"{label} is not deterministically serialized")
    return payload


def _load_actions(path: Path) -> dict[tuple[str, str], Mapping[str, Any]]:
    actions: dict[tuple[str, str], Mapping[str, Any]] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise A1CompletionError(f"cannot read normalized action file: {path}") from exc
    for line_number, line in enumerate(lines, start=1):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise A1CompletionError(f"invalid action JSON at {path}:{line_number}") from exc
        key = (str(row.get("action_type")), str(row.get("action_date")))
        if key in actions:
            raise A1CompletionError(f"duplicate normalized action: {path}:{key}")
        actions[key] = row
    return actions


def _validate_sources(facts: Mapping[str, Any]) -> None:
    references = facts.get("source_references")
    if not isinstance(references, list) or not references:
        raise A1CompletionError("completion facts omit official source references")
    for reference in references:
        url = str(reference.get("url", ""))
        if not url.startswith("https://"):
            raise A1CompletionError("completion source must use HTTPS")
        host = url.split("/", 3)[2]
        if host not in ALLOWED_SOURCE_HOSTS:
            raise A1CompletionError(f"completion source host is not official: {host}")


def _sample_results(root: Path, facts: Mapping[str, Any]) -> list[dict[str, Any]]:
    loaded: dict[str, dict[tuple[str, str], Mapping[str, Any]]] = {}
    results: list[dict[str, Any]] = []
    samples = facts.get("corporate_action_samples")
    if not isinstance(samples, list) or not samples:
        raise A1CompletionError("completion facts omit corporate-action samples")
    for sample in samples:
        symbol = str(sample.get("symbol"))
        if symbol not in NORMALIZED_ACTION_FILES:
            raise A1CompletionError(f"unsupported corporate-action sample symbol: {symbol}")
        if symbol not in loaded:
            loaded[symbol] = _load_actions(root / NORMALIZED_ACTION_FILES[symbol])
        key = (str(sample.get("action_type")), str(sample.get("action_date")))
        provider = loaded[symbol].get(key)
        if provider is None:
            raise A1CompletionError(f"issuer action sample is absent from provider data: {symbol} {key}")
        try:
            issuer_amount = Decimal(str(sample["issuer_amount"]))
            provider_amount = Decimal(str(provider["amount_per_share"]))
            tolerance = Decimal(str(sample["maximum_absolute_difference"]))
        except (KeyError, InvalidOperation) as exc:
            raise A1CompletionError("invalid corporate-action sample amount") from exc
        difference = abs(issuer_amount - provider_amount)
        if difference > tolerance:
            raise A1CompletionError(
                f"issuer sample disagrees with provider data: {symbol} {key[1]}"
            )
        results.append(
            {
                "action_date": key[1],
                "action_type": key[0],
                "absolute_difference": format(difference, "f"),
                "issuer_amount": format(issuer_amount, "f"),
                "matched": True,
                "maximum_absolute_difference": format(tolerance, "f"),
                "provider_amount": format(provider_amount, "f"),
                "provider_source_sha256": str(provider.get("source_lineage_sha256")),
                "symbol": symbol,
            }
        )
    return results


def build_completion_report(
    root: Path, contract_path: Path, facts_path: Path
) -> dict[str, Any]:
    contract = _load_canonical(contract_path, "A1 completion contract")
    facts = _load_canonical(facts_path, "A1 completion source facts")
    if contract.get("schema_version") != "cross-asset-a1-completion-review-contract-v1":
        raise A1CompletionError("unexpected A1 completion contract schema")
    if facts.get("schema_version") != "cross-asset-a1-completion-source-facts-v1":
        raise A1CompletionError("unexpected A1 completion facts schema")
    if facts.get("review_id") != contract.get("review_id"):
        raise A1CompletionError("completion contract and fact IDs differ")
    for key, value in contract.get("prohibitions", {}).items():
        if value is not False:
            raise A1CompletionError(f"unsafe completion contract permission: {key}")
    _validate_sources(facts)
    samples = _sample_results(root, facts)

    corporate = facts.get("corporate_action_findings")
    expected_symbols = tuple(item["symbol"] for item in contract["instruments"])
    if not isinstance(corporate, list) or tuple(item.get("symbol") for item in corporate) != expected_symbols:
        raise A1CompletionError("corporate-action findings do not cover the frozen universe")
    corporate_passed = all(item.get("full_history_reconciled") is True for item in corporate)
    gate_results = {
        "archival_use": {
            "passed": facts.get("archival_use", {}).get("gate_passed") is True,
            "status": "failed",
        },
        "corporate_actions": {
            "passed": corporate_passed,
            "status": "passed" if corporate_passed else "incomplete",
        },
        "cost_model": {
            "passed": facts.get("cost_findings", {}).get("gate_passed") is True,
            "status": "incomplete",
        },
        "executable_mapping": {
            "passed": facts.get("execution_mapping", {}).get("gate_passed") is True,
            "status": "failed",
        },
    }
    a1_passed = all(result["passed"] for result in gate_results.values())
    if a1_passed:
        raise A1CompletionError("public-document review cannot silently pass A1")

    return {
        "a1_stage_passed": False,
        "accepted_strategy_arms": [],
        "approved_execution_instruments": [],
        "contract_sha256": sha256_file(contract_path),
        "corporate_action_findings": corporate,
        "corporate_action_sample_results": samples,
        "decision": "a1_blocked_completion_gates",
        "facts_sha256": sha256_file(facts_path),
        "gate_results": gate_results,
        "next_permitted_actions": [
            "Obtain a written Twelve Data retention amendment before subscription termination, or replace the source with one whose archival rights meet the data contract.",
            "Choose the actual UK-retail broker and exact cash trading lines; confirm them through a separately authorized read-only account check.",
            "Qualify history for those same executable trading lines, including complete issuer actions and effective-dated costs.",
        ],
        "review_id": contract["review_id"],
        "safety": {
            "account_login_used": False,
            "broker_credentials_used": False,
            "economic_metrics_computed": False,
            "features_generated": False,
            "incidental_market_data_retained": False,
            "new_market_prices_downloaded": False,
            "partial_ob0_accessed": False,
            "pnl_computed": False,
            "protected_services_accessed": False,
            "returns_computed": False,
            "sealed_2026_partition_accessed": False,
            "strategy_signals_generated": False,
        },
        "schema_version": "cross-asset-a1-completion-report-v1",
        "source_references": facts["source_references"],
    }


def write_completion_evidence(
    root: Path, contract_path: Path, facts_path: Path, output_root: Path
) -> tuple[Path, Path]:
    report = build_completion_report(root, contract_path, facts_path)
    output_root.mkdir(parents=True, exist_ok=True)
    report_path = output_root / "audit-report.json"
    report_path.write_text(f"{canonical_json(report)}\n", encoding="utf-8")
    facts_relative = facts_path.resolve().relative_to(root.resolve()).as_posix()
    report_relative = report_path.resolve().relative_to(root.resolve()).as_posix()
    evidence = {
        "artifacts": [
            {
                "bytes": facts_path.stat().st_size,
                "path": facts_relative,
                "sha256": sha256_file(facts_path),
            },
            {
                "bytes": report_path.stat().st_size,
                "path": report_relative,
                "sha256": sha256_file(report_path),
            },
        ],
        "contract_sha256": sha256_file(contract_path),
        "decision": report["decision"],
        "review_id": report["review_id"],
        "schema_version": "cross-asset-a1-completion-evidence-manifest-v1",
    }
    evidence_path = output_root / "evidence-manifest.json"
    evidence_path.write_text(f"{canonical_json(evidence)}\n", encoding="utf-8")
    return report_path, evidence_path
