from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from trading_platform.unified_btc_accounting import (
    InstrumentRules,
    KernelLineage,
    UnifiedAccountingError,
    UnifiedBtcAccounting,
    content_digest,
    decimal_string,
    notional_mismatch_fraction,
    validate_candle_all_or_none,
)


D = Decimal
ROOT = Path(__file__).resolve().parents[1]
T0 = datetime(2020, 1, 1, tzinfo=timezone.utc)


def lineage() -> KernelLineage:
    return KernelLineage(
        experiment_id="synthetic-e1",
        run_id="fixture",
        scenario_id="candle-primary-30bps-rt-v1",
        implementation_digest="a" * 64,
        contract_digest="b" * 64,
        execution_config_digest="c" * 64,
        mandate_digest="d" * 64,
    )


def ledger(**kwargs) -> UnifiedBtcAccounting:
    return UnifiedBtcAccounting(
        starting_quote_cash=D("1000"),
        spot_mark=D("100"),
        perpetual_mark=D("100"),
        lineage=lineage(),
        **kwargs,
    )


def test_decimal_canonicalization_and_float_rejection():
    assert decimal_string(D("-0.000")) == "0"
    assert decimal_string(D("10.5000")) == "10.5"
    assert decimal_string(D("1E+3")) == "1000"
    with pytest.raises(UnifiedAccountingError, match="Decimal"):
        decimal_string(1.0)  # type: ignore[arg-type]
    assert content_digest({"x": D("1.0")}) == content_digest({"x": D("1")})


def test_spot_round_trip_loses_exact_costs_and_entry_base_fee_reduces_btc():
    book = ledger()
    book.apply_spot_fill(
        event_id="buy", at=T0, signed_quantity=D("1"), price=D("100"),
        fee_amount=D("0.001"), fee_asset="BTC", implicit_cost=D("0.25")
    )
    assert book.state.spot_quantity == D("0.999")
    book.apply_spot_fill(
        event_id="sell", at=T0, signed_quantity=D("-0.998"), price=D("100"),
        fee_amount=D("0.001"), fee_asset="BTC", implicit_cost=D("0.25")
    )
    assert book.state.spot_quantity == ZERO
    assert book.nav() == D("999.3")
    assert book.state.explicit_costs_memo == D("0.2")
    assert book.state.implicit_costs_memo == D("0.5")


ZERO = D("0")


def test_third_asset_fee_mutates_balance_and_is_in_nav_once():
    book = ledger(fee_asset_balances={"BNB": D("1")}, fee_asset_marks={"BNB": D("10")})
    start = book.nav()
    book.apply_spot_fill(
        event_id="buy", at=T0, signed_quantity=D("1"), price=D("100"),
        fee_amount=D("0.01"), fee_asset="BNB"
    )
    assert book.state.fee_asset_balances["BNB"] == D("0.99")
    assert book.nav() == start - D("0.1")
    with pytest.raises(UnifiedAccountingError, match="unsupported fee"):
        ledger().apply_spot_fill(
            event_id="bad", at=T0, signed_quantity=D("1"), price=D("100"),
            fee_amount=D("0.01"), fee_asset="DOGE"
        )


@pytest.mark.parametrize(
    ("opening_delta", "close_delta", "exit", "expected"),
    [(D("1"), D("-1"), D("110"), D("10")), (D("-1"), D("1"), D("90"), D("10"))],
)
def test_linear_perpetual_long_and_short_realized_pnl(opening_delta, close_delta, exit, expected):
    book = ledger()
    book.apply_perpetual_fill(
        event_id="open", at=T0, signed_quantity_delta=opening_delta, price=D("100"), leverage=D("1")
    )
    book.mark_to_market(
        event_id="mark", at=T0, spot_mark=D("100"), perpetual_mark=exit
    )
    book.apply_perpetual_fill(
        event_id="close", at=T0, phase="intrabar_mark_or_liquidation",
        signed_quantity_delta=close_delta, price=exit, leverage=D("1")
    )
    assert book.state.realized_pnl_memo == expected
    assert book.nav() == D("1000") + expected
    assert book.state.perpetual_quantity == ZERO
    assert book.state.average_perpetual_entry is None


def test_resize_partial_release_and_explicit_two_fill_reversal():
    book = ledger()
    book.apply_perpetual_fill(
        event_id="open", at=T0, signed_quantity_delta=D("2"), price=D("100"), leverage=D("2")
    )
    book.apply_perpetual_fill(
        event_id="reduce", at=T0, signed_quantity_delta=D("-0.5"), price=D("100"), leverage=D("2")
    )
    assert book.state.allocated_initial_margin_memo == D("75")
    assert book.state.isolated_collateral == D("75")
    with pytest.raises(UnifiedAccountingError, match="explicit close"):
        book.apply_perpetual_fill(
            event_id="bad-reverse", at=T0, signed_quantity_delta=D("-2"), price=D("100"), leverage=D("2")
        )
    book.apply_perpetual_fill(
        event_id="flat", at=T0, signed_quantity_delta=D("-1.5"), price=D("100"), leverage=D("2")
    )
    book.apply_perpetual_fill(
        event_id="short", at=T0, signed_quantity_delta=D("-1"), price=D("100"), leverage=D("2")
    )
    assert book.state.perpetual_quantity == D("-1")


@pytest.mark.parametrize(
    ("quantity", "rate", "expected"),
    [(D("1"), D("0.01"), D("-1")), (D("-1"), D("0.01"), D("1")),
     (D("1"), D("-0.01"), D("1")), (D("-1"), D("-0.01"), D("-1"))],
)
def test_funding_signs(quantity, rate, expected):
    book = ledger()
    book.apply_perpetual_fill(
        event_id="open", at=T0, signed_quantity_delta=quantity, price=D("100"), leverage=D("1")
    )
    start = book.nav()
    book.apply_funding(
        event_id="fund", at=T0, t_minus_quantity=quantity, rate=rate, funding_mark=D("100")
    )
    assert book.state.funding_memo == expected
    assert book.nav() == start + expected


def test_same_timestamp_entry_does_not_acquire_funding_and_exit_does_not_evade_it():
    entry = ledger()
    entry.apply_funding(
        event_id="pre-entry-funding", at=T0, t_minus_quantity=ZERO, rate=D("0.01"), funding_mark=D("100")
    )
    entry.apply_perpetual_fill(
        event_id="entry", at=T0, signed_quantity_delta=D("1"), price=D("100"), leverage=D("1")
    )
    assert entry.state.funding_memo == ZERO

    exited = ledger()
    exited.apply_perpetual_fill(
        event_id="open", at=T0 - timedelta(hours=1), signed_quantity_delta=D("1"), price=D("100"), leverage=D("1")
    )
    exited.apply_perpetual_fill(
        event_id="exit", at=T0, phase="protective_exit", signed_quantity_delta=D("-1"), price=D("100"), leverage=D("1")
    )
    exited.apply_funding(
        event_id="owed", at=T0, t_minus_quantity=D("1"), rate=D("0.01"), funding_mark=D("100")
    )
    assert exited.state.quote_cash == D("999")
    assert exited.state.isolated_collateral == ZERO


def test_funding_can_create_observed_margin_breach():
    book = ledger()
    book.apply_perpetual_fill(
        event_id="open", at=T0, signed_quantity_delta=D("1"), price=D("100"), leverage=D("10")
    )
    book.apply_funding(
        event_id="fund", at=T0, t_minus_quantity=D("1"), rate=D("0.06"), funding_mark=D("100")
    )
    assert book.margin_snapshot(mark=D("100"), maintenance_rate=D("0.05")).observed_liquidation


def test_gap_through_liquidation_records_fee_deficit_and_terminal_invalidation():
    book = ledger()
    book.apply_perpetual_fill(
        event_id="open", at=T0 - timedelta(hours=1), signed_quantity_delta=D("1"), price=D("100"), leverage=D("10")
    )
    row = book.liquidate(
        event_id="gap-liquidation", at=T0, phase="open_mark_or_liquidation",
        observed_mark=D("80"), maintenance_rate=D("0.05"), liquidation_fee_rate=D("0.01")
    )
    assert book.state.terminal
    assert book.state.invalidation_reason == "observed_liquidation"
    assert book.state.liabilities == D("10.8")
    assert row["explicit_cost"] == D("0.8")
    assert book.nav() == D("979.2")
    with pytest.raises(UnifiedAccountingError, match="terminal"):
        book.apply_funding(
            event_id="later", at=T0, t_minus_quantity=D("1"), rate=D("0.01"), funding_mark=D("80")
        )


def test_marking_is_linear_mirrored_and_zero_position_is_invariant():
    flat = ledger()
    flat.mark_to_market(event_id="flat-mark", at=T0, spot_mark=D("120"), perpetual_mark=D("80"))
    assert flat.nav() == D("1000")
    long = ledger()
    short = ledger()
    long.apply_perpetual_fill(event_id="lo", at=T0, signed_quantity_delta=D("2"), price=D("100"), leverage=D("1"))
    short.apply_perpetual_fill(event_id="so", at=T0, signed_quantity_delta=D("-2"), price=D("100"), leverage=D("1"))
    long.mark_to_market(event_id="lm", at=T0, spot_mark=D("100"), perpetual_mark=D("110"))
    short.mark_to_market(event_id="sm", at=T0, spot_mark=D("100"), perpetual_mark=D("90"))
    assert long.nav() == short.nav() == D("1020")


def test_event_duplicates_phase_permutation_and_naive_time_fail_closed():
    book = ledger()
    book.mark_to_market(event_id="one", at=T0, spot_mark=D("100"), perpetual_mark=D("100"), phase="funding")
    with pytest.raises(UnifiedAccountingError, match="duplicated"):
        book.mark_to_market(event_id="one", at=T0, spot_mark=D("100"), perpetual_mark=D("100"), phase="funding")
    with pytest.raises(UnifiedAccountingError, match="permuted"):
        book.mark_to_market(event_id="two", at=T0, spot_mark=D("100"), perpetual_mark=D("100"), phase="open_mark_or_liquidation")
    with pytest.raises(UnifiedAccountingError, match="UTC"):
        ledger().mark_to_market(event_id="naive", at=datetime(2020, 1, 1), spot_mark=D("100"), perpetual_mark=D("100"))


def test_rules_round_down_and_candle_adapter_forbids_partial_or_forward_search():
    rules = InstrumentRules(D("0.01"), D("0.01"), D("1"))
    assert rules.rounded_quantity(D("1.019"), D("100")) == D("1.01")
    exact = T0 + timedelta(hours=1)
    validate_candle_all_or_none(
        decision_at=T0, fill_at=exact, exact_next_open=exact,
        requested_quantity=D("1"), reported_filled_quantity=D("1")
    )
    with pytest.raises(UnifiedAccountingError, match="partial"):
        validate_candle_all_or_none(
            decision_at=T0, fill_at=exact, exact_next_open=exact,
            requested_quantity=D("1"), reported_filled_quantity=D("0.5")
        )
    with pytest.raises(UnifiedAccountingError, match="exact next"):
        validate_candle_all_or_none(
            decision_at=T0, fill_at=exact + timedelta(hours=1), exact_next_open=exact,
            requested_quantity=D("1"), reported_filled_quantity=D("1")
        )


def test_notional_mismatch_and_event_rows_are_deterministic_checksums():
    assert notional_mismatch_fraction(D("1"), D("100"), D("-0.99"), D("100")) == D("0.01")
    first = ledger()
    second = ledger()
    for item in (first, second):
        item.apply_spot_fill(event_id="x", at=T0, signed_quantity=D("1"), price=D("100"))
    assert first.events == second.events
    assert len(first.events[0]["row_digest"]) == 64
    assert first.events[0]["actionable_arm_id"] == "no_trade"
    assert first.events[0]["event_accounting_residual"] == ZERO


def test_module_has_no_external_production_or_historical_imports():
    path = ROOT / "src/trading_platform/unified_btc_accounting.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    prohibited = {"ccxt", "freqtrade", "httpx", "nats", "psycopg", "requests"}
    assert not imports.intersection(prohibited)
    assert not any(name.startswith("trading_platform.") for name in imports)

