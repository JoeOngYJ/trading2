"""Closed-form synthetic tests for the clean-room E1 Decimal ledger."""

from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path

import pytest

from trading_platform.btc_decimal_ledger_e1 import (
    CostSchedule,
    InstrumentRules,
    LedgerError,
    Lineage,
    PairCloseCartesianOutcome,
    Phase,
    PhaseError,
    RunLineage,
    SyntheticDecimalLedger as _SyntheticDecimalLedger,
    canonical_json,
    digest,
    expected_run_digests,
    load_json_no_collisions,
)


D = Decimal
ZERO = D("0")
ROOT = Path(__file__).resolve().parents[3]
E = D("0.001")
I = D("0.0005")
SE = SI = D("0.002")
STANDARD = CostSchedule(E, I, SE, SI)
COSTLESS = CostSchedule(ZERO, ZERO, SE, SI)
EXPLICIT_ONLY = CostSchedule(E, ZERO, SE, SI)
SPOT = InstrumentRules("BTC_USDT_spot", D("0.001"), D("0.01"), D("1"))
PERP = InstrumentRules("BTCUSDT_USD_M_perpetual", D("0.001"), D("0.01"), D("1"))
RULES = {SPOT.instrument: SPOT, PERP.instrument: PERP}
SOURCE_DESCRIPTOR = {
    "source_path": "synthetic://fixture", "segment_id": "synthetic-segment",
    "observed_at": "1970-01-01T00:00:00.000000Z",
    "source_available_at": "1970-01-01T00:00:00.000000Z",
}
SOURCE_DIGEST = digest(SOURCE_DESCRIPTOR)
LINEAGE = Lineage(
    SOURCE_DIGEST, digest(RULES),
    digest({"source_digest": SOURCE_DIGEST, "kind": "official_mark"}),
    digest({"source_digest": SOURCE_DIGEST, "kind": "official_index"}),
)


def lineage_for(rule_registry):
    return Lineage(
        SOURCE_DIGEST, digest(rule_registry),
        digest({"source_digest": SOURCE_DIGEST, "kind": "official_mark"}),
        digest({"source_digest": SOURCE_DIGEST, "kind": "official_index"}),
    )


def SyntheticDecimalLedger(**kwargs):
    schedule = kwargs.pop("cost_schedule", STANDARD)
    rule_registry = kwargs.pop("rule_registry", RULES)
    mandate_mode = kwargs.get("mandate_mode", "spot")
    if mandate_mode == "delta_neutral" and "maximum_allocation_fraction" not in kwargs:
        kwargs["maximum_allocation_fraction"] = D("0.50")
    if mandate_mode == "delta_neutral" and "leverage" not in kwargs:
        kwargs["leverage"] = D("1")
    settings = {
        "initial_nav": kwargs.get("initial_nav", D("1000")),
        "leverage": kwargs.get("leverage", D("4")),
        "maintenance_fraction": kwargs.get("maintenance_fraction", D("0.10")),
        "liquidation_fee_rate": kwargs.get("liquidation_fee_rate", D("0.01")),
        "exit_cost_rate": kwargs.get("exit_cost_rate", D("0.004")),
        "maximum_allocation_fraction": kwargs.get("maximum_allocation_fraction", D("0.25")),
        "zero_exit_reserve_fixture": kwargs.get("zero_exit_reserve_fixture", False),
        "terminal_timestamp": kwargs.get("terminal_timestamp"),
        "mandate_mode": mandate_mode,
    }
    bound = expected_run_digests(cost_schedule=schedule, **settings)
    run = RunLineage(
        "synthetic-accounting-only", "e1-fixture", "synthetic",
        bound["implementation_digest"], bound["contract_digest"],
        bound["predecessor_contract_digest"],
        bound["foundational_contract_digest"], bound["execution_config_digest"],
        bound["base_run_settings_digest"], bound["mandate_digest"],
    )
    return _SyntheticDecimalLedger(
        run_lineage=run, cost_schedule=schedule, rule_registry=rule_registry, **kwargs
    )


def orders(engine: SyntheticDecimalLedger, timestamp: str, *, spot: str = "100", perp: str = "100",
           funding: str | None = None, missing_funding: bool = False) -> None:
    engine.begin_event(timestamp, lineage_for(engine.rule_registry))
    engine.advance(Phase.OPEN_MARK)
    engine.mark_open(spot=D(spot), perpetual=D(perp))
    engine.advance(Phase.PROTECTIVE)
    engine.complete_phase()
    engine.advance(Phase.FUNDING)
    if funding is not None or missing_funding:
        engine.apply_funding(
            rate=None if funding is None else D(funding), mark=D(perp),
            economic_at=timestamp, available_at=timestamp, missing=missing_funding,
        )
    else:
        engine.complete_phase()
    engine.advance(Phase.PERMISSIONS)
    engine.permissions(decision_id=f"d:{timestamp}", requested_target="fixture")
    engine.advance(Phase.ORDERS)


def finish(engine: SyntheticDecimalLedger, timestamp: str, *, spot: str = "100", perp: str = "100",
           low: str | None = None, high: str | None = None) -> None:
    engine.complete_phase()
    engine.advance(Phase.POST_FILL_MARGIN)
    engine.post_fill_margin()
    engine.advance(Phase.INTRABAR)
    engine.intrabar(
        low=D(low or perp), high=D(high or perp), close=D(perp), spot_close=D(spot),
    )
    engine.advance(Phase.RECONCILE)
    engine.finalize_event(utc_day=timestamp[:10])


def test_spot_partial_exit_full_exit_oracle_1019_37():
    engine = SyntheticDecimalLedger(zero_exit_reserve_fixture=True)
    orders(engine, "2026-01-01T00:00:00.000000Z")
    engine.spot_fill(order_id="buy", requested_delta=D("2"), filled_quantity=D("2"),
                     price=D("100"), rules=SPOT, explicit_rate=E, implicit_rate=I)
    finish(engine, "2026-01-01T00:00:00.000000Z")
    orders(engine, "2026-01-02T00:00:00.000000Z", spot="110", perp="100")
    engine.spot_fill(order_id="sell-1", requested_delta=D("-0.5"), filled_quantity=D("-0.5"),
                     price=D("110"), rules=SPOT, explicit_rate=E, implicit_rate=I)
    assert engine.state.quote_cash == D("854.6175")
    finish(engine, "2026-01-02T00:00:00.000000Z", spot="110")
    orders(engine, "2026-01-03T00:00:00.000000Z", spot="110", perp="100")
    engine.spot_fill(order_id="sell-2", requested_delta=D("-1.5"), filled_quantity=D("-1.5"),
                     price=D("110"), rules=SPOT, explicit_rate=E, implicit_rate=I)
    finish(engine, "2026-01-03T00:00:00.000000Z", spot="110")
    assert engine.nav() == D("1019.37")
    assert engine.reconcile() == 0
    spot_episode = engine.ledgers["episode"][0]
    assert D(spot_episode["entry_costs"]) == D("0.3")
    assert D(spot_episode["exit_costs"]) == D("0.33")
    assert D(spot_episode["net_dollar_pnl"]) == D("19.37")


@pytest.mark.parametrize(("target", "exit_price", "expected"), [
    ("2", "110", "1019.37"),
    ("-2", "90", "1019.43"),
])
def test_perpetual_long_and_short_oracles(target: str, exit_price: str, expected: str):
    engine = SyntheticDecimalLedger(
        zero_exit_reserve_fixture=True, mandate_mode="directional_perpetual"
    )
    orders(engine, "2026-01-01T00:00:00.000000Z")
    engine.rebalance_perpetual(order_id="entry", target_quantity=D(target), price=D("100"),
                               rules=PERP, explicit_rate=E, implicit_rate=I)
    finish(engine, "2026-01-01T00:00:00.000000Z")
    orders(engine, "2026-01-02T00:00:00.000000Z", perp=exit_price)
    engine.rebalance_perpetual(order_id="exit", target_quantity=D("0"), price=D(exit_price),
                               rules=PERP, explicit_rate=E, implicit_rate=I)
    finish(engine, "2026-01-02T00:00:00.000000Z", perp=exit_price)
    assert engine.nav() == D(expected)
    assert engine.reconcile() == 0


def test_resize_release_average_and_reversal_oracle_989_58():
    no_cost = SyntheticDecimalLedger(
        zero_exit_reserve_fixture=True, cost_schedule=COSTLESS,
        mandate_mode="directional_perpetual",
    )
    orders(no_cost, "2026-01-01T00:00:00.000000Z")
    no_cost.rebalance_perpetual(order_id="one", target_quantity=D("1"), price=D("100"),
                                rules=PERP, explicit_rate=ZERO, implicit_rate=ZERO)
    finish(no_cost, "2026-01-01T00:00:00.000000Z")
    orders(no_cost, "2026-01-02T00:00:00.000000Z", perp="120")
    no_cost.rebalance_perpetual(order_id="two", target_quantity=D("2"), price=D("120"),
                                rules=PERP, explicit_rate=ZERO, implicit_rate=ZERO)
    assert no_cost.state.average_perpetual_entry == D("110")
    finish(no_cost, "2026-01-02T00:00:00.000000Z", perp="120")
    orders(no_cost, "2026-01-03T00:00:00.000000Z", perp="130")
    no_cost.rebalance_perpetual(order_id="reduce", target_quantity=D("1.5"), price=D("130"),
                                rules=PERP, explicit_rate=ZERO, implicit_rate=ZERO)
    assert no_cost.state.quote_cash == D("958.75")
    assert no_cost.state.isolated_collateral == D("51.25")
    assert no_cost.state.allocated_initial_margin == D("41.25")
    assert no_cost.nav() == D("1040")

    engine = SyntheticDecimalLedger(
        zero_exit_reserve_fixture=True, mandate_mode="directional_perpetual"
    )
    orders(engine, "2026-01-01T00:00:00.000000Z")
    engine.rebalance_perpetual(order_id="long", target_quantity=D("1"), price=D("100"),
                               rules=PERP, explicit_rate=E, implicit_rate=I)
    finish(engine, "2026-01-01T00:00:00.000000Z")
    orders(engine, "2026-01-02T00:00:00.000000Z", perp="90")
    engine.rebalance_perpetual(order_id="reverse", target_quantity=D("-1"), price=D("90"),
                               rules=PERP, explicit_rate=E, implicit_rate=I)
    assert engine.nav() == D("989.58")
    assert len(engine.ledgers["fill"]) == 3
    assert D(engine.ledgers["episode"][0]["net_dollar_pnl"]) == D("-10.285")
    assert engine._episode is not None and engine._episode.entry_costs == D("0.135")
    assert engine.reconcile() == 0


def test_engine_owned_t_minus_funding_membership_for_exit_and_entry():
    exiting = SyntheticDecimalLedger(
        zero_exit_reserve_fixture=True, cost_schedule=COSTLESS,
        mandate_mode="directional_perpetual",
    )
    orders(exiting, "2026-01-01T00:00:00.000000Z")
    exiting.rebalance_perpetual(order_id="entry", target_quantity=D("2"), price=D("100"),
                                rules=PERP, explicit_rate=ZERO, implicit_rate=ZERO)
    finish(exiting, "2026-01-01T00:00:00.000000Z")
    orders(exiting, "2026-01-02T00:00:00.000000Z", funding="0.001")
    assert exiting.state.funding_pnl == D("-0.2")
    exiting.rebalance_perpetual(order_id="exit", target_quantity=ZERO, price=D("100"),
                                rules=PERP, explicit_rate=ZERO, implicit_rate=ZERO)
    assert exiting.nav() == D("999.8")

    entering = SyntheticDecimalLedger(
        zero_exit_reserve_fixture=True, cost_schedule=COSTLESS,
        mandate_mode="directional_perpetual",
    )
    orders(entering, "2026-01-01T00:00:00.000000Z", funding="0.001")
    entering.rebalance_perpetual(order_id="entry", target_quantity=D("2"), price=D("100"),
                                 rules=PERP, explicit_rate=ZERO, implicit_rate=ZERO)
    assert entering.state.funding_pnl == 0

    negative = SyntheticDecimalLedger(
        zero_exit_reserve_fixture=True, cost_schedule=COSTLESS,
        mandate_mode="directional_perpetual",
    )
    orders(negative, "2026-01-01T00:00:00.000000Z")
    negative.rebalance_perpetual(order_id="short", target_quantity=D("-1"), price=D("100"),
                                 rules=PERP, explicit_rate=ZERO, implicit_rate=ZERO)
    finish(negative, "2026-01-01T00:00:00.000000Z")
    orders(negative, "2026-01-02T00:00:00.000000Z", funding="-0.001")
    assert negative.state.funding_pnl == D("-0.1")


@pytest.mark.parametrize(("target", "rate", "expected"), [
    ("-1", "0.001", "0.1"),
    ("1", "-0.001", "0.1"),
])
def test_receive_side_funding(target: str, rate: str, expected: str):
    engine = SyntheticDecimalLedger(
        zero_exit_reserve_fixture=True, cost_schedule=COSTLESS,
        mandate_mode="directional_perpetual",
    )
    orders(engine, "2026-01-01T00:00:00.000000Z")
    engine.rebalance_perpetual(
        order_id="entry", target_quantity=D(target), price=D("100"), rules=PERP,
        explicit_rate=ZERO, implicit_rate=ZERO,
    )
    finish(engine, "2026-01-01T00:00:00.000000Z")
    orders(engine, "2026-01-02T00:00:00.000000Z", funding=rate)
    assert engine.state.funding_pnl == D(expected)
    assert engine.nav() == D("1000") + D(expected)


def test_protective_exit_keeps_t_minus_funding_in_owning_episode():
    engine = SyntheticDecimalLedger(
        zero_exit_reserve_fixture=True, cost_schedule=COSTLESS,
        mandate_mode="directional_perpetual",
    )
    orders(engine, "2026-01-01T00:00:00.000000Z")
    engine.rebalance_perpetual(
        order_id="entry", target_quantity=D("1"), price=D("100"), rules=PERP,
        explicit_rate=ZERO, implicit_rate=ZERO,
    )
    finish(engine, "2026-01-01T00:00:00.000000Z")
    engine.begin_event("2026-01-02T00:00:00.000000Z", LINEAGE)
    engine.advance(Phase.OPEN_MARK)
    engine.mark_open(spot=D("100"), perpetual=D("100"))
    engine.advance(Phase.PROTECTIVE)
    engine.protective_flatten_perpetual(
        order_id="protect", price=D("100"), rules=PERP,
        explicit_rate=ZERO, implicit_rate=ZERO, reason="protective_exit",
    )
    assert engine.ledgers["episode"] == []
    engine.advance(Phase.FUNDING)
    engine.apply_funding(
        rate=D("0.001"), mark=D("100"), economic_at=engine.timestamp or "",
        available_at=engine.timestamp or "",
    )
    episode = engine.ledgers["episode"][-1]
    assert D(episode["funding_pnl"]) == D("-0.1")
    assert D(episode["net_dollar_pnl"]) == D("-0.1")


def test_invalid_funding_rolls_back_economics_and_retains_diagnostic():
    engine = SyntheticDecimalLedger(zero_exit_reserve_fixture=True)
    engine.begin_event("2026-01-01T00:00:00.000000Z", LINEAGE)
    engine.advance(Phase.OPEN_MARK)
    engine.mark_open(spot=D("100"), perpetual=D("100"))
    engine.advance(Phase.PROTECTIVE)
    engine.complete_phase()
    engine.advance(Phase.FUNDING)
    state_before = engine.state_digest()
    with pytest.raises(LedgerError, match="economic timestamp"):
        engine.apply_funding(
            rate=D("0.001"), mark=D("100"),
            economic_at="2026-01-02T00:00:00.000000Z",
            available_at="2026-01-01T00:00:00.000000Z",
        )
    assert engine.state_digest() == state_before
    assert engine.phase == Phase.FUNDING
    assert engine.ledgers["funding"] == []
    assert engine.ledgers["diagnostic"][-1]["kind"] == "rejected_funding"
    assert D(engine.ledgers["diagnostic"][-1]["cash_effect"]) == 0


def test_funding_caused_liquidation_full_run_oracle_982_17():
    engine = SyntheticDecimalLedger(
        zero_exit_reserve_fixture=True, mandate_mode="directional_perpetual"
    )
    orders(engine, "2026-01-01T00:00:00.000000Z")
    engine.rebalance_perpetual(order_id="entry", target_quantity=D("1"), price=D("100"),
                               rules=PERP, explicit_rate=E, implicit_rate=I)
    finish(engine, "2026-01-01T00:00:00.000000Z")
    engine.begin_event("2026-01-02T00:00:00.000000Z", LINEAGE)
    engine.advance(Phase.OPEN_MARK)
    engine.mark_open(spot=D("100"), perpetual=D("84"))
    assert engine.margin_equity() == D("8.85") and engine.maintenance() == D("8.4")
    engine.advance(Phase.PROTECTIVE)
    engine.complete_phase()
    engine.advance(Phase.FUNDING)
    engine.apply_funding(rate=D("0.01"), mark=D("84"), economic_at=engine.timestamp or "",
                         available_at=engine.timestamp or "")
    assert engine.state.margin_state == "liquidated"
    assert engine.state.invalidation_reason == "observed_liquidation_funding"
    assert engine.nav() == D("982.17")
    assert engine.reconcile() == 0


def test_open_liquidation_removes_funding_membership_and_is_terminal():
    engine = SyntheticDecimalLedger(
        leverage=D("5"), zero_exit_reserve_fixture=True, cost_schedule=COSTLESS,
        mandate_mode="directional_perpetual",
    )
    orders(engine, "2026-01-01T00:00:00.000000Z")
    engine.rebalance_perpetual(order_id="entry", target_quantity=D("1"), price=D("100"),
                               rules=PERP, explicit_rate=ZERO, implicit_rate=ZERO)
    finish(engine, "2026-01-01T00:00:00.000000Z")
    engine.begin_event("2026-01-02T00:00:00.000000Z", LINEAGE)
    engine.advance(Phase.OPEN_MARK)
    engine.mark_open(spot=D("100"), perpetual=D("80"))
    assert engine.state.margin_state == "liquidated"
    engine.advance(Phase.PROTECTIVE)
    engine.complete_phase()
    engine.advance(Phase.FUNDING)
    assert engine.apply_funding(
        rate=D("0.01"), mark=D("80"), economic_at=engine.timestamp or "",
        available_at=engine.timestamp or "",
    ) == 0
    with pytest.raises(LedgerError, match="terminal liquidation"):
        engine.begin_event("2026-01-03T00:00:00.000000Z", LINEAGE)


def test_gap_neutralization_and_missing_funding_fail_closed_oracle_979_68():
    engine = SyntheticDecimalLedger(
        leverage=D("2"), zero_exit_reserve_fixture=True, cost_schedule=COSTLESS,
        mandate_mode="directional_perpetual",
    )
    orders(engine, "2026-01-01T00:00:00.000000Z")
    engine.rebalance_perpetual(order_id="entry", target_quantity=D("1"), price=D("100"),
                               rules=PERP, explicit_rate=ZERO, implicit_rate=ZERO)
    finish(engine, "2026-01-01T00:00:00.000000Z")
    engine.begin_event("2026-01-03T00:00:00.000000Z", LINEAGE)
    engine.advance(Phase.OPEN_MARK)
    engine.mark_open(spot=D("100"), perpetual=D("80"))
    engine.advance(Phase.PROTECTIVE)
    engine.handle_gap(next_spot=None, next_perpetual=D("80"), spot_rules=None,
                      perp_rules=PERP, severe_explicit=SE, severe_implicit=SI)
    assert engine.nav() == D("979.68")
    assert engine.state.invalidation_reason == "missing_bar_while_exposed"
    assert engine.reconcile() == 0

    missing = SyntheticDecimalLedger(
        zero_exit_reserve_fixture=True, cost_schedule=COSTLESS,
        mandate_mode="directional_perpetual",
    )
    orders(missing, "2026-01-01T00:00:00.000000Z")
    missing.rebalance_perpetual(order_id="entry", target_quantity=D("1"), price=D("100"),
                                rules=PERP, explicit_rate=ZERO, implicit_rate=ZERO)
    finish(missing, "2026-01-01T00:00:00.000000Z")
    orders(missing, "2026-01-02T00:00:00.000000Z", missing_funding=True)
    assert missing.state.invalidation_reason == "missing_funding_while_exposed"


@pytest.mark.parametrize(("target", "adverse", "low", "high", "expected"), [
    ("1", "80", "80", "120", "979.2"),
    ("-1", "120", "80", "120", "978.8"),
])
def test_intrabar_adverse_extreme_liquidates_before_favourable_close(
    target: str, adverse: str, low: str, high: str, expected: str,
):
    engine = SyntheticDecimalLedger(
        leverage=D("5"), zero_exit_reserve_fixture=True, cost_schedule=COSTLESS,
        mandate_mode="directional_perpetual",
    )
    orders(engine, "2026-01-01T00:00:00.000000Z")
    engine.rebalance_perpetual(order_id="entry", target_quantity=D(target), price=D("100"),
                               rules=PERP, explicit_rate=ZERO, implicit_rate=ZERO)
    engine.complete_phase()
    engine.advance(Phase.POST_FILL_MARGIN)
    engine.post_fill_margin()
    engine.advance(Phase.INTRABAR)
    engine.intrabar(low=D(low), high=D(high), close=D("110"))
    assert engine.state.invalidation_reason == "observed_liquidation_intrabar"
    assert engine.nav() == D(expected)
    assert engine.state.perpetual_mark == D(adverse)
    assert engine.reconcile() == 0


def test_partial_fill_rounding_atomic_pair_and_transactional_rollback():
    partial = SyntheticDecimalLedger(zero_exit_reserve_fixture=True)
    orders(partial, "2026-01-01T00:00:00.000000Z")
    partial.spot_fill(order_id="partial", requested_delta=D("2"), filled_quantity=D("1.2"),
                      price=D("100"), rules=SPOT, explicit_rate=E, implicit_rate=I)
    assert partial.state.quote_cash == D("879.82")
    assert partial.state.spot_quantity == D("1.2")
    assert partial.nav() == D("999.82")
    assert D(partial.ledgers["order"][-1]["unfilled_quantity"]) == D("0.8")
    with pytest.raises(LedgerError, match="candle adapter"):
        partial.spot_fill(order_id="bad-candle", requested_delta=D("1"),
                          filled_quantity=D("0.5"), price=D("100"), rules=SPOT,
                          explicit_rate=E, implicit_rate=I, adapter="candle")

    strict = InstrumentRules("BTC_USDT_spot", D("0.001"), D("0.01"), D("10"))
    strict_engine = SyntheticDecimalLedger(
        rule_registry={strict.instrument: strict, PERP.instrument: PERP}
    )
    orders(strict_engine, "2026-01-01T00:00:00.000000Z")
    state_before = strict_engine.state_digest()
    rejected_before = len(strict_engine.ledgers["order"])
    with pytest.raises(LedgerError, match="minimum_notional"):
        strict_engine.spot_fill(order_id="too-small", requested_delta=D("0.0999"),
                          filled_quantity=D("0.099"), price=D("100"), rules=strict,
                          explicit_rate=E, implicit_rate=I)
    assert strict_engine.state_digest() == state_before
    assert len(strict_engine.ledgers["order"]) == rejected_before + 1
    assert strict_engine.ledgers["order"][-1]["status"] == "rejected"
    assert strict.quantity(D("-0.1239")) == D("-0.123")

    pair = SyntheticDecimalLedger(
        zero_exit_reserve_fixture=True, mandate_mode="delta_neutral"
    )
    orders(pair, "2026-01-01T00:00:00.000000Z")
    accepted = pair.atomic_pair_entry(
        order_id="pair", requested_spot=D("1"), spot_filled=D("1"),
        perpetual_filled_abs=ZERO, spot_price=D("100"), perpetual_price=D("100"),
        spot_rules=SPOT, perp_rules=PERP, explicit_rate=E, implicit_rate=I,
        severe_explicit=SE, severe_implicit=SI,
    )
    assert accepted is False and pair.nav() == D("999.45")
    assert pair.state.spot_quantity == pair.state.perpetual_quantity == 0
    assert pair.state.invalidation_reason == "atomic_pair_leg_failure"
    assert pair.reconcile() == 0

    rollback = SyntheticDecimalLedger(
        initial_nav=D("50"), zero_exit_reserve_fixture=True, mandate_mode="delta_neutral"
    )
    orders(rollback, "2026-01-01T00:00:00.000000Z")
    snapshot = rollback.state_digest()
    with pytest.raises(LedgerError, match="preflight"):
        rollback.atomic_pair_entry(
            order_id="unfunded", requested_spot=D("1"), spot_filled=D("1"),
            perpetual_filled_abs=ZERO, spot_price=D("100"), perpetual_price=D("100"),
            spot_rules=SPOT, perp_rules=PERP, explicit_rate=E, implicit_rate=I,
            severe_explicit=SE, severe_implicit=SI,
        )
    assert rollback.state_digest() == snapshot
    assert rollback.ledgers["order"][-1]["status"] == "rejected"

    second_leg = SyntheticDecimalLedger(
        zero_exit_reserve_fixture=True, mandate_mode="delta_neutral"
    )
    orders(second_leg, "2026-01-01T00:00:00.000000Z")
    before = second_leg.state_digest()
    with pytest.raises(LedgerError, match="second-leg funding preflight"):
        second_leg.atomic_pair_entry(
            order_id="unfunded-second", requested_spot=D("8"), spot_filled=D("8"),
            perpetual_filled_abs=D("8"), spot_price=D("100"), perpetual_price=D("100"),
            spot_rules=SPOT, perp_rules=PERP, explicit_rate=E, implicit_rate=I,
            severe_explicit=SE, severe_implicit=SI,
        )
    assert second_leg.state_digest() == before
    assert second_leg.state.spot_quantity == 0
    assert second_leg.ledgers["order"][-1]["status"] == "rejected"


def test_base_fee_atomic_pair_failure_neutralizes_exact_post_fee_inventory():
    base_spot = InstrumentRules(
        "BTC_USDT_spot", D("0.001"), D("0.01"), D("1"), fee_asset="base"
    )
    engine = SyntheticDecimalLedger(
        zero_exit_reserve_fixture=True,
        mandate_mode="delta_neutral",
        rule_registry={base_spot.instrument: base_spot, PERP.instrument: PERP},
    )
    orders(engine, "2026-01-01T00:00:00.000000Z")
    accepted = engine.atomic_pair_entry(
        order_id="base-pair", requested_spot=D("1.002"), spot_filled=D("1.002"),
        perpetual_filled_abs=ZERO, spot_price=D("100"), perpetual_price=D("100"),
        spot_rules=base_spot, perp_rules=PERP, explicit_rate=E, implicit_rate=I,
        severe_explicit=SE, severe_implicit=SI,
    )
    assert accepted is False
    assert engine.state.spot_quantity == 0
    assert engine.nav() == D("999.4501")
    assert engine.reconcile() == 0


def test_base_fee_at_execution_price_different_from_official_mark():
    base_spot = InstrumentRules(
        "BTC_USDT_spot", D("0.001"), D("0.01"), D("1"), fee_asset="base"
    )
    engine = SyntheticDecimalLedger(
        zero_exit_reserve_fixture=True,
        rule_registry={base_spot.instrument: base_spot, PERP.instrument: PERP},
    )
    orders(engine, "2026-01-01T00:00:00.000000Z", spot="100")
    engine.spot_fill(
        order_id="base-worse", requested_delta=D("1"), filled_quantity=D("1"),
        price=D("101"), rules=base_spot, explicit_rate=E, implicit_rate=I,
    )
    assert engine.nav() == D("998.8495")
    assert engine.state.explicit_costs == D("0.1")
    assert engine.reconcile() == 0


def test_zero_position_marks_and_funding_are_invariant_and_costs_scale_linearly():
    flat = SyntheticDecimalLedger(
        zero_exit_reserve_fixture=True, cost_schedule=COSTLESS
    )
    orders(flat, "2026-01-01T00:00:00.000000Z", spot="123", perp="117", funding="0.9")
    assert flat.nav() == D("1000") and flat.state.funding_pnl == 0

    endings = []
    for quantity in (D("1"), D("2")):
        engine = SyntheticDecimalLedger(zero_exit_reserve_fixture=True)
        orders(engine, "2026-01-01T00:00:00.000000Z")
        engine.spot_fill(
            order_id="buy", requested_delta=quantity, filled_quantity=quantity,
            price=D("100"), rules=SPOT, explicit_rate=E, implicit_rate=I,
        )
        finish(engine, "2026-01-01T00:00:00.000000Z")
        orders(engine, "2026-01-02T00:00:00.000000Z")
        engine.spot_fill(
            order_id="sell", requested_delta=-quantity, filled_quantity=-quantity,
            price=D("100"), rules=SPOT, explicit_rate=E, implicit_rate=I,
        )
        endings.append(engine.nav())
    assert endings == [D("999.7"), D("999.4")]


def test_sequence_duplicate_gap_flat_and_gap_liquidation_deficit():
    duplicate = SyntheticDecimalLedger()
    orders(duplicate, "2026-01-01T00:00:00.000000Z")
    finish(duplicate, "2026-01-01T00:00:00.000000Z")
    with pytest.raises(LedgerError, match="strictly increasing"):
        duplicate.begin_event("2026-01-01T00:00:00.000000Z", LINEAGE)
    with pytest.raises(PhaseError, match="advance exactly once"):
        duplicate.advance(Phase.INTRABAR)

    flat_gap = SyntheticDecimalLedger()
    flat_gap.begin_event("2026-01-01T00:00:00.000000Z", LINEAGE)
    flat_gap.advance(Phase.OPEN_MARK)
    flat_gap.mark_open(spot=D("100"), perpetual=D("100"))
    flat_gap.advance(Phase.PROTECTIVE)
    flat_gap.handle_gap(
        next_spot=None, next_perpetual=None, spot_rules=None, perp_rules=None,
        severe_explicit=SE, severe_implicit=SI,
    )
    assert flat_gap.state.invalidation_reason is None

    deficit = SyntheticDecimalLedger(
        leverage=D("5"), zero_exit_reserve_fixture=True, cost_schedule=COSTLESS,
        mandate_mode="directional_perpetual",
    )
    orders(deficit, "2026-01-01T00:00:00.000000Z")
    deficit.rebalance_perpetual(
        order_id="entry", target_quantity=D("1"), price=D("100"), rules=PERP,
        explicit_rate=ZERO, implicit_rate=ZERO,
    )
    finish(deficit, "2026-01-01T00:00:00.000000Z")
    deficit.begin_event("2026-01-03T00:00:00.000000Z", LINEAGE)
    deficit.advance(Phase.OPEN_MARK)
    deficit.mark_open(spot=D("100"), perpetual=D("1"))
    assert deficit.state.margin_state == "liquidated"
    assert deficit.state.liabilities == D("79.01")
    assert deficit.nav() == D("900.99")
    assert deficit.reconcile() == 0


def test_immediate_post_fill_margin_and_nonquote_perp_fail_closed():
    engine = SyntheticDecimalLedger(leverage=D("100"), mandate_mode="directional_perpetual")
    orders(engine, "2026-01-01T00:00:00.000000Z")
    engine.rebalance_perpetual(
        order_id="unsafe", target_quantity=D("1"), price=D("100"), rules=PERP,
        explicit_rate=E, implicit_rate=I,
    )
    assert engine.state.margin_state == "liquidated"
    assert engine.state.perpetual_quantity == 0
    with pytest.raises(LedgerError, match="terminal liquidation"):
        engine.rebalance_perpetual(
            order_id="again", target_quantity=D("1"), price=D("100"), rules=PERP,
            explicit_rate=E, implicit_rate=I,
        )

    bad_rules = InstrumentRules(
        "BTCUSDT_USD_M_perpetual", D("0.001"), D("0.01"), D("1"), fee_asset="base"
    )
    rejected = SyntheticDecimalLedger(
        mandate_mode="directional_perpetual",
        rule_registry={SPOT.instrument: SPOT, bad_rules.instrument: bad_rules}
    )
    orders(rejected, "2026-01-01T00:00:00.000000Z")
    before = rejected.state_digest()
    with pytest.raises(LedgerError, match="quote-denominated"):
        rejected.rebalance_perpetual(
            order_id="bad-fee", target_quantity=D("1"), price=D("100"), rules=bad_rules,
            explicit_rate=E, implicit_rate=I,
        )
    assert rejected.state_digest() == before


def test_partition_terminal_buy_hold_episode_and_required_artifact_digests():
    terminal = "2026-01-02T00:00:00.000000Z"
    engine = SyntheticDecimalLedger(
        terminal_timestamp=terminal, zero_exit_reserve_fixture=True
    )
    orders(engine, "2026-01-01T00:00:00.000000Z")
    engine.spot_fill(
        order_id="partition-buy", requested_delta=D("1"), filled_quantity=D("1"),
        price=D("100"), rules=SPOT, explicit_rate=E, implicit_rate=I,
    )
    finish(engine, "2026-01-01T00:00:00.000000Z")
    orders(engine, terminal, spot="110")
    engine.spot_fill(
        order_id="predeclared-terminal-flatten", requested_delta=D("-1"),
        filled_quantity=D("-1"), price=D("110"), rules=SPOT,
        explicit_rate=E, implicit_rate=I,
    )
    finish(engine, terminal, spot="110")
    assert engine.nav() == D("1009.685")
    assert D(engine.ledgers["episode"][-1]["net_dollar_PnL"]) == D("9.685")
    bundle = engine.evidence_bundle()
    required = {
        "decision_ledger.jsonl", "order_ledger.jsonl", "fill_ledger.jsonl",
        "funding_ledger.jsonl", "account_ledger.jsonl", "closed_episode_ledger.jsonl",
        "report.json", "evidence_manifest.json",
    }
    assert set(bundle) == required
    for path, expected in engine.run_summary()["artifact_digests"].items():
        import hashlib
        assert hashlib.sha256(bundle[path].encode("utf-8")).hexdigest() == expected
    assert engine.ledgers["account"][-1]["segment_id"] == "synthetic-segment"
    assert "exit_cost_reserve_memo" in engine.ledgers["account"][-1]


def test_fill_mark_basis_is_attributed_once_and_reconciles():
    engine = SyntheticDecimalLedger(zero_exit_reserve_fixture=True)
    orders(engine, "2026-01-01T00:00:00.000000Z", spot="100")
    engine.spot_fill(order_id="worse-fill", requested_delta=D("1"), filled_quantity=D("1"),
                     price=D("101"), rules=SPOT, explicit_rate=E, implicit_rate=I)
    assert engine.nav() == D("998.8485")
    assert engine.state.implicit_costs == D("1.0505")
    assert engine.reconcile() == 0


def test_fee_asset_identity_collision_lineage_and_phase_gates():
    third = InstrumentRules("BTC_USDT_spot", D("0.001"), D("0.01"), D("1"),
                            fee_asset="third", fee_asset_name="BNB")
    engine = SyntheticDecimalLedger(
        zero_exit_reserve_fixture=True, cost_schedule=EXPLICIT_ONLY,
        rule_registry={third.instrument: third, PERP.instrument: PERP},
    )
    engine.initialize_fee_asset(asset="BNB", quantity=D("0.1"), quote_mark=D("10"))
    orders(engine, "2026-01-01T00:00:00.000000Z")
    before = engine.state_digest()
    with pytest.raises(LedgerError, match="identity"):
        engine.spot_fill(order_id="bad-fee", requested_delta=D("1"), filled_quantity=D("1"),
                         price=D("100"), rules=third, explicit_rate=E, implicit_rate=ZERO,
                         fee_mark_asset="OTHER", fee_mark=D("10"))
    assert engine.state_digest() == before
    engine.spot_fill(order_id="fee", requested_delta=D("1"), filled_quantity=D("1"),
                     price=D("100"), rules=third, explicit_rate=E, implicit_rate=ZERO,
                     fee_mark_asset="BNB", fee_mark=D("10"))
    assert engine.nav() == D("999.9")
    row = engine.ledgers["fill"][-1]
    assert all(row[key] for key in (
        "source_digest", "rules_digest", "mark_source_digest", "index_source_digest",
        "before_state_digest", "after_state_digest", "row_digest",
    ))
    with pytest.raises(LedgerError, match="collision"):
        canonical_json({1: "one", "1": "string-one"})
    with pytest.raises(LedgerError, match="duplicate"):
        load_json_no_collisions('{"a":1,"a":2}')
    with pytest.raises(PhaseError):
        engine.advance(Phase.RECONCILE)
    with pytest.raises(PhaseError, match="has not reconciled"):
        engine.begin_event("2026-01-02T00:00:00.000000Z", LINEAGE)

    for rows in engine.ledgers.values():
        for ledger_row in rows:
            assert abs(D(ledger_row["event_accounting_residual"])) <= D("0.00000001")

    empty = SyntheticDecimalLedger()
    empty.begin_event("2026-01-01T00:00:00.000000Z", LINEAGE)
    empty.advance(Phase.OPEN_MARK)
    with pytest.raises(PhaseError, match="mandatory phase"):
        empty.complete_phase()


def test_daily_drawdown_blocks_entry_but_gap_protection_still_flattens():
    engine = SyntheticDecimalLedger(
        zero_exit_reserve_fixture=True, cost_schedule=COSTLESS
    )
    orders(engine, "2026-01-01T00:00:00.000000Z")
    engine.spot_fill(order_id="buy", requested_delta=D("1"), filled_quantity=D("1"),
                     price=D("100"), rules=SPOT, explicit_rate=ZERO, implicit_rate=ZERO)
    finish(engine, "2026-01-01T00:00:00.000000Z", spot="80")
    assert engine.state.entries_disabled is True
    engine.begin_event("2026-01-01T01:00:00.000000Z", LINEAGE)
    engine.advance(Phase.OPEN_MARK)
    engine.mark_open(spot=D("80"), perpetual=D("100"))
    engine.advance(Phase.PROTECTIVE)
    engine.handle_gap(next_spot=D("80"), next_perpetual=None, spot_rules=SPOT,
                      perp_rules=None, severe_explicit=SE, severe_implicit=SI)
    assert engine.state.spot_quantity == 0

    reset = SyntheticDecimalLedger(zero_exit_reserve_fixture=True, cost_schedule=COSTLESS)
    orders(reset, "2026-01-01T00:00:00.000000Z")
    reset.spot_fill(order_id="buy", requested_delta=D("1"), filled_quantity=D("1"),
                    price=D("100"), rules=SPOT, explicit_rate=ZERO, implicit_rate=ZERO)
    finish(reset, "2026-01-01T00:00:00.000000Z", spot="80")
    assert reset.state.daily_entries_disabled and not reset.state.drawdown_entries_disabled
    reset.begin_event("2026-01-02T00:00:00.000000Z", LINEAGE)
    assert reset.state.entries_disabled is False


def test_terminal_guard_unfilled_diagnostics_summary_and_replay():
    terminal = "2026-01-01T00:00:00.000000Z"
    engine = SyntheticDecimalLedger(terminal_timestamp=terminal, zero_exit_reserve_fixture=True)
    orders(engine, terminal)
    with pytest.raises(LedgerError, match="terminal timestamp"):
        engine.spot_fill(order_id="late-entry", requested_delta=D("1"), filled_quantity=D("1"),
                         price=D("100"), rules=SPOT, explicit_rate=E, implicit_rate=I)
    engine.record_unfilled_order(order_id="expired", instrument=SPOT.instrument,
                                 requested_quantity=D("1"), rounded_quantity=D("1"),
                                 status="expired", reason="price_bound", price_bound=D("99"))
    summary = engine.run_summary()
    assert summary["actionable_arm_id"] == "no_trade"
    assert summary["historical_rows_accessed"] is False
    assert summary["rejected_expired_partial_and_unfilled_counts"]["rejected"] == D("1")
    assert summary["rejected_expired_partial_and_unfilled_counts"]["expired"] == D("1")
    assert all(len(summary[key]) == 64 for key in (
        "implementation_digest", "contract_digest", "execution_config_digest", "mandate_digest",
    ))
    with pytest.raises(LedgerError, match="terminal boundary"):
        SyntheticDecimalLedger(terminal_timestamp=terminal).begin_event(
            "2026-01-02T00:00:00.000000Z", LINEAGE
        )

    def replay() -> dict[str, str]:
        candidate = SyntheticDecimalLedger(zero_exit_reserve_fixture=True)
        orders(candidate, "2026-01-01T00:00:00.000000Z")
        candidate.spot_fill(order_id="buy", requested_delta=D("1"), filled_quantity=D("1"),
                            price=D("100"), rules=SPOT, explicit_rate=E, implicit_rate=I)
        finish(candidate, "2026-01-01T00:00:00.000000Z")
        return candidate.canonical_ledgers()

    assert replay() == replay()


def test_one_shot_ids_mandate_caps_and_spoofed_reasons_fail_closed():
    funding = SyntheticDecimalLedger(cost_schedule=COSTLESS)
    funding.begin_event("2026-01-01T00:00:00.000000Z", LINEAGE)
    funding.advance(Phase.OPEN_MARK)
    funding.mark_open(spot=D("100"), perpetual=D("100"))
    funding.advance(Phase.PROTECTIVE)
    funding.complete_phase()
    funding.advance(Phase.FUNDING)
    funding.apply_funding(
        rate=D("0.1"), mark=D("100"), economic_at=funding.timestamp or "",
        available_at=funding.timestamp or "",
    )
    with pytest.raises(PhaseError, match="already completed"):
        funding.apply_funding(
            rate=D("0.1"), mark=D("100"), economic_at=funding.timestamp or "",
            available_at=funding.timestamp or "",
        )

    spot = SyntheticDecimalLedger()
    orders(spot, "2026-01-01T00:00:00.000000Z")
    spot.spot_fill(
        order_id="unique", requested_delta=D("1"), filled_quantity=D("1"),
        price=D("100"), rules=SPOT, explicit_rate=E, implicit_rate=I,
    )
    with pytest.raises(LedgerError, match="duplicate order_id"):
        spot.spot_fill(
            order_id="unique", requested_delta=D("1"), filled_quantity=D("1"),
            price=D("100"), rules=SPOT, explicit_rate=E, implicit_rate=I,
        )
    with pytest.raises(LedgerError, match="allocation"):
        spot.spot_fill(
            order_id="over-cap", requested_delta=D("2"), filled_quantity=D("2"),
            price=D("100"), rules=SPOT, explicit_rate=E, implicit_rate=I,
        )
    with pytest.raises(LedgerError, match="prohibits standalone perpetual"):
        spot.rebalance_perpetual(
            order_id="spoof", target_quantity=D("1"), price=D("100"), rules=PERP,
            explicit_rate=E, implicit_rate=I, reason="protective_neutralization",
        )

    directional = SyntheticDecimalLedger(mandate_mode="directional_perpetual")
    orders(directional, "2026-01-01T00:00:00.000000Z")
    with pytest.raises(LedgerError, match="prohibits standalone spot"):
        directional.spot_fill(
            order_id="spoof", requested_delta=D("1"), filled_quantity=D("1"),
            price=D("100"), rules=SPOT, explicit_rate=E, implicit_rate=I,
            reason="gap_neutralization",
        )
    with pytest.raises(LedgerError, match="allocation"):
        directional.rebalance_perpetual(
            order_id="over-cap", target_quantity=D("3"), price=D("100"), rules=PERP,
            explicit_rate=E, implicit_rate=I,
        )


def test_delta_neutral_mandate_requires_1x():
    with pytest.raises(LedgerError, match="1x"):
        SyntheticDecimalLedger(mandate_mode="delta_neutral", leverage=D("2"))


def test_flat_gap_resets_generated_rolling_risk_and_lineage_causality():
    engine = SyntheticDecimalLedger(zero_exit_reserve_fixture=True)
    orders(engine, "2026-01-01T00:00:00.000000Z")
    engine.spot_fill(
        order_id="buy", requested_delta=D("1"), filled_quantity=D("1"),
        price=D("100"), rules=SPOT, explicit_rate=E, implicit_rate=I,
    )
    engine.spot_fill(
        order_id="sell", requested_delta=D("-1"), filled_quantity=D("-1"),
        price=D("80"), rules=SPOT, explicit_rate=E, implicit_rate=I,
    )
    finish(engine, "2026-01-01T00:00:00.000000Z", spot="80")
    assert engine.state.daily_entries_disabled
    engine.begin_event("2026-01-01T01:00:00.000000Z", LINEAGE)
    engine.advance(Phase.OPEN_MARK)
    engine.mark_open(spot=D("80"), perpetual=D("100"))
    engine.advance(Phase.PROTECTIVE)
    engine.handle_gap(
        next_spot=None, next_perpetual=None, spot_rules=None, perp_rules=None,
        severe_explicit=SE, severe_implicit=SI,
    )
    assert not engine.state.entries_disabled
    assert engine.state.high_water_nav == engine.nav()

    future_observed = "2026-01-02T00:00:00.000000Z"
    future_source = digest({
        "source_path": "synthetic://fixture", "segment_id": "synthetic-segment",
        "observed_at": future_observed,
        "source_available_at": "1970-01-01T00:00:00.000000Z",
    })
    bad_lineage = Lineage(
        future_source, digest(RULES),
        digest({"source_digest": future_source, "kind": "official_mark"}),
        digest({"source_digest": future_source, "kind": "official_index"}),
        observed_at=future_observed,
    )
    fresh = SyntheticDecimalLedger()
    with pytest.raises(LedgerError, match="observation occurs after"):
        fresh.begin_event("2026-01-03T00:00:00.000000Z", bad_lineage)


def open_delta_pair(*, spot_rules=SPOT):
    registry = {spot_rules.instrument: spot_rules, PERP.instrument: PERP}
    engine = SyntheticDecimalLedger(
        mandate_mode="delta_neutral", zero_exit_reserve_fixture=True,
        rule_registry=registry,
    )
    orders(engine, "2026-01-01T00:00:00.000000Z")
    requested = D("1.002") if spot_rules.fee_asset == "base" else D("1")
    assert engine.atomic_pair_entry(
        order_id="open-pair", requested_spot=requested, spot_filled=requested,
        perpetual_filled_abs=D("1"), spot_price=D("100"), perpetual_price=D("100"),
        spot_rules=spot_rules, perp_rules=PERP, explicit_rate=E, implicit_rate=I,
        severe_explicit=SE, severe_implicit=SI,
    )
    finish(engine, "2026-01-01T00:00:00.000000Z")
    orders(engine, "2026-01-02T00:00:00.000000Z")
    return engine


@pytest.mark.parametrize(("ordinary_fill", "expected"), [
    ("1", "999.4"),
    ("0", "999.15"),
])
def test_v3_candle_pair_close_full_and_rejected_perp_residual(
    ordinary_fill: str, expected: str,
):
    engine = open_delta_pair()
    valid = engine.atomic_pair_close(
        order_id=f"close-{ordinary_fill}", requested_spot_gross=D("1"),
        spot_filled_gross=D("1"), perpetual_filled_abs=D(ordinary_fill),
        spot_price=D("100"), perpetual_price=D("100"),
        severe_spot_price=D("100"), severe_perpetual_price=D("100"),
        worst_permitted_severe_perpetual_price=D("100"),
        post_spot_mark=D("100"), post_perpetual_mark=D("100"),
        valuation_timestamp=engine.timestamp or "", spot_rules=SPOT, perp_rules=PERP,
        full_close=True,
        spot_source_digest=LINEAGE.source_digest,
        perpetual_source_digest=LINEAGE.source_digest,
    )
    assert valid
    assert engine.state.spot_quantity == engine.state.perpetual_quantity == 0
    assert engine.nav() == D(expected)
    completion = engine.ledgers["diagnostic"][-1]
    assert completion["kind"] == "pair_close_completion"
    assert len(completion["semantic_run_settings_digest"]) == 64
    assert digest(completion["semantic_run_settings"]) == completion[
        "semantic_run_settings_digest"
    ]
    if ordinary_fill == "0":
        assert any(row["status"] == "rejected" for row in engine.ledgers["order"])
        assert D(completion["created_residual_naked_short_quantity"]) == D("1")


def test_v3_l2_cartesian_partial_close_and_spot_zero_outcome():
    engine = open_delta_pair()
    valid = engine.atomic_pair_close(
        order_id="partial-close", requested_spot_gross=D("1"),
        spot_filled_gross=D("0.5"), perpetual_filled_abs=D("0.3"),
        spot_price=D("100"), perpetual_price=D("100"), severe_spot_price=D("100"),
        severe_perpetual_price=D("100"),
        worst_permitted_severe_perpetual_price=D("100"),
        post_spot_mark=D("100"), post_perpetual_mark=D("100"),
        valuation_timestamp=engine.timestamp or "", spot_rules=SPOT, perp_rules=PERP,
        adapter="qualified_quote_or_L2",
        cartesian_outcomes=tuple(
            PairCloseCartesianOutcome(gross, D("100"), q, D("100"), D("100"))
            for gross, quantities in (
                (ZERO, (ZERO,)),
                (D("0.5"), (ZERO, D("0.3"), D("0.5"))),
                (D("1"), (ZERO, D("0.3"), D("0.5"), D("1"))),
            )
            for q in quantities
        ),
        spot_source_digest=LINEAGE.source_digest,
        perpetual_source_digest=LINEAGE.source_digest,
    )
    assert valid
    assert engine.state.spot_quantity == D("0.5")
    assert engine.state.perpetual_quantity == D("-0.5")
    assert engine.nav() == D("999.5")
    intended_perp = next(
        row for row in engine.ledgers["order"] if row["order_id"] == "partial-close:perp"
    )
    assert D(intended_perp["rounded_quantity"]) == D("0.5")
    assert D(intended_perp["filled_quantity"]) == D("0.3")
    assert D(intended_perp["unfilled_quantity"]) == D("0.2")

    unchanged = open_delta_pair()
    before = unchanged.state_digest()
    assert not unchanged.atomic_pair_close(
        order_id="spot-zero", requested_spot_gross=D("1"), spot_filled_gross=ZERO,
        perpetual_filled_abs=ZERO, spot_price=D("100"), perpetual_price=D("100"),
        severe_spot_price=D("100"), severe_perpetual_price=D("100"),
        worst_permitted_severe_perpetual_price=D("100"),
        post_spot_mark=D("100"), post_perpetual_mark=D("100"),
        valuation_timestamp=unchanged.timestamp or "", spot_rules=SPOT, perp_rules=PERP,
        full_close=True,
        spot_source_digest=LINEAGE.source_digest,
        perpetual_source_digest=LINEAGE.source_digest,
    )
    assert unchanged.state_digest() == before


def test_v3_base_fee_preflight_and_delayed_residual_boundary():
    base = InstrumentRules(
        "BTC_USDT_spot", D("0.001"), D("0.01"), D("1"), fee_asset="base"
    )
    base_engine = open_delta_pair(spot_rules=base)
    before = base_engine.state_digest()
    with pytest.raises(LedgerError, match="spot dust"):
        base_engine.atomic_pair_close(
            order_id="base-close", requested_spot_gross=base_engine.state.spot_quantity,
            spot_filled_gross=D("1"), perpetual_filled_abs=D("1"),
            spot_price=D("100"), perpetual_price=D("100"), severe_spot_price=D("100"),
            severe_perpetual_price=D("100"),
            worst_permitted_severe_perpetual_price=D("100"),
            post_spot_mark=D("100"), post_perpetual_mark=D("100"),
            valuation_timestamp=base_engine.timestamp or "", spot_rules=base, perp_rules=PERP,
            full_close=True,
            spot_source_digest=base_engine.current_lineage.source_digest,
            perpetual_source_digest=base_engine.current_lineage.source_digest,
        )
    assert base_engine.state_digest() == before

    delayed = open_delta_pair()
    assert not delayed.atomic_pair_close(
        order_id="delayed", requested_spot_gross=D("1"), spot_filled_gross=D("1"),
        perpetual_filled_abs=ZERO, spot_price=D("100"), perpetual_price=D("100"),
        severe_spot_price=D("100"), severe_perpetual_price=None,
        worst_permitted_severe_perpetual_price=D("100"),
        post_spot_mark=D("100"), post_perpetual_mark=D("100"),
        valuation_timestamp=delayed.timestamp or "", spot_rules=SPOT, perp_rules=PERP,
        full_close=True,
        spot_source_digest=LINEAGE.source_digest,
        perpetual_source_digest=LINEAGE.source_digest,
    )
    assert delayed.state.spot_quantity == 0
    assert delayed.state.perpetual_quantity == D("-1")
    assert delayed.state.pending_forced_perpetual_buy_to_close == D("1")
    finish(delayed, "2026-01-02T00:00:00.000000Z")
    other_descriptor = {
        **SOURCE_DESCRIPTOR, "segment_id": "synthetic-segment-2",
    }
    other_source = digest(other_descriptor)
    other_lineage = Lineage(
        other_source, digest(RULES),
        digest({"source_digest": other_source, "kind": "official_mark"}),
        digest({"source_digest": other_source, "kind": "official_index"}),
        segment_id="synthetic-segment-2",
    )
    delayed.begin_event("2026-01-03T00:00:00.000000Z", other_lineage)
    delayed.advance(Phase.OPEN_MARK)
    delayed.mark_open(spot=D("100"), perpetual=D("100"))
    delayed.advance(Phase.PROTECTIVE)
    assert delayed.resolve_pending_pair_close(
        order_id="delayed-safety", price=D("100"), rules=PERP,
        spot_mark=D("100"), perpetual_mark=D("100"),
        valuation_timestamp=delayed.timestamp or "",
        spot_source_digest=other_lineage.source_digest,
        perpetual_source_digest=other_lineage.source_digest,
    )
    assert delayed.state.perpetual_quantity == 0
    completion = delayed.ledgers["diagnostic"][-1]
    assert completion["kind"] == "pair_close_delayed_completion"
    assert completion["origin_segment_id"] == "synthetic-segment"
    assert completion["completion_segment_id"] == "synthetic-segment-2"
    assert D(completion["remaining_pair_quantity_mismatch"]) == 0


def test_v3_worst_price_gate_and_mismatch_whole_pair_attempt():
    bounded = open_delta_pair()
    before = bounded.state_digest()
    with pytest.raises(LedgerError, match="exceeds frozen worst"):
        bounded.atomic_pair_close(
            order_id="worse-than-bound", requested_spot_gross=D("1"),
            spot_filled_gross=D("1"), perpetual_filled_abs=ZERO,
            spot_price=D("100"), perpetual_price=D("100"),
            severe_spot_price=D("100"), severe_perpetual_price=D("101"),
            worst_permitted_severe_perpetual_price=D("100"),
            post_spot_mark=D("100"), post_perpetual_mark=D("100"),
            valuation_timestamp=bounded.timestamp or "", spot_rules=SPOT, perp_rules=PERP,
            full_close=True,
            adapter="qualified_quote_or_L2",
            cartesian_outcomes=(
                PairCloseCartesianOutcome(ZERO, D("100"), ZERO, D("100"), D("100")),
                PairCloseCartesianOutcome(D("1"), D("100"), ZERO, D("100"), D("101")),
                PairCloseCartesianOutcome(D("1"), D("100"), D("1"), D("100"), D("100")),
            ),
            spot_source_digest=LINEAGE.source_digest,
            perpetual_source_digest=LINEAGE.source_digest,
        )
    assert bounded.state_digest() == before

    mismatch = open_delta_pair()
    valid = mismatch.atomic_pair_close(
        order_id="mismatch", requested_spot_gross=D("1"),
        spot_filled_gross=D("0.5"), perpetual_filled_abs=D("0.5"),
        spot_price=D("100"), perpetual_price=D("100"), severe_spot_price=D("100"),
        severe_perpetual_price=D("100"),
        worst_permitted_severe_perpetual_price=D("100"),
        post_spot_mark=D("100"), post_perpetual_mark=D("120"),
        valuation_timestamp=mismatch.timestamp or "", spot_rules=SPOT, perp_rules=PERP,
        adapter="qualified_quote_or_L2",
        cartesian_outcomes=tuple(
            PairCloseCartesianOutcome(gross, D("100"), q, D("100"), D("100"))
            for gross, quantities in (
                (ZERO, (ZERO,)), (D("0.5"), (ZERO, D("0.5"))),
                (D("1"), (ZERO, D("0.5"), D("1"))),
            )
            for q in quantities
        ),
        spot_source_digest=LINEAGE.source_digest,
        perpetual_source_digest=LINEAGE.source_digest,
    )
    assert valid
    assert mismatch.state.spot_quantity == mismatch.state.perpetual_quantity == 0
    assert any(
        row["order_id"] == "mismatch:severe-whole-spot"
        for row in mismatch.ledgers["order"]
    )


def test_v3_partial_delayed_close_persists_matched_pair_and_binds_cartesian_set():
    engine = open_delta_pair()
    outcomes = tuple(
        PairCloseCartesianOutcome(gross, D("100"), q, D("100"), D("100"))
        for gross, quantities in (
            (ZERO, (ZERO,)), (D("0.5"), (ZERO, D("0.5"))),
            (D("1"), (ZERO, D("0.5"), D("1"))),
        )
        for q in quantities
    )
    assert not engine.atomic_pair_close(
        order_id="partial-delayed", requested_spot_gross=D("1"),
        spot_filled_gross=D("0.5"), perpetual_filled_abs=ZERO,
        spot_price=D("100"), perpetual_price=D("100"), severe_spot_price=D("100"),
        severe_perpetual_price=None,
        worst_permitted_severe_perpetual_price=D("100"),
        post_spot_mark=D("100"), post_perpetual_mark=D("100"),
        valuation_timestamp=engine.timestamp or "", spot_rules=SPOT, perp_rules=PERP,
        adapter="qualified_quote_or_L2", cartesian_outcomes=outcomes,
        spot_source_digest=LINEAGE.source_digest,
        perpetual_source_digest=LINEAGE.source_digest,
    )
    pending = engine.ledgers["diagnostic"][-1]
    settings = pending["semantic_run_settings"]
    assert settings["cartesian_outcome_set_digest"] == digest(
        settings["cartesian_outcome_set"]
    )
    finish(engine, "2026-01-02T00:00:00.000000Z")
    engine.begin_event("2026-01-03T00:00:00.000000Z", LINEAGE)
    engine.advance(Phase.OPEN_MARK)
    engine.mark_open(spot=D("100"), perpetual=D("100"))
    engine.advance(Phase.PROTECTIVE)
    assert engine.resolve_pending_pair_close(
        order_id="partial-delayed-safety", price=D("100"), rules=PERP,
        spot_mark=D("100"), perpetual_mark=D("100"),
        valuation_timestamp=engine.timestamp or "",
        spot_source_digest=LINEAGE.source_digest,
        perpetual_source_digest=LINEAGE.source_digest,
    )
    assert engine.state.spot_quantity == D("0.5")
    assert engine.state.perpetual_quantity == D("-0.5")
    completion = engine.ledgers["diagnostic"][-1]
    assert D(completion["remaining_pair_quantity_mismatch"]) == 0
    assert D(completion["remaining_pair_notional_mismatch"]) == 0


def test_v3_rejects_price_substitution_and_undeclared_oversell_before_fill():
    engine = open_delta_pair()
    outcomes = (
        PairCloseCartesianOutcome(ZERO, D("100"), ZERO, D("100"), D("100")),
        PairCloseCartesianOutcome(D("1"), D("100"), ZERO, D("100"), D("100")),
        PairCloseCartesianOutcome(D("1"), D("100"), D("1"), D("100"), D("100")),
    )
    before = engine.state_digest()
    with pytest.raises(LedgerError, match="exact same instrument open"):
        engine.atomic_pair_close(
            order_id="candle-substitute", requested_spot_gross=D("1"),
            spot_filled_gross=D("1"), perpetual_filled_abs=ZERO,
            spot_price=D("100"), perpetual_price=D("100"), severe_spot_price=D("99"),
            severe_perpetual_price=D("90"),
            worst_permitted_severe_perpetual_price=D("100"),
            post_spot_mark=D("100"), post_perpetual_mark=D("100"),
            valuation_timestamp=engine.timestamp or "", spot_rules=SPOT, perp_rules=PERP,
            full_close=True, spot_source_digest=LINEAGE.source_digest,
            perpetual_source_digest=LINEAGE.source_digest,
        )
    assert engine.state_digest() == before
    with pytest.raises(LedgerError, match="absent from Cartesian outcome"):
        engine.atomic_pair_close(
            order_id="substitute", requested_spot_gross=D("1"),
            spot_filled_gross=D("1"), perpetual_filled_abs=ZERO,
            spot_price=D("100"), perpetual_price=D("100"), severe_spot_price=D("100"),
            severe_perpetual_price=D("99"),
            worst_permitted_severe_perpetual_price=D("100"),
            post_spot_mark=D("100"), post_perpetual_mark=D("100"),
            valuation_timestamp=engine.timestamp or "", spot_rules=SPOT, perp_rules=PERP,
            adapter="qualified_quote_or_L2", cartesian_outcomes=outcomes,
            full_close=True, spot_source_digest=LINEAGE.source_digest,
            perpetual_source_digest=LINEAGE.source_digest,
        )
    assert engine.state_digest() == before
    with pytest.raises(LedgerError, match="exceeds inventory"):
        engine.atomic_pair_close(
            order_id="oversell", requested_spot_gross=D("2"),
            spot_filled_gross=D("2"), perpetual_filled_abs=D("1"),
            spot_price=D("100"), perpetual_price=D("100"), severe_spot_price=D("100"),
            severe_perpetual_price=D("100"),
            worst_permitted_severe_perpetual_price=D("100"),
            post_spot_mark=D("100"), post_perpetual_mark=D("100"),
            valuation_timestamp=engine.timestamp or "", spot_rules=SPOT, perp_rules=PERP,
            spot_source_digest=LINEAGE.source_digest,
            perpetual_source_digest=LINEAGE.source_digest,
        )
    assert engine.state_digest() == before


def test_v3_whole_pair_spot_checkpoint_liquidation_is_terminal_failure():
    engine = open_delta_pair()
    outcomes = tuple(
        PairCloseCartesianOutcome(gross, D("100"), q, D("100"), D("100"))
        for gross, quantities in (
            (ZERO, (ZERO,)), (D("0.5"), (ZERO, D("0.5"))),
            (D("1"), (ZERO, D("0.5"), D("1"))),
        )
        for q in quantities
    )
    assert not engine.atomic_pair_close(
        order_id="terminal-whole", requested_spot_gross=D("1"),
        spot_filled_gross=D("0.5"), perpetual_filled_abs=D("0.5"),
        spot_price=D("100"), perpetual_price=D("100"), severe_spot_price=D("100"),
        severe_perpetual_price=D("100"),
        worst_permitted_severe_perpetual_price=D("100"),
        post_spot_mark=D("100"), post_perpetual_mark=D("190"),
        valuation_timestamp=engine.timestamp or "", spot_rules=SPOT, perp_rules=PERP,
        adapter="qualified_quote_or_L2", cartesian_outcomes=outcomes,
        spot_source_digest=LINEAGE.source_digest,
        perpetual_source_digest=LINEAGE.source_digest,
    )
    assert engine.state.margin_state == "liquidated"
    assert engine.state.invalidation_reason == "observed_liquidation_post_severe_pair_spot_fill"
    assert engine.ledgers["diagnostic"][-1]["reason"] == "mismatch"


def test_v3_cartesian_set_rejects_duplicates_and_is_order_canonical():
    outcomes = (
        PairCloseCartesianOutcome(ZERO, D("100"), ZERO, D("100"), D("100")),
        PairCloseCartesianOutcome(D("1"), D("100"), ZERO, D("100"), D("100")),
        PairCloseCartesianOutcome(D("1"), D("100"), D("1"), D("100"), D("100")),
    )

    def close_with(rows):
        engine = open_delta_pair()
        engine.atomic_pair_close(
            order_id="canonical", requested_spot_gross=D("1"),
            spot_filled_gross=D("1"), perpetual_filled_abs=D("1"),
            spot_price=D("100"), perpetual_price=D("100"), severe_spot_price=D("100"),
            severe_perpetual_price=D("100"),
            worst_permitted_severe_perpetual_price=D("100"),
            post_spot_mark=D("100"), post_perpetual_mark=D("100"),
            valuation_timestamp=engine.timestamp or "", spot_rules=SPOT, perp_rules=PERP,
            adapter="qualified_quote_or_L2", cartesian_outcomes=rows, full_close=True,
            spot_source_digest=LINEAGE.source_digest,
            perpetual_source_digest=LINEAGE.source_digest,
        )
        return engine.ledgers["diagnostic"][-1]["semantic_run_settings_digest"]

    assert close_with(outcomes) == close_with(tuple(reversed(outcomes)))
    duplicate = open_delta_pair()
    before = duplicate.state_digest()
    with pytest.raises(LedgerError, match="duplicate Cartesian"):
        duplicate.atomic_pair_close(
            order_id="duplicate", requested_spot_gross=D("1"),
            spot_filled_gross=D("1"), perpetual_filled_abs=D("1"),
            spot_price=D("100"), perpetual_price=D("100"), severe_spot_price=D("100"),
            severe_perpetual_price=D("100"),
            worst_permitted_severe_perpetual_price=D("100"),
            post_spot_mark=D("100"), post_perpetual_mark=D("100"),
            valuation_timestamp=duplicate.timestamp or "", spot_rules=SPOT, perp_rules=PERP,
            adapter="qualified_quote_or_L2", cartesian_outcomes=outcomes + (outcomes[-1],),
            full_close=True, spot_source_digest=LINEAGE.source_digest,
            perpetual_source_digest=LINEAGE.source_digest,
        )
    assert duplicate.state_digest() == before


def test_no_strategy_history_metrics_or_external_imports():
    tree = ast.parse((ROOT / "src/trading_platform/btc_decimal_ledger_e1.py").read_text())
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    prohibited = {"requests", "httpx", "ccxt", "freqtrade", "nats", "psycopg", "pandas"}
    assert not imports.intersection(prohibited)
    source = (ROOT / "src/trading_platform/btc_decimal_ledger_e1.py").read_text().lower()
    assert "def score" not in source and "def sharpe" not in source
    assert "read_csv" not in source and "read_parquet" not in source
