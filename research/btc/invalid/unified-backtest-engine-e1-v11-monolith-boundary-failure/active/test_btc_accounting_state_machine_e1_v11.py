"""The 56 frozen E1-v11 probes, one explicit substantive test per probe."""

from __future__ import annotations

import inspect
import json
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from trading_platform.btc_accounting_state_machine_e1_v11 import (  # noqa: E402
    ACCOUNT_FIELDS, DECISION_FIELDS, EPISODE_FIELDS, FILL_FIELDS, FUNDING_FIELDS,
    ORDER_FIELDS, AccountingStateMachine, AuthorityVerifiedFactory, ContractViolation,
    PERP, SPOT, Rules, build_control, canonical_bytes, decimal, decimal_text, digest,
    quantize_down, strict_json, utc_text,
)

T1 = "2025-01-01T01:00:00.000000Z"
T2 = "2025-01-01T02:00:00.000000Z"
T3 = "2025-01-01T03:00:00.000000Z"
T4 = "2025-01-01T04:00:00.000000Z"
T5 = "2025-01-01T05:00:00.000000Z"
T6 = "2025-01-01T06:00:00.000000Z"
D = Decimal


class E1V11Probes(unittest.TestCase):
    def machine(self, timestamp=T1):
        m = AuthorityVerifiedFactory.create()
        m._begin_interval(timestamp, "S1")
        m._protection_phase()
        m._funding_phase()
        m._risk_phase()
        m._execution_phase()
        return m

    def entered(self):
        m = self.machine(T1)
        m.atomic_pair_entry(D("1"))
        return m

    def advance(self, m, timestamp, segment="S1"):
        m.close_interval()
        m._begin_interval(timestamp, segment)
        m._protection_phase()
        m._funding_phase()
        m._risk_phase()
        m._execution_phase()

    def test_A01_factory_only(self):
        with self.assertRaises(ContractViolation):
            AccountingStateMachine(None, {}, {}, {}, {}, {}, {}, {}, {})
        self.assertIsInstance(AuthorityVerifiedFactory.create(), AccountingStateMachine)

    def test_A02_manifest_fields(self):
        manifest = strict_json(AuthorityVerifiedFactory._MANIFEST.read_bytes())
        self.assertRegex(manifest["UTC_creation_timestamp"], r"Z$")
        self.assertTrue(all(set(e) == {"path", "sha256", "size_bytes", "semantic_role"} for e in manifest["entries"]))

    def test_A03_active_snapshot_identity(self):
        root = AuthorityVerifiedFactory._ROOT
        expected = AuthorityVerifiedFactory._EXPECTED
        self.assertEqual((root / expected["active_module"]).read_bytes(), (root / expected["snapshot_module"]).read_bytes())
        self.assertEqual((root / expected["active_test"]).read_bytes(), (root / expected["snapshot_test"]).read_bytes())

    def test_A04_binding_immutable(self):
        m = AuthorityVerifiedFactory.create()
        with self.assertRaises(TypeError): m.bindings["x"] = "y"
        with self.assertRaises(ContractViolation): m._phase = 8

    def test_B01_phase_zero(self):
        m = AuthorityVerifiedFactory.create(); before = m.snapshot_digest()
        for call in (lambda: m.atomic_pair_entry(D("1")), lambda: m._funding_phase(D("0.01")), lambda: m.atomic_pair_close()):
            with self.assertRaises(ContractViolation): call()
        self.assertEqual(before, m.snapshot_digest()); self.assertTrue(all(not rows for rows in m.rows.values()))

    def test_B02_wrong_phase(self):
        m = AuthorityVerifiedFactory.create(); m._begin_interval(T1, "S1"); before = m.snapshot_digest()
        with self.assertRaises(ContractViolation): m.atomic_pair_entry(D("1"))
        with self.assertRaises(ContractViolation): m._funding_phase()
        self.assertEqual(before, m.snapshot_digest())

    def test_B03_direct_phase_mutation(self):
        m = AuthorityVerifiedFactory.create()
        with self.assertRaises(ContractViolation): m._phase = 6
        self.assertEqual(0, m.phase)

    def test_B04_ID_time_order(self):
        m = AuthorityVerifiedFactory.create(); self.assertEqual(1, m._next_id())
        with self.assertRaises(ContractViolation): m._next_id(1)
        m = AuthorityVerifiedFactory.create(); m._begin_interval(T1, "S1"); m._protection_phase(); m._funding_phase(); m._risk_phase(); m._execution_phase(); m.close_interval()
        with self.assertRaises(ContractViolation): m._begin_interval(T1, "S1")
        with self.assertRaises(ContractViolation): utc_text("2025-01-01T01:00:00")

    def test_B05_stale_reversal(self):
        m = self.entered(); self.advance(m, T2)
        before = m.snapshot_digest()
        with self.assertRaises(ContractViolation): m._begin_interval(T1, "S1")
        self.assertEqual(before, m.snapshot_digest())

    def test_B06_terminal_monotone(self):
        m = AuthorityVerifiedFactory.create(); m.terminate()
        before = m.snapshot_digest()
        with self.assertRaises(ContractViolation): m._begin_interval(T1, "S1")
        with self.assertRaises(ContractViolation): m._funding_phase(D("0.01"))
        self.assertEqual(before, m.snapshot_digest())

    def test_B07_exact_phase_priority(self):
        m = AuthorityVerifiedFactory.create(); m._begin_interval(T1, "S1"); self.assertEqual(2, m.phase)
        m._protection_phase(); self.assertEqual(3, m.phase); m._funding_phase(); self.assertEqual(4, m.phase)
        m._risk_phase(); self.assertEqual(5, m.phase); m._execution_phase(); self.assertEqual(6, m.phase)
        m.close_interval(); self.assertEqual(9, m.phase)

    def test_B08_funding_ownership(self):
        m = self.entered(); incoming = m.state["perpetual_quantity"]; self.advance(m, T2)
        # advance used zero rate; return to a new machine to settle a nonzero owned payment.
        m = self.entered(); m.close_interval(); m._begin_interval(T2, "S1"); m._protection_phase(); m._funding_phase(D("0.01"), T2, T2)
        row = m.rows["funding"][-1]
        self.assertEqual(D(row["cashflow_quote"]), -incoming * D(row["funding_mark"]) * D(row["funding_rate"]))

    def test_B09_risk_PnL_separation(self):
        m = self.entered(); m.close_interval()
        close = D(m._source["observations"][1]["close"])
        self.assertEqual(close, m.state["perpetual_mark"])
        self.assertEqual(m.state["perpetual_quantity"] * (close - D("101")), m.state["unrealized_PnL"])

    def test_C01_pair_methods(self):
        self.assertTrue(callable(getattr(AccountingStateMachine, "atomic_pair_entry")))
        self.assertTrue(callable(getattr(AccountingStateMachine, "atomic_pair_close")))
        self.assertFalse(hasattr(AccountingStateMachine, "fill"))
        self.assertFalse(hasattr(AccountingStateMachine, "funding_phase"))
        self.assertFalse(hasattr(AccountingStateMachine, "begin_interval"))
        self.assertFalse(hasattr(AccountingStateMachine, "execution_phase"))

    def test_C02_pair_entry_success(self):
        m = self.entered(); self.assertEqual(D("1"), m.state["spot_quantity"]); self.assertEqual(D("-1"), m.state["perpetual_quantity"])
        self.assertEqual([SPOT, PERP], [r["instrument"] for r in m.rows["fill"]]); self.assertEqual(2, len(m.rows["order"]))

    def test_C03_pair_entry_zero(self):
        m = self.machine(T3); m.atomic_pair_entry(D("1"))
        self.assertEqual((D("0"), D("0")), (m.state["spot_quantity"], m.state["perpetual_quantity"]))
        self.assertEqual("invalid_unknown", m.state["state"]); self.assertEqual([SPOT, SPOT], [r["instrument"] for r in m.rows["fill"]])

    def test_C04_pair_entry_partial(self):
        m = self.machine(T4); m.atomic_pair_entry(D("1"))
        reasons = [r["reason"] for r in m.rows["order"]]
        self.assertEqual(["pair_entry_spot", "pair_entry_perpetual_partial", "pair_entry_recover_perpetual", "pair_entry_recover_spot"], reasons)
        self.assertEqual((D("0"), D("0")), (m.state["spot_quantity"], m.state["perpetual_quantity"]))

    def test_C05_pair_entry_preflight_atomicity(self):
        m = self.machine(T1); before = m.snapshot_digest(); rows = {k: len(v) for k,v in m.rows.items()}
        with self.assertRaises(ContractViolation): m.atomic_pair_entry(D("9"))
        self.assertEqual(before, m.snapshot_digest()); self.assertEqual(rows, {k: len(v) for k,v in m.rows.items()})

    def test_C06_committed_fills(self):
        m = self.machine(T4); m.atomic_pair_entry(D("1"))
        self.assertEqual(4, len(m.rows["fill"])); self.assertEqual(4, len({r["fill_id"] for r in m.rows["fill"]}))
        self.assertTrue(all(r["row_digest"] for r in m.rows["fill"]))

    def test_C07_pair_close_success(self):
        m = self.entered(); self.advance(m, T2); start = len(m.rows["fill"]); m.atomic_pair_close(); new = m.rows["fill"][start:]
        self.assertEqual([SPOT, PERP], [r["instrument"] for r in new]); self.assertEqual("0", new[-1]["unfilled_quantity"] if "unfilled_quantity" in new[-1] else m.rows["order"][-1]["unfilled_quantity"])
        self.assertEqual((D("0"), D("0")), (m.state["spot_quantity"], m.state["perpetual_quantity"]))

    def test_E01_cartesian_universe(self):
        m = self.entered(); self.advance(m, T2); u = m._cartesian_preflight(D("1"))
        self.assertEqual(D("1"), u.outcomes[-1].quantity); self.assertEqual(64, len(u.set_digest))

    def test_E02_no_caller_universe(self):
        sig = inspect.signature(m := AccountingStateMachine.atomic_pair_close)
        self.assertEqual(["self"], list(sig.parameters)); self.assertNotIn("price", inspect.signature(AccountingStateMachine.atomic_pair_entry).parameters)

    def test_E03_depth_economics(self):
        m = self.machine(T1); u = m.derive_depth_outcome_universe(SPOT, "buy", D("1"))
        o = u.outcomes[-1]; self.assertEqual(D("100"), o.vwap)
        self.assertEqual(o.quantity * o.vwap * D("0.001"), o.explicit_cost)
        with self.assertRaises(ContractViolation): m.derive_depth_outcome_universe(SPOT, "buy", D("2"))

    def test_E04_set_canonical(self):
        first, second = self.machine(T1), self.machine(T1)
        self.assertEqual(first.derive_depth_outcome_universe(SPOT, "buy", D("1")).set_digest,
                         second.derive_depth_outcome_universe(SPOT, "buy", D("1")).set_digest)
        with self.assertRaises(ContractViolation): strict_json(b'{"levels":[1],"levels":[1]}')
        with self.assertRaises(TypeError): first._source["observations"][0]["asks"][0]["price"] = "99.00"

    def test_E05_candle_exact(self):
        m = self.entered(); self.assertEqual(D("100"), D(m.rows["fill"][0]["accounting_fill_price"])); self.assertEqual("0", m.rows["order"][0]["unfilled_quantity"])

    def test_E06_severe_bound(self):
        m = self.machine(T1); before = m.snapshot_digest()
        with self.assertRaises(ContractViolation): m.atomic_pair_entry(D("11"))
        self.assertEqual(before, m.snapshot_digest())

    def test_F01_mismatch_immediate(self):
        m = self.entered(); self.advance(m, T6); m.atomic_pair_close()
        self.assertEqual("pair_close_severe_residual", m.rows["order"][-1]["reason"])

    def test_F02_mismatch_checkpoint(self):
        m = self.entered(); self.advance(m, T6); m.atomic_pair_close()
        self.assertEqual(D("0"), m.state["perpetual_quantity"]); self.assertFalse(m._liquidated)

    def test_F03_delayed_persistence(self):
        m = self.entered(); self.advance(m, T5); m.atomic_pair_close()
        self.assertIsNotNone(m._pending); self.assertEqual("invalid_unknown", m.state["state"]); self.assertEqual(0, m._pending["attempts"])

    def test_F04_segment_exception(self):
        m = self.entered(); self.advance(m, T5); m.atomic_pair_close(); m.close_interval(); m._begin_interval(T6, "S2"); m._protection_phase()
        self.assertIsNone(m._pending); self.assertEqual(D("0"), m.state["perpetual_quantity"]); self.assertEqual("delayed_segment_safety", m.rows["order"][-1]["reason"])

    def test_F05_boundary_denials(self):
        m = self.entered(); self.advance(m, T5); m.atomic_pair_close(); m.close_interval()
        with self.assertRaises(ContractViolation): m._begin_interval(T6, "S2", terminal=True)
        self.assertIsNotNone(m._pending)

    def test_G01_cost_authority(self):
        m = self.entered(); fee = D(m.rows["fill"][0]["explicit_fee_native"]); implicit = D(m.rows["fill"][0]["implicit_cost_quote"])
        self.assertEqual(D("1") * D("100") * D("10") / D("10000"), fee)
        self.assertEqual(D("1") * D("100") * D("5") / D("10000"), implicit)

    def test_G02_instrument_authority(self):
        m = self.machine(); before = m.snapshot_digest()
        with self.assertRaises(ContractViolation): m._preflight("ETH/USDT", D("1"), D("100"), True)
        self.assertEqual(before, m.snapshot_digest())

    def test_G03_caps(self):
        m = self.machine(); before = m.snapshot_digest()
        with self.assertRaises(ContractViolation): m.atomic_pair_entry(D("6"))
        self.assertEqual(before, m.snapshot_digest())

    def test_G04_pair_constraints(self):
        self.assertEqual(["self", "quantity"], list(inspect.signature(AccountingStateMachine.atomic_pair_entry).parameters))
        self.assertFalse(hasattr(AccountingStateMachine, "naked_pair_leg"))

    def test_G05_pyramiding(self):
        m = self.entered(); before = m.snapshot_digest()
        with self.assertRaises(ContractViolation): m.atomic_pair_entry(D("0.1"))
        self.assertEqual(before, m.snapshot_digest())

    def test_H01_authority_bytes(self):
        original = Path.read_bytes
        active = AuthorityVerifiedFactory._ROOT / AuthorityVerifiedFactory._EXPECTED["execution_configuration"]
        def changed(path):
            raw = original(path)
            return raw + b" " if path == active else raw
        with patch.object(Path, "read_bytes", changed):
            with self.assertRaises(ContractViolation): AuthorityVerifiedFactory.create()

    def test_H02_lineage(self):
        m = self.entered(); fill = m.rows["fill"][-1]
        self.assertEqual(m._rules[PERP].digest, fill["rules_digest"]); self.assertIn(fill["source_digest"], [r["row_digest"] for r in m._source["observations"]])
        self.assertEqual(64, len(fill["row_digest"]))

    def test_D01_gap_execution(self):
        m = self.entered(); m.close_interval(); m.gap_cleanup(T6, "S2")
        self.assertEqual((D("0"), D("0")), (m.state["spot_quantity"], m.state["perpetual_quantity"]))
        self.assertTrue(any(r["reason"].startswith("gap_") for r in m.rows["order"])); self.assertTrue(m.rows["account"])

    def test_D02_gap_state_reset(self):
        m = self.entered(); m._rolling.append("warm"); m.close_interval(); m.gap_cleanup(T6, "S2")
        self.assertEqual([], m._rolling); self.assertEqual("invalid_unknown", m.state["state"])

    def test_D03_gap_unavailable(self):
        m = self.entered(); m.close_interval(); before = m.snapshot_digest()
        with self.assertRaises(ContractViolation): m.gap_cleanup("2025-01-01T07:00:00.000000Z", "S2")
        self.assertNotEqual("valid", m.state["state"]); self.assertNotEqual(before, m.snapshot_digest())

    def test_D04_flat_control(self):
        a, b = build_control("flat"), build_control("flat"); self.assertIsNot(a, b)
        a._begin_interval(T1, "S1"); a._protection_phase(); a._funding_phase(); a._risk_phase(); a._execution_phase(); a._decision("flat", "abstain", "control"); a.close_interval()
        self.assertEqual(D("0"), a.state["spot_quantity"]); self.assertEqual(1, len(a.rows["decision"])); self.assertEqual(1, len(a.rows["account"]))

    def test_D05_buy_hold_control(self):
        m = build_control("buy_and_hold"); m._begin_interval(T1, "S1"); m._protection_phase(); m._funding_phase(); m._risk_phase(); m._execution_phase(); m.atomic_pair_entry(D("1"))
        self.assertEqual(T1, m.rows["order"][0]["arrival_at"]); self.assertGreater(m.state["explicit_costs"], D("0"))

    def test_D06_same_exposure_control(self):
        m = build_control("same_exposure"); self.assertTrue(m._rolling[0]["independent_information_rule"])
        m._begin_interval(T1, "S1"); m._protection_phase(); m._funding_phase(); m._risk_phase(); m._execution_phase(); m.atomic_pair_entry(D("1"))
        self.assertEqual(abs(m.state["spot_quantity"]), abs(m.state["perpetual_quantity"]))

    def test_I01_daily_loss(self):
        m = AuthorityVerifiedFactory.create(); m._state["NAV"] = D("985"); m._set("_phase", 4)
        self.assertFalse(m._risk_phase()); m._state["UTC_day_start"] = D("984"); m._set("_phase", 4); self.assertTrue(m._risk_phase())

    def test_I02_drawdown(self):
        m = AuthorityVerifiedFactory.create(); m._state["NAV"] = D("900"); m._state["UTC_day_start"] = D("900"); m._state["high_water"] = D("1000"); m._set("_phase", 4)
        self.assertFalse(m._risk_phase()); m._state["high_water"] = D("999"); m._set("_phase", 4); self.assertTrue(m._risk_phase())

    def test_I03_protective_reduction(self):
        m = self.entered(); m._set("_risk_increase_allowed", False); self.advance(m, T2); m._set("_risk_increase_allowed", False); m.atomic_pair_close()
        self.assertEqual((D("0"), D("0")), (m.state["spot_quantity"], m.state["perpetual_quantity"]))

    def test_J01_decimal_only(self):
        with self.assertRaises(ContractViolation): decimal(1.25)
        source = inspect.getsource(sys.modules[AccountingStateMachine.__module__]); self.assertNotIn("math.", source)
        self.assertIsInstance(self.entered().state["NAV"], Decimal)

    def test_J02_rule_rounding(self):
        r = Rules(D("0.01"), D("0.001"), D("5"), D("10"), "x")
        self.assertEqual(D("1.234"), quantize_down(D("1.2349"), r.step)); self.assertEqual(D("-1.234"), quantize_down(D("-1.2349"), r.step))
        with self.assertRaises(ContractViolation): r.quantity(D("0.001"), D("100"))

    def test_J03_canonical_serialization(self):
        self.assertEqual(b'{"a":"1.2","b":"0"}\n', canonical_bytes({"b": D("-0"), "a": D("1.200")}))
        self.assertEqual("0", decimal_text(D("-0")))
        with self.assertRaises(ContractViolation): strict_json(b'{"a":1,"a":2}')
        with self.assertRaises(ContractViolation): strict_json(b'{"a":NaN}')

    def test_K01_exact_schemas(self):
        m = self.entered(); self.advance(m, T2); m.atomic_pair_close(); m.close_interval(); account = m.rows["account"][-1]
        self.assertEqual(DECISION_FIELDS, set(m.rows["decision"][0])); self.assertEqual(ORDER_FIELDS, set(m.rows["order"][0])); self.assertEqual(FILL_FIELDS, set(m.rows["fill"][0])); self.assertEqual(ACCOUNT_FIELDS, set(account)); self.assertEqual(EPISODE_FIELDS, set(m.episodes[-1]))

    def test_K02_digest_sequence(self):
        m = self.entered(); all_rows = sorted((r for rows in m.rows.values() for r in rows), key=lambda r:r["event_sequence"])
        for left, right in zip(all_rows, all_rows[1:]): self.assertEqual(left["after_state_digest"], right["before_state_digest"])
        self.assertEqual(list(range(1, len(all_rows)+1)), [r["event_sequence"] for r in all_rows])

    def test_K03_liquidation(self):
        m = self.entered(); m._state["isolated_collateral"] = D("0.01"); m._liquidation_checkpoint("intrabar", D("300"), "b"*64)
        self.assertTrue(m._liquidated); self.assertEqual("liquidation", m.rows["order"][-1]["scenario_id"]); self.assertEqual(m.rows["order"][-1]["order_id"], m.rows["fill"][-1]["order_id"])

    def test_K04_episode_attribution(self):
        m = self.entered(); self.advance(m, T2); m.atomic_pair_close(); ep = m.episodes[-1]
        expected = D(ep["price_PnL"]) + D(ep["funding_PnL"]) - D(ep["entry_costs"]) - D(ep["exit_costs"])
        self.assertEqual("matched_pair", ep["direction"]); self.assertEqual(expected, D(ep["net_dollar_PnL"]))

    def test_K05_artifact_derivation(self):
        m = self.entered(); art = m.artifacts()
        self.assertEqual({k:len(v) for k,v in m.rows.items()}, {k:art["counts"][k] for k in m.rows})
        self.assertEqual(decimal_text(sum(D(r["explicit_fee_quote_equivalent"]) for r in m.rows["fill"])), art["explicit_costs"])

    def test_K06_failure_side_effects(self):
        m = self.machine(); before = (m.snapshot_digest(), m.phase, m._clock, m._last_id, {k:len(v) for k,v in m.rows.items()})
        with self.assertRaises(ContractViolation): m.atomic_pair_entry(D("20"))
        after = (m.snapshot_digest(), m.phase, m._clock, m._last_id, {k:len(v) for k,v in m.rows.items()})
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
