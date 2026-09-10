from __future__ import annotations

import copy
import importlib.util
import json
import unittest


SPEC = importlib.util.spec_from_file_location(
    "e0v7_validator", "scripts/validate_btc_unified_engine_e0_v7.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class E0V7DesignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = MODULE.load_json(MODULE.CONTRACT)
        cls.interface = MODULE.load_json(MODULE.INTERFACE)
        cls.obligations = MODULE.load_json(MODULE.OBLIGATIONS)

    def assert_document_mutation_fails(self, *, contract=None, interface=None, obligations=None):
        with self.assertRaises(MODULE.ValidationError):
            MODULE.validate_documents(
                contract or self.contract,
                interface or self.interface,
                obligations or self.obligations,
            )

    def test_frozen_documents_are_valid(self):
        MODULE.validate_documents(self.contract, self.interface, self.obligations)

    def test_duplicate_key_rejected(self):
        with self.assertRaises(MODULE.ValidationError):
            json.loads('{"a":1,"a":2}', object_pairs_hook=MODULE._unique_object)

    def test_nonfinite_rejected(self):
        with self.assertRaises(MODULE.ValidationError):
            json.loads('{"a":NaN}', parse_constant=MODULE._reject_constant)

    def test_unsafe_paths_rejected(self):
        for value in ("", "/tmp/x", "../x", "a/../x", "a//x", "a\\x"):
            with self.subTest(value=value), self.assertRaises(MODULE.ValidationError):
                MODULE.resolve_safe(value)

    def test_hyphenated_and_underscored_future_paths_rejected(self):
        forbidden = [
            "src/trading_platform/btc-backtest-ledger-c1.py",
            "src/trading_platform/btc_backtest_l2_c3.py",
            "research/btc/tests/btc-backtest-pair-c4-test.py",
            "research/btc/contracts/unified_backtest_engine_e1_v15.json",
            "research/btc/candidates/unified-backtest-engine-e2/candidate.json",
            "research/btc/oracles/c6/answer.json",
        ]
        for value in forbidden:
            with self.subTest(value=value):
                self.assertTrue(MODULE.is_forbidden_future_relative_path(value))
        self.assertFalse(MODULE.is_forbidden_future_relative_path("research/btc/invalid/btc-backtest-ledger-c1.py"))

    def test_interface_type_mutation_rejected(self):
        value = copy.deepcopy(self.interface)
        value["types"]["RunContext"]["fields"][0]["type"] = "NonEmptyIdentifier"
        self.assert_document_mutation_fails(interface=value)

    def test_interface_nullability_mutation_rejected(self):
        value = copy.deepcopy(self.interface)
        value["types"]["RunSpec"]["fields"][5]["nullable"] = False
        self.assert_document_mutation_fails(interface=value)

    def test_interface_producer_mutation_rejected(self):
        value = copy.deepcopy(self.interface)
        value["types"]["RunContext"]["fields"][1]["producer"] = "caller"
        self.assert_document_mutation_fails(interface=value)

    def test_interface_consumer_mutation_rejected(self):
        value = copy.deepcopy(self.interface)
        value["types"]["AuthorityRef"]["fields"][0]["consumers"] = []
        self.assert_document_mutation_fails(interface=value)

    def test_obligation_owner_mutation_rejected(self):
        value = copy.deepcopy(self.obligations)
        value["c0_owned_obligations"][0]["owner"] = "C1"
        self.assert_document_mutation_fails(obligations=value)

    def test_obligation_probe_mutation_rejected(self):
        value = copy.deepcopy(self.obligations)
        value["c0_owned_obligations"][0]["probe_id"] = "P14"
        self.assert_document_mutation_fails(obligations=value)

    def test_obligation_pointer_mutation_rejected(self):
        value = copy.deepcopy(self.obligations)
        value["c0_owned_obligations"][0]["source_pointer"] = "/data_contract"
        self.assert_document_mutation_fails(obligations=value)

    def test_finding_mapping_mutation_rejected(self):
        value = copy.deepcopy(self.contract)
        value["failure_findings"][0]["probe_id"] = "P02"
        self.assert_document_mutation_fails(contract=value)

    def test_gate_mutation_rejected(self):
        value = copy.deepcopy(self.contract)
        value["qualification_gates"].pop()
        self.assert_document_mutation_fails(contract=value)

    def test_future_boundary_mutation_rejected(self):
        value = copy.deepcopy(self.contract)
        value["future_component_boundary"]["C3"] = "implemented"
        self.assert_document_mutation_fails(contract=value)

    def test_bundle_role_mutation_rejected(self):
        value = copy.deepcopy(self.contract)
        value["required_bundle_roles"][0] = "plan"
        self.assert_document_mutation_fails(contract=value)

    def test_public_api_economic_argument_mutation_rejected(self):
        value = copy.deepcopy(self.interface)
        value["supported_public_api"]["arguments"].append(
            {"consumers": ["C0"], "name": "price", "nullable": False, "producer": "caller", "type": "NonNegativeInteger"}
        )
        self.assert_document_mutation_fails(interface=value)


if __name__ == "__main__":
    unittest.main()
