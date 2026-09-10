import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).parents[1]
SPEC_PATH = (
    ROOT
    / "artifacts"
    / "agent-level-experiment"
    / "btc-volatility-expansion"
    / "btc-volatility-expansion-hypothesis.json"
)


def load_spec():
    return json.loads(SPEC_PATH.read_text())


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_hypothesis_is_frozen_but_holdout_is_locked():
    spec = load_spec()
    assert spec["experiment_id"] == "btc-volatility-expansion-continuation-v1"
    assert spec["status"] == "frozen_pre_analysis"
    assert spec["lineage"]["holdout_permitted"] is False
    assert spec["lineage"]["holdout_inspected_for_this_hypothesis"] is False
    assert spec["holdout_unlock"]["currently_locked"] is True


def test_lineage_files_match_frozen_checksums():
    spec = load_spec()
    lineage = spec["lineage"]
    for path_key, digest_key in (
        ("development_manifest", "development_manifest_sha256"),
        ("holdout_manifest", "holdout_manifest_sha256"),
        ("mandate_file", "mandate_sha256"),
        ("execution_scenarios_file", "execution_scenarios_sha256"),
    ):
        assert sha256(ROOT / lineage[path_key]) == lineage[digest_key]


def test_timestamps_are_causal_and_aggregates_are_segment_safe():
    timing = load_spec()["time_and_aggregation"]
    assert timing["all_lookbacks_exclude_current_bar"] is True
    assert "trigger 1h bar open timestamp" in timing["context_cutoff"]
    assert "12 contiguous" in timing["one_hour_bar"]
    assert "48 contiguous" in timing["four_hour_bar"]
    assert "never forward-fill" in timing["gap_policy"]


def test_event_has_one_primary_horizon_and_no_lagging_indicator_dependency():
    spec = load_spec()
    event = spec["event_definition"]
    assert "t+24h" in event["primary_raw_label"]
    assert event["secondary_labels_may_rescue_primary_failure"] is False
    assert {condition["name"] for condition in event["conditions"]} == {
        "compressed_4h_state",
        "positive_return_shock",
        "range_expansion",
        "volume_expansion",
        "close_near_high",
        "positive_aggressive_flow",
    }
    assert {"moving_average", "rsi", "macd", "adx"}.issubset(
        spec["scope"]["excluded_primary_inputs"]
    )


def test_execution_and_risk_match_retail_mandate():
    spec = load_spec()
    orders = spec["orders_and_position"]
    risk = spec["sizing_and_risk"]
    assert orders["primary_execution_scenario_id"] == "candle-primary-30bps-rt-v1"
    assert orders["entry_price_protection_bps"] == "10"
    assert orders["maker_entry_allowed"] is False
    assert orders["maximum_open_positions"] == 1
    assert orders["maximum_entries_per_utc_day"] == 1
    assert orders["maximum_entries_per_rolling_7_days"] == 4
    assert orders["holding_period_hours"] == 24
    assert risk["maximum_position_fraction"] == "0.25"
    assert risk["maximum_planned_risk_fraction"] == "0.005"
    assert risk["daily_loss_stop_fraction"] == "0.015"
    assert risk["strategy_drawdown_stop_fraction"] == "0.10"


def test_development_failure_cannot_be_rescued_or_unlock_holdout():
    spec = load_spec()
    gates = spec["development_acceptance_gates"]
    unlock = spec["holdout_unlock"]
    assert gates["all_gates_required"] is True
    assert gates["minimum_executed_trades_each_confirmation_year"] == 30
    assert gates["gate_failure_action"].startswith("reject experiment before holdout")
    assert spec["evaluation"]["threshold_tuning_allowed"] is False
    assert spec["evaluation"]["one_at_a_time_sensitivity"]["not_for_selection_or_rescue"] is True
    assert unlock["requires_all_development_gates"] is True
    assert unlock["holdout_acceptance_gates"]["any_failure_rejects"] is True
