"""Twenty-two literal adversarial E1-v8 probes, using synthetic inputs only."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from trading_platform.btc_accounting_state_machine_e1_v8 import (  # noqa: E402
    ACCOUNT_FIELDS, DECISION_FIELDS, EPISODE_FIELDS, FILL_FIELDS, FUNDING_FIELDS,
    ORDER_FIELDS, AccountingEngine, AccountingError, Fee, InstrumentRules,
    RunBinding, SourceMark, canonical_json, decimal_string, parse_json_strict,
    verify_manifest_bound_implementation,
)


T0 = datetime(2025, 1, 1, tzinfo=timezone.utc)
SPOT_DIGEST = "spot-rules"
PERP_DIGEST = "perp-rules"


def rules():
    return (
        InstrumentRules("BTC_USDT_spot", Decimal("0.01"), Decimal("1"),
                        Decimal("0.01"), Decimal("1"), Decimal("100"), SPOT_DIGEST),
        InstrumentRules("BTCUSDT_USD_M_linear_perpetual", Decimal("0.01"), Decimal("1"),
                        Decimal("0.01"), Decimal("1"), Decimal("100"), PERP_DIGEST),
    )


def binding(mandate="retail-btc-directional-perpetual-research-v1", adapter="candle_OHLC",
            scenario="candle-primary-30bps-rt-v1", terminal=None):
    mandates = {
        "retail-btc-spot-v2": ("config/retail_mandate.json",
            "7e34cfb0928b4373bbf52b5c5505f63a2b19e674124059191c1b6c62ec129041"),
        "retail-btc-directional-perpetual-research-v1":
            ("config/mandates/retail-btc-directional-perpetual-research-v1.json",
             "1b5d492f12f71ebe28e1bdfbd0b5916bcf0ad285b483cb10bf8770504371165d"),
        "retail-btc-delta-neutral-research-v1":
            ("config/mandates/retail-btc-delta-neutral-research-v1.json",
             "d95a53ee493862549b932dc5f80600a02a0e38e4ba1b3da0d79d0b0c5bb9eeba"),
    }
    path, mdigest = mandates[mandate]
    return RunBinding("synthetic-run", scenario, mandate, path, mdigest,
        "config/execution_scenarios.json",
        "a020cb07780e88b60fffd4c6e1b205922f0b815f033a4676dd422a7038538f36",
        "contract", "implementation", SPOT_DIGEST, PERP_DIGEST, "spot-fee", "perp-fee",
        "severe", "margin-v1", ("source",), adapter, Decimal("1"), Decimal("0.001"),
        Decimal("0.004"), Decimal("0.25"), Decimal("0.01"), T0,
        terminal or T0 + timedelta(days=2), "eligible_next_open")


def mark(instrument, at=T0 + timedelta(hours=1), segment="s1", opening="100",
         high="105", low="95", close="102", source="source", mark_source="official-mark",
         rule_digest=None):
    return SourceMark(instrument, at, segment, Decimal(opening), Decimal(high), Decimal(low),
        Decimal(close), at, at, source, mark_source,
        rule_digest or (SPOT_DIGEST if instrument == "BTC_USDT_spot" else PERP_DIGEST))


def engine(mandate="retail-btc-directional-perpetual-research-v1", adapter="candle_OHLC",
           scenario="candle-primary-30bps-rt-v1", cash="1000", terminal=None):
    spot, perp = rules()
    out = AccountingEngine(binding(mandate, adapter, scenario, terminal), Decimal(cash), spot, perp)
    out.segment_id = "s1"
    out.spot_mark = Decimal("100")
    out.perpetual_mark = Decimal("100")
    return out


def mutable_image(e):
    return deepcopy((e.snapshot(), e.seen_keys, e.ledgers, e.sequence, e.invalid,
                     e.unknown, e.pending_safety, e.current_phase))


class E1V8MandatoryProbes(unittest.TestCase):
    # Preserved-v7 probe 1.
    def test_01_reject_phase_2_ordinary_increase(self):
        e = engine()
        e.current_phase = 2
        before = mutable_image(e)
        with self.assertRaisesRegex(AccountingError, "phase/terminal increase"):
            e.fill("o1", T0 + timedelta(hours=1), "BTCUSDT_USD_M_linear_perpetual",
                   Decimal("1"), Decimal("100"), Fee("quote", Decimal("0.001")),
                   mark("BTCUSDT_USD_M_linear_perpetual"))
        self.assertEqual(mutable_image(e), before)

    # Preserved-v7 probe 2.
    def test_02_failing_preflight_leaves_state_keys_orders_rows_unchanged(self):
        e = engine(mandate="retail-btc-spot-v2")
        before = mutable_image(e)
        bad = mark("BTC_USDT_spot", rule_digest="wrong")
        with self.assertRaisesRegex(AccountingError, "source/rule"):
            e.fill("o2", bad.timestamp, bad.instrument, Decimal("1"), Decimal("100"),
                   Fee("quote", Decimal("0.001")), bad)
        self.assertEqual(mutable_image(e), before)
        # Third-fee insufficiency is likewise checked before any event key/row mutation.
        with self.assertRaisesRegex(AccountingError, "insufficient third"):
            e.fill("o3", T0 + timedelta(hours=1), "BTC_USDT_spot", Decimal("1"), Decimal("100"),
                   Fee("third", Decimal("0.001"), third_asset_mark=Decimal("2")),
                   mark("BTC_USDT_spot"))
        self.assertEqual(mutable_image(e), before)

    # Preserved-v7 probe 3.
    def test_03_reject_post_observed_open_liquidation_funding_event_and_row(self):
        e = engine(cash="20")
        src = mark("BTCUSDT_USD_M_linear_perpetual", opening="100", high="101", low="1", close="2")
        e.fill("entry", src.timestamp, src.instrument, Decimal("0.1"), Decimal("100"),
               Fee("quote", Decimal("0")), mark(src.instrument))
        self.assertTrue(e.liquidate(src, Decimal("0.01"), Decimal("1")))
        rows = len(e.ledgers["funding"])
        with self.assertRaisesRegex(AccountingError, "funding at/after"):
            e.funding(src.timestamp, Decimal("0.01"), Decimal("1"), src.timestamp,
                      "source", "official-mark", "index", PERP_DIGEST)
        self.assertEqual(len(e.ledgers["funding"]), rows)

    # Preserved-v7 probe 4.
    def test_04_adverse_extreme_does_not_replace_close_to_close_PnL_mark(self):
        e = engine()
        entry = mark("BTCUSDT_USD_M_linear_perpetual")
        e.fill("entry", entry.timestamp, entry.instrument, Decimal("1"), Decimal("100"),
               Fee("quote", Decimal("0")), entry)
        later = mark(entry.instrument, T0 + timedelta(hours=2), opening="102", high="120", low="80", close="110")
        e.segment_id = "s1"; e.perpetual_mark = later.close
        e._refresh_reserve(later.low)
        adverse_equity = e.margin_equity(later.low)
        e._refresh_reserve(later.close)
        nav = e.nav(perpetual_mark=later.close)
        self.assertEqual(e.state.unrealized_PnL, Decimal("10"))
        self.assertNotEqual(adverse_equity, e.margin_equity(later.close))
        self.assertEqual(nav, e.state.quote_cash + e.state.isolated_collateral + Decimal("10"))

    # Preserved-v7 probe 5.
    def test_05_reject_pair_entry_before_leg_1_when_any_recovery_path_missing_or_invalid(self):
        e = engine("retail-btc-delta-neutral-research-v1")
        before = mutable_image(e)
        paths = [{"R":"1", "q":"0", "ordinary_funded":True, "residual_valid":True,
                  "severe_funded":True, "spot_rules_digest":SPOT_DIGEST,
                  "perp_rules_digest":PERP_DIGEST, "source_digest":"source"}]
        with self.assertRaisesRegex(AccountingError, "Cartesian"):
            e.pair_close_preflight(paths, [("1", "0"), ("1", "1")], "source")
        self.assertEqual(mutable_image(e), before)
        paths.append({"R":"1", "q":"1", "ordinary_funded":True, "residual_valid":False,
                      "severe_funded":True, "spot_rules_digest":SPOT_DIGEST,
                      "perp_rules_digest":PERP_DIGEST, "source_digest":"source"})
        with self.assertRaisesRegex(AccountingError, "invalid recovery"):
            e.pair_close_preflight(paths, [("1", "0"), ("1", "1")], "source")
        self.assertEqual(mutable_image(e), before)

    # Preserved-v7 probe 6.
    def test_06_failed_pair_intention_invalid_unknown_after_complete_neutralization(self):
        e = engine("retail-btc-delta-neutral-research-v1")
        e.pair_failure("second_leg_failure", neutralized=True, attempts=1, commits=2)
        self.assertTrue(e.invalid and e.unknown)
        self.assertIsNone(e.pending_safety)
        self.assertFalse(e.entry_allowed(Decimal("1000")))

    # Preserved-v7 probe 7.
    def test_07_controls_emit_real_ledgers_under_predeclared_partition_terminal_convention(self):
        e = engine("retail-btc-spot-v2")
        opening = mark("BTC_USDT_spot", T0)
        closing = mark("BTC_USDT_spot", T0 + timedelta(days=1))
        controls = e.controls(opening, closing, [{"at": T0 + timedelta(hours=1), "exposure": "0.2"}])
        self.assertEqual(len(controls["flat"]["ledger"]["account"]), 2)
        self.assertEqual(len(controls["true_buy_and_hold"]["ledger"]["fill"]), 2)
        self.assertEqual(len(controls["same_timestamp_same_exposure"]["ledger"]["decision"]), 1)
        self.assertEqual(controls["terminal_convention"], e.binding.terminal_convention)
        with self.assertRaisesRegex(AccountingError, "partition boundary"):
            e.controls(mark("BTC_USDT_spot", T0 + timedelta(hours=1)), closing, [])

    # Preserved-v7 probe 8.
    def test_08_gap_first_valid_in_bound_open_full_path_reset_and_sticky_invalid(self):
        e = engine()
        src = mark("BTCUSDT_USD_M_linear_perpetual")
        e.fill("entry", src.timestamp, src.instrument, Decimal("1"), Decimal("100"),
               Fee("quote", Decimal("0")), src)
        next_at = T0 + timedelta(hours=5)
        e.gap(mark("BTC_USDT_spot", next_at, "s2", opening="70", high="72", low="60", close="71"),
              mark(src.instrument, next_at, "s2", opening="65", high="70", low="50", close="68"))
        self.assertEqual(e.perpetual_mark, Decimal("65"))
        self.assertEqual(e.segment_id, "s2")
        self.assertTrue(e.invalid and e.unknown)
        self.assertEqual(e.pending_safety, "forced_neutralization")
        with self.assertRaisesRegex(AccountingError, "outside boundary"):
            e.gap(mark("BTC_USDT_spot", T0 + timedelta(days=3), "s3"),
                  mark(src.instrument, T0 + timedelta(days=3), "s3"))
        self.assertTrue(e.invalid)  # sticky

    # Preserved-v7 probe 9.
    def test_09_reject_caller_endpoint_only_partial_Cartesian_and_missing_intermediate_R_or_q(self):
        e = engine("retail-btc-delta-neutral-research-v1", "qualified_quote_L2",
                   "book-taker-primary-250ms-v1")
        endpoint = {"R":"1", "q":"1", "spot_vwap":"100", "perp_vwap":"100",
            "severe_vwap":"100", "spot_rules_digest":SPOT_DIGEST, "perp_rules_digest":PERP_DIGEST,
            "source_digest":"source", "spot_explicit_cost":"0", "spot_implicit_cost":"0",
            "perp_explicit_cost":"0", "perp_implicit_cost":"0"}
        with self.assertRaisesRegex(AccountingError, "missing intermediate R"):
            e.qualify_partial_outcomes("source", [endpoint], ["0.5", "1"], {"1":["1"]},
                                       Fee("quote", Decimal("0")), Fee("quote", Decimal("0")))
        with self.assertRaisesRegex(AccountingError, "incomplete Cartesian"):
            e.qualify_partial_outcomes("source", [endpoint], ["1"], {"1":["0.5", "1"]},
                                       Fee("quote", Decimal("0")), Fee("quote", Decimal("0")))

    # Preserved-v7 probe 10.
    def test_10_reject_unqualified_outcome_VWAP_cost_fee_or_tick(self):
        e = engine("retail-btc-delta-neutral-research-v1", "qualified_quote_L2",
                   "book-taker-primary-250ms-v1")
        base = {"R":"1", "q":"1", "spot_vwap":"100", "perp_vwap":"100",
            "severe_vwap":"100", "spot_rules_digest":SPOT_DIGEST, "perp_rules_digest":PERP_DIGEST,
            "source_digest":"source", "spot_explicit_cost":"1", "spot_implicit_cost":"0",
            "perp_explicit_cost":"0", "perp_implicit_cost":"0"}
        with self.assertRaisesRegex(AccountingError, "fee mutation"):
            e.qualify_partial_outcomes("source", [base], ["1"], {"1":["1"]},
                                       Fee("quote", Decimal("0")), Fee("quote", Decimal("0")))
        bad = dict(base, spot_explicit_cost="0", perp_vwap="100.5")
        with self.assertRaisesRegex(AccountingError, "off-rule"):
            e.qualify_partial_outcomes("source", [bad], ["1"], {"1":["1"]},
                                       Fee("quote", Decimal("0")), Fee("quote", Decimal("0")))

    # Preserved-v7 probe 11.
    def test_11_reject_caller_substituted_candle_open_common_marks_memo_delay_segment(self):
        e = engine()
        src = mark("BTCUSDT_USD_M_linear_perpetual")
        for kwargs, phrase in [({"price":Decimal("99")}, "caller-substituted"),
                               ({"at":T0 + timedelta(hours=2)}, "timestamp" )]:
            before = mutable_image(e)
            params = dict(order_id="x" + phrase, at=src.timestamp, instrument=src.instrument,
                          signed_quantity=Decimal("1"), price=Decimal("100"),
                          fee=Fee("quote", Decimal("0")), source=src)
            params.update(kwargs)
            with self.assertRaises(AccountingError): e.fill(**params)
            self.assertEqual(mutable_image(e), before)
        wrong_segment = mark(src.instrument, segment="s9")
        with self.assertRaisesRegex(AccountingError, "segment"):
            e.fill("seg", wrong_segment.timestamp, wrong_segment.instrument, Decimal("1"),
                   Decimal("100"), Fee("quote", Decimal("0")), wrong_segment)

    # Preserved-v7 probe 12.
    def test_12_reject_delayed_price_at_or_beyond_boundary(self):
        terminal = T0 + timedelta(hours=2)
        e = engine(terminal=terminal)
        e.state.signed_perpetual_quantity_BTC = Decimal("1")
        e.state.average_perpetual_entry = Decimal("100")
        e.state.isolated_collateral = Decimal("100")
        for at in (terminal, terminal + timedelta(microseconds=1)):
            with self.assertRaises(AccountingError):
                e.gap(mark("BTC_USDT_spot", at, "s2"), mark("BTCUSDT_USD_M_linear_perpetual", at, "s2"))

    # Preserved-v7 probe 13.
    def test_13_pair_mismatch_failure_records_commits_and_invalidates_after_one_attempt(self):
        e = engine("retail-btc-delta-neutral-research-v1")
        with self.assertRaisesRegex(AccountingError, "one finite"):
            e.pair_failure("mismatch", neutralized=False, attempts=2, commits=1)
        e.pair_failure("mismatch", neutralized=False, attempts=1, commits=3)
        self.assertEqual(e.invalidation_reason, "mismatch")
        self.assertEqual(e.pending_safety, "whole_pair_close")

    # Preserved-v7 probe 14.
    def test_14_reject_mutating_binding_wrong_instrument_order_unauthorized_tax_base_fee_and_pyramiding(self):
        e = engine()
        with self.assertRaises((AttributeError, TypeError)):
            e.binding.scenario_id = "changed"
        src = mark("BTCUSDT_USD_M_linear_perpetual")
        with self.assertRaisesRegex(AccountingError, "wrong instrument"):
            InstrumentRules("ETH", Decimal("1"), Decimal("1"), Decimal("1"), Decimal("1"), Decimal("2"), "x")
        with self.assertRaisesRegex(AccountingError, "unauthorized tax"):
            Fee("quote", Decimal("0"), Decimal("0.01"))
        with self.assertRaisesRegex(AccountingError, "base perpetual"):
            e.fill("base", src.timestamp, src.instrument, Decimal("1"), Decimal("100"),
                   Fee("base", Decimal("0.001")), src)
        e.fill("first", src.timestamp, src.instrument, Decimal("1"), Decimal("100"),
               Fee("quote", Decimal("0")), src)
        with self.assertRaisesRegex(AccountingError, "pyramiding"):
            e.fill("second", src.timestamp, src.instrument, Decimal("1"), Decimal("100"),
                   Fee("quote", Decimal("0")), src)

    # Preserved-v7 probe 15.
    def test_15_reject_post_terminal_order_decision_fill_and_future_timestamp(self):
        e = engine()
        e.terminal = True; e.last_timestamp = T0 + timedelta(hours=1)
        src = mark("BTCUSDT_USD_M_linear_perpetual", T0 + timedelta(hours=2))
        with self.assertRaisesRegex(AccountingError, "post-terminal"):
            e.decision("d", src.timestamp, "flat", "source", PERP_DIGEST, src.timestamp, False)
        with self.assertRaisesRegex(AccountingError, "post-terminal"):
            e.fill("o", src.timestamp, src.instrument, Decimal("1"), Decimal("100"),
                   Fee("quote", Decimal("0")), src)
        with self.assertRaisesRegex(AccountingError, "future source"):
            SourceMark("BTC_USDT_spot", T0 + timedelta(hours=1), "s1", Decimal("100"),
                Decimal("101"), Decimal("99"), Decimal("100"), T0 + timedelta(hours=1),
                T0 + timedelta(hours=2), "source", "mark", SPOT_DIGEST)

    # Preserved-v7 probe 16.
    def test_16_reject_caller_path_value_implementation_digest_and_mismatched_rule_source_margin_digest(self):
        payload = b"synthetic implementation"
        h = sha256(payload).hexdigest()
        manifest = {"entries": [
            {"path":"active.py", "sha256":h, "size_bytes":len(payload), "semantic_role":"active_module"},
            {"path":"snapshot.py", "sha256":h, "size_bytes":len(payload), "semantic_role":"snapshot_module"}]}
        self.assertEqual(verify_manifest_bound_implementation(manifest, "active.py", "snapshot.py", payload, payload), h)
        with self.assertRaisesRegex(AccountingError, "bytes differ"):
            verify_manifest_bound_implementation(manifest, "active.py", "snapshot.py", payload, b"caller")
        e = engine(cash="20")
        src = mark("BTCUSDT_USD_M_linear_perpetual")
        e.fill("entry", src.timestamp, src.instrument, Decimal("0.1"), Decimal("100"), Fee("quote", Decimal("0")), src)
        for changed in (mark(src.instrument, rule_digest="bad"), mark(src.instrument, mark_source="placeholder")):
            with self.assertRaisesRegex(AccountingError, "lineage"):
                e.liquidate(changed, Decimal("0.01"))

    # Preserved-v7 probe 17.
    def test_17_reconcile_liquidation_sequentially_and_match_episode_fill_digest(self):
        e = engine(cash="20")
        entry = mark("BTCUSDT_USD_M_linear_perpetual")
        e.fill("entry", entry.timestamp, entry.instrument, Decimal("0.1"), Decimal("100"), Fee("quote", Decimal("0")), entry)
        shock = mark(entry.instrument, T0 + timedelta(hours=2), opening="100", high="100", low="1", close="1")
        self.assertTrue(e.liquidate(shock, Decimal("0.01"), Decimal("1")))
        order, fill, episode = e.ledgers["order"][-1], e.ledgers["fill"][-1], e.ledgers["episode"][-1]
        self.assertLess(order["event_sequence"], fill["event_sequence"])
        self.assertEqual(fill["row_digest"], episode["exit_fill_digests"][-1])
        self.assertEqual(fill["source_digest"], episode["source_digests"][-1])

    # Preserved-v7 probe 18.
    def test_18_verify_per_episode_funding_spot_pair_direction_PnL_MAE_MFE_and_sticky_invalid_rows_results(self):
        e = engine()
        src = mark("BTCUSDT_USD_M_linear_perpetual")
        e.fill("entry", src.timestamp, src.instrument, Decimal("1"), Decimal("100"), Fee("quote", Decimal("0")), src)
        e.funding(T0 + timedelta(hours=2), Decimal("0.01"), Decimal("100"), T0 + timedelta(hours=2),
                  "source", "official-mark", "index", PERP_DIGEST)
        ep = e.open_episodes[src.instrument]
        self.assertEqual(ep.direction, "long")
        self.assertEqual(ep.funding_PnL, Decimal("-1"))
        ep.maximum_adverse_excursion = Decimal("-5")
        ep.maximum_favourable_excursion = Decimal("8")
        e._invalidate("missing_funding")
        exit_src = mark(src.instrument, T0 + timedelta(hours=3), opening="110", high="112", low="109", close="111")
        e.fill("exit", exit_src.timestamp, exit_src.instrument, Decimal("-1"), Decimal("110"), Fee("quote", Decimal("0")), exit_src, protective=True)
        row = e.ledgers["episode"][-1]
        self.assertEqual((row["direction"], row["funding_PnL"], row["maximum_adverse_excursion"], row["maximum_favourable_excursion"]),
                         ("long", "-1", "-5", "8"))
        self.assertEqual(row["invalidation_reason"], "missing_funding")
        self.assertTrue(e.invalid)
        # Pair direction is independently enforced by mandate.
        pair = engine("retail-btc-delta-neutral-research-v1")
        with self.assertRaisesRegex(AccountingError, "long perpetual"):
            pair.fill("bad", src.timestamp, src.instrument, Decimal("1"), Decimal("100"), Fee("quote", Decimal("0")), src)

    # Preserved-v7 probe 19.
    def test_19_reject_pair_outcome_off_tick_price(self):
        e = engine("retail-btc-delta-neutral-research-v1", "qualified_quote_L2", "book-taker-primary-250ms-v1")
        outcome = {"R":"1", "q":"1", "spot_vwap":"100.5", "perp_vwap":"100",
            "severe_vwap":"100", "spot_rules_digest":SPOT_DIGEST, "perp_rules_digest":PERP_DIGEST,
            "source_digest":"source", "spot_explicit_cost":"0", "spot_implicit_cost":"0",
            "perp_explicit_cost":"0", "perp_implicit_cost":"0"}
        with self.assertRaisesRegex(AccountingError, "off-rule"):
            e.qualify_partial_outcomes("source", [outcome], ["1"], {"1":["1"]},
                                       Fee("quote", Decimal("0")), Fee("quote", Decimal("0")))

    # New-v8 probe 20.
    def test_20_valid_source_derived_observed_severe_path_worse_than_frozen_bound_rejects_before_mutation(self):
        e = engine("retail-btc-delta-neutral-research-v1")
        src = mark("BTCUSDT_USD_M_linear_perpetual", opening="106", high="108", low="105", close="107")
        before = mutable_image(e)
        with self.assertRaisesRegex(AccountingError, "worse than frozen"):
            e.severe_path_preflight(Decimal("106"), Decimal("105"), "buy", src, PERP_DIGEST)
        self.assertEqual(mutable_image(e), before)
        e.severe_path_preflight(Decimal("106"), Decimal("107"), "buy", src, PERP_DIGEST)

    # New-v8 probe 21.
    def test_21_exact_per_ledger_E0_schema_account_actual_segment_numeric_maintenance_and_explicit_invalidation(self):
        e = engine()
        src = mark("BTCUSDT_USD_M_linear_perpetual")
        decision = e.decision("d", src.timestamp, "long", "source", PERP_DIGEST, src.timestamp, True)
        fill = e.fill("o", src.timestamp, src.instrument, Decimal("1"), Decimal("100"), Fee("quote", Decimal("0")), src, decision_id="d")
        funding = e.funding(T0 + timedelta(hours=2), Decimal("0"), Decimal("100"), T0 + timedelta(hours=2),
                            "source", "official-mark", "index", PERP_DIGEST)
        account = e.account_row(src, Decimal("0.005"), Decimal("1"), "index")
        lineage = set(e.binding.lineage)
        self.assertEqual(set(decision), set(DECISION_FIELDS) | lineage)
        self.assertEqual(set(e.ledgers["order"][-1]), set(ORDER_FIELDS) | lineage)
        self.assertEqual(set(fill), set(FILL_FIELDS) | lineage)
        self.assertEqual(set(funding), set(FUNDING_FIELDS) | lineage)
        self.assertEqual(set(account), set(ACCOUNT_FIELDS) | lineage)
        self.assertEqual(account["segment_id"], src.segment_id)
        expected = abs(e.state.signed_perpetual_quantity_BTC) * src.close * Decimal("0.005") + Decimal("1")
        self.assertEqual(Decimal(account["maintenance_requirement"]), expected)
        for ledger in ("decision", "order", "fill", "funding", "account"):
            self.assertIn("invalidation_reason_or_null", e.ledgers[ledger][-1])

    # New-v8 probe 22.
    def test_22_liquidation_rows_reject_placeholder_and_bind_mark_rule_margin_lineage_transitively(self):
        e = engine(cash="20")
        src = mark("BTCUSDT_USD_M_linear_perpetual")
        e.fill("entry", src.timestamp, src.instrument, Decimal("0.1"), Decimal("100"), Fee("quote", Decimal("0")), src)
        placeholder = mark(src.instrument, T0 + timedelta(hours=2), opening="1", high="2", low="1", close="1", mark_source="placeholder")
        before_counts = {k:len(v) for k,v in e.ledgers.items()}
        with self.assertRaisesRegex(AccountingError, "lineage mismatch"):
            e.liquidate(placeholder, Decimal("0.01"))
        self.assertEqual({k:len(v) for k,v in e.ledgers.items()}, before_counts)
        shock = mark(src.instrument, T0 + timedelta(hours=2), opening="1", high="2", low="1", close="1")
        self.assertTrue(e.liquidate(shock, Decimal("0.01"), Decimal("1")))
        order, fill, episode = e.ledgers["order"][-1], e.ledgers["fill"][-1], e.ledgers["episode"][-1]
        self.assertEqual(order["source_digest"], shock.source_digest)
        self.assertEqual(fill["rules_digest"], shock.rules_digest)
        self.assertIn(shock.mark_source_digest, episode["source_digests"])
        self.assertIn(e.binding.margin_rule_digest, episode["rules_digests"])
        self.assertIn(fill["row_digest"], episode["exit_fill_digests"])
        for row in (order, fill):
            self.assertEqual(row["implementation_digest"], e.binding.implementation_digest)
            self.assertEqual(row["contract_digest"], e.binding.contract_digest)


class FoundationSemantics(unittest.TestCase):
    def test_decimal_canonical_duplicate_nonfinite_collision(self):
        self.assertEqual(decimal_string(Decimal("-0.000")), "0")
        self.assertEqual(decimal_string(Decimal("10.2300")), "10.23")
        with self.assertRaisesRegex(AccountingError, "duplicate"):
            parse_json_strict('{"a":1,"a":2}')
        with self.assertRaisesRegex(AccountingError, "nonfinite"):
            parse_json_strict('{"a":NaN}')
        with self.assertRaisesRegex(AccountingError, "collision"):
            canonical_json({1:"a", "1":"b"})

    def test_daily_and_drawdown_exact_thresholds_allow_reductions(self):
        e = engine()
        e.day_start_nav = Decimal("1000")
        self.assertFalse(e.entry_allowed(Decimal("985")))
        e.day_start_nav = Decimal("2000"); e.high_water_nav = Decimal("1000")
        self.assertFalse(e.entry_allowed(Decimal("900")))
        src = mark("BTCUSDT_USD_M_linear_perpetual")
        e.invalid = False; e.high_water_nav = Decimal("1000"); e.day_start_nav = Decimal("1000")
        e.fill("entry", src.timestamp, src.instrument, Decimal("1"), Decimal("100"), Fee("quote", Decimal("0")), src)
        e.invalid = True
        e.fill("protect", src.timestamp, src.instrument, Decimal("-1"), Decimal("100"), Fee("quote", Decimal("0")), src, protective=True)
        self.assertEqual(e.state.signed_perpetual_quantity_BTC, Decimal("0"))

    def test_reversal_is_two_fills_and_episode_local_costs(self):
        e = engine()
        src = mark("BTCUSDT_USD_M_linear_perpetual")
        e.fill("long", src.timestamp, src.instrument, Decimal("1"), Decimal("100"), Fee("quote", Decimal("0.001")), src)
        with self.assertRaisesRegex(AccountingError, "two fills"):
            e.fill("cross", src.timestamp, src.instrument, Decimal("-2"), Decimal("100"), Fee("quote", Decimal("0")), src)
        e.fill("close", src.timestamp, src.instrument, Decimal("-1"), Decimal("100"), Fee("quote", Decimal("0.001")), src)
        e.fill("short", src.timestamp, src.instrument, Decimal("-1"), Decimal("100"), Fee("quote", Decimal("0.001")), src)
        self.assertEqual(len(e.ledgers["episode"]), 1)
        self.assertGreater(Decimal(e.ledgers["episode"][0]["entry_costs"]), Decimal("0"))
        self.assertEqual(e.open_episodes[src.instrument].direction, "short")


if __name__ == "__main__":
    unittest.main()
