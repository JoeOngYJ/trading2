from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = ROOT / "scripts/validate_btc_unified_engine_e0.py"
SPEC = importlib.util.spec_from_file_location("validate_btc_unified_engine_e0", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class UnifiedEngineE0ContractTests(unittest.TestCase):
    def test_frozen_contract_passes_semantic_validation(self) -> None:
        contract = MODULE.load_contract()
        self.assertTrue(all(MODULE.validate_contract(contract).values()))

    def test_action_boundary_mutation_fails_closed(self) -> None:
        contract = MODULE.load_contract()
        contract["action_boundary"]["actionable_arm_id"] = "btc_strategy"
        with self.assertRaisesRegex(MODULE.E0ValidationError, "no_trade"):
            MODULE.validate_contract(contract)

    def test_missing_fixture_mutation_fails_closed(self) -> None:
        contract = MODULE.load_contract()
        contract["synthetic_fixture_requirements_for_E1_E2"].remove(
            "same_timestamp_funding_and_exit_membership"
        )
        with self.assertRaisesRegex(MODULE.E0ValidationError, "fixture"):
            MODULE.validate_contract(contract)

    def test_duplicate_json_key_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.json"
            path.write_text('{"a":1,"a":2}\n', encoding="utf-8")
            with self.assertRaisesRegex(MODULE.E0ValidationError, "duplicate"):
                MODULE.load_contract(path)

    def test_noncanonical_contract_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "noncanonical.json"
            path.write_text(json.dumps(MODULE.load_contract()), encoding="utf-8")
            with self.assertRaisesRegex(MODULE.E0ValidationError, "canonical"):
                MODULE.load_contract(path)


if __name__ == "__main__":
    unittest.main()
