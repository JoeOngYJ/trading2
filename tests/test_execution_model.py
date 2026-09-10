import json
from decimal import Decimal
from pathlib import Path

import pytest

from trading_platform.execution_model import (
    BookLevel,
    BookObservation,
    BinanceCommissionRates,
    Commission,
    ExecutionScenario,
    Fill,
    MarketRules,
    OrderIntent,
    OrderKind,
    OrderStatus,
    PortfolioLedger,
    Side,
    SubmitDisposition,
    TradeEvent,
    load_scenarios,
    classify_submit_response,
    reconcile_unknown_result,
    resolve_long_exit_in_candle,
    simulate_book_taker,
    simulate_candle_taker,
    simulate_maker_hybrid,
    unknown_execution_result,
    write_execution_manifest,
)


D = Decimal
ROOT = Path(__file__).parents[1]


@pytest.fixture
def rules():
    return MarketRules(
        symbol="BTCUSDT", effective_at="2026-08-25T00:00:00Z",
        tick_size=D("0.01"), step_size=D("0.00001"),
        min_quantity=D("0.00001"), min_notional=D("0.1"),
    )


def scenario(mode="candle_taker", **changes):
    values = dict(
        scenario_id=f"test-{mode}", mode=mode,
        taker_fee_bps=D("10"), maker_fee_bps=D("5"),
        implicit_cost_bps_per_side=D("5"), residual_impact_bps=D("0"),
        latency_ms=250, price_protection_bps=D("10"), maker_timeout_ms=1_000,
        cancel_latency_ms=250, maker_taker_fallback=False,
    )
    values.update(changes)
    return ExecutionScenario(**values)


def intent(side=Side.BUY, quantity="0.1", price="100", **changes):
    values = dict(
        client_order_id="test-order", side=side, quantity=D(quantity),
        decision_time_ns=1_000_000_000, decision_price=D(price),
        kind=OrderKind.MARKETABLE_LIMIT,
    )
    values.update(changes)
    return OrderIntent(**values)


def book(timestamp=1_250_000_000, stale=False):
    return BookObservation(
        timestamp_ns=timestamp,
        bids=(BookLevel(D("99.99"), D("1")), BookLevel(D("99.98"), D("2"))),
        asks=(BookLevel(D("100.01"), D("0.01")), BookLevel(D("100.02"), D("0.02"))),
        stale=stale,
    )


def test_versioned_scenarios_are_valid_and_primary_is_30_bps_round_trip():
    scenarios = load_scenarios(ROOT / "config" / "execution_scenarios.json")
    primary = scenarios["candle-primary-30bps-rt-v1"]
    assert primary.taker_fee_bps == 10
    assert primary.implicit_cost_bps_per_side == 5
    assert primary.promotion_eligible is True
    assert len(primary.checksum) == 64
    assert scenarios["candle-fees-only-diagnostic-v1"].promotion_eligible is False


def test_candle_taker_charges_fee_and_adverse_implicit_cost(rules):
    result = simulate_candle_taker(
        intent(), D("100"), 1_000_000_001,
        scenario(latency_ms=0), rules,
    )
    assert result.status is OrderStatus.FILLED
    assert result.average_fill_price == D("100.05")
    assert result.costs.explicit_fees_quote == D("0.010005")
    assert result.costs.residual_impact_quote == D("0.005")
    assert result.costs.total_quote == D("0.015005")


def test_candle_entry_outside_protection_is_missed_but_protective_exit_is_not(rules):
    entry = simulate_candle_taker(intent(), D("101"), 1_000_000_001, scenario(latency_ms=0), rules)
    assert entry.status is OrderStatus.EXPIRED
    assert entry.reason == "price_protection"

    exit_intent = intent(
        side=Side.SELL, kind=OrderKind.PROTECTIVE, protective=True,
        decision_price=D("100"), limit_price=None,
    )
    protective = simulate_candle_taker(
        exit_intent, D("90"), 1_000_000_001, scenario(latency_ms=0), rules,
    )
    assert protective.status is OrderStatus.FILLED
    assert protective.average_fill_price == D("89.95")


def test_book_taker_walks_depth_and_reports_partial_fill(rules):
    book_scenario = scenario("book_taker", implicit_cost_bps_per_side=D("0"))
    filled = simulate_book_taker(intent(quantity="0.015"), book(), book_scenario, rules)
    assert filled.status is OrderStatus.FILLED
    assert filled.filled_quantity == D("0.015")
    assert filled.average_fill_price == D("100.0133333333333333333333333")
    assert filled.costs.spread_quote > 0
    assert filled.costs.depth_impact_quote > 0

    partial = simulate_book_taker(intent(quantity="0.05"), book(), book_scenario, rules)
    assert partial.status is OrderStatus.PARTIALLY_FILLED
    assert partial.filled_quantity == D("0.03")
    assert partial.unfilled_quantity == D("0.02")


def test_book_taker_rejects_future_requirement_and_stale_book(rules):
    book_scenario = scenario("book_taker")
    early = simulate_book_taker(intent(), book(timestamp=1_249_999_999), book_scenario, rules)
    assert early.reason == "book_before_arrival"
    stale = simulate_book_taker(intent(), book(stale=True), book_scenario, rules)
    assert stale.reason == "stale_book"
    wrong_segment = simulate_book_taker(
        intent(), book(), book_scenario, rules, expected_segment_id=2,
    )
    assert wrong_segment.reason == "segment_mismatch"


def test_maker_queue_partial_fill_and_cancel_race(rules):
    maker = scenario(
        "maker_hybrid", implicit_cost_bps_per_side=D("0"),
        maker_timeout_ms=1_000, cancel_latency_ms=250,
    )
    order = intent(quantity="0.005", limit_price=D("99.99"), kind=OrderKind.POST_ONLY)
    events = [
        TradeEvent(1_500_000_000, D("99.99"), D("1.002"), Side.SELL),
        TradeEvent(2_100_000_000, D("99.99"), D("0.003"), Side.SELL),
    ]
    result = simulate_maker_hybrid(
        order, book(timestamp=1_250_000_000), events, maker, rules,
        post_fill_midprice=D("99.90"),
    )
    assert result.status is OrderStatus.FILLED
    assert [fill.quantity for fill in result.fills] == [D("0.002"), D("0.003")]
    assert result.costs.explicit_fees_quote == D("0.000249975")
    assert result.costs.adverse_selection_quote == D("0.00045")


def test_maker_timeout_can_use_price_protected_taker_fallback(rules):
    maker = scenario(
        "maker_hybrid", implicit_cost_bps_per_side=D("0"), maker_taker_fallback=True,
        maker_timeout_ms=1_000, cancel_latency_ms=250,
    )
    order = intent(quantity="0.01", limit_price=D("99.99"), kind=OrderKind.POST_ONLY)
    fallback = book(timestamp=2_500_000_000)
    result = simulate_maker_hybrid(
        order, book(timestamp=1_250_000_000), [], maker, rules, fallback,
    )
    assert result.status is OrderStatus.FILLED
    assert result.fills[0].liquidity == "taker"
    assert "taker_fallback" in result.events


def test_unfilled_maker_reports_opportunity_cost(rules):
    maker = scenario("maker_hybrid", implicit_cost_bps_per_side=D("0"))
    order = intent(quantity="0.01", limit_price=D("99.99"), kind=OrderKind.POST_ONLY)
    result = simulate_maker_hybrid(
        order, book(timestamp=1_250_000_000), [], maker, rules,
        opportunity_price=D("110"),
    )
    assert result.status is OrderStatus.CANCELLED
    assert result.costs.opportunity_quote == D("0.1")


def test_post_only_order_that_crosses_is_rejected(rules):
    maker = scenario("maker_hybrid")
    crossing = intent(quantity="0.01", limit_price=D("100.01"), kind=OrderKind.POST_ONLY)
    result = simulate_maker_hybrid(crossing, book(timestamp=1_250_000_000), [], maker, rules)
    assert result.status is OrderStatus.REJECTED
    assert result.reason == "post_only_would_take"


def test_binance_rules_parser_enforces_rounding_and_min_notional():
    payload = {"symbols": [{"symbol": "BTCUSDT", "filters": [
        {"filterType": "PRICE_FILTER", "minPrice": "0.01", "maxPrice": "1000000", "tickSize": "0.01"},
        {"filterType": "LOT_SIZE", "minQty": "0.00001", "maxQty": "100", "stepSize": "0.00001"},
        {"filterType": "NOTIONAL", "minNotional": "10", "maxNotional": "1000000"},
        {"filterType": "PERCENT_PRICE_BY_SIDE", "bidMultiplierUp": "1.2", "bidMultiplierDown": "0.2", "askMultiplierUp": "5", "askMultiplierDown": "0.8"},
    ]}]}
    parsed = MarketRules.from_binance_exchange_info(payload, "BTCUSDT", "2026-08-25T00:00:00Z")
    assert parsed.round_quantity(D("0.123456")) == D("0.12345")
    assert parsed.round_price(D("100.009"), Side.BUY) == D("100.00")
    assert parsed.round_price(D("100.001"), Side.SELL) == D("100.01")
    assert parsed.validate(D("0.00001"), D("100"), D("100"), Side.BUY) == "min_notional"


def test_binance_commission_parser_keeps_special_tax_and_optional_discount():
    parsed = BinanceCommissionRates.from_binance_response({
        "standardCommission": {"maker": "0.001", "taker": "0.0012", "buyer": "0.0001", "seller": "0"},
        "specialCommission": {"maker": "0.0002", "taker": "0.0003", "buyer": "0", "seller": "0"},
        "taxCommission": {"maker": "0.00001", "taker": "0.00002", "buyer": "0", "seller": "0"},
        "discount": {"enabledForAccount": True, "enabledForSymbol": True, "discountAsset": "BNB", "discount": "0.25"},
    })
    assert parsed.effective_bps("taker", Side.BUY, use_discount=False) == D("16.2")
    assert parsed.effective_bps("taker", Side.BUY, use_discount=True) == D("12.95")
    assert parsed.discount_asset == "BNB"


def test_ledger_accounts_for_quote_base_and_third_asset_fees_atomically():
    ledger = PortfolioLedger(D("1000"))
    buy_quote_fee = Fill(1, Side.BUY, D("100"), D("1"), "taker", Commission(D("0.1"), "quote", D("0.1")))
    ledger.apply_fill(buy_quote_fee)
    assert ledger.quote_balance == D("899.9")
    assert ledger.base_balance == D("1")

    sell_base_fee = Fill(2, Side.SELL, D("110"), D("0.5"), "taker", Commission(D("0.001"), "base", D("0.11")))
    ledger.apply_fill(sell_base_fee)
    assert ledger.quote_balance == D("954.9")
    assert ledger.base_balance == D("0.499")

    ledger.other_balances["BNB"] = D("1")
    third_fee = Fill(3, Side.SELL, D("110"), D("0.1"), "taker", Commission(D("0.01"), "BNB", D("0.05")))
    ledger.apply_fill(third_fee)
    assert ledger.other_balances["BNB"] == D("0.99")

    before = (ledger.quote_balance, ledger.base_balance)
    too_large = Fill(4, Side.SELL, D("110"), D("10"), "taker", Commission(D("0"), "quote", D("0")))
    with pytest.raises(ValueError, match="insufficient base"):
        ledger.apply_fill(too_large)
    assert (ledger.quote_balance, ledger.base_balance) == before


def test_unknown_transport_result_requires_reconciliation(rules):
    order = intent(quantity="0.01")
    unknown = unknown_execution_result(order, scenario(latency_ms=0), rules)
    assert unknown.status is OrderStatus.UNKNOWN
    with pytest.raises(ValueError):
        reconcile_unknown_result(unknown, OrderStatus.FILLED, ())

    fee = Commission(D("0.001"), "quote", D("0.001"))
    fill = Fill(2, Side.BUY, D("100"), D("0.01"), "taker", fee)
    reconciled = reconcile_unknown_result(unknown, OrderStatus.FILLED, (fill,))
    assert reconciled.status is OrderStatus.RECONCILED
    assert reconciled.reason == "reconciled_filled"


def test_submit_failures_are_fail_closed_without_blind_retry():
    assert classify_submit_response(503).status is OrderStatus.UNKNOWN
    assert classify_submit_response(503).action == "reconcile_by_client_order_id"
    assert classify_submit_response(None, transport_timeout=True).status is OrderStatus.UNKNOWN
    assert classify_submit_response(429).action == "disable_entries_and_backoff"
    assert classify_submit_response(400, -1021).action == "resync_clock_before_new_entry"
    assert classify_submit_response(400, -1013).action == "do_not_retry_without_correction"
    assert classify_submit_response(200).status is OrderStatus.ACKNOWLEDGED


def test_long_stop_gap_and_same_candle_ambiguity_are_conservative():
    assert resolve_long_exit_in_candle(D("90"), D("95"), D("85"), D("95"), D("110")) == ("stop_gap", D("90"))
    assert resolve_long_exit_in_candle(D("100"), D("115"), D("90"), D("95"), D("110")) == ("stop", D("95"))
    assert resolve_long_exit_in_candle(D("100"), D("115"), D("99"), D("95"), D("110")) == ("target", D("110"))
    assert resolve_long_exit_in_candle(D("100"), D("105"), D("99"), D("95"), D("110")) is None


def test_manifest_is_deterministic_and_checksummed(tmp_path, rules):
    execution_scenario = scenario(latency_ms=0)
    result = simulate_candle_taker(intent(), D("100"), 1_000_000_001, execution_scenario, rules)
    first = write_execution_manifest(tmp_path / "first.json", execution_scenario, rules, "a" * 64, [result])
    second = write_execution_manifest(tmp_path / "second.json", execution_scenario, rules, "a" * 64, [result])
    assert first == second
    assert (tmp_path / "first.json").read_bytes() == (tmp_path / "second.json").read_bytes()
    assert len(first["results_sha256"]) == 64
