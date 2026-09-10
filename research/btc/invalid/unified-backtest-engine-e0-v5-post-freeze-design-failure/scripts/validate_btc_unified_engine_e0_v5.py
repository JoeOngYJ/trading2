#!/usr/bin/env python3
"""Validate the E0-v5 BTC backtest component design without engine or market access."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "research/btc/contracts/btc-unified-backtest-engine-e0-v5-component-boundaries.json"
INTERFACES_PATH = ROOT / "research/btc/specs/btc-backtest-component-interfaces-e0-v5.json"
FIXTURES_PATH = ROOT / "research/btc/specs/btc-backtest-component-fixtures-e0-v5.json"
EXPERIMENT_ID = "btc-unified-backtest-engine-e0-v5-component-boundaries"
PASS_DECISION = "E0_v5_component_design_passed_only_C0_freeze_permitted"


class E0V5ValidationError(ValueError):
    pass


def canonical_json(value: Any) -> str:
    return json.dumps(
        value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False
    ) + "\n"


def canonical_line(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


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
            raise E0V5ValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_nonfinite(token: str) -> None:
    raise E0V5ValidationError(f"non-finite JSON value: {token}")


def load_canonical(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
        value = json.loads(
            raw,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise E0V5ValidationError(f"cannot parse canonical JSON: {path}") from exc
    if not isinstance(value, dict) or raw != canonical_json(value):
        raise E0V5ValidationError(f"non-canonical JSON: {path}")
    _reject_nonfinite_recursive(value)
    return value


def _reject_nonfinite_recursive(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise E0V5ValidationError("non-finite number")
    if isinstance(value, dict):
        for item in value.values():
            _reject_nonfinite_recursive(item)
    elif isinstance(value, list):
        for item in value:
            _reject_nonfinite_recursive(item)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise E0V5ValidationError(message)


def _safe_relative(path: Any) -> bool:
    return (
        isinstance(path, str)
        and bool(path)
        and not path.startswith("/")
        and ".." not in Path(path).parts
    )


def _validate_bound_group(items: Any, expected_roles: set[str], label: str) -> None:
    _require(isinstance(items, list), f"{label} is not a list")
    roles: set[str] = set()
    paths: set[str] = set()
    for item in items:
        _require(isinstance(item, dict), f"invalid {label} item")
        path = item.get("path")
        role = item.get("role")
        _require(_safe_relative(path), f"unsafe {label} path")
        _require(isinstance(role, str) and role, f"invalid {label} role")
        _require(path not in paths and role not in roles, f"duplicate {label} path or role")
        resolved = ROOT / path
        _require(resolved.is_file(), f"missing {label}: {path}")
        _require(sha256_path(resolved) == item.get("sha256"), f"changed {label}: {path}")
        paths.add(path)
        roles.add(role)
    _require(roles == expected_roles, f"unexpected {label} role set")


EXPECTED_DEPENDENCIES = {
    "C0": [],
    "C1": ["C0"],
    "C2": ["C0"],
    "C3": ["C0"],
    "C4": ["C0", "C1", "C2", "C3"],
    "C5": ["C0", "C1", "C2"],
    "C6": ["C0", "C1", "C2", "C3", "C4", "C5"],
}

EXPECTED_EXPERIMENTS = {
    "C0": "btc-backtest-authorities-c0-v1",
    "C1": "btc-backtest-ledger-c1-v1",
    "C2": "btc-backtest-candle-adapter-c2-v1",
    "C3": "btc-backtest-l2-adapter-c3-v1",
    "C4": "btc-backtest-pair-coordinator-c4-v1",
    "C5": "btc-backtest-candle-controls-c5-v1",
    "C6": "btc-backtest-integration-c6-v1",
}

EXPECTED_SEQUENCE = [
    "C0",
    "C1",
    "C2",
    "C5_candle_v1",
    "C3",
    "C4",
    "C5_L2_and_pair_new_ID_extensions",
    "C6",
    "Q0_end_to_end",
]

EXPECTED_MUTATIONS = {f"X{index:02d}" for index in range(1, 13)}
EXPECTED_FINDINGS = {f"F{index:02d}" for index in range(1, 27)}
EXPECTED_REQUIREMENTS = {f"R{index:02d}" for index in range(1, 27)}
EXPECTED_PROBES = {f"M{index:02d}" for index in range(1, 27)}


def _prefix_id(value: Any) -> str:
    _require(isinstance(value, str) and len(value) >= 3, "invalid stable identifier")
    return value.split("_", 1)[0]


def validate_bundle(
    contract: dict[str, Any],
    interfaces: dict[str, Any],
    fixtures: dict[str, Any],
    *,
    verify_bound_hashes: bool,
) -> dict[str, bool]:
    _require(contract.get("experiment_id") == EXPERIMENT_ID, "wrong experiment ID")
    _require(
        contract.get("schema_version") == EXPERIMENT_ID,
        "wrong contract schema",
    )
    _require(contract.get("status") == "frozen_before_independent_review", "contract not frozen")
    _require(contract.get("actionable_arm_id") == "no_trade", "action boundary is not no_trade")
    _require(
        contract.get("scope") == "offline_synthetic_zero_capital_design_qualification_only",
        "scope changed",
    )
    _require(
        contract.get("trust_model")
        == "supported_public_API_correctness_contract_not_hostile_Python_security_sandbox",
        "unrealistic trust model",
    )
    if verify_bound_hashes:
        _validate_bound_group(
            contract.get("bound_design_artifacts"),
            {
                "design_plan",
                "failure_requirement_matrix",
                "machine_component_interfaces",
                "machine_fixture_and_probe_specification",
            },
            "design artifact",
        )
        _validate_bound_group(
            contract.get("bound_inheritance_and_evidence"),
            {
                "inherited_economic_semantics_v1",
                "inherited_economic_clarifications_v2",
                "inherited_final_fill_and_pair_semantics_v3",
                "pending_contract_retained_as_incident_evidence_not_implementation_authority",
                "lineage_incident_tombstone",
                "latest_rejection_summary",
                "latest_rejected_identity",
                "latest_rejected_candidate_manifest",
            },
            "inheritance evidence",
        )
        _validate_bound_group(
            contract.get("bound_policies"),
            {
                "research_policy",
                "spot_mandate_document",
                "execution_cost_policy",
                "execution_scenarios",
                "spot_machine_mandate",
                "directional_perpetual_machine_mandate",
                "pair_machine_mandate",
            },
            "policy",
        )

    _require(contract.get("component_sequence") == EXPECTED_SEQUENCE, "wrong component sequence")
    supersession = contract.get("supersession", {})
    _require(supersession.get("economic_semantics_changed") is False, "economics changed")
    _require(
        supersession.get("supersedes")
        == "only_E0_v4_obsolete_process_and_E1_v4_path_authorization",
        "E0-v4 process supersession is ambiguous",
    )
    _require(
        contract.get("future_boundary", {}).get("on_E0_v5_pass")
        == "only_btc-backtest-authorities-c0-v1_may_be_frozen_next",
        "future boundary permits more than C0",
    )
    _require(
        contract.get("independent_review", {}).get("contract_may_not_self_certify") is True
        and contract.get("independent_review", {}).get("required_after_contract_freeze") is True,
        "independent review is not external and post-freeze",
    )

    _require(
        interfaces.get("schema_version") == "btc-backtest-component-interfaces-e0-v5",
        "wrong interface schema",
    )
    _require(interfaces.get("actionable_arm_id") == "no_trade", "interface action changed")
    _require(
        interfaces.get("trust_model")
        == "supported_public_API_contract_not_hostile_Python_security_boundary",
        "interface trust model changed",
    )
    components = interfaces.get("components")
    _require(isinstance(components, list) and len(components) == 7, "wrong component count")
    by_id: dict[str, dict[str, Any]] = {}
    responsibility_owner: dict[str, str] = {}
    for component in components:
        cid = component.get("id")
        _require(cid in EXPECTED_DEPENDENCIES and cid not in by_id, "invalid component ID")
        _require(
            component.get("acceptance_dependencies") == EXPECTED_DEPENDENCIES[cid],
            f"wrong dependency set for {cid}",
        )
        _require(
            component.get("future_experiment_id") == EXPECTED_EXPERIMENTS[cid],
            f"wrong future experiment for {cid}",
        )
        for responsibility in component.get("responsibilities", []):
            _require(
                isinstance(responsibility, str) and responsibility not in responsibility_owner,
                "responsibility is missing or multiply owned",
            )
            responsibility_owner[responsibility] = cid
        _require(component.get("internal_inputs") and component.get("outputs"), f"empty {cid} interface")
        by_id[cid] = component
    _require(set(by_id) == set(EXPECTED_DEPENDENCIES), "component set changed")
    _require(
        "runtime_residual_gate_and_exact_synthetic_reconciliation"
        in by_id["C1"]["responsibilities"],
        "residual responsibility changed",
    )
    _require(
        "partial_fill_creation" in by_id["C2"]["forbidden_responsibilities"]
        and "full_partial_unfilled_or_rejected_ExecutionFact" in by_id["C3"]["outputs"],
        "candle and L2 capabilities overlap",
    )
    _require(
        "fill_rollback" in by_id["C4"]["forbidden_responsibilities"]
        and "spot_first_final_fill_ordering_without_rollback" in by_id["C4"]["responsibilities"],
        "pair rollback boundary changed",
    )
    _require(
        "deriving_control_economics_from_candidate_rows"
        in by_id["C5"]["forbidden_responsibilities"]
        and "independent_control_intention_generation" in by_id["C5"]["responsibilities"],
        "control independence changed",
    )

    expected_edges = {
        ("verified_RunContext", "C0", "C1_C2_C3_C4_C5"),
        ("ExecutionFact", "C2_or_C3", "C1"),
        ("account_transition_interface", "C1", "C4_or_C5"),
        ("execution_interface", "C2_or_C3_as_bound_by_RunContext", "C4_or_C5"),
        ("accepted_component_artifacts", "C0_C1_C2_C3_C4_C5", "C6"),
        ("canonical_emitted_JSON_only", "C6", "Q0"),
    }
    actual_edges = {
        (item.get("artifact"), item.get("producer"), item.get("consumer"))
        for item in interfaces.get("producer_consumer_edges", [])
    }
    _require(actual_edges == expected_edges, "typed producer-consumer edges changed")

    public = interfaces.get("public_API", {})
    _require(
        public.get("caller_may_supply") == ["frozen_RunSpec_ID", "authorized_target"],
        "public caller authority expanded",
    )
    forbidden_public = " ".join(public.get("caller_must_not_supply", []))
    for token in ("price", "timestamp", "fill", "fee", "scenario", "adapter", "state", "phase", "lineage"):
        _require(token in forbidden_public, f"public caller prohibition omits {token}")
    unsupported = " ".join(public.get("unsupported_hostile_actions", []))
    for token in ("private", "reflection", "monkey", "object___setattr__", "memory"):
        _require(token in unsupported, f"unsupported hostile action omits {token}")
    q0 = interfaces.get("qualification_authority", {})
    _require(
        q0.get("id") == "Q0"
        and q0.get("candidate_component_id") is False
        and q0.get("implementation_import_allowed") is False
        and q0.get("oracle_values_created_only_after_candidate_snapshot") is True,
        "Q0 independence changed",
    )
    lineage = interfaces.get("row_lineage", {})
    for field in (
        "run_context_digest",
        "complete_implementation_manifest_digest",
        "before_state_digest",
        "after_state_digest",
        "row_digest",
        "decision_at_UTC",
        "available_at_UTC",
        "execution_at_UTC",
        "adapter_ID",
        "execution_mode",
    ):
        _require(field in lineage.get("always_required", []), f"lineage omits {field}")
    for field in (
        "source_digest",
        "instrument_rule_digest",
        "margin_rule_digest",
        "selected_mandate_digest",
        "semantic_settings_digest",
        "execution_scenario_digest",
        "mark_index_or_funding_source_digest",
    ):
        _require(
            field in lineage.get("event_specific_required_or_not_applicable", []),
            f"event lineage omits {field}",
        )

    _require(
        fixtures.get("schema_version") == "btc-backtest-component-fixtures-e0-v5",
        "wrong fixture schema",
    )
    policy = fixtures.get("fixture_policy", {})
    _require(
        policy
        == {
            "implementation_candidate_must_be_frozen_before_oracle_values_exist": True,
            "implementer_tests_may_contain_hidden_oracle_terminal_values": False,
            "independent_oracle_imports_implementation": False,
            "market_or_strategy_data_allowed": False,
            "numerical_terminal_oracle_values_present_in_E0_v5": False,
        },
        "fixture policy changed",
    )
    mutations = fixtures.get("mutation_cases")
    _require(isinstance(mutations, list), "mutation cases missing")
    mutation_ids = {_prefix_id(item.get("id")) for item in mutations}
    _require(mutation_ids == EXPECTED_MUTATIONS and len(mutations) == 12, "mutation set incomplete")
    _require(
        all(isinstance(item.get("expected_rejection"), str) and item["expected_rejection"] for item in mutations),
        "mutation expected rejection missing",
    )
    probes = fixtures.get("probe_definitions")
    _require(isinstance(probes, list) and len(probes) == 26, "probe count changed")
    probe_by_prefix: dict[str, dict[str, Any]] = {}
    for probe in probes:
        prefix = _prefix_id(probe.get("id"))
        _require(prefix not in probe_by_prefix, "duplicate probe ID")
        _require(
            probe.get("component") in {*EXPECTED_DEPENDENCIES, "Q0"},
            "invalid probe owner",
        )
        _require(
            isinstance(probe.get("observable"), str)
            and probe["observable"]
            and isinstance(probe.get("reject_if"), str)
            and probe["reject_if"],
            "probe lacks public observable or rejection condition",
        )
        mutation = probe.get("mutation_id")
        _require(mutation is None or _prefix_id(mutation) in mutation_ids, "unknown probe mutation")
        probe_by_prefix[prefix] = probe
    _require(set(probe_by_prefix) == EXPECTED_PROBES, "probe set incomplete")
    _require(
        probe_by_prefix["M14"].get("reject_if")
        == "closed-form fixture is nonzero or runtime absolute residual exceeds 0.00000001 USDT",
        "residual probe silently relaxed inherited tolerance",
    )
    _require(
        probe_by_prefix["M26"].get("reject_if")
        == "a fill is rolled back or an unforeseen failure remains performance-eligible or apparently valid",
        "pair recovery probe silently relaxed final-fill semantics",
    )
    _require(
        probe_by_prefix["M11"].get("reject_if")
        == "control economics are inferred from candidate rows or are placeholders",
        "control oracle became self-referential",
    )

    mappings = contract.get("failure_mapping")
    _require(isinstance(mappings, list) and len(mappings) == 26, "failure mapping count changed")
    findings: set[str] = set()
    requirements: set[str] = set()
    mapped_probes: set[str] = set()
    for mapping in mappings:
        finding = _prefix_id(mapping.get("finding_id"))
        requirement = _prefix_id(mapping.get("requirement_id"))
        probe = _prefix_id(mapping.get("probe_id"))
        _require(finding not in findings, "duplicate finding mapping")
        _require(requirement not in requirements, "duplicate requirement mapping")
        _require(probe not in mapped_probes, "probe has multiple primary findings")
        _require(probe in probe_by_prefix, "mapped probe absent")
        _require(mapping.get("component") == probe_by_prefix[probe].get("component"), "probe owner mismatch")
        findings.add(finding)
        requirements.add(requirement)
        mapped_probes.add(probe)
    _require(findings == EXPECTED_FINDINGS, "finding set incomplete")
    _require(requirements == EXPECTED_REQUIREMENTS, "requirement set incomplete")
    _require(mapped_probes == EXPECTED_PROBES, "probe mapping incomplete")

    inherited_v2 = load_canonical(
        ROOT / "research/btc/contracts/btc-unified-backtest-engine-e0-v2.json"
    )
    _require(
        inherited_v2.get("clarifications_replacing_ambiguous_v1_wording", {})
        .get("decimal_and_quantization", {})
        .get("residual_gate")
        == "absolute_exact_event_residual_less_than_or_equal_to_0.00000001_USDT",
        "inherited E0-v2 residual tolerance changed",
    )
    inherited_v3 = load_canonical(
        ROOT / "research/btc/contracts/btc-unified-backtest-engine-e0-v3-pair-close.json"
    )
    _require(
        inherited_v3.get("atomic_pair_close", {})
        .get("transactionality", {})
        .get("rollback")
        == "forbidden_after_any_fill",
        "inherited E0-v3 no-rollback rule changed",
    )
    inherited_v4 = load_canonical(
        ROOT / "research/btc/contracts/btc-unified-backtest-engine-e0-v4-lineage-recovery.json"
    )
    _require(
        inherited_v4.get("status") == "frozen_pending_independent_review",
        "E0-v4 was falsely promoted or rewritten",
    )

    required_cases = set(fixtures.get("required_synthetic_cases", []))
    _require(len(required_cases) == 15, "synthetic case inventory incomplete")
    for token in ("funding", "fee", "candle", "L2", "pair", "control", "30_40_80"):
        _require(any(token in case for case in required_cases), f"synthetic cases omit {token}")

    prohibited = " ".join(contract.get("prohibited", []))
    for token in ("E1_v15", "oracle", "historical", "2026", "OB0", "network", "NATS", "Freqtrade", "no_trade"):
        _require(token in prohibited, f"prohibited boundary omits {token}")
    return {
        "bound_artifact_integrity": True,
        "component_DAG_and_ownership": True,
        "failure_requirement_probe_bijection": True,
        "fixture_oracle_separation": True,
        "inherited_economics_and_process_supersession": True,
        "public_API_trust_boundary": True,
        "row_lineage_complete": True,
        "scope_and_no_trade_boundary": True,
    }


def validate_forbidden_paths() -> None:
    forbidden = [
        "src/trading_platform/btc_backtest_authorities_c0_v1",
        "src/trading_platform/btc_backtest_ledger_c1_v1",
        "src/trading_platform/btc_backtest_candle_adapter_c2_v1",
        "src/trading_platform/btc_backtest_l2_adapter_c3_v1",
        "src/trading_platform/btc_backtest_pair_coordinator_c4_v1",
        "src/trading_platform/btc_backtest_candle_controls_c5_v1",
        "src/trading_platform/btc_backtest_integration_c6_v1",
        "research/btc/oracles/btc-unified-backtest-engine-e0-v5",
        "research/btc/contracts/btc-unified-backtest-engine-e1-v15.json",
        "research/btc/candidates/unified-backtest-engine-e1-v15",
    ]
    for relative in forbidden:
        _require(not (ROOT / relative).exists(), f"prohibited implementation or oracle exists: {relative}")

    allowed_e0_v5_files = {
        "research/btc/contracts/btc-unified-backtest-engine-e0-v5-component-boundaries.json",
        "research/btc/reports/BTC_UNIFIED_BACKTEST_ENGINE_E0_V5_COMPONENT_BOUNDARIES_PLAN.md",
        "research/btc/reports/BTC_UNIFIED_BACKTEST_ENGINE_E0_V5_FAILURE_MATRIX.md",
        "research/btc/specs/btc-backtest-component-interfaces-e0-v5.json",
        "research/btc/specs/btc-backtest-component-fixtures-e0-v5.json",
        "research/btc/reviews/btc-unified-backtest-engine-e0-v5-independent-review.json",
        "research/btc/tests/test_unified_engine_e0_v5.py",
        "scripts/validate_btc_unified_engine_e0_v5.py",
        "artifacts/agent-level-experiment/btc-focused/unified-backtest-engine-e0-v5/qualification-report.json",
        "artifacts/agent-level-experiment/btc-focused/unified-backtest-engine-e0-v5/evidence-manifest.json",
    }
    scan_roots = [
        ROOT / "research/btc/contracts",
        ROOT / "research/btc/reports",
        ROOT / "research/btc/specs",
        ROOT / "research/btc/reviews",
        ROOT / "research/btc/tests",
        ROOT / "scripts",
        ROOT / "artifacts/agent-level-experiment/btc-focused/unified-backtest-engine-e0-v5",
    ]
    discovered: set[str] = set()
    for scan_root in scan_roots:
        if not scan_root.exists():
            continue
        for path in scan_root.rglob("*"):
            if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
                continue
            relative = str(path.relative_to(ROOT))
            if "e0-v5" in relative.lower() or "e0_v5" in relative.lower():
                discovered.add(relative)
    unexpected = discovered - allowed_e0_v5_files
    _require(not unexpected, f"unexpected E0-v5 file set: {sorted(unexpected)}")


def validate_review(review_path: Path, contract_sha256: str) -> dict[str, Any]:
    review = load_canonical(review_path)
    _require(review.get("experiment_id") == EXPERIMENT_ID, "review experiment mismatch")
    _require(review.get("contract_sha256") == contract_sha256, "review contract binding mismatch")
    _require(review.get("decision") == PASS_DECISION, "independent review did not pass")
    _require(review.get("actionable_arm_id") == "no_trade", "review action boundary changed")
    _require(review.get("reviewer_is_independent_of_contract_author") is True, "review not independent")
    _require(review.get("reviewer_edited_frozen_contract_or_specs") is False, "review mutated frozen design")
    _require(review.get("historical_market_or_strategy_data_accessed") is False, "review accessed market data")
    _require(review.get("production_external_2026_or_partial_OB0_accessed") is False, "review crossed scope")
    findings = {_prefix_id(value) for value in review.get("findings_closed", [])}
    _require(findings == EXPECTED_FINDINGS, "review did not close every finding")
    return review


def qualify(output: Path, review_path: Path) -> dict[str, Any]:
    output = output.resolve()
    _require(not output.exists(), "output path must not exist")
    contract = load_canonical(CONTRACT_PATH)
    interfaces = load_canonical(INTERFACES_PATH)
    fixtures = load_canonical(FIXTURES_PATH)
    gates = validate_bundle(contract, interfaces, fixtures, verify_bound_hashes=True)
    validate_forbidden_paths()
    contract_sha = sha256_path(CONTRACT_PATH)
    review = validate_review(review_path.resolve(), contract_sha)
    output.mkdir(parents=True)
    report = {
        "actionable_arm_id": "no_trade",
        "contract_sha256": contract_sha,
        "decision": PASS_DECISION,
        "design_artifact_count": len(contract["bound_design_artifacts"]),
        "experiment_id": EXPERIMENT_ID,
        "failure_mapping_count": len(contract["failure_mapping"]),
        "gates": gates,
        "historical_market_rows_or_strategy_results_accessed": 0,
        "next_permitted_experiment": "btc-backtest-authorities-c0-v1",
        "production_external_2026_or_partial_OB0_accessed": False,
        "review_path": str(review_path.resolve().relative_to(ROOT)),
        "review_sha256": sha256_path(review_path.resolve()),
    }
    report_path = output / "qualification-report.json"
    report_path.write_text(canonical_json(report), encoding="utf-8")
    manifest = {
        "actionable_arm_id": "no_trade",
        "artifacts": [
            {
                "path": str(CONTRACT_PATH.relative_to(ROOT)),
                "role": "frozen_contract",
                "sha256": contract_sha,
            },
            {
                "path": str(review_path.resolve().relative_to(ROOT)),
                "role": "independent_review",
                "sha256": sha256_path(review_path.resolve()),
            },
            {
                "path": str(report_path.relative_to(ROOT)),
                "role": "qualification_report",
                "sha256": sha256_path(report_path),
            },
        ],
        "decision": PASS_DECISION,
        "experiment_id": EXPERIMENT_ID,
    }
    (output / "evidence-manifest.json").write_text(canonical_json(manifest), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--review", type=Path)
    args = parser.parse_args()
    if args.output is None and args.review is None:
        contract = load_canonical(CONTRACT_PATH)
        interfaces = load_canonical(INTERFACES_PATH)
        fixtures = load_canonical(FIXTURES_PATH)
        result = validate_bundle(contract, interfaces, fixtures, verify_bound_hashes=True)
        validate_forbidden_paths()
        print(canonical_line({"decision": "preflight_passed_pending_independent_review", "gates": result}))
        return
    _require(args.output is not None and args.review is not None, "--output and --review are required together")
    print(canonical_line(qualify(args.output, args.review)))


if __name__ == "__main__":
    main()
