import importlib.util
import json
import sys
from decimal import Decimal
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "evaluate_btc_volatility_expansion.py"
SPEC = importlib.util.spec_from_file_location("evaluate_btc_volatility_expansion", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def row(index, *, segment=0, start=MODULE.CONFIRMATION_START_MS, price=100.0, low=None):
    open_ms = start + index * MODULE.FIVE_MINUTES_MS
    return MODULE.Row(
        segment=segment, open_ms=open_ms, open=price, high=price + 1,
        low=price - 1 if low is None else low, close=price,
        base_volume=10, quote_volume=1000,
        taker_buy_base=6, taker_sell_base=4,
    )


def point(index=0, **changes):
    values = dict(
        bar_index=index, segment=0,
        open_ms=MODULE.CONFIRMATION_START_MS + index * MODULE.HOUR_MS,
        close_ms=MODULE.CONFIRMATION_START_MS + (index + 1) * MODULE.HOUR_MS,
        trigger_close=100.0, trigger_low=99.0, range_fraction=0.01,
        return_shock=2.0, range_ratio=2.0, quote_volume_ratio=1.5,
        close_location=0.8, taker_imbalance=0.1, compression_quantile=0.2, rv24=0.03,
        raw_return_24h=0.01, entry_row=index,
    )
    values.update(changes)
    return MODULE.SignalPoint(**values)


def test_quantile_uses_frozen_linear_interpolation():
    assert MODULE.quantile([0, 10], 0.2) == 2
    assert MODULE.quantile([4, 1, 3, 2], 0.5) == 2.5


def test_aggregation_requires_alignment_contiguity_and_one_segment():
    complete = [row(i, start=MODULE.CONFIRMATION_START_MS) for i in range(12)]
    bars, discarded = MODULE.aggregate_bars(complete, MODULE.HOUR_MS)
    assert len(bars) == 1
    assert discarded == 0
    assert bars[0].start_row == 0 and bars[0].end_row == 11

    broken = complete[:6] + [row(i, segment=1, start=MODULE.CONFIRMATION_START_MS) for i in range(6, 12)]
    bars, discarded = MODULE.aggregate_bars(broken, MODULE.HOUR_MS)
    assert bars == []
    assert discarded == 12


def test_event_thresholds_are_inclusive_except_taker_flow_and_cool_down_24_bars():
    candidates = [point(0), point(24), point(25)]
    selected = MODULE.select_events(candidates, MODULE.Thresholds())
    assert [candidate.bar_index for candidate in selected] == [0, 25]
    assert MODULE.select_events([point(taker_imbalance=0.0)], MODULE.Thresholds()) == []


def test_current_market_rules_snapshot_rounds_down_and_matches_recorded_digest():
    root = Path(__file__).parents[1]
    rules = MODULE.market_rules(root / "artifacts/real-data-research/BTCUSDT-market-rules-20260825.json")
    assert rules.round_quantity(Decimal("0.123456")) == Decimal("0.12345")
    assert rules.checksum == "50367ea97aa7da015569959c917f6a39d17ff1df74683f292a0115dd93aad768"


def test_same_bar_stop_is_resolved_before_time_or_segment_exit():
    root = Path(__file__).parents[1]
    rules = MODULE.market_rules(root / "artifacts/real-data-research/BTCUSDT-market-rules-20260825.json")
    scenario = MODULE.load_scenarios(root / "config/execution_scenarios.json")["candle-primary-30bps-rt-v1"]
    source = [row(0, low=98.0)]
    event = point(
        entry_row=0,
        open_ms=MODULE.CONFIRMATION_START_MS - MODULE.HOUR_MS,
        close_ms=MODULE.CONFIRMATION_START_MS,
    )
    result = MODULE.simulate_strategy(
        source, [event], scenario, rules,
        start_ms=MODULE.CONFIRMATION_START_MS - MODULE.HOUR_MS,
    )
    assert result["trade_count"] == 1
    assert result["stop_exit_count"] == 1
    assert result["segment_boundary_exit_count"] == 0
    assert result["trades"][0]["exit_reason"] == "stop"


def test_holdout_named_input_is_rejected_before_evaluation(tmp_path):
    data = tmp_path / "holdout-data.csv.gz"
    data.write_bytes(b"not a development dataset")
    manifest = tmp_path / "manifest.json"
    manifest.write_text('{"partition":"holdout-2026-01-07","accepted":true,"dataset_sha256":"x"}')
    hypothesis = tmp_path / "hypothesis.json"
    hypothesis.write_text(
        '{"experiment_id":"btc-volatility-expansion-continuation-v1",'
        '"status":"frozen_pre_analysis","lineage":{"holdout_permitted":false,'
        '"development_dataset_sha256":"x"}}'
    )
    args = type("Args", (), {"data": data, "manifest": manifest, "hypothesis": hypothesis})()
    try:
        MODULE.verify_inputs(args)
    except ValueError as error:
        assert "development partition required" in str(error)
    else:
        raise AssertionError("holdout input was not rejected")


def test_committed_development_report_records_rejection_without_holdout_access():
    root = Path(__file__).parents[1]
    report = json.loads((
        root / "artifacts/agent-level-experiment/btc-volatility-expansion/"
        "btc-volatility-expansion-development-report.json"
    ).read_text())
    assert report["decision"] == "rejected_before_holdout"
    assert report["accepted_for_holdout"] is False
    assert report["holdout_accessed"] is False
    assert report["raw_confirmation"]["events"] == 55
    assert report["positive_sensitivities_out_of_10"] == 0
    assert sum(report["development_gates"].values()) == 1
    primary = report["execution_scenarios"]["candle-primary-30bps-rt-v1"]
    assert primary["trade_count"] == 55
    assert primary["net_return"] < 0
    assert primary["profit_factor"] < 1
    assert primary["monthly_results"]
    assert primary["compression_quantile_regimes"]
    assert primary["realized_volatility_sample_quartiles"]
