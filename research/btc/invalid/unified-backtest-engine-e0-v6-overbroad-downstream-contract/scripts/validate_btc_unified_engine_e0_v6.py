#!/usr/bin/env python3
"""Validate the E0-v6 BTC backtest component design without engine or market access."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "research/btc/contracts/btc-unified-backtest-engine-e0-v6-exact-component-contracts.json"
INTERFACES_PATH = ROOT / "research/btc/specs/btc-backtest-component-interfaces-e0-v6.json"
FIXTURES_PATH = ROOT / "research/btc/specs/btc-backtest-component-fixtures-e0-v6.json"
OBLIGATIONS_PATH = ROOT / "research/btc/specs/btc-backtest-inherited-obligations-e0-v6.json"
BUNDLE_MANIFEST_PATH = ROOT / "research/btc/candidates/unified-backtest-engine-e0-v6-design/pre-review-bundle-manifest.json"
EXPERIMENT_ID = "btc-unified-backtest-engine-e0-v6-exact-component-contracts"
PASS_DECISION = "E0_v6_exact_component_design_passed_only_C0_freeze_permitted"


class E0V6ValidationError(ValueError):
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
            raise E0V6ValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_nonfinite(token: str) -> None:
    raise E0V6ValidationError(f"non-finite JSON value: {token}")


def load_canonical(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
        value = json.loads(
            raw,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise E0V6ValidationError(f"cannot parse canonical JSON: {path}") from exc
    if not isinstance(value, dict) or raw != canonical_json(value):
        raise E0V6ValidationError(f"non-canonical JSON: {path}")
    _reject_nonfinite_recursive(value)
    return value


def _reject_nonfinite_recursive(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise E0V6ValidationError("non-finite number")
    if isinstance(value, dict):
        for item in value.values():
            _reject_nonfinite_recursive(item)
    elif isinstance(value, list):
        for item in value:
            _reject_nonfinite_recursive(item)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise E0V6ValidationError(message)


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
EXPECTED_RESPONSIBILITIES = {
    "C0": {"canonical_duplicate_safe_finite_JSON", "authority_checksum_role_and_safe_path_verification", "adapter_scenario_mandate_compatibility", "complete_transitive_implementation_identity"},
    "C1": {"authorized_target_to_OrderIntention_during_inherited_phase_clock", "execution_neutral_Decimal_state_transitions", "inherited_nine_phase_event_clock", "funding_margin_liquidation_gap_and_terminal_accounting", "asset_specific_fee_and_tax_balance_mutation", "runtime_residual_gate_and_exact_synthetic_reconciliation"},
    "C2": {"candle_timestamp_segment_and_gap_validation", "exact_next_open_price_selection", "side_aware_price_bound_and_expiry", "all_or_none_fill_fact_creation"},
    "C3": {"book_timestamp_segment_staleness_and_cross_validation", "frozen_latency_application_for_every_fill_reason", "side_aware_depth_walk_and_price_bound", "VWAP_filled_unfilled_spread_depth_and_residual_impact_facts"},
    "C4": {"currently_bound_pair_outcome_resource_and_rule_preflight", "spot_first_final_fill_ordering_without_rollback", "bounded_neutralization_and_pending_safety_orchestration", "truthful_post_commit_invalid_unknown_termination"},
    "C5": {"independent_control_intention_generation", "same_adapter_and_ledger_control_execution", "complete_cost_scenario_reporting", "execution_metadata_identity_checks"},
    "C6": {"dependency_wiring_only", "supported_public_API_surface", "complete_manifest_composition", "end_to_end_conformance_handoff_to_Q0"},
}
EXPECTED_MUTATION_REJECTIONS = {
    "X01_double_fee": "residual_above_inherited_tolerance",
    "X02_missed_funding": "missing_owned_funding_event",
    "X03_wrong_side_execution": "wrong_side_or_protected_bound",
    "X04_candle_L2_substitution": "adapter_source_or_mode_changed",
    "X05_post_commit_pair_exception": "sticky_invalid_unknown_and_no_performance_eligibility",
    "X06_broken_manifest_or_RunSpec_digest": "lineage_failure_before_mutation",
    "X07_omitted_or_wrong_asset_fee_tax": "actual_fee_asset_balance_or_tax_mismatch",
    "X08_L2_safety_path_candle_or_zero_latency": "L2_path_did_not_use_bound_depth_and_latency",
    "X09_pair_stranded_mutation": "final_fill_not_rolled_back_and_run_invalid_unknown",
    "X10_scenario_relabel": "execution_identity_changed_by_cost_overlay",
    "X11_funding_timestamp_ambiguity": "funding_causality_tuple_incomplete_or_ambiguous",
    "X12_sell_bound_inversion": "sell_price_below_floor",
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
EXPECTED_FINDINGS = {f"F{index:02d}" for index in range(1, 33)}
EXPECTED_REQUIREMENTS = {f"R{index:02d}" for index in range(1, 33)}
EXPECTED_PROBES = {f"M{index:02d}" for index in range(1, 33)}
EXPECTED_TYPE_FIELDS = {
    "AccountState": {"state_digest", "status", "phase", "quote_cash", "asset_balances", "positions", "isolated_collateral", "liabilities", "NAV"},
    "ComponentManifest": {"component_id", "experiment_id", "schema_version", "files", "authority_bindings", "dependency_acceptances", "manifest_digest"},
    "EventRow": {"row_kind", "event_sequence", "run_context_digest", "complete_implementation_manifest_digest", "before_state_digest", "after_state_digest", "transition_plan_digest", "economic_terms", "exact_residual", "timestamps", "event_lineage", "row_digest"},
    "ExecutionFact": {"execution_fact_digest", "order_intention_digest", "run_context_digest", "before_state_digest", "adapter_id", "execution_mode", "status", "side", "requested_rounded_filled_unfilled_quantities", "price_and_VWAP", "fee_asset_amount_tax_and_implicit_cost", "available_at_UTC", "execution_at_UTC", "latency_ms", "source_rule_scenario_and_depth_lineage"},
    "OrderIntention": {"order_intention_digest", "run_context_digest", "before_state_digest", "decision_at_UTC", "available_at_UTC", "instrument_side_requested_and_rounded_quantity", "price_bound_and_expiry", "adapter_scenario_source_rule_and_mandate_digests"},
    "RunContext": {"run_context_digest", "run_spec_id", "selected_mandate_id_and_digest", "adapter_id_execution_mode_and_latency", "source_rule_margin_settings_and_scenario_digests", "complete_implementation_manifest_digest", "partition_start_and_exclusive_terminal_UTC"},
    "TransitionPlan": {"transition_plan_digest", "run_context_digest", "before_state_digest", "order_intention_or_execution_fact_digest", "phase_and_row_kind", "source_rule_margin_mandate_settings_scenario_digests", "stale_or_mismatched_binding_response"},
}
EXPECTED_QUALIFICATION_REQUIREMENTS = {
    "canonical_duplicate_safe_finite_JSON_and_safe_unique_paths",
    "exact_bound_artifact_roles_paths_and_hashes",
    "exact_C0_C6_and_Q0_roles_dependency_DAG_and_typed_edges",
    "exact_F01_F32_to_R01_R32_to_unique_probe_mapping",
    "exact_RunContext_OrderIntention_ExecutionFact_TransitionPlan_AccountState_EventRow_ComponentManifest_schemas",
    "exact_E0_v1_v2_v3_JSON_pointer_obligation_registry",
    "probe_public_observables_and_structured_rejection_conditions",
    "exact_E0_v1_v2_v3_economic_inheritance",
    "E0_v4_and_rejected_E0_v5_retained_only_as_evidence",
    "obsolete_prior_process_paths_superseded_by_this_contract",
    "runtime_residual_tolerance_preserved_and_exact_zero_limited_to_closed_form_fixtures",
    "final_fills_no_rollback_and_unforeseen_failure_sticky_invalid_unknown",
    "candle_and_L2_adapter_separation",
    "candle_economic_runs_distinct_from_L2_reporting_overlays",
    "row_kind_timestamp_and_event_specific_lineage",
    "C6_requires_base_L2_control_and_pair_control_acceptances",
    "exact_whitelist_contains_only_frozen_bundle_review_and_qualification",
    "no_component_or_oracle_implementation_or_answer_exists",
    "separate_post_freeze_independent_review_binds_full_bundle_manifest",
    "only_no_trade_actionable",
}
EXPECTED_MAPPING = {
    ("F01_v4_incomplete_contract_coverage", "R01_complete_owned_obligations", "C0", "M01_contract_coverage"),
    ("F02_v5_oracle_leak", "R02_post_snapshot_oracle_only", "Q0", "M02_oracle_absence_before_snapshot"),
    ("F03_v6_structural_transition_bypass", "R03_public_transition_mutations", "C1", "M03_transition_mutations"),
    ("F04_v7_missing_probes", "R04_complete_unique_probe_registry", "C0", "M04_probe_bijection"),
    ("F05_v8_self_referential_oracle", "R05_external_closed_form_oracle", "Q0", "M05_external_oracle"),
    ("F06_v8_nonatomic_entry", "R06_bound_outcome_preflight_before_fill", "C4", "M06_pair_preflight"),
    ("F07_v9_phase_contradictions", "R07_single_nine_phase_owner", "C1", "M07_phase_ownership"),
    ("F08_v10_opaque_probes", "R08_public_observable_rejection_rule", "C0", "M08_probe_observability"),
    ("F09_v11_private_test_mutation", "R09_supported_public_API_tests", "C0", "M09_public_API_only"),
    ("F10_v11_candle_partial_conflation", "R10_candle_all_or_none_L2_partial_only", "C2", "M10_adapter_capability_separation"),
    ("F11_v11_placeholder_controls", "R11_independent_control_intentions", "C5", "M11_control_economics"),
    ("F12_v12_unfrozen_RunSpecs", "R12_frozen_complete_run_identity", "C0", "M12_runspec_lineage"),
    ("F13_v12_overlapping_probe_ownership", "R13_integration_does_not_duplicate_semantics", "C6", "M24_integration_probe_ownership"),
    ("F14_v13_L2_scenario_mismatch", "R14_adapter_scenario_mandate_compatibility", "C0", "M13_scenario_compatibility"),
    ("F15_v14_hostile_Python_boundary_claim", "R15_realistic_supported_API_trust_model", "C0", "M25_no_hostile_Python_claim"),
    ("F16_v14_valid_L2_nonzero_residual", "R16_inherited_runtime_and_exact_fixture_residual_gates", "C1", "M14_residual_gate"),
    ("F17_v14_incomplete_implementation_lineage", "R17_complete_run_and_event_lineage", "C0", "M15_complete_lineage"),
    ("F18_v14_missing_L2_cost_reports", "R18_complete_distinct_cost_reports", "C5", "M16_cost_grid_completeness"),
    ("F19_v14_candle_substitution_in_L2_controls", "R19_immutable_adapter_execution_facts", "C5", "M17_no_adapter_substitution"),
    ("F20_v14_exceptional_L2_bypass", "R20_all_L2_fill_reasons_use_depth_latency", "C3", "M18_exceptional_L2_paths"),
    ("F21_v14_unintegrated_fees_taxes", "R21_actual_asset_balance_and_NAV_effect", "C1", "M19_fee_asset_balance"),
    ("F22_v14_incomplete_pair_recovery_preflight", "R22_final_fills_no_rollback_truthful_invalid_unknown", "C4", "M26_pair_recovery_preflight"),
    ("F23_v14_wrong_pair_direction", "R23_delta_neutral_pair_identity", "C4", "M20_pair_episode_identity"),
    ("F24_v14_severe_L2_relabelled_candle", "R24_separate_execution_and_budget_identity", "C5", "M21_scenario_label_integrity"),
    ("F25_v14_incomplete_funding_causality", "R25_complete_funding_time_and_source_tuple", "C1", "M22_funding_causality"),
    ("F26_v14_wrong_sell_bound", "R26_buy_cap_and_sell_floor", "C3", "M23_side_aware_bounds"),
    ("F27_e0_v5_missing_target_to_order_edge", "R27_C1_target_to_bound_order_intention", "C1", "M27_target_to_order_edge"),
    ("F28_e0_v5_false_universal_timestamps", "R28_row_kind_timestamp_requirements", "C0", "M28_row_kind_lineage"),
    ("F29_e0_v5_nominal_untyped_interfaces", "R29_exact_field_type_nullability_producer_schemas", "C0", "M29_exact_type_schemas"),
    ("F30_e0_v5_missing_inherited_coverage", "R30_exact_inherited_JSON_pointer_registry", "C0", "M30_inherited_obligation_registry"),
    ("F31_e0_v5_incomplete_C6_dependencies", "R31_C6_requires_all_control_extensions", "C6", "M31_complete_integration_dependencies"),
    ("F32_e0_v5_weak_review_bundle_binding", "R32_review_binds_complete_pre_review_manifest", "Q0", "M32_complete_review_bundle"),
}


def _prefix_id(value: Any) -> str:
    _require(isinstance(value, str) and len(value) >= 3, "invalid stable identifier")
    return value.split("_", 1)[0]


def validate_bundle(
    contract: dict[str, Any],
    interfaces: dict[str, Any],
    fixtures: dict[str, Any],
    obligations: dict[str, Any],
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
                "machine_inherited_obligation_registry",
                "preimplementation_validator",
                "preimplementation_validator_tests",
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
                "rejected_E0_v5_summary",
                "rejected_E0_v5_contract",
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
    _require(
        contract.get("qualification_requirements") == sorted(EXPECTED_QUALIFICATION_REQUIREMENTS),
        "qualification requirements changed",
    )
    supersession = contract.get("supersession", {})
    _require(supersession.get("economic_semantics_changed") is False, "economics changed")
    _require(
        supersession.get("supersedes")
        == "only_E0_v4_obsolete_process_paths_and_rejected_E0_v5_process_authorizations",
        "E0-v4 process supersession is ambiguous",
    )
    _require(
        contract.get("future_boundary")
        == {
            "on_E0_v6_fail": "archive_under_new_invalid_path_and_require_new_E0_ID",
            "on_E0_v6_pass": "only_btc-backtest-authorities-c0-v1_may_be_frozen_next",
            "passing_component_is_necessary_not_sufficient": True,
            "Q0_end_to_end_required_before_historical_reconciliation": True,
        },
        "future boundary changed or expanded",
    )
    _require(
        contract.get("future_boundary", {}).get("on_E0_v6_pass")
        == "only_btc-backtest-authorities-c0-v1_may_be_frozen_next",
        "future boundary permits more than C0",
    )
    _require(
        contract.get("independent_review", {}).get("contract_may_not_self_certify") is True
        and contract.get("independent_review", {}).get("required_after_contract_freeze") is True,
        "independent review is not external and post-freeze",
    )

    _require(
        interfaces.get("schema_version") == "btc-backtest-component-interfaces-e0-v6",
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
        _require(
            set(component.get("responsibilities", [])) == EXPECTED_RESPONSIBILITIES[cid]
            and len(component.get("responsibilities", [])) == len(EXPECTED_RESPONSIBILITIES[cid]),
            f"responsibility set changed for {cid}",
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
    _require(
        by_id["C6"].get("internal_inputs")
        == [
            "accepted_btc-backtest-authorities-c0-v1",
            "accepted_btc-backtest-ledger-c1-v1",
            "accepted_btc-backtest-candle-adapter-c2-v1",
            "accepted_btc-backtest-l2-adapter-c3-v1",
            "accepted_btc-backtest-pair-coordinator-c4-v1",
            "accepted_btc-backtest-candle-controls-c5-v1",
            "accepted_btc-backtest-l2-controls-c5-v2",
            "accepted_separately_frozen_pair-control-C5-extension",
        ],
        "C6 integration dependencies incomplete",
    )

    expected_edges = {
        ("verified_RunContext", "C0", "C1_C2_C3_C4_C5"),
        ("OrderIntention", "C1", "C2_or_C3_as_bound_by_RunContext"),
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
        "event_sequence",
        "row_kind",
    ):
        _require(field in lineage.get("always_required", []), f"lineage omits {field}")
    timestamp_rules = lineage.get("row_kind_timestamp_rules", {})
    _require(
        set(timestamp_rules) == {"account_or_margin_checkpoint", "decision_or_order", "fill", "funding", "terminal"},
        "row-kind timestamp rule set changed",
    )
    for rule in timestamp_rules.values():
        _require(
            isinstance(rule.get("required"), list)
            and isinstance(rule.get("forbidden"), list)
            and set(rule["required"]).isdisjoint(rule["forbidden"]),
            "row-kind timestamp requirements overlap",
        )
    _require("execution_at_UTC" in timestamp_rules["fill"]["required"], "fill execution time missing")
    _require("execution_at_UTC" in timestamp_rules["funding"]["forbidden"], "funding placeholder time allowed")

    schemas = interfaces.get("type_schemas", {})
    _require(set(schemas) == set(EXPECTED_TYPE_FIELDS), "exact type schema set changed")
    for schema_name, expected_fields in EXPECTED_TYPE_FIELDS.items():
        rows = schemas[schema_name]
        _require(isinstance(rows, list) and len(rows) == len(expected_fields), f"{schema_name} field count changed")
        names = {row.get("name") for row in rows}
        _require(names == expected_fields, f"{schema_name} fields changed")
        for row in rows:
            _require(
                isinstance(row.get("type"), str)
                and row["type"]
                and isinstance(row.get("producer"), str)
                and row["producer"]
                and isinstance(row.get("nullable"), bool),
                f"{schema_name} field type nullability or producer missing",
            )

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
        fixtures.get("schema_version") == "btc-backtest-component-fixtures-e0-v6",
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
            "numerical_terminal_oracle_values_present_in_E0_v6": False,
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
    _require(
        {item.get("id"): item.get("expected_rejection") for item in mutations}
        == EXPECTED_MUTATION_REJECTIONS,
        "mutation rejection semantics changed",
    )
    probes = fixtures.get("probe_definitions")
    _require(isinstance(probes, list) and len(probes) == 32, "probe count changed")
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
    _require(
        probe_by_prefix["M18"].get("reject_if")
        == "any L2 fill bypasses qualified depth or bound latency",
        "exceptional L2 probe silently relaxed",
    )

    mappings = contract.get("failure_mapping")
    _require(isinstance(mappings, list) and len(mappings) == 32, "failure mapping count changed")
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
    actual_mapping = {
        (item.get("finding_id"), item.get("requirement_id"), item.get("component"), item.get("probe_id"))
        for item in mappings
    }
    _require(actual_mapping == EXPECTED_MAPPING, "full failure mapping semantics changed")
    _require(
        {probe.get("id") for probe in probes} == {item[3] for item in EXPECTED_MAPPING},
        "full probe identifiers changed",
    )

    _require(
        set(contract.get("qualification_requirements", [])) == EXPECTED_QUALIFICATION_REQUIREMENTS
        and len(contract.get("qualification_requirements", [])) == len(EXPECTED_QUALIFICATION_REQUIREMENTS),
        "qualification requirements changed",
    )

    _require(
        obligations.get("schema_version") == "btc-backtest-inherited-obligations-e0-v6"
        and obligations.get("actionable_arm_id") == "no_trade",
        "obligation registry identity changed",
    )
    obligation_rows = obligations.get("obligations", [])
    _require(isinstance(obligation_rows, list) and len(obligation_rows) == 32, "obligation registry count changed")
    obligation_ids: set[str] = set()
    qualification_ids: set[str] = set()
    for row in obligation_rows:
        obligation_id = _prefix_id(row.get("obligation_id"))
        qualification_id = row.get("qualification_probe_id")
        _require(obligation_id not in obligation_ids, "duplicate inherited obligation")
        _require(isinstance(qualification_id, str) and qualification_id not in qualification_ids, "duplicate obligation probe")
        _require(row.get("component") in EXPECTED_DEPENDENCIES, "invalid obligation owner")
        contract_path = row.get("contract_path")
        pointer = row.get("value_pointer")
        _require(_safe_relative(contract_path) and isinstance(pointer, str) and pointer.startswith("/"), "invalid obligation path or pointer")
        value: Any = load_canonical(ROOT / contract_path)
        try:
            for token in pointer.strip("/").split("/"):
                value = value[token.replace("~1", "/").replace("~0", "~")]
        except (KeyError, TypeError) as exc:
            raise E0V6ValidationError(f"missing inherited obligation pointer: {pointer}") from exc
        value_digest = hashlib.sha256(canonical_line(value).encode()).hexdigest()
        _require(value_digest == row.get("value_sha256"), f"changed inherited obligation: {pointer}")
        obligation_ids.add(obligation_id)
        qualification_ids.add(qualification_id)
    _require(obligation_ids == {f"O{index:02d}" for index in range(1, 33)}, "obligation IDs incomplete")

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
    future_tokens = {
        "btc_backtest_authorities_c0_v1",
        "btc_backtest_ledger_c1_v1",
        "btc_backtest_candle_adapter_c2_v1",
        "btc_backtest_l2_adapter_c3_v1",
        "btc_backtest_pair_coordinator_c4_v1",
        "btc_backtest_candle_controls_c5_v1",
        "btc_backtest_integration_c6_v1",
        "unified-backtest-engine-e1-v15",
        "btc-unified-backtest-engine-e1-v15",
    }
    implementation_roots = [
        ROOT / "src/trading_platform",
        ROOT / "research/btc/tests",
        ROOT / "research/btc/contracts",
        ROOT / "research/btc/candidates",
        ROOT / "research/btc/oracles",
    ]
    for scan_root in implementation_roots:
        if not scan_root.exists():
            continue
        for path in scan_root.rglob("*"):
            relative_lower = str(path.relative_to(ROOT)).lower()
            _require(
                not any(token in relative_lower for token in future_tokens),
                f"prohibited component implementation or oracle exists: {path.relative_to(ROOT)}",
            )

    allowed_e0_v6_files = {
        "research/btc/contracts/btc-unified-backtest-engine-e0-v6-exact-component-contracts.json",
        "research/btc/reports/BTC_UNIFIED_BACKTEST_ENGINE_E0_V6_COMPONENT_CONTRACT_PLAN.md",
        "research/btc/reports/BTC_UNIFIED_BACKTEST_ENGINE_E0_V6_FAILURE_MATRIX.md",
        "research/btc/specs/btc-backtest-component-interfaces-e0-v6.json",
        "research/btc/specs/btc-backtest-component-fixtures-e0-v6.json",
        "research/btc/specs/btc-backtest-inherited-obligations-e0-v6.json",
        "research/btc/reviews/btc-unified-backtest-engine-e0-v6-independent-review.json",
        "research/btc/tests/test_unified_engine_e0_v6.py",
        "scripts/validate_btc_unified_engine_e0_v6.py",
        "research/btc/candidates/unified-backtest-engine-e0-v6-design/pre-review-bundle-manifest.json",
        "artifacts/agent-level-experiment/btc-focused/unified-backtest-engine-e0-v6/qualification-report.json",
        "artifacts/agent-level-experiment/btc-focused/unified-backtest-engine-e0-v6/evidence-manifest.json",
    }
    scan_roots = [
        ROOT / "research/btc/contracts",
        ROOT / "research/btc/reports",
        ROOT / "research/btc/specs",
        ROOT / "research/btc/reviews",
        ROOT / "research/btc/tests",
        ROOT / "scripts",
        ROOT / "research/btc/candidates/unified-backtest-engine-e0-v6-design",
        ROOT / "artifacts/agent-level-experiment/btc-focused/unified-backtest-engine-e0-v6",
    ]
    discovered: set[str] = set()
    for scan_root in scan_roots:
        if not scan_root.exists():
            continue
        for path in scan_root.rglob("*"):
            if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
                continue
            relative = str(path.relative_to(ROOT))
            if "e0-v6" in relative.lower() or "e0_v6" in relative.lower():
                discovered.add(relative)
    unexpected = discovered - allowed_e0_v6_files
    _require(not unexpected, f"unexpected E0-v6 file set: {sorted(unexpected)}")


def validate_bundle_manifest() -> dict[str, Any]:
    manifest = load_canonical(BUNDLE_MANIFEST_PATH)
    _require(manifest.get("experiment_id") == EXPERIMENT_ID, "bundle experiment mismatch")
    _require(manifest.get("status") == "frozen_before_independent_review", "bundle not frozen")
    _require(manifest.get("actionable_arm_id") == "no_trade", "bundle action changed")
    expected_paths = {
        str(CONTRACT_PATH.relative_to(ROOT)),
        "research/btc/reports/BTC_UNIFIED_BACKTEST_ENGINE_E0_V6_COMPONENT_CONTRACT_PLAN.md",
        "research/btc/reports/BTC_UNIFIED_BACKTEST_ENGINE_E0_V6_FAILURE_MATRIX.md",
        str(INTERFACES_PATH.relative_to(ROOT)),
        str(FIXTURES_PATH.relative_to(ROOT)),
        str(OBLIGATIONS_PATH.relative_to(ROOT)),
        "scripts/validate_btc_unified_engine_e0_v6.py",
        "research/btc/tests/test_unified_engine_e0_v6.py",
    }
    artifacts = manifest.get("artifacts", [])
    _require(isinstance(artifacts, list) and len(artifacts) == 8, "bundle artifact count changed")
    paths: set[str] = set()
    roles: set[str] = set()
    for item in artifacts:
        path = item.get("path")
        role = item.get("role")
        _require(_safe_relative(path) and path not in paths, "unsafe or duplicate bundle path")
        _require(isinstance(role, str) and role and role not in roles, "duplicate bundle role")
        resolved = ROOT / path
        _require(resolved.is_file() and sha256_path(resolved) == item.get("sha256"), f"changed bundle artifact: {path}")
        paths.add(path)
        roles.add(role)
    _require(paths == expected_paths and len(roles) == 8, "bundle file set changed")
    return manifest


def validate_review(review_path: Path, contract_sha256: str, bundle_manifest_sha256: str) -> dict[str, Any]:
    review = load_canonical(review_path)
    _require(review.get("experiment_id") == EXPERIMENT_ID, "review experiment mismatch")
    _require(review.get("contract_sha256") == contract_sha256, "review contract binding mismatch")
    _require(review.get("bundle_manifest_sha256") == bundle_manifest_sha256, "review bundle binding mismatch")
    _require(review.get("decision") == PASS_DECISION, "independent review did not pass")
    _require(review.get("actionable_arm_id") == "no_trade", "review action boundary changed")
    _require(review.get("reviewer_is_independent_of_contract_author") is True, "review not independent")
    _require(review.get("reviewer_edited_frozen_contract_or_specs") is False, "review mutated frozen design")
    _require(review.get("historical_market_or_strategy_data_accessed") is False, "review accessed market data")
    _require(review.get("production_external_2026_or_partial_OB0_accessed") is False, "review crossed scope")
    findings = set(review.get("findings_closed", []))
    _require(findings == {item[0] for item in EXPECTED_MAPPING}, "review did not close every exact finding")
    return review


def qualify(output: Path, review_path: Path) -> dict[str, Any]:
    output = output.resolve()
    _require(not output.exists(), "output path must not exist")
    contract = load_canonical(CONTRACT_PATH)
    interfaces = load_canonical(INTERFACES_PATH)
    fixtures = load_canonical(FIXTURES_PATH)
    obligations = load_canonical(OBLIGATIONS_PATH)
    gates = validate_bundle(contract, interfaces, fixtures, obligations, verify_bound_hashes=True)
    validate_forbidden_paths()
    bundle_manifest = validate_bundle_manifest()
    contract_sha = sha256_path(CONTRACT_PATH)
    bundle_manifest_sha = sha256_path(BUNDLE_MANIFEST_PATH)
    review = validate_review(review_path.resolve(), contract_sha, bundle_manifest_sha)
    output.mkdir(parents=True)
    report = {
        "actionable_arm_id": "no_trade",
        "contract_sha256": contract_sha,
        "bundle_manifest_sha256": bundle_manifest_sha,
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
            *bundle_manifest["artifacts"],
            {
                "path": str(BUNDLE_MANIFEST_PATH.relative_to(ROOT)),
                "role": "pre_review_bundle_manifest",
                "sha256": bundle_manifest_sha,
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
        obligations = load_canonical(OBLIGATIONS_PATH)
        result = validate_bundle(contract, interfaces, fixtures, obligations, verify_bound_hashes=True)
        validate_forbidden_paths()
        print(canonical_line({"decision": "preflight_passed_pending_independent_review", "gates": result}))
        return
    _require(args.output is not None and args.review is not None, "--output and --review are required together")
    print(canonical_line(qualify(args.output, args.review)))


if __name__ == "__main__":
    main()
