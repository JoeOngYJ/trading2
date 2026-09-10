from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
PATH = ROOT / "scripts/validate_btc_unified_engine_e0_v2.py"
SPEC = importlib.util.spec_from_file_location("validate_e0_v2", PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class E0V2Tests(unittest.TestCase):
    def test_contract_passes(self) -> None:
        self.assertTrue(all(MODULE.validate(MODULE.load()).values()))

    def test_liquidation_cost_mutation_fails(self) -> None:
        contract = MODULE.load()
        contract["clarifications_replacing_ambiguous_v1_wording"]["liquidation_cost"]["ordinary_close_commission"] = "charged"
        with self.assertRaisesRegex(MODULE.ValidationError, "liquidation"):
            MODULE.validate(contract)

    def test_terminal_increase_mutation_fails(self) -> None:
        contract = MODULE.load()
        contract["clarifications_replacing_ambiguous_v1_wording"]["terminal_execution"]["prohibited"] = "none"
        with self.assertRaisesRegex(MODULE.ValidationError, "terminal"):
            MODULE.validate(contract)


if __name__ == "__main__":
    unittest.main()
