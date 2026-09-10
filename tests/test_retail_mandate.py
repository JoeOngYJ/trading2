import json
from pathlib import Path


MANDATE = Path(__file__).parents[1] / "config" / "retail_mandate.json"


def test_retail_mandate_is_safe_and_research_only():
    mandate = json.loads(MANDATE.read_text(encoding="utf-8"))

    assert mandate["status"] == "frozen_research_execution_model_v1"
    assert mandate["mandate_id"] == "retail-btc-spot-v2"
    assert mandate["live_trading_authorized"] is False
    assert mandate["scope"]["market_type"] == "spot"
    assert mandate["scope"]["pairs"] == ["BTC/USDT"]
    assert mandate["scope"]["position_directions"] == ["long", "flat"]
    assert mandate["capital"]["maximum_live_allocation_usdt"] == 0
    assert mandate["risk"]["maximum_open_positions"] == 1
    assert mandate["risk"]["protective_exits_remain_enabled"] is True
    assert mandate["promotion"]["live_credentials_allowed"] is False
    assert mandate["promotion"]["live_funds_allowed"] is False


def test_retail_mandate_has_conservative_bounded_risk():
    mandate = json.loads(MANDATE.read_text(encoding="utf-8"))
    capital = mandate["capital"]
    risk = mandate["risk"]
    cadence = mandate["cadence"]

    assert 0 < capital["maximum_position_fraction"] <= 0.25
    assert 0 < risk["maximum_risk_per_trade_fraction"] <= 0.005
    assert 0 < risk["daily_loss_stop_fraction"] <= 0.015
    assert 0 < risk["strategy_drawdown_stop_fraction"] <= 0.10
    assert cadence["completed_candles_only"] is True
    assert cadence["decision_timeframe"] == "1h"
    assert cadence["maximum_new_entries_per_utc_day"] <= 1


def test_execution_defaults_are_frozen_but_account_calibration_remains_pending():
    mandate = json.loads(MANDATE.read_text(encoding="utf-8"))
    execution = mandate["execution_policy"]

    assert execution["status"] == "research_execution_model_v1_account_calibration_pending"
    assert execution["primary_execution"] == "price_protected_taker"
    assert execution["primary_price_protection_bps"] == 10
    assert execution["maker_timeout_seconds"] == 60
    assert execution["default_taker_fee_bps_per_fill"] == 10
    assert execution["fee_tier"] == "unknown_conservative_default_no_bnb_discount"
