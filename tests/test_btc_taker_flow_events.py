import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "analyze_btc_taker_flow_events.py"
SPEC = importlib.util.spec_from_file_location("analyze_btc_taker_flow_events", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_quantile_interpolates_deterministically():
    assert MODULE.quantile([0, 10], 0.25) == 2.5
    assert MODULE.quantile([3, 1, 2], 0.5) == 2


def test_summary_sign_adjusts_negative_events():
    result = MODULE.summarize([-0.01, -0.02, None, 0.01], -1, 7)
    assert result["events"] == 3
    assert result["continuation_mean"] > 0
    assert result["direction_hit_rate"] == 2 / 3


def test_bootstrap_is_reproducible():
    values = [0.01 if i % 7 == 0 else None for i in range(600)]
    assert MODULE.daily_block_bootstrap(values, 42, 100) == MODULE.daily_block_bootstrap(values, 42, 100)


def test_forward_return_starts_after_event_bar():
    base = 1_704_067_200_000
    bars = [MODULE.Bar(base + i * MODULE.BAR_MS, close, imbalance) for i, (close, imbalance) in enumerate([
        (100, 1.0), (110, 0.0), (121, -1.0), (108.9, 0.0), (108.9, 0.0),
    ])]
    report = MODULE.analyze(bars, -0.5, 0.5)
    positive = report["splits"]["train_2024"]["5m"]["positive_imbalance"]
    negative = report["splits"]["train_2024"]["5m"]["negative_imbalance"]
    assert positive["mean_forward_log_return"] > 0
    assert negative["mean_forward_log_return"] < 0


def test_sealed_holdout_requires_frozen_matching_hypothesis(tmp_path):
    manifest = {"partition": "holdout-2026-01-07"}
    with pytest.raises(ValueError, match="requires"):
        MODULE.enforce_holdout_access(manifest, "abc", None)
    hypothesis = tmp_path / "hypothesis.json"
    hypothesis.write_text('{"status":"frozen","holdout_dataset_sha256":"abc"}')
    MODULE.enforce_holdout_access(manifest, "abc", hypothesis)
    with pytest.raises(ValueError, match="not frozen"):
        MODULE.enforce_holdout_access(manifest, "different", hypothesis)
