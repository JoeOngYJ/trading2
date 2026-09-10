import importlib.util
import json
import sys
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "backtest_btc_online_regime_breakout.py"
SPEC = importlib.util.spec_from_file_location("backtest_btc_online_regime_breakout", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def row(index, *, segment=0, start=MODULE.EVALUATION_START_MS, price=100.0, low=None):
    return MODULE.Row(
        segment, start + index * MODULE.FIVE_MINUTES_MS,
        price, price + 1.0, price - 1.0 if low is None else low, price,
    )


def daily_bar(index, close, *, segment=0, start=0):
    open_ms = start + index * MODULE.DAY_MS
    return MODULE.Bar(segment, open_ms, open_ms + MODULE.DAY_MS, 100.0, max(100.0, close), min(100.0, close), close, index, index)


def test_aggregation_requires_utc_alignment_contiguity_and_one_segment():
    rows = [row(index) for index in range(48)]
    bars, discarded = MODULE.aggregate_bars(rows, MODULE.FOUR_HOURS_MS)
    assert len(bars) == 1
    assert discarded == 0
    assert bars[0].start_row == 0 and bars[0].end_row == 47
    broken = rows[:24] + [row(index, segment=1) for index in range(24, 48)]
    bars, discarded = MODULE.aggregate_bars(broken, MODULE.FOUR_HOURS_MS)
    assert bars == []
    assert discarded == 48


def test_bocpd_is_filtered_causal_and_deterministic():
    prior = MODULE.NIG(0.0, 0.25, 3.0, 0.001)
    first = [daily_bar(index, 100.0 * (1.003 ** (index + 1))) for index in range(30)]
    changed_future = first + [daily_bar(index, 50.0) for index in range(30, 40)]
    ordinary_future = first + [daily_bar(index, 120.0) for index in range(30, 40)]
    left = MODULE.bocpd_states(changed_future, prior)
    right = MODULE.bocpd_states(ordinary_future, prior)
    assert left[:30] == right[:30]
    assert left == MODULE.bocpd_states(changed_future, prior)


def test_latest_regime_state_is_not_available_before_daily_close():
    state = MODULE.RegimeState(0, 0, MODULE.DAY_MS, 101.0, "positive", 0.1, 20, 0.01, 0.005, 2.0)
    bars = [
        MODULE.Bar(0, 0, MODULE.DAY_MS - 1, 100, 101, 99, 100, 0, 0),
        MODULE.Bar(0, MODULE.DAY_MS, MODULE.DAY_MS + MODULE.FOUR_HOURS_MS, 100, 101, 99, 100, 1, 1),
    ]
    assert MODULE.latest_states(bars, [state]) == [None, "positive"]


def test_entry_is_next_row_and_stop_gap_is_conservative():
    rows = [row(0), row(1, price=100.0, low=94.0), row(2)]
    signal_bar = MODULE.Bar(
        0, MODULE.EVALUATION_START_MS - MODULE.FOUR_HOURS_MS,
        MODULE.EVALUATION_START_MS + MODULE.FIVE_MINUTES_MS,
        99, 101, 98, 100, 0, 0,
    )
    result = MODULE.simulate(
        rows, [signal_bar], [0], {}, side_cost_bps=15.0,
        price_protection_bps=10.0, stop_fraction=0.04, maximum_holding_days=14,
    )
    trade = result["trades"][0]
    assert trade["entry_row"] == 1
    assert trade["exit_reason"] == "protective_stop"
    assert trade["exit_reference"] == 96.0


def test_committed_contract_keeps_llm_l2_and_holdout_out_of_primary_experiment():
    root = Path(__file__).parents[1]
    contract = json.loads((root / "config/experiments/btc-online-regime-breakout-v1.json").read_text())
    assert contract["isolation"]["network_access_allowed"] is False
    assert contract["isolation"]["active_order_book_partial_access_allowed"] is False
    assert contract["llm_boundary"].startswith("No LLM output is used")
    assert contract["data"]["sealed_holdout_partition"].startswith("2026")


def test_committed_evidence_records_rejection_and_sealed_holdout():
    root = Path(__file__).parents[1]
    evidence = root / "artifacts/agent-level-experiment/btc-online-regime-breakout/development-v1"
    report = json.loads((evidence / "development-report.json").read_text())
    manifest = json.loads((evidence / "manifest.json").read_text())
    assert report["decision"] == "rejected_before_holdout"
    assert report["accepted_for_holdout_review"] is False
    assert report["holdout_accessed"] is False
    assert report["signals"]["breakout_conditions"] == 291
    assert report["combined_execution_scenarios"]["candle-primary-30bps-rt-v1"]["trade_count"] == 45
    assert len(report["gate_failures"]) == 9
    assert manifest["holdout_accessed"] is False
    for name, metadata in manifest["artifacts"].items():
        assert MODULE.sha256(evidence / name) == metadata["sha256"]
