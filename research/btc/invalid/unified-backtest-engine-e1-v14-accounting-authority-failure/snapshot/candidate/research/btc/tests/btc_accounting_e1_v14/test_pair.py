from __future__ import annotations

from decimal import Decimal
import inspect

import pytest

from trading_platform.btc_accounting_e1_v14.authorities import get_run_spec
from trading_platform.btc_accounting_e1_v14.canonical import canonical_sha256
from trading_platform.btc_accounting_e1_v14.ledger import _create_ledger
from trading_platform.btc_accounting_e1_v14.pair import (
    PairError, _attach_pair, _depth_fill, _levels,
)


def engine(run_id="pair_candle_primary", cursor=0):
    value = _attach_pair(_create_ledger(get_run_spec(run_id)))
    if cursor:
        value._PairEngine__ledger._cursor = cursor
    value.open_next_interval()
    return value


def l2_at_second():
    value = engine("pair_l2_primary")
    value.close_interval()
    value.open_next_interval()
    return value


def test_C01_direct_pair_methods_no_generic_fill():
    value = engine()
    assert callable(value.atomic_pair_entry) and callable(value.atomic_pair_close)
    assert not hasattr(value, "fill") and not hasattr(value, "submit_fill")
    assert tuple(inspect.signature(value.atomic_pair_entry).parameters) == ("target_quantity",)


def test_C02_pair_entry_success_preflight_spot_first():
    value = engine()
    result = value.atomic_pair_entry(Decimal("0.5"))
    assert result["recovered"] is False
    assert value.state.spot_quantity == Decimal("0.5")
    assert value.state.perpetual_quantity == Decimal("-0.5")
    assert [row["instrument"] for row in value.rows["fill"]] == ["BTC/USDT", "BTCUSDT_USD_M_perpetual"]
    assert value.rows["pair"][0]["kind"] == "entry"


def test_C03_zero_reject_truthful_order_spot_recovery_invalid():
    value = l2_at_second()
    result = value.atomic_pair_entry(Decimal("0.5"))
    failed = result["perpetual_order"]
    assert (failed["requested_quantity"], failed["filled_quantity"], failed["unfilled_quantity"]) == ("-0.5", "0", "-0.5")
    assert failed["status"] == "rejected"
    assert value.state.spot_quantity == 0 and value.state.perpetual_quantity == 0
    assert value.state.state == "invalid_unknown"
    assert value.rows["order"][-1]["scenario_id"] == "candle-severe-80bps-rt-v1"


def test_C04_partial_truthful_order_perp_then_spot_recovery_invalid():
    value = engine("pair_l2_primary", cursor=3)
    result = value.atomic_pair_entry(Decimal("0.5"))
    partial = result["perpetual_order"]
    assert (partial["requested_quantity"], partial["filled_quantity"], partial["unfilled_quantity"]) == ("-0.5", "-0.4", "-0.1")
    assert partial["status"] == "partial"
    reasons = [row["reason"] for row in value.rows["order"]]
    assert reasons[-2:] == ["severe_pair_recovery_perpetual_first", "severe_pair_recovery_spot_second"]
    assert value.state.spot_quantity == value.state.perpetual_quantity == 0


def test_C05_all_entry_paths_preflight_before_leg1_and_failure_atomicity():
    value = engine()
    before = value.state
    with pytest.raises(ValueError):
        value.atomic_pair_entry(Decimal("5"))
    assert value.state == before and not value.rows["fill"]
    zero = l2_at_second()
    zero.atomic_pair_entry(Decimal("0.5"))
    assert zero.rows["pair"][0]["selected_outcome_digest"]


def test_C06_commits_persist_each_checkpoint():
    value = engine("pair_l2_primary", cursor=3)
    value.atomic_pair_entry(Decimal("0.5"))
    fills = value.rows["fill"]
    assert len(fills) == 4
    assert all(row["before_state_digest"] != row["after_state_digest"] for row in fills)
    assert fills[1]["before_state_digest"] == fills[0]["after_state_digest"]
    assert fills[2]["before_state_digest"] == fills[1]["after_state_digest"]


def test_C07_pair_close_order_and_quantity_truth():
    value = engine()
    value.atomic_pair_entry(Decimal("0.5"))
    value.close_interval(); value.open_next_interval()
    result = value.atomic_pair_close(Decimal("0"))
    assert result["spot_order"]["requested_quantity"] == "-0.5"
    assert result["perpetual_order"]["requested_quantity"] == "0.5"
    assert [row["instrument"] for row in value.rows["fill"][-2:]] == ["BTC/USDT", "BTCUSDT_USD_M_perpetual"]
    assert value.state.spot_quantity == value.state.perpetual_quantity == 0


def test_E01_complete_priced_fee_mutated_Rxq():
    value = engine("pair_l2_primary", cursor=3)
    value.atomic_pair_entry(Decimal("0.5"))
    outcomes = value.rows["pair"][0]["outcomes"]
    pairs = {(row["spot_filled_quantity"], row["perpetual_filled_quantity"]) for row in outcomes}
    assert len(outcomes) == len(pairs) == 20
    assert all(row["spot_price"] is not None and row["perpetual_price"] is not None for row in outcomes)
    assert all(Decimal(row["spot_fee_quote"]) >= 0 and Decimal(row["perpetual_fee_quote"]) >= 0 for row in outcomes)


def test_E02_no_caller_depth_outcome_inputs():
    parameters = set(inspect.signature(engine().atomic_pair_entry).parameters)
    assert not parameters & {"price", "depth", "outcome", "source", "scenario", "cost", "latency"}


def test_E03_depth_rule_VWAP_cost_collateral_rejects():
    value = engine("pair_l2_primary")
    value.atomic_pair_entry(Decimal("1.5"))
    fills = value.rows["fill"]
    assert fills[0]["accounting_fill_price"] == "100.1"
    assert Decimal(fills[0]["explicit_fee_quote_equivalent"]) > 0
    assert Decimal(fills[0]["implicit_cost_quote"]) > 0
    rejected = engine("pair_l2_primary")
    with pytest.raises(ValueError):
        rejected.atomic_pair_entry(Decimal("6"))
    assert not rejected.rows["fill"]


def test_E04_duplicate_reject_permutation_digest_collision():
    duplicate = {"adapter_status": "qualified", "asks": (("100", "1"), ("100", "2")), "bids": ()}
    with pytest.raises(PairError):
        _levels(duplicate, "buy")
    a = {"adapter_status": "qualified", "asks": (("101", "1"), ("100", "1")), "bids": (), "reference_open": "100"}
    b = {**a, "asks": tuple(reversed(a["asks"]))}
    rule = {"step": "0.1", "maximum_quantity": "10", "minimum_notional": "5"}
    assert _depth_fill(a, Decimal("1.5"), rule, Decimal("200")) == _depth_fill(b, Decimal("1.5"), rule, Decimal("200"))


def test_E05_candle_exact_open_no_partial():
    value = engine()
    value.atomic_pair_entry(Decimal("0.59"))
    orders = value.rows["order"]
    assert all(row["status"] != "partial" for row in orders)
    assert [row["accounting_fill_price"] for row in value.rows["fill"]] == ["100", "101"]


def test_E06_actual_preflight_row_and_severe_bound():
    value = engine("pair_l2_primary", cursor=3)
    result = value.atomic_pair_entry(Decimal("0.5"))
    preflight = value.rows["pair"][0]
    selected = preflight["selected_outcome_digest"]
    assert selected in {canonical_sha256(row) for row in preflight["outcomes"]}
    assert all(row["severe_recovery_bound"] == "candle-severe-80bps-rt-v1" for row in preflight["outcomes"])
    assert result["recovered"]


def test_F01_one_immediate_finite_mismatch_attempt():
    value = engine("pair_l2_primary", cursor=3)
    value.atomic_pair_entry(Decimal("0.5"))
    severe = [row for row in value.rows["order"] if row["scenario_id"] == "candle-severe-80bps-rt-v1"]
    assert len(severe) == 2
    assert value._PairEngine__recovery_attempts == 1


def test_F02_every_mismatch_fill_has_checkpoint_digest():
    value = engine("pair_l2_primary", cursor=3)
    value.atomic_pair_entry(Decimal("0.5"))
    for fill in value.rows["fill"]:
        assert fill["before_state_digest"] and fill["after_state_digest"] and fill["event_sequence"]


def test_F03_one_pending_close_full_lineage():
    value = engine("pair_l2_primary")
    value.atomic_pair_entry(Decimal("0.5")); value.close_interval(); value.open_next_interval()
    value.atomic_pair_close()
    assert value.state.pending_protection == "forced_perpetual_buy_to_close"
    assert value.state.spot_quantity == 0 and value.state.perpetual_quantity == Decimal("-0.5")
    pending = value.rows["order"][-1]
    assert pending["scenario_id"] == "candle-severe-80bps-rt-v1"
    assert pending["source_digest"] and pending["rules_digest"] and pending["mandate_digest"]


def test_F04_sole_segment_exception_then_reset():
    value = engine("pair_l2_primary")
    value.atomic_pair_entry(Decimal("0.5")); value.close_interval(); value.open_next_interval()
    value.atomic_pair_close(); value.close_interval()
    value._PairEngine__ledger._cursor = 4
    value.open_next_interval()
    assert value.state.perpetual_quantity == 0
    assert value.state.pending_protection is None
    assert value.state.segment_id == "S2"
    assert value.rows["order"][-1]["reason"] == "gap_exit"


def test_F05_all_other_boundary_crossings_reject():
    value = engine("pair_l2_primary")
    value.atomic_pair_entry(Decimal("0.5")); value.close_interval(); value.open_next_interval()
    value.atomic_pair_close(); value.close_interval()
    value._PairEngine__ledger._cursor = 6
    with pytest.raises(StopIteration):
        value.open_next_interval()
    assert value.state.pending_protection == "forced_perpetual_buy_to_close"


def test_R07_R08_truthful_partial_and_candle_partial_impossible():
    partial = engine("pair_l2_primary", cursor=3)
    partial.atomic_pair_entry(Decimal("0.5"))
    row = partial.rows["order"][1]
    assert Decimal(row["filled_quantity"]) + Decimal(row["unfilled_quantity"]) == Decimal(row["requested_quantity"])
    candle = engine(); candle.atomic_pair_entry(Decimal("0.59"))
    assert not any(row["status"] == "partial" for row in candle.rows["order"])


def test_R09_Cartesian_emitted_bound_actual_selected():
    value = engine("pair_l2_primary")
    value.atomic_pair_entry(Decimal("0.5"))
    row = value.rows["pair"][0]
    assert row["outcome_count"] == len(row["outcomes"])
    assert sum(canonical_sha256(item) == row["selected_outcome_digest"] for item in row["outcomes"]) == 1


def test_R10_severe_scenario_identity():
    value = l2_at_second(); value.atomic_pair_entry(Decimal("0.5"))
    severe = [row for row in value.rows["order"] if row["reason"].startswith("severe_")]
    assert severe and {row["scenario_id"] for row in severe} == {"candle-severe-80bps-rt-v1"}


def test_R13_price_delta_tolerance():
    ledger = _create_ledger(get_run_spec("pair_candle_primary"))
    ledger._check_pair_delta(Decimal("1"), Decimal("-1"), Decimal("100"), Decimal("101"))
    with pytest.raises(ValueError):
        ledger._check_pair_delta(Decimal("1"), Decimal("-1"), Decimal("100"), Decimal("102"))
    with pytest.raises(ValueError):
        ledger._check_pair_delta(Decimal("1"), Decimal("0"), Decimal("100"), Decimal("100"))
