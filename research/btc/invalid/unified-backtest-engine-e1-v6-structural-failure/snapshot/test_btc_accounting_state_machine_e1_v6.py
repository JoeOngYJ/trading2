"""Synthetic conformance tests for the E1-v6 accounting state machine.

Assertions calculate expectations from each fixture's declared inputs.  The file contains
no preserved terminal oracle values and reads no historical or external data.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import unittest

from src.trading_platform.btc_accounting_state_machine_e1_v6 import (
    ACTIONABLE_ARM_ID, AccountingError, AccountingStateMachine, D, Fee, FillSpec,
    FundingSpec, InstrumentRules, LedgerState, MarginRules, PAIR_MISMATCH_LIMIT,
    PERPETUAL, PairOutcome, PhaseError, RunBinding, SCENARIOS, SPOT, SourceLineage,
    State, canonical_digest, canonical_json_bytes, decimal_string, strict_json_loads,
    canonical_candle_arrival,
)


T0 = "2001-01-01T00:00:00.000000Z"
T1 = "2001-01-01T01:00:00.000000Z"
T2 = "2001-01-01T02:00:00.000000Z"
DIGEST_A = "a" * 64
DIGEST_B = "b" * 64


def source(at: str = T0, digest: str = DIGEST_A, segment: str = "synthetic-1") -> SourceLineage:
    return SourceLineage("synthetic://fixture", digest, segment, at, at, DIGEST_B)


SPOT_RULES = InstrumentRules(SPOT, D("0.001"), D("0.01"), D("0.001"), D("1"), DIGEST_A)
PERP_RULES = InstrumentRules(PERPETUAL, D("0.001"), D("0.01"), D("0.001"), D("1"), DIGEST_B)
MARGIN = MarginRules(D("0.005"), D("0"), D("0.01"), D("1"), DIGEST_B)


def binding(kind: str = "spot", scenario: str = "candle-primary-30bps-rt-v1",
            leverage: str = "1", adapter: str = "candle_OHLC") -> RunBinding:
    ids = {
        "spot": ("retail-btc-spot-v2", "config/retail_mandate.json",
                 "7e34cfb0928b4373bbf52b5c5505f63a2b19e674124059191c1b6c62ec129041"),
        "directional": ("retail-btc-directional-perpetual-research-v1",
                        "config/mandates/retail-btc-directional-perpetual-research-v1.json",
                        "1b5d492f12f71ebe28e1bdfbd0b5916bcf0ad285b483cb10bf8770504371165d"),
        "pair": ("retail-btc-delta-neutral-research-v1",
                 "config/mandates/retail-btc-delta-neutral-research-v1.json",
                 "d95a53ee493862549b932dc5f80600a02a0e38e4ba1b3da0d79d0b0c5bb9eeba"),
    }
    mandate_id, path, digest = ids[kind]
    return RunBinding("synthetic-run", scenario, mandate_id, path, digest, adapter,
                      SPOT_RULES.digest, PERP_RULES.digest, (DIGEST_A, DIGEST_B),
                      D(leverage), D("0.001"))


def engine(kind: str = "spot", *, state: LedgerState | None = None,
           spot_mark: str = "100", perp_mark: str = "100", scenario: str = "candle-primary-30bps-rt-v1",
           leverage: str = "1", third_marks: dict[str, Decimal] | None = None,
           adapter: str = "candle_OHLC") -> AccountingStateMachine:
    state = state or LedgerState(D("1000"))
    sm, pm = D(spot_mark), D(perp_mark)
    third_value = sum((balance * (third_marks or {})[asset]
                       for asset, balance in state.fee_asset_balances.items()), D("0"))
    unrealized = (state.perpetual_quantity * (pm - state.average_perpetual_entry)
                  if state.perpetual_quantity else D("0"))
    start = state.quote_cash + state.spot_quantity * sm + state.isolated_collateral + unrealized \
        + third_value - state.liabilities
    return AccountingStateMachine(binding(kind, scenario, leverage, adapter), state, starting_nav=start,
                                  spot_mark=sm, perpetual_mark=pm, margin_rules=MARGIN,
                                  mark_lineage=source(T0), third_asset_marks=third_marks)


def fill(machine: AccountingStateMachine, instrument: str, quantity: str, price: str,
         *, at: str = T0, ident: str = "f", fee_asset: str = "quote",
         authorization: str = "ordinary", third_mark: str | None = None,
         lineage: SourceLineage | None = None,
         fill_lineage: SourceLineage | None = None) -> FillSpec:
    q, p = D(quantity), D(price)
    rate, implicit_rate, _ = SCENARIOS[
        "candle-severe-80bps-rt-v1" if authorization == "forced" else machine.binding.scenario_id
    ]
    fee = Fee(fee_asset, rate, D("0"), D(third_mark) if third_mark else None,
              lineage if fee_asset == "third" else None)
    return FillSpec(ident, "o-" + ident, instrument, q, p, fee,
                    abs(q) * p * implicit_rate, at,
                    SPOT_RULES if instrument == SPOT else PERP_RULES,
                    fill_lineage or source(at), authorization, p)


def enter_order_phase(machine: AccountingStateMachine, at: str = T0, mark: str = "100") -> None:
    machine.begin_timestamp(at)
    machine.phase_open(spot_open=D(mark), perpetual_open=D(mark))
    machine.phase_protective_complete()
    machine.phase_funding_complete()
    machine.phase_risk()


class CanonicalContractTests(unittest.TestCase):
    def test_decimal_and_strict_json(self) -> None:
        for raw, expected in (("1.2300", "1.23"), ("-0.000", "0"), ("10", "10")):
            self.assertEqual(decimal_string(D(raw)), expected)
        parsed = strict_json_loads('{"x":1.25}')
        self.assertIsInstance(parsed["x"], Decimal)
        self.assertEqual(canonical_json_bytes(parsed), b'{"x":"1.25"}')
        with self.assertRaises(AccountingError):
            strict_json_loads('{"x":1,"x":2}')
        with self.assertRaises(AccountingError):
            strict_json_loads('{"x":NaN}')
        with self.assertRaises(AccountingError):
            canonical_json_bytes({1: "a", "1": "b"})
        with self.assertRaises(AccountingError):
            D(0.1)

    def test_exact_tick_step_and_minimum(self) -> None:
        self.assertEqual(SPOT_RULES.quantity(D("1.0009")), D("1.000"))
        SPOT_RULES.validate_order(D("0.01"), D("100.00"))
        with self.assertRaises(AccountingError):
            SPOT_RULES.validate_order(D("0.01"), D("100.001"))
        with self.assertRaises(AccountingError):
            SPOT_RULES.validate_order(D("0.000"), D("100"))
        self.assertEqual(canonical_candle_arrival(T0, T1), T1)
        with self.assertRaises(AccountingError):
            canonical_candle_arrival(T0, "2001-01-01T01:00:00.000001Z")

    def test_authority_and_scenario_are_immutable(self) -> None:
        with self.assertRaises(AccountingError):
            replace(binding(), selected_mandate_sha256=DIGEST_A)
        with self.assertRaises(AccountingError):
            replace(binding(), scenario_id="caller-fee")
        self.assertEqual(ACTIONABLE_ARM_ID, "no_trade")

    def test_exact_authority_hashes_and_cost_grid(self) -> None:
        expected = {
            "config/execution_scenarios.json": "a020cb07780e88b60fffd4c6e1b205922f0b815f033a4676dd422a7038538f36",
            "config/retail_mandate.json": "7e34cfb0928b4373bbf52b5c5505f63a2b19e674124059191c1b6c62ec129041",
            "config/mandates/retail-btc-directional-perpetual-research-v1.json": "1b5d492f12f71ebe28e1bdfbd0b5916bcf0ad285b483cb10bf8770504371165d",
            "config/mandates/retail-btc-delta-neutral-research-v1.json": "d95a53ee493862549b932dc5f80600a02a0e38e4ba1b3da0d79d0b0c5bb9eeba",
        }
        for path, digest in expected.items():
            self.assertEqual(sha256(Path(path).read_bytes()).hexdigest(), digest)
        self.assertEqual(SCENARIOS["candle-primary-30bps-rt-v1"][:2], (D("0.001"), D("0.0005")))
        self.assertEqual(SCENARIOS["candle-stress-40bps-rt-v1"][:2], (D("0.001"), D("0.001")))
        self.assertEqual(SCENARIOS["candle-severe-80bps-rt-v1"][:2], (D("0.002"), D("0.002")))


class SpotAndFeeTests(unittest.TestCase):
    def test_spot_long_entry_hold_partial_and_full_exit_identity(self) -> None:
        m = engine()
        enter_order_phase(m)
        initial = m.nav()
        buy = fill(m, SPOT, "2", "100", ident="buy")
        m.apply_fill(buy)
        buy_cost = abs(buy.signed_quantity) * buy.price * (
            m.binding.scenario_fee_rate + m.binding.scenario_implicit_rate)
        self.assertEqual(initial - m.nav(), buy_cost)
        m.apply_fill(fill(m, SPOT, "-0.5", "110", ident="partial"))
        self.assertEqual(m.state.spot_quantity, D("1.5"))
        m.apply_fill(fill(m, SPOT, "-1.5", "110", ident="full"))
        self.assertEqual(m.state.spot_quantity, D("0"))
        self.assertEqual(len(m.rows["closed_episode"]), 1)
        episode = m.rows["closed_episode"][0]
        self.assertEqual(D(episode["net_dollar_PnL"]), D(episode["price_PnL"])
                         - D(episode["entry_costs"]) - D(episode["exit_costs"]))

    def test_quote_base_and_third_asset_fees_mutate_once(self) -> None:
        # Base fee: gross receipt minus a native BTC fee.
        m = engine()
        enter_order_phase(m)
        spec = fill(m, SPOT, "1", "100", ident="base", fee_asset="base")
        m.apply_fill(spec)
        native = abs(spec.signed_quantity) * spec.fee.rate
        self.assertEqual(m.state.spot_quantity, spec.signed_quantity - native)

        # Third fee: initialized balance and its quote value are reduced exactly once.
        third_mark = D("2")
        state = LedgerState(D("998"), fee_asset_balances={"third": D("1")})
        m2 = engine(state=state, third_marks={"third": third_mark})
        enter_order_phase(m2)
        start = m2.nav()
        spec2 = fill(m2, SPOT, "1", "100", ident="third", fee_asset="third",
                     third_mark="2", lineage=source(T0))
        m2.apply_fill(spec2)
        native2 = abs(spec2.signed_quantity) * spec2.fee.rate
        implicit = spec2.implicit_cost_quote
        self.assertEqual(start - m2.nav(), native2 * third_mark + implicit)

    def test_unavailable_or_unsupported_fee_is_atomic(self) -> None:
        m = engine()
        enter_order_phase(m)
        before = m.state_digest()
        unavailable = fill(m, SPOT, "1", "100", ident="third", fee_asset="third",
                           third_mark="2", lineage=source(T1))
        with self.assertRaises(AccountingError):
            m.apply_fill(unavailable)
        self.assertEqual(before, m.state_digest())
        with self.assertRaises(AccountingError):
            Fee("unsupported", D("0"))


class PerpetualAndFundingTests(unittest.TestCase):
    def test_linear_long_short_pnl_and_additive_margin(self) -> None:
        for quantity, exit_price in (("1", "110"), ("-1", "90")):
            m = engine("directional", leverage="2")
            enter_order_phase(m)
            open_fill = fill(m, PERPETUAL, quantity, "100", ident="open")
            m.apply_fill(open_fill)
            expected_margin = abs(D(quantity)) * D("100") / D("2")
            self.assertEqual(m.state.allocated_initial_margin_memo, expected_margin)
            close_fill = fill(m, PERPETUAL, str(-D(quantity)), exit_price, ident="close")
            m.apply_fill(close_fill)
            expected_realized = abs(D(quantity)) * (D(exit_price) - D("100")) * (D("1") if D(quantity) > 0 else D("-1"))
            self.assertEqual(m.state.realized_pnl, expected_realized)
            self.assertEqual(m.state.perpetual_quantity, D("0"))

    def test_resize_partial_release_and_two_fill_reversal(self) -> None:
        m = engine("directional", leverage="2")
        enter_order_phase(m)
        m.apply_fill(fill(m, PERPETUAL, "1", "100", ident="open"))
        m.apply_fill(fill(m, PERPETUAL, "1", "120", ident="resize"))
        expected_average = (D("100") + D("120")) / D("2")
        self.assertEqual(m.state.average_perpetual_entry, expected_average)
        old_memo = m.state.allocated_initial_margin_memo
        m.apply_fill(fill(m, PERPETUAL, "-0.5", "115", ident="reduce"))
        self.assertEqual(m.state.allocated_initial_margin_memo,
                         old_memo - old_memo * D("0.5") / D("2"))
        close_qty = -m.state.perpetual_quantity
        m.reverse_perpetual(fill(m, PERPETUAL, str(close_qty), "115", ident="reverse-close"),
                            fill(m, PERPETUAL, "-1", "115", ident="reverse-open"))
        self.assertEqual(m.state.perpetual_quantity, D("-1"))
        self.assertEqual(m.state.average_perpetual_entry, D("115"))

    def test_funding_signs_and_engine_owned_same_timestamp_membership(self) -> None:
        state = LedgerState(D("900"), isolated_collateral=D("100"), perpetual_quantity=D("1"),
                            average_perpetual_entry=D("100"), allocated_initial_margin_memo=D("100"))
        m = engine("directional", state=state)
        m.begin_timestamp(T0)
        m.phase_open(spot_open=D("100"), perpetual_open=D("100"))
        m.phase_protective_complete()
        funding = FundingSpec(T0, T0, T0, D("0.01"), D("100"), source(T0), source(T0, DIGEST_B), DIGEST_B)
        cashflow = m.apply_funding(funding)
        self.assertEqual(cashflow, -D("1") * D("100") * D("0.01"))
        self.assertEqual(D(m.rows["funding"][0]["t_minus_signed_quantity"]), D("1"))

        flat = engine("directional")
        enter_order_phase(flat)
        flat.apply_fill(fill(flat, PERPETUAL, "1", "100", ident="same-time-entry"))
        # Funding phase has already passed and cannot be caller-replayed.
        with self.assertRaises(PhaseError):
            flat.apply_funding(funding)

    def test_same_timestamp_exit_pays_t_minus_funding_before_exit(self) -> None:
        state = LedgerState(D("900"), isolated_collateral=D("100"), perpetual_quantity=D("1"),
                            average_perpetual_entry=D("100"), allocated_initial_margin_memo=D("100"))
        m = engine("directional", state=state)
        m.begin_timestamp(T0); m.phase_open(spot_open=D("100"), perpetual_open=D("100")); m.phase_protective_complete()
        rate = D("0.001")
        m.apply_funding(FundingSpec(T0, T0, T0, rate, D("100"), source(T0), source(T0, DIGEST_B), DIGEST_B))
        m.phase_funding_complete(); m.phase_risk()
        m.apply_fill(fill(m, PERPETUAL, "-1", "100", ident="same-time-exit"))
        self.assertEqual(D(m.rows["funding"][-1]["t_minus_signed_quantity"]), D("1"))
        self.assertEqual(m.state.accrued_funding, -D("1") * D("100") * rate)

    def test_positive_negative_funding_for_long_and_short(self) -> None:
        for q in (D("1"), D("-1")):
            for rate in (D("0.001"), D("-0.001")):
                state = LedgerState(D("900"), isolated_collateral=D("100"), perpetual_quantity=q,
                                    average_perpetual_entry=D("100"), allocated_initial_margin_memo=D("100"))
                m = engine("directional", state=state)
                m.begin_timestamp(T0); m.phase_open(spot_open=D("100"), perpetual_open=D("100")); m.phase_protective_complete()
                f = FundingSpec(T0, T0, T0, rate, D("100"), source(T0), source(T0, DIGEST_B), DIGEST_B)
                self.assertEqual(m.apply_funding(f), -q * D("100") * rate)

    def test_funding_caused_liquidation_and_complete_rows(self) -> None:
        state = LedgerState(D("990"), isolated_collateral=D("10"), perpetual_quantity=D("1"),
                            average_perpetual_entry=D("100"), allocated_initial_margin_memo=D("10"))
        m = engine("directional", state=state)
        m.begin_timestamp(T0); m.phase_open(spot_open=D("100"), perpetual_open=D("100")); m.phase_protective_complete()
        f = FundingSpec(T0, T0, T0, D("0.10"), D("100"), source(T0), source(T0, DIGEST_B), DIGEST_B)
        m.apply_funding(f, MARGIN)
        self.assertIs(m.state.status, State.LIQUIDATED)
        self.assertEqual(m.state.perpetual_quantity, D("0"))
        for row in (m.rows["order"][-1], m.rows["fill"][-1]):
            for field in ("event_sequence", "before_state_digest", "after_state_digest",
                          "event_accounting_residual", "implementation_digest", "contract_digests",
                          "execution_config_digest", "mandate_digest", "semantic_settings_digest",
                          "row_digest", "invalidation_reason"):
                self.assertIn(field, row)
        episode = m.rows["closed_episode"][-1]
        for field in ("entry_costs", "exit_costs", "price_PnL", "funding_PnL",
                      "maximum_adverse_excursion", "maximum_favourable_excursion",
                      "entry_fill_digests", "exit_fill_digests", "close_reason"):
            self.assertIn(field, episode)

    def test_intrabar_adverse_first_long_and_short(self) -> None:
        for q, high, low in ((D("1"), D("120"), D("80")), (D("-1"), D("120"), D("80"))):
            state = LedgerState(D("990"), isolated_collateral=D("10"), perpetual_quantity=q,
                                average_perpetual_entry=D("100"), allocated_initial_margin_memo=D("10"))
            m = engine("directional", state=state)
            enter_order_phase(m); m.phase_orders_complete(); m.phase_post_fill_complete()
            m.phase_intrabar_close(high=high, low=low, close_spot=D("100"), close_perpetual=D("100"), margin_rules=MARGIN)
            self.assertIs(m.state.status, State.LIQUIDATED)

    def test_open_gap_liquidation_fee_replaces_close_cost_and_retains_deficit(self) -> None:
        state = LedgerState(D("995"), isolated_collateral=D("5"), perpetual_quantity=D("1"),
                            average_perpetual_entry=D("100"), allocated_initial_margin_memo=D("5"))
        m = engine("directional", state=state)
        m.begin_timestamp(T0)
        m.phase_open(spot_open=D("50"), perpetual_open=D("50"), margin_rules=MARGIN)
        fee = D("1") * D("50") * MARGIN.liquidation_fee_rate
        self.assertIs(m.state.status, State.LIQUIDATED)
        self.assertEqual(m.state.explicit_costs, fee)
        self.assertGreater(m.state.liabilities, D("0"))


class ClockGapRiskAndTerminalTests(unittest.TestCase):
    def test_nine_phase_progression_and_duplicate_permuted_rejection(self) -> None:
        m = engine()
        with self.assertRaises(PhaseError):
            m.phase_risk()
        enter_order_phase(m)
        m.phase_orders_complete(); m.phase_post_fill_complete()
        m.phase_intrabar_close(high=D("101"), low=D("99"), close_spot=D("100"), close_perpetual=D("100"))
        m.phase_reconcile()
        with self.assertRaises(AccountingError):
            m.begin_timestamp(T0)

    def test_gap_flat_exposed_pending_and_completed_neutralization(self) -> None:
        flat = engine(); flat.exposed_gap(); self.assertIs(flat.state.status, State.ACTIVE)
        state = LedgerState(D("900"), spot_quantity=D("1"))
        m = engine(state=state)
        enter_order_phase(m)
        m.exposed_gap()
        self.assertIs(m.state.status, State.UNKNOWN)
        self.assertTrue(m.state.pending_safety_actions)

        state2 = LedgerState(D("900"), spot_quantity=D("1"))
        done = engine(state=state2, scenario="candle-severe-80bps-rt-v1")
        enter_order_phase(done)
        forced = fill(done, SPOT, "-1", "90", ident="gap-close", authorization="forced")
        done.exposed_gap(protective_fills=[forced])
        self.assertEqual(done.state.spot_quantity, D("0"))
        self.assertFalse(done.state.pending_safety_actions)
        self.assertIs(done.state.status, State.UNKNOWN)  # invalid performance stays invalid

    def test_missing_funding_invalidates_exposed_only(self) -> None:
        state = LedgerState(D("900"), isolated_collateral=D("100"), perpetual_quantity=D("1"),
                            average_perpetual_entry=D("100"), allocated_initial_margin_memo=D("100"))
        m = engine("directional", state=state)
        m.begin_timestamp(T0); m.phase_open(spot_open=D("100"), perpetual_open=D("100")); m.phase_protective_complete()
        m.missing_funding()
        self.assertIs(m.state.status, State.UNKNOWN)

    def test_daily_loss_and_drawdown_exact_thresholds_allow_reductions(self) -> None:
        m = engine(state=LedgerState(D("1000"), spot_quantity=D("0")))
        m.begin_timestamp(T0); m.phase_open(spot_open=D("100"), perpetual_open=D("100")); m.phase_protective_complete(); m.phase_funding_complete()
        m.state.quote_cash = m.day_start_nav * (D("1") + D("-0.015"))
        m.phase_risk()
        self.assertFalse(m.state.new_exposure_enabled)
        with self.assertRaises(AccountingError):
            m.apply_fill(fill(m, SPOT, "1", "100", ident="blocked"))

        state = LedgerState(D("900"), spot_quantity=D("1"))
        reduce = engine(state=state)
        enter_order_phase(reduce)
        reduce.state.new_exposure_enabled = False
        reduce.apply_fill(fill(reduce, SPOT, "-1", "100", ident="allowed-reduction"))
        self.assertEqual(reduce.state.spot_quantity, D("0"))

        drawdown = engine()
        drawdown.high_water_nav = D("1100")
        drawdown.begin_timestamp(T0); drawdown.phase_open(spot_open=D("100"), perpetual_open=D("100")); drawdown.phase_protective_complete(); drawdown.phase_funding_complete()
        drawdown.state.quote_cash = drawdown.high_water_nav * (D("1") + D("-0.10"))
        drawdown.phase_risk()
        self.assertFalse(drawdown.state.new_exposure_enabled)

        protected = engine(state=LedgerState(D("900"), spot_quantity=D("1")))
        enter_order_phase(protected); protected.state.new_exposure_enabled = False
        protected.apply_fill(fill(protected, SPOT, "-1", "100", ident="protective",
                                  authorization="protective"))
        self.assertEqual(protected.state.spot_quantity, D("0"))

    def test_terminal_and_liquidation_are_monotone(self) -> None:
        m = engine(state=LedgerState(D("900"), spot_quantity=D("1")))
        enter_order_phase(m)
        m.terminal_flatten([fill(m, SPOT, "-1", "100", ident="terminal", authorization="terminal")])
        with self.assertRaises(AccountingError):
            m.apply_fill(fill(m, SPOT, "1", "100", ident="resume"))

    def test_true_partition_boundary_buy_hold_and_terminal_causality(self) -> None:
        m = engine()
        self.assertTrue(m.buy_and_hold_entry_allowed(partition_start=T0, observation_at=T0))
        self.assertFalse(m.buy_and_hold_entry_allowed(partition_start=T0, observation_at=T1))

    def test_terminal_flatten_closes_open_episode_with_cost_attribution(self) -> None:
        m = engine(); enter_order_phase(m)
        m.apply_fill(fill(m, SPOT, "1", "100", ident="entry"))
        m.terminal_flatten([fill(m, SPOT, "-1", "100", ident="terminal-exit", authorization="terminal")])
        episode = m.rows["closed_episode"][-1]
        self.assertGreater(D(episode["entry_costs"]), D("0"))
        self.assertGreater(D(episode["exit_costs"]), D("0"))
        self.assertEqual(episode["close_reason"], "terminal")


class PairTests(unittest.TestCase):
    def test_atomic_pair_entry_direct_and_second_leg_failure_neutralizes(self) -> None:
        m = engine("pair", scenario="candle-severe-80bps-rt-v1")
        enter_order_phase(m)
        spot = fill(m, SPOT, "1", "100", ident="spot-entry")
        spot_close = fill(m, SPOT, "-0.998", "100", ident="forced-spot",
                          authorization="forced")
        # Quote fees leave BTC quantity unchanged, so exact gross close is one BTC.
        spot_close = replace(spot_close, signed_quantity=D("-1"),
                             implicit_cost_quote=D("1") * D("100") * m.binding.scenario_implicit_rate)
        m.atomic_pair_entry(spot, None, severe_spot_close=spot_close)
        self.assertEqual(m.state.spot_quantity, D("0"))
        self.assertEqual(m.state.perpetual_quantity, D("0"))

    def test_atomic_pair_entry_full_success_and_caps(self) -> None:
        m = engine("pair", scenario="candle-primary-30bps-rt-v1")
        enter_order_phase(m)
        recovery = fill(m, SPOT, "-1", "100", ident="entry-recovery", authorization="forced")
        m.atomic_pair_entry(fill(m, SPOT, "1", "100", ident="spot"),
                            fill(m, PERPETUAL, "-1", "100", ident="perp"),
                            severe_spot_close=recovery)
        self.assertEqual(m.state.spot_quantity, abs(m.state.perpetual_quantity))
        too_large = engine("pair"); enter_order_phase(too_large)
        with self.assertRaises(AccountingError):
            too_large.atomic_pair_entry(fill(too_large, SPOT, "6", "100", ident="large"), None,
                                        severe_spot_close=fill(too_large, SPOT, "-6", "100", ident="undo", authorization="forced"))

    def test_atomic_pair_entry_partial_second_leg_closes_perp_then_spot(self) -> None:
        m = engine("pair", adapter="synthetic_partial")
        enter_order_phase(m)
        m.atomic_pair_entry(
            fill(m, SPOT, "1", "100", ident="spot"),
            fill(m, PERPETUAL, "-0.5", "100", ident="partial-perp"),
            severe_perpetual_close=fill(m, PERPETUAL, "0.5", "100", ident="undo-perp", authorization="forced"),
            severe_spot_close=fill(m, SPOT, "-1", "100", ident="undo-spot", authorization="forced"),
        )
        self.assertEqual(m.state.spot_quantity, D("0"))
        self.assertEqual(m.state.perpetual_quantity, D("0"))
        forced = [row for row in m.rows["fill"] if row.get("authorization") == "forced"]
        self.assertEqual([row["instrument"] for row in forced], [PERPETUAL, SPOT])

    @staticmethod
    def outcomes() -> list[PairOutcome]:
        z = D("0")
        return [
            PairOutcome(z, z, D("100"), z, z, D("101"), z, z),
            PairOutcome(D("1"), z, D("100"), z, z, D("101"), D("0.202"), D("0.202")),
            PairOutcome(D("1"), D("1"), D("100"), D("0.1"), D("0.05"), D("101"), z, z),
        ]

    def pair_machine(self) -> AccountingStateMachine:
        state = LedgerState(D("800"), spot_quantity=D("1"), isolated_collateral=D("100"),
                            perpetual_quantity=D("-1"), average_perpetual_entry=D("100"),
                            allocated_initial_margin_memo=D("100"))
        m = engine("pair", state=state)
        enter_order_phase(m)
        return m

    def test_pair_outcome_completeness_duplicate_and_permutation_digest(self) -> None:
        a, b = self.pair_machine(), self.pair_machine()
        outcomes = self.outcomes()
        da = a.validate_pair_outcomes(outcomes, full_reduction=D("1"), incoming_short=D("1"),
                                      collateral=D("100"), initial_margin_memo=D("100"), entry_price=D("100"))
        db = b.validate_pair_outcomes(list(reversed(outcomes)), full_reduction=D("1"), incoming_short=D("1"),
                                      collateral=D("100"), initial_margin_memo=D("100"), entry_price=D("100"))
        self.assertEqual(da, db)
        with self.assertRaises(AccountingError):
            a.validate_pair_outcomes(outcomes + [outcomes[0]], full_reduction=D("1"), incoming_short=D("1"),
                                     collateral=D("100"), initial_margin_memo=D("100"), entry_price=D("100"))
        with self.assertRaises(AccountingError):
            a.validate_pair_outcomes(outcomes[:1], full_reduction=D("1"), incoming_short=D("1"),
                                     collateral=D("100"), initial_margin_memo=D("100"), entry_price=D("100"))

    def test_full_pair_close_and_complete_identity(self) -> None:
        m = self.pair_machine()
        result = m.atomic_pair_close(
            spot_fill=fill(m, SPOT, "-1", "100", ident="close-spot"),
            perpetual_fill=fill(m, PERPETUAL, "1", "100", ident="close-perp"),
            severe_residual_fill=None, outcomes=self.outcomes(), full_reduction=D("1"),
            spot_mark=D("100"), perpetual_mark=D("100"), initial_margin_memo=D("100"),
        )
        self.assertEqual(m.state.spot_quantity, D("0"))
        self.assertEqual(m.state.perpetual_quantity, D("0"))
        self.assertEqual(D(result["remaining_quantity_mismatch"]), D("0"))
        self.assertEqual(len(result["outcome_set_digest"]), 64)

    def test_pair_close_partial_or_rejected_second_leg_severe_residual(self) -> None:
        m = self.pair_machine()
        result = m.atomic_pair_close(
            spot_fill=fill(m, SPOT, "-1", "100", ident="spot"), perpetual_fill=None,
            severe_residual_fill=fill(m, PERPETUAL, "1", "100", ident="severe", authorization="forced"),
            outcomes=self.outcomes(), full_reduction=D("1"), spot_mark=D("100"),
            perpetual_mark=D("100"), initial_margin_memo=D("100"),
        )
        self.assertEqual(D(result["created_residual_naked_short_quantity"]), D("1"))
        self.assertEqual(m.state.perpetual_quantity, D("0"))

        partial = self.pair_machine()
        partial.binding = replace(partial.binding, adapter_id="synthetic_partial")
        outcomes = self.outcomes() + [
            PairOutcome(D("1"), D("0.5"), D("100"), D("0.05"), D("0.025"),
                        D("100"), D("0.1"), D("0.1"))
        ]
        result2 = partial.atomic_pair_close(
            spot_fill=fill(partial, SPOT, "-1", "100", ident="spot-partial-case"),
            perpetual_fill=fill(partial, PERPETUAL, "0.5", "100", ident="perp-partial"),
            severe_residual_fill=fill(partial, PERPETUAL, "0.5", "100", ident="perp-residual", authorization="forced"),
            outcomes=outcomes, full_reduction=D("1"), spot_mark=D("100"),
            perpetual_mark=D("100"), initial_margin_memo=D("100"),
        )
        self.assertEqual(D(result2["created_residual_naked_short_quantity"]), D("0.5"))

    def test_pair_close_delayed_residual_preserves_lineage_and_segment_reset(self) -> None:
        m = self.pair_machine()
        result = m.atomic_pair_close(
            spot_fill=fill(m, SPOT, "-1", "100", ident="spot"), perpetual_fill=None,
            severe_residual_fill=fill(m, PERPETUAL, "1", "100", ident="delayed", at=T1,
                                      authorization="forced",
                                      fill_lineage=source(T1, segment="synthetic-2")),
            outcomes=self.outcomes(), full_reduction=D("1"), spot_mark=D("100"),
            perpetual_mark=D("100"), initial_margin_memo=D("100"), delayed=True, new_segment=True,
        )
        for field in ("remaining_quantity_mismatch", "remaining_notional_mismatch", "common_spot_mark",
                      "common_perpetual_mark", "semantic_settings_digest", "outcome_set_digest", "segment_reset"):
            self.assertIn(field, result)
        self.assertTrue(result["segment_reset"])
        self.assertTrue(all(row.get("pair_outcome_set_digest") == result["outcome_set_digest"]
                            for row in m.rows["fill"][-2:]))

    def test_base_fee_pair_close_exact_solver_and_dust_rejection(self) -> None:
        state = LedgerState(D("799.9"), spot_quantity=D("1.001"), isolated_collateral=D("100"),
                            perpetual_quantity=D("-1.001"), average_perpetual_entry=D("100"),
                            allocated_initial_margin_memo=D("100.1"))
        m = engine("pair", state=state)
        enter_order_phase(m)
        z = D("0")
        outcomes = [
            PairOutcome(z, z, D("100"), z, z, D("100"), z, z),
            PairOutcome(D("1.001"), z, D("100"), z, z, D("100"), D("0.2002"), D("0.2002")),
            PairOutcome(D("1.001"), D("1.001"), D("100"), D("0.1001"), D("0.05005"), D("100"), z, z),
        ]
        result = m.atomic_pair_close(
            spot_fill=fill(m, SPOT, "-1", "100", ident="base-close", fee_asset="base"),
            perpetual_fill=fill(m, PERPETUAL, "1.001", "100", ident="perp-close"),
            severe_residual_fill=None, outcomes=outcomes, full_reduction=D("1.001"),
            spot_mark=D("100"), perpetual_mark=D("100"), initial_margin_memo=D("100.1"),
        )
        self.assertEqual(D(result["actual_spot_inventory_reduction"]), D("1.001"))
        self.assertEqual(m.state.spot_quantity, D("0"))

        dust = self.pair_machine()
        before = dust.state_digest()
        with self.assertRaises(AccountingError):
            dust.atomic_pair_close(
                spot_fill=fill(dust, SPOT, "-0.999", "100", ident="dust", fee_asset="base"),
                perpetual_fill=None, severe_residual_fill=None, outcomes=self.outcomes(),
                full_reduction=D("1"), spot_mark=D("100"), perpetual_mark=D("100"),
                initial_margin_memo=D("100"),
            )
        self.assertEqual(before, dust.state_digest())

    def test_notional_mismatch_gets_one_spot_first_whole_pair_attempt(self) -> None:
        state = LedgerState(D("600"), spot_quantity=D("2"), isolated_collateral=D("200"),
                            perpetual_quantity=D("-2"), average_perpetual_entry=D("100"),
                            allocated_initial_margin_memo=D("200"))
        m = engine("pair", state=state)
        enter_order_phase(m)
        result = m.atomic_pair_close(
            spot_fill=fill(m, SPOT, "-1", "100", ident="intended-spot"),
            perpetual_fill=fill(m, PERPETUAL, "1", "100", ident="intended-perp"),
            severe_residual_fill=None, outcomes=self.outcomes(), full_reduction=D("1"),
            spot_mark=D("100"), perpetual_mark=D("103"), initial_margin_memo=D("200"),
            mismatch_spot_fill=fill(m, SPOT, "-1", "100", ident="mismatch-spot", authorization="forced"),
            mismatch_perpetual_fill=fill(m, PERPETUAL, "1", "103", ident="mismatch-perp", authorization="forced"),
        )
        self.assertGreater(D(result["remaining_notional_mismatch"]), PAIR_MISMATCH_LIMIT)
        self.assertEqual((m.state.spot_quantity, m.state.perpetual_quantity), (D("0"), D("0")))
        forced = [row["instrument"] for row in m.rows["fill"] if row.get("authorization") == "forced"]
        self.assertEqual(forced, [SPOT, PERPETUAL])

    def test_candle_partial_fill_rejected_and_order_outcomes_retained(self) -> None:
        m = engine(adapter="synthetic_partial"); enter_order_phase(m)
        m.record_order(order_id="reject", decision_id="d", instrument=SPOT,
                       requested_quantity=D("1"), rounded_quantity=D("1"), filled_quantity=D("0"),
                       status="rejected", reason="minimum_notional", price_bound=D("100"),
                       source_digest=DIGEST_A, rules_digest=DIGEST_A)
        m.record_order(order_id="partial", decision_id="d", instrument=SPOT,
                       requested_quantity=D("1"), rounded_quantity=D("1"), filled_quantity=D("0.5"),
                       status="partial", reason="synthetic_qualified_L2_only", price_bound=D("100"),
                       source_digest=DIGEST_A, rules_digest=DIGEST_A)
        self.assertEqual(D(m.rows["order"][-1]["unfilled_quantity"]), D("0.5"))
        candle = engine(); enter_order_phase(candle)
        with self.assertRaises(AccountingError):
            candle.record_order(order_id="bad-partial", decision_id="d", instrument=SPOT,
                                requested_quantity=D("1"), rounded_quantity=D("1"), filled_quantity=D("0.5"),
                                status="partial", reason="forbidden", price_bound=D("100"),
                                source_digest=DIGEST_A, rules_digest=DIGEST_A)


class OutputAndIdentityTests(unittest.TestCase):
    def test_unchanged_price_round_trip_loses_exact_costs_and_scales(self) -> None:
        losses = []
        for q in (D("1"), D("2")):
            m = engine(); enter_order_phase(m)
            start = m.nav()
            m.apply_fill(fill(m, SPOT, str(q), "100", ident=f"b{q}"))
            m.apply_fill(fill(m, SPOT, str(-q), "100", ident=f"s{q}"))
            loss = start - m.nav()
            per_side = q * D("100") * (m.binding.scenario_fee_rate + m.binding.scenario_implicit_rate)
            self.assertEqual(loss, per_side * D("2"))
            losses.append(loss)
        self.assertEqual(losses[1], losses[0] * D("2"))

    def test_rows_and_report_are_deterministic_and_no_trade(self) -> None:
        m = engine(); enter_order_phase(m)
        m.record_order(order_id="expired", decision_id="d", instrument=SPOT,
                       requested_quantity=D("1"), rounded_quantity=D("1"), filled_quantity=D("0"),
                       status="expired", reason="price_cap", price_bound=D("100"),
                       source_digest=DIGEST_A, rules_digest=DIGEST_A)
        report = m.run_summary()
        encoded = canonical_json_bytes(report)
        self.assertEqual(encoded, canonical_json_bytes(json.loads(encoded)))
        self.assertEqual(report["actionable_arm_id"], "no_trade")
        self.assertEqual(report["rejected_expired_partial_and_unfilled_counts"]["expired"], 1)
        self.assertEqual(report["result_digest"], canonical_digest({k: v for k, v in report.items() if k != "result_digest"}))
        artifacts = m.artifacts()
        self.assertEqual(set(artifacts), {
            "decision_ledger.jsonl", "order_ledger.jsonl", "fill_ledger.jsonl",
            "funding_ledger.jsonl", "account_ledger.jsonl", "closed_episode_ledger.jsonl",
            "report.json", "evidence_manifest.json",
        })
        self.assertEqual(artifacts, m.artifacts())

    def test_entry_price_protection_uses_bound_scenario_and_protective_bypasses(self) -> None:
        m = engine()
        cap = SCENARIOS[m.binding.scenario_id][2]
        reference = D("100")
        self.assertTrue(m.price_within_entry_cap(reference_price=reference,
                                                 executable_price=reference * (D("1") + cap),
                                                 signed_quantity=D("1")))
        self.assertFalse(m.price_within_entry_cap(reference_price=reference,
                                                  executable_price=reference * (D("1") + cap) + D("0.01"),
                                                  signed_quantity=D("1")))
        self.assertTrue(m.price_within_entry_cap(reference_price=reference,
                                                 executable_price=D("1000"),
                                                 signed_quantity=D("1"), protective=True))

    def test_wrong_instruments_and_arbitrary_costs_reject_atomically(self) -> None:
        m = engine(); enter_order_phase(m)
        before = m.state_digest()
        with self.assertRaises(AccountingError):
            m.apply_fill(fill(m, PERPETUAL, "1", "100", ident="wrong"))
        self.assertEqual(before, m.state_digest())
        bad = fill(m, SPOT, "1", "100", ident="fee")
        bad = replace(bad, fee=Fee("quote", D("0.009")))
        with self.assertRaises(AccountingError):
            m.apply_fill(bad)
        self.assertEqual(before, m.state_digest())

    def test_spot_directional_caps_and_zero_position_invariance(self) -> None:
        spot = engine(); enter_order_phase(spot)
        with self.assertRaises(AccountingError):
            spot.apply_fill(fill(spot, SPOT, "3", "100", ident="over-cap"))
        directional = engine("directional"); enter_order_phase(directional)
        with self.assertRaises(AccountingError):
            directional.apply_fill(fill(directional, PERPETUAL, "3", "100", ident="over-cap"))

        flat = engine("directional")
        start = flat.nav()
        flat.begin_timestamp(T0); flat.phase_open(spot_open=D("150"), perpetual_open=D("150")); flat.phase_protective_complete()
        f = FundingSpec(T0, T0, T0, D("0.01"), D("150"), source(T0), source(T0, DIGEST_B), DIGEST_B)
        self.assertEqual(flat.apply_funding(f), D("0"))
        self.assertEqual(flat.nav(), start)

    def test_event_and_run_identity_from_declared_marks(self) -> None:
        state = LedgerState(D("900"), spot_quantity=D("1"))
        m = engine(state=state)
        m.begin_timestamp(T0); m.phase_open(spot_open=D("100"), perpetual_open=D("100")); m.phase_protective_complete(); m.phase_funding_complete(); m.phase_risk(); m.phase_orders_complete(); m.phase_post_fill_complete()
        m.phase_intrabar_close(high=D("110"), low=D("100"), close_spot=D("110"), close_perpetual=D("100"))
        m.phase_reconcile()
        summary = m.run_summary()
        self.assertLessEqual(abs(D(summary["accounting_residual"])), D("0.00000001"))


if __name__ == "__main__":
    unittest.main()
