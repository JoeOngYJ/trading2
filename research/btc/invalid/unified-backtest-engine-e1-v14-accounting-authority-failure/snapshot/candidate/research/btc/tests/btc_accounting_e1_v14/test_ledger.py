from dataclasses import FrozenInstanceError, replace
from decimal import Decimal

import pytest

from src.trading_platform.btc_accounting_e1_v14 import authorities
from src.trading_platform.btc_accounting_e1_v14.canonical import canonical_sha256, thaw
from src.trading_platform.btc_accounting_e1_v14.ledger import (
    ACCOUNT_FIELDS,
    DECISION_FIELDS,
    EPISODE_FIELDS,
    FILL_FIELDS,
    FUNDING_FIELDS,
    LINEAGE_FIELDS,
    ORDER_FIELDS,
    PHASES,
    AccountState,
    _apply_native_fee,
    _create_ledger,
)


def engine(run_spec_id="directional_candle_primary"):
    return _create_ledger(authorities.get_run_spec(run_spec_id))


def frozen_binding(run_spec_id, observations, *, margin=None):
    spec = thaw(authorities.get_run_spec(run_spec_id).payload)
    return {
        "run_spec": spec,
        "rules": thaw(authorities.authority("instrument_rules")),
        "margin": margin or thaw(authorities.authority("margin_rules")),
        "settings": thaw(authorities.authority("semantic_settings")),
        "source": {"observations": observations},
        "scenarios": thaw(authorities.authority("execution_scenarios")),
    }


def candle(at, spot="100", perp="100", *, low=None, high=None, close=None,
           segment="S1", funding=None):
    stamp = f"2025-01-{at}.000000Z"
    return [
        {"observed_at": stamp, "available_at": stamp, "instrument": "BTC/USDT",
         "segment_id": segment, "open": spot, "low": low or spot,
         "high": high or spot, "close": close or spot},
        {"observed_at": stamp, "available_at": stamp,
         "instrument": "BTCUSDT_USD_M_perpetual", "segment_id": segment,
         "open": perp, "mark_open": perp, "index_open": perp, "low": low or perp,
         "high": high or perp, "close": close or perp, "funding": funding},
    ]


def test_B01_B02_B03_R02_wrong_phase_and_bad_values_are_side_effect_free():
    book = engine()
    before = (book.state, book.rows, book.episodes)
    with pytest.raises(RuntimeError):
        book.submit_directional_target("1")
    assert (book.state, book.rows, book.episodes) == before
    book.open_next_interval()
    before = (book.state, book.rows, book.episodes)
    for bad in (float("nan"), True, "NaN"):
        with pytest.raises((TypeError, ValueError)):
            book.submit_directional_target(bad)
        assert (book.state, book.rows, book.episodes) == before
    assert not any(name in {"set_state", "set_phase", "set_clock", "fill", "fund"}
                   for name in dir(book) if not name.startswith("_"))


def test_B04_B07_K02_exact_nine_phases_monotone_ids_and_digest_chain():
    book = engine("spot_candle_primary")
    book.open_next_interval()
    book.submit_spot_target("2")
    book.close_interval()
    assert tuple(row["name"] for row in book.rows["phase"]) == PHASES
    economic = [row for key in ("decision", "order", "fill", "funding", "account")
                for row in book.rows[key]]
    sequences = sorted(row["event_sequence"] for row in economic)
    assert sequences == list(range(1, len(sequences) + 1))
    for row in economic:
        copy = dict(row)
        digest = copy.pop("row_digest")
        assert digest == canonical_sha256(copy)
        assert abs(Decimal(row["event_accounting_residual"])) <= Decimal("0.00000001")


def test_B05_G05_reversal_is_two_fills_and_same_direction_pyramid_rejects():
    observations = candle("01T01:00:00", perp="100") + candle(
        "01T02:00:00", perp="105")
    book = _create_ledger(frozen_binding("directional_candle_primary", observations))
    book.open_next_interval()
    book.submit_directional_target("2")
    book.close_interval()
    book.open_next_interval()
    rejected = book.submit_directional_target("2.1")
    assert rejected["status"] == "rejected" and rejected["reason"] == "pyramiding_forbidden"

    # A separate frozen run proves a reversal is close-to-zero then a new episode/fill.
    book = _create_ledger(frozen_binding("directional_candle_primary", observations))
    book.open_next_interval(); book.submit_directional_target("2"); book.close_interval()
    book.open_next_interval(); book.submit_directional_target("-2")
    assert [row["post_fill_position"] for row in book.rows["fill"]][-2:] == ["0", "-2"]
    assert len(book.episodes) == 1


def test_B06_R05_terminal_is_monotone_and_suppresses_later_events():
    book = engine("spot_candle_primary")
    book.open_next_interval(); book.submit_spot_target("1"); book.terminate()
    counts = {key: len(value) for key, value in book.rows.items()}
    assert book.state.terminal and book.state.spot_quantity == 0
    assert tuple(row["phase"] for row in book.rows["phase"]) == tuple(range(1, 10))
    with pytest.raises(RuntimeError):
        book.open_next_interval()
    assert {key: len(value) for key, value in book.rows.items()} == counts


def test_B08_funding_uses_tminus_membership_before_same_time_exit():
    book = engine()
    book.open_next_interval(); book.submit_directional_target("2"); book.close_interval()
    book.open_next_interval()
    row = book.rows["funding"][0]
    assert row["t_minus_signed_quantity"] == "2"
    assert row["cashflow_quote"] == "-0.218"
    book.submit_directional_target("0")
    assert book.state.funding == Decimal("-0.218")


def test_B09_K04_R17_intrabar_marks_do_not_replace_close_pnl_and_episode_is_local():
    obs = candle("01T01:00:00", perp="100", low="90", high="110", close="102") + candle(
        "01T02:00:00", perp="105", low="100", high="108", close="106")
    book = _create_ledger(frozen_binding("directional_candle_primary", obs))
    book.open_next_interval(); book.submit_directional_target("2"); book.close_interval()
    book.open_next_interval(); book.submit_directional_target("0"); book.close_interval()
    episode = book.episodes[0]
    assert set(episode) == set(EPISODE_FIELDS)
    assert Decimal(episode["maximum_adverse_excursion"]) <= 0
    assert Decimal(episode["maximum_favourable_excursion"]) >= 0
    assert Decimal(episode["net_dollar_PnL"]) == (
        Decimal(episode["price_PnL"]) + Decimal(episode["funding_PnL"])
        - Decimal(episode["entry_costs"]) - Decimal(episode["exit_costs"])
    )


def test_G01_R12_quote_base_third_tax_mutate_once_and_insufficient_fails():
    state = AccountState(quote_cash=Decimal("100"), spot_quantity=Decimal("2"),
                         isolated_collateral=Decimal("20"), fee_asset_balances=(("BNB", Decimal("1")),),
                         fee_asset_marks=(("BNB", Decimal("500")),), explicit_costs=Decimal("0"))
    quote = _apply_native_fee(state, instrument="BTC/USDT", asset="USDT",
                              native_amount="1.1", quote_equivalent="1.1")
    base = _apply_native_fee(quote, instrument="BTC/USDT", asset="BTC",
                             native_amount="0.01", quote_equivalent="1")
    third = _apply_native_fee(base, instrument="BTC/USDT", asset="BNB",
                              native_amount="0.01", quote_equivalent="5")
    assert third.quote_cash == Decimal("98.9")
    assert third.spot_quantity == Decimal("1.99")
    assert dict(third.fee_asset_balances)["BNB"] == Decimal("0.99")
    assert third.explicit_costs == Decimal("7.1")
    with pytest.raises(ValueError):
        _apply_native_fee(third, instrument="BTC/USDT", asset="BNB",
                          native_amount="2", quote_equivalent="1000")


def test_G02_G03_exact_mandate_method_and_25_percent_cap():
    spot = engine("spot_candle_primary"); spot.open_next_interval()
    with pytest.raises(PermissionError):
        spot.submit_directional_target("1")
    rejected = spot.submit_spot_target("2.6")
    assert rejected["reason"] == "exposure_cap" and spot.state.spot_quantity == 0
    directional = engine(); directional.open_next_interval()
    assert directional.submit_directional_target("2.5")["reason"] == "exposure_cap"


def test_G04_pair_is_price_matched_capped_and_never_naked():
    book = engine("pair_candle_primary")
    book.open_next_interval()
    book._check_pair_delta("2", "-2", "100", "100")
    with pytest.raises(ValueError, match="naked"):
        book._check_pair_delta("2", "0", "100", "100")
    with pytest.raises(ValueError, match="mismatch"):
        book._check_pair_delta("2", "-2", "100", "110")
    with pytest.raises(ValueError, match="50 percent"):
        book._check_pair_delta("6", "-6", "100", "100")


def test_I01_I02_I03_loss_boundaries_block_increase_not_reduction():
    book = engine()
    book.open_next_interval()
    book._state = replace(book.state, NAV=Decimal("985"), UTC_day_start_equity=Decimal("1000"))
    book._phase = 4
    book._phase_permissions()
    assert not book.state.new_exposure_enabled
    # Protective/private reduction remains available at the exact boundary.
    book._state = replace(book.state, perpetual_quantity=Decimal("1"),
                          average_perpetual_entry=Decimal("101"), isolated_collateral=Decimal("101"),
                          allocated_initial_margin_memo=Decimal("101"))
    book._apply_pair_fill("BTCUSDT_USD_M_perpetual", "-1", severe=True, reason="protective")
    assert book.state.perpetual_quantity == 0


def test_K01_literal_schemas_nullable_invalidation_and_lineage():
    book = engine(); book.open_next_interval(); book.submit_directional_target("1"); book.close_interval()
    expected = {"decision": DECISION_FIELDS, "order": ORDER_FIELDS, "fill": FILL_FIELDS,
                "funding": FUNDING_FIELDS, "account": ACCOUNT_FIELDS}
    for ledger, fields in expected.items():
        for row in book.rows[ledger]:
            assert set(fields).issubset(row)
            assert set(LINEAGE_FIELDS).issubset(row)
            assert "invalidation_reason" in row


def test_K03_R16_liquidation_is_immediate_full_close_with_no_caller_lineage():
    obs = candle("01T01:00:00", perp="100", low="99", high="101", close="100")
    margin = thaw(authorities.authority("margin_rules")); margin["maintenance_fraction"] = "2"
    book = _create_ledger(frozen_binding("directional_candle_primary", obs, margin=margin))
    book.open_next_interval(); book.submit_directional_target("1")
    assert book.state.terminal and book.state.perpetual_quantity == 0
    assert book.rows["order"][-1]["reason"] == "liquidation:post_fill"
    assert book.rows["order"][-1]["scenario_id"] == "liquidation"
    assert book.episodes[-1]["invalidation_reason"].startswith("liquidation:")


def test_R03_recursive_views_and_state_are_immutable():
    book = engine(); book.open_next_interval()
    with pytest.raises(FrozenInstanceError):
        book.state.quote_cash = Decimal("0")
    with pytest.raises(TypeError):
        book.rows["phase"][0]["phase"] = 9
    with pytest.raises(TypeError):
        book.bindings["run_spec_id"] = "wrong"


def test_R04_invalid_source_is_atomic():
    obs = candle("01T01:00:00")
    obs[1]["available_at"] = "2025-01-01T00:59:59.000000Z"
    book = _create_ledger(frozen_binding("directional_candle_primary", obs))
    before = (book.state, book.rows)
    with pytest.raises(ValueError):
        book.open_next_interval()
    assert (book.state, book.rows) == before


def test_R06_gap_cleanup_is_genuinely_phase3_and_sticky_invalid():
    obs = candle("01T01:00:00", perp="100") + candle(
        "01T03:00:00", spot="80", perp="80", segment="S2")
    book = _create_ledger(frozen_binding("directional_candle_primary", obs))
    book.open_next_interval(); book.submit_directional_target("1"); book.close_interval()
    book.open_next_interval()
    assert book.state.perpetual_quantity == 0
    assert book.state.invalidation_reason == "exposed_gap"
    assert book.rows["order"][-1]["reason"] == "gap_exit"
    assert book.rows["phase"][-3]["phase"] == 3


def test_R18_flat_segment_gap_resets_risk_and_cadence():
    obs = candle("01T01:00:00") + candle("01T03:00:00", segment="S2")
    book = _create_ledger(frozen_binding("directional_candle_primary", obs))
    book.open_next_interval(); book.close_interval()
    book._entry_days.add("2025-01-01")
    book.open_next_interval()
    assert book.state.segment_id == "S2"
    assert book.state.high_water_NAV == book.state.NAV
    assert not book._entry_days


def test_R20_transition_residual_is_computed_not_a_placeholder():
    book = engine("spot_candle_primary"); book.open_next_interval(); book.submit_spot_target("1")
    fill = book.rows["fill"][0]
    before = Decimal("1000")
    after = book.state.NAV
    expected = after - before + Decimal(fill["explicit_fee_quote_equivalent"]) + Decimal(fill["implicit_cost_quote"])
    assert Decimal(fill["event_accounting_residual"]) == expected == 0
