from __future__ import annotations

import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = ROOT / "scripts/validate_btc_unified_engine_e0_v6.py"
SPEC = importlib.util.spec_from_file_location("validate_btc_unified_engine_e0_v6", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class UnifiedEngineE0V6Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = MODULE.load_canonical(MODULE.CONTRACT_PATH)
        self.interfaces = MODULE.load_canonical(MODULE.INTERFACES_PATH)
        self.fixtures = MODULE.load_canonical(MODULE.FIXTURES_PATH)
        self.obligations = MODULE.load_canonical(MODULE.OBLIGATIONS_PATH)

    def validate_mutation(self, *, contract=None, interfaces=None, fixtures=None, obligations=None) -> None:
        MODULE.validate_bundle(
            contract or self.contract,
            interfaces or self.interfaces,
            fixtures or self.fixtures,
            obligations or self.obligations,
            verify_bound_hashes=False,
        )

    def test_frozen_bundle_passes_structural_preflight(self) -> None:
        gates = MODULE.validate_bundle(
            self.contract, self.interfaces, self.fixtures, self.obligations, verify_bound_hashes=True
        )
        self.assertEqual(len(gates), 8)
        MODULE.validate_forbidden_paths()

    def test_duplicate_and_nonfinite_JSON_reject(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            duplicate = Path(directory) / "duplicate.json"
            duplicate.write_text('{"a":1,"a":2}\n', encoding="utf-8")
            with self.assertRaisesRegex(MODULE.E0V6ValidationError, "duplicate"):
                MODULE.load_canonical(duplicate)
            nonfinite = Path(directory) / "nonfinite.json"
            nonfinite.write_text('{"a":NaN}\n', encoding="utf-8")
            with self.assertRaisesRegex(MODULE.E0V6ValidationError, "non-finite"):
                MODULE.load_canonical(nonfinite)

    def test_public_caller_cannot_gain_economic_inputs(self) -> None:
        interfaces = copy.deepcopy(self.interfaces)
        interfaces["public_API"]["caller_may_supply"].append("execution_price")
        with self.assertRaisesRegex(MODULE.E0V6ValidationError, "public caller"):
            self.validate_mutation(interfaces=interfaces)

    def test_ledger_and_adapter_dependency_overlap_rejects(self) -> None:
        interfaces = copy.deepcopy(self.interfaces)
        next(item for item in interfaces["components"] if item["id"] == "C1")[
            "acceptance_dependencies"
        ].append("C3")
        with self.assertRaisesRegex(MODULE.E0V6ValidationError, "dependency"):
            self.validate_mutation(interfaces=interfaces)

    def test_oracle_cannot_become_candidate_component(self) -> None:
        interfaces = copy.deepcopy(self.interfaces)
        interfaces["qualification_authority"]["candidate_component_id"] = True
        with self.assertRaisesRegex(MODULE.E0V6ValidationError, "Q0"):
            self.validate_mutation(interfaces=interfaces)

    def test_probe_owner_and_mapping_mismatch_rejects(self) -> None:
        fixtures = copy.deepcopy(self.fixtures)
        next(item for item in fixtures["probe_definitions"] if item["id"].startswith("M18_"))[
            "component"
        ] = "C2"
        with self.assertRaisesRegex(MODULE.E0V6ValidationError, "owner mismatch"):
            self.validate_mutation(fixtures=fixtures)

    def test_duplicate_probe_primary_mapping_rejects(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["failure_mapping"][1]["probe_id"] = contract["failure_mapping"][0]["probe_id"]
        with self.assertRaisesRegex(MODULE.E0V6ValidationError, "multiple primary"):
            self.validate_mutation(contract=contract)

    def test_residual_policy_cannot_self_relax(self) -> None:
        fixtures = copy.deepcopy(self.fixtures)
        next(item for item in fixtures["probe_definitions"] if item["id"].startswith("M14_"))[
            "reject_if"
        ] = "accept every residual"
        with self.assertRaisesRegex(MODULE.E0V6ValidationError, "residual"):
            self.validate_mutation(fixtures=fixtures)

    def test_pair_cannot_gain_rollback(self) -> None:
        interfaces = copy.deepcopy(self.interfaces)
        pair = next(item for item in interfaces["components"] if item["id"] == "C4")
        pair["forbidden_responsibilities"].remove("fill_rollback")
        pair["responsibilities"].append("fill_rollback")
        with self.assertRaises(MODULE.E0V6ValidationError):
            self.validate_mutation(interfaces=interfaces)

    def test_independent_review_must_bind_contract_and_close_all_findings(self) -> None:
        review = {
            "actionable_arm_id": "no_trade",
            "contract_sha256": "wrong",
            "decision": MODULE.PASS_DECISION,
            "experiment_id": MODULE.EXPERIMENT_ID,
            "findings_closed": [item["finding_id"] for item in self.contract["failure_mapping"]],
            "historical_market_or_strategy_data_accessed": False,
            "production_external_2026_or_partial_OB0_accessed": False,
            "reviewer_edited_frozen_contract_or_specs": False,
            "reviewer_is_independent_of_contract_author": True,
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "review.json"
            path.write_text(MODULE.canonical_json(review), encoding="utf-8")
            with self.assertRaisesRegex(MODULE.E0V6ValidationError, "binding"):
                MODULE.validate_review(path, MODULE.sha256_path(MODULE.CONTRACT_PATH), "bundle")

    def test_extra_future_permission_rejects(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["future_boundary"]["also_permitted"] = "C1"
        with self.assertRaisesRegex(MODULE.E0V6ValidationError, "future boundary"):
            self.validate_mutation(contract=contract)

    def test_qualification_requirements_cannot_be_removed(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["qualification_requirements"] = []
        with self.assertRaisesRegex(MODULE.E0V6ValidationError, "qualification requirements"):
            self.validate_mutation(contract=contract)

    def test_full_finding_identity_is_frozen(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["failure_mapping"][0]["finding_id"] = "F01_rewritten"
        with self.assertRaisesRegex(MODULE.E0V6ValidationError, "full failure mapping"):
            self.validate_mutation(contract=contract)

    def test_exceptional_L2_probe_cannot_be_relaxed(self) -> None:
        fixtures = copy.deepcopy(self.fixtures)
        next(item for item in fixtures["probe_definitions"] if item["id"].startswith("M18_"))[
            "reject_if"
        ] = "always accept"
        with self.assertRaisesRegex(MODULE.E0V6ValidationError, "L2"):
            self.validate_mutation(fixtures=fixtures)

    def test_mutation_rejection_semantics_are_exact(self) -> None:
        fixtures = copy.deepcopy(self.fixtures)
        next(item for item in fixtures["mutation_cases"] if item["id"].startswith("X08_"))[
            "expected_rejection"
        ] = "accept mutation"
        with self.assertRaisesRegex(MODULE.E0V6ValidationError, "mutation rejection"):
            self.validate_mutation(fixtures=fixtures)

    def test_synonym_responsibility_cannot_expand_ledger(self) -> None:
        interfaces = copy.deepcopy(self.interfaces)
        next(item for item in interfaces["components"] if item["id"] == "C1")[
            "responsibilities"
        ].append("L2_book_execution_alias")
        with self.assertRaisesRegex(MODULE.E0V6ValidationError, "responsibility"):
            self.validate_mutation(interfaces=interfaces)

    def test_inherited_obligation_pointer_is_verified(self) -> None:
        obligations = copy.deepcopy(self.obligations)
        obligations["obligations"][0]["value_pointer"] = "/status"
        with self.assertRaisesRegex(MODULE.E0V6ValidationError, "changed inherited obligation"):
            self.validate_mutation(obligations=obligations)


if __name__ == "__main__":
    unittest.main()
