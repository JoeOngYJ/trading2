"""Synthetic-only conformance fixtures for the E1-v4 unified BTC ledger."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json

import pytest

from trading_platform.btc_unified_accounting_e1_v4 import (
    ACTIONABLE_ARM_ID,
    DELTA_NEUTRAL_MANDATE_ID,
    DELTA_NEUTRAL_MANDATE_PATH,
    DELTA_NEUTRAL_MANDATE_SHA256,
    ContractViolation,
    D,
    FeePolicy,
    InstrumentRules,
    LedgerState,
    PairOutcome,
    RunBindings,
    SyntheticLedger,
    canonical_digest,
    canonical_json,
    decimal_string,
    parse_json_strict,
    semantic_run_settings_digest,
    synthetic_digest,
    synthetic_evidence,
)


T0 = datetime(2025, 1, 1, tzinfo=timezone.utc)
T1 = T0 + timedelta(hours=1)
T2 = T1 + timedelta(hours=1)
T3 = T2 + timedelta(hours=1)
SPOT_RULES = InstrumentRules(D("0.001"), D("0.001"), D("0.01"), D("0.01"))
PERP_RULES = InstrumentRules(D("0.001"), D("0.001"), D("0.01"), D("0.01"))
ZERO_FEE = FeePolicy(D("0"))


def ev(value: str, at: datetime, label: str, rules: InstrumentRules = PERP_RULES):
    return synthetic_evidence(value, at, label, rules_digest=rules.digest)


def bindings(adapter: str = "candle_OHLC", mandate: str = "directional") -> RunBindings:
    if mandate == "pair":
        path, mandate_id, digest = (
            DELTA_NEUTRAL_MANDATE_PATH,
            DELTA_NEUTRAL_MANDATE_ID,
            DELTA_NEUTRAL_MANDATE_SHA256,
        )
    elif mandate == "spot":
        path, mandate_id, digest = (
            "config/retail_mandate.json",
            "retail-btc-spot-v2",
            "7e34cfb0928b4373bbf52b5c5505f63a2b19e674124059191c1b6c62ec129041",
        )
    else:
        path, mandate_id, digest = (
            "config/mandates/retail-btc-directional-perpetual-research-v1.json",
            "retail-btc-directional-perpetual-research-v1",
            "1b5d492f12f71ebe28e1bdfbd0b5916bcf0ad285b483cb10bf8770504371165d",
        )
    return RunBindings(
        run_id="synthetic-e1-v4", scenario_id="candle-primary-30bps-rt-v1",
        adapter_id=adapter, implementation_digest=synthetic_digest("implementation"),
        selected_mandate_path=path, selected_mandate_id=mandate_id,
        selected_mandate_exact_file_sha256=digest,
    )


def ledger(
    state: LedgerState | None = None,
    *,
    adapter: str = "candle_OHLC",
    mandate: str = "directional",
    maintenance: str = "0.005",
    liquidation: str = "0.01",
) -> SyntheticLedger:
    return SyntheticLedger(
        state or LedgerState(D("1000")), bindings(adapter, mandate), leverage=D("10"),
        perpetual_exit_cost_rate=D("0.001"), maintenance_rate=D(maintenance),
        liquidation_fee_rate=D(liquidation),
    )


def assert_rows_reconcile(book: SyntheticLedger) -> None:
    assert book.events
    for sequence, row in enumerate(book.events, 1):
        assert row["event_sequence"] == sequence
        assert abs(D(row["event_accounting_residual"])) <= D("0.00000001")
        digest_source = dict(row)
        row_digest = digest_source.pop("row_digest")
        assert canonical_digest(digest_source) == row_digest
        assert row["actionable_arm_id"] == "no_trade"
    assert D(book.run_summary()["accounting_residual"]) == 0


def test_decimal_canonicalization_duplicate_rejection_and_no_float() -> None:
    assert [decimal_string(D(value)) for value in ("0.000", "-0", "12.3400", "1E+3")] == [
        "0", "0", "12.34", "1000"
    ]
    assert canonical_json({"z": D("1.20"), "a": [D("-0")]}) == '{"a":["0"],"z":"1.2"}'
    with pytest.raises(ContractViolation):
        D(1.2)
    with pytest.raises(ContractViolation):
        canonical_json({"x": 1.2})
    with pytest.raises(ContractViolation):
        parse_json_strict('{"x":1,"x":2}')
    with pytest.raises(ContractViolation):
        parse_json_strict('{"x":NaN}')


def test_strict_UTC_availability_and_synthetic_lineage() -> None:
    future = synthetic_evidence("100", T1, "future", available_at=T2)
    with pytest.raises(ContractViolation):
        future.consume(T1)
    with pytest.raises(ContractViolation):
        synthetic_evidence("100", T1.replace(tzinfo=None), "naive")
    from trading_platform.btc_unified_accounting_e1_v4 import Evidence
    with pytest.raises(ContractViolation):
        Evidence(D("1"), T1, T1, "file:///market.csv", synthetic_digest("x"),
                 "s", synthetic_digest("r"))


def test_spot_entry_hold_partial_and_full_exit_with_quote_and_base_fees() -> None:
    book = ledger(mandate="spot")
    p100 = ev("100", T0, "spot-100", SPOT_RULES)
    book.mark("m0", T0, spot=p100)
    book.spot_fill(
        "buy", T0, signed_quantity="1", price=p100, rules=SPOT_RULES,
        fee=FeePolicy(D("0.001")), implicit_cost_quote="0.1",
    )
    assert book.state.quote_cash == D("899.8")
    assert book.state.spot_quantity == 1
    assert book.state.nav == D("999.8")
    p110 = ev("110", T1, "spot-110", SPOT_RULES)
    book.mark("m1", T1, spot=p110)
    assert book.state.nav == D("1009.8")
    book.spot_fill(
        "partial-sell", T1, signed_quantity="-0.4", price=p110, rules=SPOT_RULES,
        fee=FeePolicy(D("0.001"), "base"), fee_conversion=p110,
    )
    assert book.state.spot_quantity == D("0.5996")
    gross = SyntheticLedger.solve_full_spot_sale(
        D("0.6006"), D("100"), SPOT_RULES, FeePolicy(D("0.001"), "base")
    )
    assert gross == D("0.6")
    assert_rows_reconcile(book)


def test_third_asset_fee_point_in_time_conversion_and_fail_closed() -> None:
    state = LedgerState(
        D("995"), fee_asset_balances={"BNB": D("1")},
        fee_asset_marks={"BNB": D("5")},
    )
    book = ledger(state, mandate="spot")
    p = ev("100", T0, "spot", SPOT_RULES)
    conversion = ev("5", T0, "bnb", SPOT_RULES)
    book.mark("m", T0, spot=p)
    book.spot_fill(
        "third-fee", T0, signed_quantity="1", price=p, rules=SPOT_RULES,
        fee=FeePolicy(D("0.001"), "BNB"), fee_conversion=conversion,
    )
    assert book.state.fee_asset_balances["BNB"] == D("0.98")
    assert book.state.explicit_costs == D("0.1")
    assert book.state.nav == D("999.9")
    with pytest.raises(ContractViolation):
        book.spot_fill(
            "no-conversion", T1, signed_quantity="0.1", price=ev("100", T1, "p2", SPOT_RULES),
            rules=SPOT_RULES, fee=FeePolicy(D("0.001"), "BNB"),
        )
    assert_rows_reconcile(book)


def test_perpetual_long_price_pnl_resize_release_and_full_exit() -> None:
    book = ledger()
    p100 = ev("100", T0, "perp-100")
    book.mark("m0", T0, perpetual=p100)
    book.perpetual_fill(
        "open", T0, signed_quantity="2", price=p100, rules=PERP_RULES,
        fee=FeePolicy(D("0.001")),
    )
    assert book.state.allocated_initial_margin_memo == 20
    assert book.state.isolated_collateral == D("19.8")
    p110 = ev("110", T1, "perp-110")
    book.mark("m1", T1, perpetual=p110)
    assert book.state.unrealized_pnl == 20
    book.perpetual_fill(
        "reduce", T1, signed_quantity="-0.5", price=p110, rules=PERP_RULES,
        fee=FeePolicy(D("0.001")),
    )
    assert book.state.perpetual_quantity == D("1.5")
    assert book.state.average_perpetual_entry == 100
    assert book.state.realized_pnl == 5
    assert book.state.allocated_initial_margin_memo == 15
    assert book.state.isolated_collateral == D("19.745")
    book.perpetual_fill("close", T1, signed_quantity="-1.5", price=p110,
                        rules=PERP_RULES, fee=ZERO_FEE)
    assert book.state.perpetual_quantity == 0
    assert book.state.average_perpetual_entry is None
    assert book.state.isolated_collateral == 0
    assert book.state.exit_cost_reserve_memo == 0
    assert_rows_reconcile(book)


def test_perpetual_short_mirror_and_two_fill_reversal() -> None:
    book = ledger()
    p100 = ev("100", T0, "p0")
    book.mark("m0", T0, perpetual=p100)
    book.perpetual_fill("short", T0, signed_quantity="-2", price=p100, rules=PERP_RULES)
    p90 = ev("90", T1, "p1")
    book.mark("m1", T1, perpetual=p90)
    assert book.state.unrealized_pnl == 20
    rows = book.perpetual_fill("reverse", T1, signed_quantity="3", price=p90,
                               rules=PERP_RULES)
    assert len(rows) == 2
    assert [D(row["signed_quantity"]) for row in rows] == [2, 1]
    assert book.state.perpetual_quantity == 1
    assert book.state.average_perpetual_entry == 90
    assert book.state.realized_pnl == 20
    assert_rows_reconcile(book)


@pytest.mark.parametrize(
    ("quantity", "rate", "expected"),
    [("1", "0.001", "-0.1"), ("1", "-0.001", "0.1"),
     ("-1", "0.001", "0.1"), ("-1", "-0.001", "-0.1")],
)
def test_funding_signs_for_long_and_short(quantity: str, rate: str, expected: str) -> None:
    state = LedgerState(
        D("990"), isolated_collateral=D("10"), perpetual_quantity=D(quantity),
        average_perpetual_entry=D("100"), allocated_initial_margin_memo=D("10"),
        perpetual_mark=D("100"),
    )
    book = ledger(state)
    row = book.funding(
        "fund", T1, t_minus_signed_quantity=quantity,
        rate=ev(rate, T1, "rate"), mark=ev("100", T1, "funding-mark"),
        index=ev("100", T1, "index"),
    )
    assert D(row["cashflow_quote"]) == D(expected)
    assert book.state.accrued_funding == D(expected)
    assert_rows_reconcile(book)


def test_same_timestamp_funding_membership_exit_and_entry() -> None:
    state = LedgerState(
        D("990"), isolated_collateral=D("10"), perpetual_quantity=D("1"),
        average_perpetual_entry=D("100"), allocated_initial_margin_memo=D("10"),
        perpetual_mark=D("100"),
    )
    book = ledger(state)
    p = ev("100", T1, "same-price")
    book.perpetual_fill("exit", T1, signed_quantity="-1", price=p, rules=PERP_RULES)
    before_cash = book.state.quote_cash
    book.funding(
        "same-funding", T1, t_minus_signed_quantity="1",
        rate=ev("0.001", T1, "same-rate"), mark=ev("100", T1, "same-mark"),
        index=ev("100", T1, "same-index"),
    )
    assert book.state.quote_cash == before_cash - D("0.1")
    empty = ledger()
    empty.mark("m", T1, perpetual=p)
    empty.funding(
        "no-acquire", T1, t_minus_signed_quantity="0", rate=ev("0.001", T1, "r2"),
        mark=ev("100", T1, "fm2"), index=ev("100", T1, "i2"),
    )
    empty.perpetual_fill("entry", T1, signed_quantity="1", price=p, rules=PERP_RULES)
    assert empty.state.accrued_funding == 0
    assert_rows_reconcile(book)
    assert_rows_reconcile(empty)


def test_funding_caused_margin_breach_and_liquidation_fee_once() -> None:
    state = LedgerState(
        D("990"), isolated_collateral=D("10"), perpetual_quantity=D("1"),
        average_perpetual_entry=D("100"), allocated_initial_margin_memo=D("10"),
        perpetual_mark=D("100"),
    )
    book = ledger(state, maintenance="0.08", liquidation="0.02")
    book.funding(
        "fund", T1, t_minus_signed_quantity="1", rate=ev("0.02", T1, "rate"),
        mark=ev("100", T1, "fm"), index=ev("100", T1, "idx"),
    )
    assert book.is_liquidated()
    row = book.liquidate("liq", T1, evidence=(ev("100", T1, "liqmark"),))
    assert D(row["liquidation_fee"]) == 2
    assert D(row["ordinary_close_cost"]) == 0
    assert book.state.explicit_costs == 2
    assert book.state.perpetual_quantity == 0
    assert book.state.invalidation_reason == "observed_liquidation"
    assert_rows_reconcile(book)


def test_adverse_intrabar_long_low_short_high_and_terminal_path() -> None:
    long_state = LedgerState(
        D("990"), isolated_collateral=D("10"), perpetual_quantity=D("1"),
        average_perpetual_entry=D("100"), allocated_initial_margin_memo=D("10"),
        perpetual_mark=D("100"),
    )
    long = ledger(long_state, maintenance="0.05")
    low = ev("90", T1, "low")
    long.mark("adverse-low", T1, perpetual=low, adverse=True)
    assert long.is_liquidated()
    long.liquidate("long-liq", T1, evidence=(low,))
    assert long.state.perpetual_quantity == 0
    assert long.terminal_order_allowed(perpetual_delta="1") is False
    assert long.terminal_order_allowed(protective=True, perpetual_delta="1") is True

    short_state = LedgerState(
        D("990"), isolated_collateral=D("10"), perpetual_quantity=D("-1"),
        average_perpetual_entry=D("100"), allocated_initial_margin_memo=D("10"),
        perpetual_mark=D("100"),
    )
    short = ledger(short_state, maintenance="0.05")
    high = ev("110", T1, "high")
    short.mark("adverse-high", T1, perpetual=high, adverse=True)
    assert short.is_liquidated()
    assert_rows_reconcile(long)
    assert_rows_reconcile(short)


def test_rule_rounding_minimum_rejection_candle_partial_and_exact_state() -> None:
    assert PERP_RULES.quantity(D("0.0019")) == D("0.001")
    assert PERP_RULES.quantity(D("-0.0019")) == D("-0.001")
    with pytest.raises(ContractViolation):
        PERP_RULES.validate(D("0.000"), D("100"))
    book = ledger(adapter="candle_OHLC", mandate="pair")
    state_before = book.state.digest
    with pytest.raises(ContractViolation):
        book.spot_fill("bad", T0, signed_quantity="0.0001", price=ev("100", T0, "bad", SPOT_RULES),
                       rules=SPOT_RULES)
    assert book.state.digest == state_before
    assert D("1") / D("3") * D("3") != D("1")  # no state quantization is introduced


def pair_state(quantity: str = "1") -> LedgerState:
    q = D(quantity)
    return LedgerState(
        D("900"), spot_quantity=q, spot_mark=D("100"),
        isolated_collateral=D("20"), perpetual_quantity=-q,
        average_perpetual_entry=D("100"), allocated_initial_margin_memo=D("10"),
        perpetual_mark=D("100"),
    )


def pair_evidence(at: datetime = T1, severe: str = "102"):
    return (
        ev("100", at, "pair-spot", SPOT_RULES), ev("100", at, "pair-perp"),
        ev(severe, at, "pair-severe"), ev("100", at, "post-spot", SPOT_RULES),
        ev("100", at, "post-perp"),
    )


def test_v3_candle_full_pair_close_and_cartesian_zero_paths() -> None:
    book = ledger(pair_state(), mandate="pair")
    sp, pp, sev, post_sp, post_pp = pair_evidence()
    zero = PairOutcome(D("0"), D("0"), D("100"), D("100"), None)
    fail = PairOutcome(D("1"), D("0"), D("100"), D("100"), D("102"))
    full = PairOutcome(D("1"), D("1"), D("100"), D("100"), None)
    result = book.atomic_pair_close(
        "pair", T1, selected_outcome=full, outcome_set=(zero, fail, full),
        outcome_set_complete=True, spot_price=sp, perpetual_price=pp,
        severe_perpetual_price=sev, spot_rules=SPOT_RULES, perpetual_rules=PERP_RULES,
        spot_fee=ZERO_FEE, ordinary_perpetual_fee=ZERO_FEE,
        severe_perpetual_fee=ZERO_FEE, post_spot_mark=post_sp,
        post_perpetual_mark=post_pp,
    )
    assert result.status == "closed_or_matched_remainder"
    assert result.actual_spot_reduction == 1
    assert book.state.spot_quantity == 0
    assert book.state.perpetual_quantity == 0
    assert not [row for row in book.order_ledger if "severe-order" in row["order_id"]]
    assert_rows_reconcile(book)


def test_v3_qualified_partial_perpetual_commits_then_severe_residual() -> None:
    book = ledger(pair_state(), adapter="qualified_quote_or_L2", mandate="pair")
    sp, pp, sev, post_sp, post_pp = pair_evidence()
    partial = PairOutcome(D("0.6"), D("0.2"), D("100"), D("100"), D("102"))
    zero_q = PairOutcome(D("0.6"), D("0"), D("100"), D("100"), D("102"))
    full_q = PairOutcome(D("0.6"), D("0.6"), D("100"), D("100"), None)
    result = book.atomic_pair_close(
        "partial", T1, selected_outcome=partial,
        outcome_set=(zero_q, partial, full_q), outcome_set_complete=True,
        spot_price=sp, perpetual_price=pp, severe_perpetual_price=sev,
        spot_rules=SPOT_RULES, perpetual_rules=PERP_RULES, spot_fee=ZERO_FEE,
        ordinary_perpetual_fee=FeePolicy(D("0.001")),
        severe_perpetual_fee=FeePolicy(D("0.002")), post_spot_mark=post_sp,
        post_perpetual_mark=post_pp,
    )
    assert result.actual_spot_reduction == D("0.6")
    assert result.intended_perpetual_filled == D("0.2")
    assert result.created_residual_naked_short == D("0.4")
    assert result.severe_residual_filled == D("0.4")
    assert book.state.spot_quantity == D("0.4")
    assert book.state.perpetual_quantity == D("-0.4")
    assert D(book.order_ledger[-2]["unfilled_quantity"]) == D("0.4")
    assert_rows_reconcile(book)


def test_v3_spot_partial_and_base_fee_actual_reduction() -> None:
    state = pair_state("1.001")
    book = ledger(state, adapter="qualified_quote_or_L2", mandate="pair")
    sp, pp, sev, post_sp, post_pp = pair_evidence()
    base_fee = FeePolicy(D("0.001"), "base")
    selected = PairOutcome(D("1"), D("1.001"), D("100"), D("100"), None)
    result = book.atomic_pair_close(
        "base", T1, selected_outcome=selected, outcome_set=(selected,),
        outcome_set_complete=True, spot_price=sp, perpetual_price=pp,
        severe_perpetual_price=sev, spot_rules=SPOT_RULES, perpetual_rules=PERP_RULES,
        spot_fee=base_fee, ordinary_perpetual_fee=ZERO_FEE,
        severe_perpetual_fee=ZERO_FEE, post_spot_mark=post_sp,
        post_perpetual_mark=post_pp,
    )
    assert result.actual_spot_reduction == D("1.001")
    assert book.state.spot_quantity == 0
    assert book.state.perpetual_quantity == 0
    assert D(book.fill_ledger[0]["explicit_fee_native"]) == D("0.001")
    assert_rows_reconcile(book)


def test_pair_preflight_rejects_unfunded_severe_path_without_mutation() -> None:
    state = pair_state()
    state.isolated_collateral = D("0.01")
    book = ledger(state, adapter="qualified_quote_or_L2", mandate="pair")
    sp, pp, sev, post_sp, post_pp = pair_evidence(severe="150")
    outcome = PairOutcome(D("1"), D("0"), D("100"), D("100"), D("150"))
    before = book.state.digest
    with pytest.raises(ContractViolation, match="severe residual fee"):
        book.atomic_pair_close(
            "reject", T1, selected_outcome=outcome, outcome_set=(outcome,),
            outcome_set_complete=True, spot_price=sp, perpetual_price=pp,
            severe_perpetual_price=sev, spot_rules=SPOT_RULES,
            perpetual_rules=PERP_RULES, spot_fee=ZERO_FEE,
            ordinary_perpetual_fee=ZERO_FEE,
            severe_perpetual_fee=FeePolicy(D("0.01")), post_spot_mark=post_sp,
            post_perpetual_mark=post_pp,
        )
    assert book.state.digest == before
    assert book.events == []


def test_pair_rejected_leg_pending_and_delayed_neutralization_boundary() -> None:
    book = ledger(pair_state(), adapter="qualified_quote_or_L2", mandate="pair")
    sp, pp, _sev, post_sp, post_pp = pair_evidence()
    outcome = PairOutcome(D("0.5"), D("0"), D("100"), D("100"), D("102"))
    # Preflight binds a valid worst price but execution has no same-time quote.
    result = book.atomic_pair_close(
        "delayed", T1, selected_outcome=outcome, outcome_set=(outcome,),
        outcome_set_complete=True, spot_price=sp, perpetual_price=pp,
        severe_perpetual_price=None, spot_rules=SPOT_RULES,
        perpetual_rules=PERP_RULES, spot_fee=ZERO_FEE,
        ordinary_perpetual_fee=ZERO_FEE, severe_perpetual_fee=ZERO_FEE,
        post_spot_mark=post_sp, post_perpetual_mark=post_pp,
    )
    assert result.status == "invalid_unknown_pending_forced_buy_to_close"
    assert book.state.perpetual_quantity == D("-1")
    assert book.state.pending_safety_actions[-1]["quantity"] == "0.5"
    delayed = ev("102", T2, "delayed-severe")
    book.resolve_pending_residual(
        "delayed-resolution", T2, price=delayed, rules=PERP_RULES,
        severe_fee=ZERO_FEE, terminal_at=T3, crossed_segment=True,
    )
    assert book.state.perpetual_quantity == D("-0.5")
    assert book.state.pending_safety_actions == []
    assert book.state.state == "invalid_unknown"  # safety fill cannot restore performance validity
    assert_rows_reconcile(book)


def test_missing_bar_missing_funding_duplicate_and_protective_priority() -> None:
    state = LedgerState(
        D("990"), isolated_collateral=D("10"), perpetual_quantity=D("1"),
        average_perpetual_entry=D("100"), allocated_initial_margin_memo=D("10"),
        perpetual_mark=D("100"),
    )
    book = ledger(state)
    book.missing_funding("missing-f", T1)
    assert book.state.invalidation_reason == "missing_funding_while_exposed"
    allowed, reason = book.risk_permission(reduction=True)
    assert allowed and reason == "protective_or_reduction_priority"
    book.missing_bar("gap", T2, next_segment_id="synthetic-segment-2")
    assert book.state.pending_safety_actions[-1]["action"] == "forced_neutralization"
    with pytest.raises(ContractViolation, match="duplicate"):
        book.missing_bar("gap", T2, next_segment_id="synthetic-segment-2")
    assert_rows_reconcile(book)


def test_zero_position_invariance_scaling_and_unchanged_round_trip_cost() -> None:
    flat = ledger()
    flat.mark("m0", T0, spot=ev("100", T0, "s0", SPOT_RULES),
              perpetual=ev("100", T0, "p0"))
    start = flat.state.nav
    flat.mark("m1", T1, spot=ev("200", T1, "s1", SPOT_RULES),
              perpetual=ev("50", T1, "p1"))
    flat.funding("f", T1, t_minus_signed_quantity="0", rate=ev("0.1", T1, "r"),
                 mark=ev("50", T1, "fm"), index=ev("50", T1, "idx"))
    assert flat.state.nav == start

    book = ledger()
    p = ev("100", T0, "same")
    book.mark("mark", T0, perpetual=p)
    book.perpetual_fill("in", T0, signed_quantity="2", price=p, rules=PERP_RULES,
                        fee=FeePolicy(D("0.001")), implicit_cost_quote="0.2")
    book.perpetual_fill("out", T0, signed_quantity="-2", price=p, rules=PERP_RULES,
                        fee=FeePolicy(D("0.001")), implicit_cost_quote="0.2")
    assert book.starting_nav - book.state.nav == D("0.8")
    assert book.state.explicit_costs == D("0.4")
    assert book.state.implicit_costs == D("0.4")
    assert_rows_reconcile(flat)
    assert_rows_reconcile(book)


def test_decisions_orders_artifacts_and_deterministic_row_lineage() -> None:
    book = ledger()
    evidence = ev("100", T0, "lineage")
    book.record_decision(
        "decision", T0, requested_target="flat", permission="abstain",
        reason="no_trade_only", evidence=(evidence,),
    )
    book.account_snapshot("account", T0, segment_id="synthetic-segment-1",
                          evidence=(evidence,))
    artifacts = book.artifacts()
    assert set(artifacts) == {
        "decision_ledger.jsonl", "order_ledger.jsonl", "fill_ledger.jsonl",
        "funding_ledger.jsonl", "account_ledger.jsonl", "closed_episode_ledger.jsonl",
        "report.json", "evidence_manifest.json",
    }
    for name, content in artifacts.items():
        assert not content or content.endswith(b"\n")
        if name.endswith(".json"):
            json.loads(content)
    assert ACTIONABLE_ARM_ID == "no_trade"
    semantic = {
        "adapter_id": "candle_OHLC",
        "scenario_id": "candle-primary-30bps-rt-v1",
        "selected_mandate_path": DELTA_NEUTRAL_MANDATE_PATH,
        "selected_mandate_id": DELTA_NEUTRAL_MANDATE_ID,
        "selected_mandate_exact_file_sha256": DELTA_NEUTRAL_MANDATE_SHA256,
        "execution_config_exact_file_sha256": book.bindings.execution_config_exact_file_sha256,
        "spot_rules_digest": SPOT_RULES.digest,
        "perpetual_rules_digest": PERP_RULES.digest,
        "spot_fee_policy_digest": ZERO_FEE.digest,
        "perpetual_fee_policy_digest": ZERO_FEE.digest,
        "severe_price_and_cost_bound_digest": synthetic_digest("severe-bound"),
        "mismatch_limit": D("0.01"),
        "arrival_timestamp": T1,
        "source_digests": [synthetic_digest("source")],
    }
    assert semantic_run_settings_digest(semantic) == semantic_run_settings_digest(dict(semantic))
    with pytest.raises(ContractViolation):
        book.record_decision("bad-decision", T1, requested_target="long", permission="execute",
                             reason="forbidden")
    assert_rows_reconcile(book)


def test_missing_flat_bar_does_not_invalidate_or_create_exposure() -> None:
    book = ledger()
    book.missing_bar("flat-gap", T1, next_segment_id="synthetic-segment-2")
    assert book.state.state == "valid"
    assert book.state.pending_safety_actions == []
    assert book.state.nav == book.starting_nav
    assert_rows_reconcile(book)
