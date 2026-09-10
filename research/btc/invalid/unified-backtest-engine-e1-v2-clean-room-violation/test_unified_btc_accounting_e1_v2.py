from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from trading_platform.unified_btc_accounting_v2 import (
    AccountingV2Error,
    LedgerV2,
    LineageV2,
    RulesV2,
    RunPolicyV2,
    canonical_digest,
    decimal_text,
    notional_mismatch_v2,
    preflight_atomic_pair_v2,
    validate_candle_fill_v2,
)


D = Decimal
ZERO = D("0")
ROOT = Path(__file__).resolve().parents[1]
T0 = datetime(2025, 1, 1, tzinfo=timezone.utc)


def lineage() -> LineageV2:
    return LineageV2(
        experiment_id="synthetic-E1-v2",
        run_id="fixture",
        scenario_id="candle-primary-30bps-rt-v1",
        implementation_digest="a" * 64,
        contract_digest="b" * 64,
        execution_config_digest="c" * 64,
        mandate_digest="d" * 64,
    )


def policy(*, terminal: datetime | None = None, rate: str = "0.01") -> RunPolicyV2:
    return RunPolicyV2(
        leverage=D("2"),
        perpetual_exit_cost_rate=D(rate),
        terminal_execution_at=terminal or T0 + timedelta(days=1),
        zero_exit_reserve_fixture=rate == "0",
    )


def rules(step: str = "0.01") -> RulesV2:
    return RulesV2(D("0.01"), D(step), D(step), D("1"))


def ledger(**kwargs) -> LedgerV2:
    return LedgerV2(
        quote_cash=D("1000"),
        spot_mark=D("100"),
        perpetual_mark=D("100"),
        policy=kwargs.pop("policy", policy()),
        lineage=lineage(),
        **kwargs,
    )


def test_canonical_decimal_digest_and_no_float():
    assert decimal_text(D("-0.000")) == "0"
    assert decimal_text(D("10.500")) == "10.5"
    assert decimal_text(D("1E+3")) == "1000"
    assert canonical_digest({"x": D("1.0")}) == canonical_digest({"x": D("1")})
    with pytest.raises(AccountingV2Error, match="finite Decimal"):
        decimal_text(1.0)  # type: ignore[arg-type]


def test_zero_exit_reserve_requires_explicit_fixture_flag():
    with pytest.raises(AccountingV2Error, match="explicit synthetic"):
        RunPolicyV2(D("1"), ZERO, T0)
    accepted = RunPolicyV2(D("1"), ZERO, T0, zero_exit_reserve_fixture=True)
    assert accepted.perpetual_exit_cost_rate == ZERO


def test_spot_unchanged_price_round_trip_loses_quote_costs_exactly():
    book = ledger()
    book.spot_fill(
        event_id="buy", at=T0, requested_quantity=D("1"), price=D("100"), rules=rules(),
        fee_amount=D("0.10"), fee_asset="USDT", implicit_cost=D("0.20")
    )
    book.spot_fill(
        event_id="sell", at=T0, requested_quantity=D("-1"), price=D("100"), rules=rules(),
        fee_amount=D("0.10"), fee_asset="USDT", implicit_cost=D("0.20")
    )
    assert book.nav() == D("999.60")
    assert book.state.explicit_cost_memo == D("0.20")
    assert book.state.implicit_cost_memo == D("0.40")
    assert all(row["event_accounting_residual"] == ZERO for row in book.events)


def test_base_and_third_asset_fees_mutate_balances_and_nav_once():
    base = ledger()
    base.spot_fill(
        event_id="base-buy", at=T0, requested_quantity=D("1"), price=D("100"), rules=rules(),
        fee_amount=D("0.01"), fee_asset="BTC"
    )
    assert base.state.spot_btc == D("0.99")
    assert base.nav() == D("999")

    third = ledger(third_asset_balances={"BNB": D("1")}, third_asset_marks={"BNB": D("10")})
    initial = third.nav()
    third.spot_fill(
        event_id="third-buy", at=T0, requested_quantity=D("1"), price=D("100"), rules=rules(),
        fee_amount=D("0.01"), fee_asset="BNB"
    )
    assert third.state.third_asset_balances["BNB"] == D("0.99")
    assert third.nav() == initial - D("0.1")
    with pytest.raises(AccountingV2Error, match="unsupported fee"):
        ledger().spot_fill(
            event_id="unsupported", at=T0, requested_quantity=D("1"), price=D("100"),
            rules=rules(), fee_amount=D("1"), fee_asset="XYZ"
        )


def test_initial_margin_is_additive_by_fill_not_whole_position_repriced():
    book = ledger()
    book.perpetual_fill(
        event_id="first", at=T0, requested_quantity_delta=D("1"), price=D("100"), rules=rules()
    )
    book.perpetual_fill(
        event_id="second", at=T0, requested_quantity_delta=D("1"), price=D("120"), rules=rules()
    )
    assert book.state.allocated_initial_margin_memo == D("110")
    assert book.state.isolated_collateral == D("110")
    assert book.state.average_perpetual_entry == D("110")


def test_partial_release_uses_pre_reduction_denominator_and_caps_cash_release():
    book = ledger()
    book.perpetual_fill(
        event_id="open", at=T0, requested_quantity_delta=D("2"), price=D("100"), rules=rules()
    )
    book.state.isolated_collateral = D("20")  # synthetic prior loss; memo remains 100
    before_cash = book.state.quote_cash
    book.perpetual_fill(
        event_id="reduce", at=T0, requested_quantity_delta=D("-0.5"), price=D("100"), rules=rules()
    )
    assert book.state.allocated_initial_margin_memo == D("75")
    assert book.state.quote_cash == before_cash + D("20")
    assert book.state.isolated_collateral == ZERO


@pytest.mark.parametrize(
    ("open_delta", "close_delta", "exit_price"),
    [(D("1"), D("-1"), D("110")), (D("-1"), D("1"), D("90"))],
)
def test_linear_long_and_short_realize_mirrored_profit(open_delta, close_delta, exit_price):
    book = ledger()
    book.perpetual_fill(
        event_id="open", at=T0, requested_quantity_delta=open_delta, price=D("100"), rules=rules()
    )
    book.mark(
        event_id="mark", at=T0 + timedelta(hours=1), spot_mark=D("100"),
        perpetual_mark=exit_price, phase="open_mark_or_liquidation"
    )
    book.perpetual_fill(
        event_id="close", at=T0 + timedelta(hours=1), requested_quantity_delta=close_delta,
        price=exit_price, rules=rules(), phase="protective_exit"
    )
    assert book.state.realized_pnl_memo == D("10")
    assert book.nav() == D("1010")


def test_reversal_requires_two_fills_and_terminal_allows_only_reduction():
    terminal = T0 + timedelta(hours=1)
    book = ledger(policy=policy(terminal=terminal))
    book.perpetual_fill(
        event_id="open", at=T0, requested_quantity_delta=D("1"), price=D("100"), rules=rules()
    )
    with pytest.raises(AccountingV2Error, match="explicit close"):
        book.perpetual_fill(
            event_id="reverse", at=T0, requested_quantity_delta=D("-2"), price=D("100"), rules=rules()
        )
    book.perpetual_fill(
        event_id="terminal-close", at=terminal, requested_quantity_delta=D("-1"), price=D("100"),
        rules=rules(), phase="protective_exit"
    )
    with pytest.raises(AccountingV2Error, match="cannot increase"):
        book.spot_fill(
            event_id="terminal-entry", at=terminal, requested_quantity=D("1"), price=D("100"), rules=rules()
        )


@pytest.mark.parametrize(
    ("quantity", "rate", "cashflow"),
    [(D("1"), D("0.01"), D("-1")), (D("-1"), D("0.01"), D("1")),
     (D("1"), D("-0.01"), D("1")), (D("-1"), D("-0.01"), D("-1"))],
)
def test_funding_signs_are_exact(quantity, rate, cashflow):
    book = ledger()
    book.perpetual_fill(
        event_id="open", at=T0, requested_quantity_delta=quantity, price=D("100"), rules=rules()
    )
    before = book.nav()
    book.funding(
        event_id="fund", at=T0 + timedelta(hours=1), t_minus_quantity=quantity, rate=rate, mark=D("100")
    )
    assert book.state.funding_memo == cashflow
    assert book.nav() == before + cashflow


def test_same_timestamp_funding_membership_for_entry_and_exit():
    entry = ledger()
    entry.funding(event_id="no-membership", at=T0, t_minus_quantity=ZERO, rate=D("0.01"), mark=D("100"))
    entry.perpetual_fill(
        event_id="new-entry", at=T0, requested_quantity_delta=D("1"), price=D("100"), rules=rules()
    )
    assert entry.state.funding_memo == ZERO

    exited = ledger()
    exited.perpetual_fill(
        event_id="old-entry", at=T0 - timedelta(hours=1), requested_quantity_delta=D("1"),
        price=D("100"), rules=rules()
    )
    exited.perpetual_fill(
        event_id="exit", at=T0, requested_quantity_delta=D("-1"), price=D("100"),
        rules=rules(), phase="protective_exit"
    )
    exited.funding(event_id="owed", at=T0, t_minus_quantity=D("1"), rate=D("0.01"), mark=D("100"))
    assert exited.state.quote_cash == D("999")
    assert exited.state.isolated_collateral == ZERO


def test_exit_reserve_formula_refreshes_on_fill_mark_and_funding():
    book = ledger()
    book.perpetual_fill(
        event_id="open", at=T0, requested_quantity_delta=D("2"), price=D("100"), rules=rules()
    )
    assert book.state.exit_cost_reserve_memo == D("2")
    book.mark(
        event_id="mark", at=T0 + timedelta(hours=1), spot_mark=D("100"),
        perpetual_mark=D("120"), phase="open_mark_or_liquidation"
    )
    assert book.state.exit_cost_reserve_memo == D("2.4")
    book.funding(
        event_id="fund", at=T0 + timedelta(hours=1), t_minus_quantity=D("2"), rate=ZERO, mark=D("120")
    )
    assert book.state.exit_cost_reserve_memo == D("2.4")


def test_adverse_mark_is_low_for_long_high_for_short_and_none_flat():
    flat = ledger()
    assert flat.adverse_perpetual_mark(interval_low=D("80"), interval_high=D("120")) is None
    long = ledger()
    long.perpetual_fill(event_id="long", at=T0, requested_quantity_delta=D("1"), price=D("100"), rules=rules())
    assert long.adverse_perpetual_mark(interval_low=D("80"), interval_high=D("120")) == D("80")
    short = ledger()
    short.perpetual_fill(event_id="short", at=T0, requested_quantity_delta=D("-1"), price=D("100"), rules=rules())
    assert short.adverse_perpetual_mark(interval_low=D("80"), interval_high=D("120")) == D("120")


def test_funding_can_cause_margin_breach():
    book = ledger(policy=RunPolicyV2(D("10"), D("0.01"), T0 + timedelta(days=1)))
    book.perpetual_fill(event_id="open", at=T0, requested_quantity_delta=D("1"), price=D("100"), rules=rules())
    book.funding(event_id="fund", at=T0 + timedelta(hours=1), t_minus_quantity=D("1"), rate=D("0.05"), mark=D("100"))
    assert book.margin(mark=D("100"), maintenance_rate=D("0.05")).liquidated


def test_liquidation_charges_only_special_fee_retains_deficit_and_is_terminal():
    book = ledger(policy=RunPolicyV2(D("10"), D("0.01"), T0 + timedelta(days=1)))
    book.perpetual_fill(
        event_id="open", at=T0, requested_quantity_delta=D("1"), price=D("100"), rules=rules()
    )
    row = book.liquidate(
        event_id="liquidate", at=T0 + timedelta(hours=1), observed_adverse_mark=D("80"),
        maintenance_rate=D("0.05"), liquidation_fee_rate=D("0.01"),
        phase="open_mark_or_liquidation"
    )
    assert row["details"]["ordinary_close_cost"] == ZERO
    assert row["explicit_cost"] == D("0.8")
    assert book.state.liabilities == D("10.8")
    assert book.nav() == D("979.2")
    assert book.state.terminal and book.state.invalidation_reason == "observed_liquidation"
    with pytest.raises(AccountingV2Error, match="terminal"):
        book.funding(event_id="later", at=T0 + timedelta(hours=1), t_minus_quantity=D("1"), rate=D("0.01"), mark=D("80"))


def test_rule_quantization_is_once_and_cash_is_not_rounded_to_quote_quantum():
    book = ledger()
    row = book.spot_fill(
        event_id="precise", at=T0, requested_quantity=D("1.019"), price=D("100"), rules=rules(),
        implicit_cost=D("0.000000001")
    )
    assert row["details"]["filled_quantity"] == D("1.01")
    assert book.state.quote_cash == D("898.999999999")
    assert row["event_accounting_residual"] == ZERO


def test_duplicate_permuted_and_naive_events_reject():
    book = ledger()
    book.mark(event_id="one", at=T0, spot_mark=D("100"), perpetual_mark=D("100"), phase="funding")
    with pytest.raises(AccountingV2Error, match="duplicated"):
        book.mark(event_id="one", at=T0, spot_mark=D("100"), perpetual_mark=D("100"), phase="funding")
    with pytest.raises(AccountingV2Error, match="permuted"):
        book.mark(event_id="two", at=T0, spot_mark=D("100"), perpetual_mark=D("100"), phase="open_mark_or_liquidation")
    with pytest.raises(AccountingV2Error, match="UTC"):
        ledger().mark(event_id="naive", at=datetime(2025, 1, 1), spot_mark=D("100"), perpetual_mark=D("100"), phase="reconcile")


def test_candle_adapter_is_exact_next_open_and_all_or_none():
    next_open = T0 + timedelta(hours=1)
    validate_candle_fill_v2(
        decision_at=T0, fill_at=next_open, exact_next_open=next_open,
        requested_quantity=D("1"), reported_filled_quantity=D("1")
    )
    with pytest.raises(AccountingV2Error, match="all-or-none"):
        validate_candle_fill_v2(
            decision_at=T0, fill_at=next_open, exact_next_open=next_open,
            requested_quantity=D("1"), reported_filled_quantity=D("0.5")
        )
    with pytest.raises(AccountingV2Error, match="exact next"):
        validate_candle_fill_v2(
            decision_at=T0, fill_at=next_open + timedelta(hours=1), exact_next_open=next_open,
            requested_quantity=D("1"), reported_filled_quantity=D("1")
        )


def test_atomic_pair_uses_actual_post_base_fee_inventory_and_preflights_exact_exit():
    spot_rules = rules("0.1")
    perp_rules = rules("0.1")
    result = preflight_atomic_pair_v2(
        requested_gross_spot_btc=D("1"), spot_price=D("100"), perpetual_price=D("100"),
        spot_rules=spot_rules, perpetual_rules=perp_rules,
        spot_entry_base_fee_rate=D("0.1"), severe_spot_exit_base_fee_rate=D("0.125")
    )
    assert result.net_spot_btc == D("0.9")
    assert result.perpetual_entry_btc == D("-0.9")
    assert result.neutralization_gross_spot_sale == D("0.8")
    assert result.neutralization_gross_spot_sale + result.neutralization_base_fee == result.net_spot_btc
    assert notional_mismatch_v2(
        spot_btc=result.net_spot_btc, spot_price=D("100"),
        perpetual_btc=result.perpetual_entry_btc, perpetual_price=D("100")
    ) == ZERO


def test_atomic_pair_rejects_before_mutation_when_fee_and_step_cannot_flatten():
    with pytest.raises(AccountingV2Error, match="exactly zero"):
        preflight_atomic_pair_v2(
            requested_gross_spot_btc=D("1"), spot_price=D("100"), perpetual_price=D("100"),
            spot_rules=rules("0.01"), perpetual_rules=rules("0.01"),
            spot_entry_base_fee_rate=D("0.001"), severe_spot_exit_base_fee_rate=D("0.001")
        )


def test_rows_are_deterministic_checksummed_and_no_trade():
    first = ledger()
    second = ledger()
    for book in (first, second):
        book.spot_fill(event_id="buy", at=T0, requested_quantity=D("1"), price=D("100"), rules=rules())
    assert first.events == second.events
    assert first.events[0]["event_sequence"] == 1
    assert len(first.events[0]["row_digest"]) == 64
    assert first.events[0]["actionable_arm_id"] == "no_trade"
    assert first.actionable_arm_id == "no_trade"


def test_module_has_only_standard_library_imports_and_no_archive_reference():
    path = ROOT / "src/trading_platform/unified_btc_accounting_v2.py"
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    assert not any(name.startswith("trading_platform") for name in imports)
    assert not {"ccxt", "freqtrade", "httpx", "nats", "psycopg", "requests"}.intersection(imports)
    assert "invalid/unified-backtest-engine-e1-v1" not in text

