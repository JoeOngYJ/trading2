from __future__ import annotations

import ast
import gzip
import hashlib
import importlib.util
import json
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from trading_platform.btc_breakout_events import (
    ONE_HOUR_MS,
    PATH_LIFETIME_MS,
    BreakoutEventError,
    build_breakout_event_catalogue,
    linear_quantile,
    load_breakout_source_candles,
)
from trading_platform.research_ledger import FIVE_MINUTES_MS, FOUR_HOURS_MS


ROOT = Path(__file__).resolve().parents[1]
DIGEST = "a" * 64
EXPERIMENT = "btc-upside-compression-breakout-v1-bex1-v3"


def catalogue(rows):
    return build_breakout_event_catalogue(
        rows, source_digest=DIGEST, experiment_id=EXPERIMENT
    )


def load_runner():
    path = ROOT / "scripts/run_btc_breakout_event_catalogue.py"
    spec = importlib.util.spec_from_file_location("run_btc_breakout_event_catalogue", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@dataclass(frozen=True, slots=True)
class CandleWithTrades:
    """SourceCandle-compatible fixture preserving the canonical trade count."""

    segment: int
    open_ms: int
    open: float
    high: float
    low: float
    close: float
    base_volume: float
    quote_volume: float
    source_row: int
    trade_count: int

    @property
    def close_ms(self) -> int:
        return self.open_ms + FIVE_MINUTES_MS


def source_rows(
    bars: int = 700,
    *,
    segment: int = 1,
    start_ms: int = 0,
    narrow_from: int = 538,
) -> list[CandleWithTrades]:
    rows: list[CandleWithTrades] = []
    for bar_index in range(bars):
        price = 100.0 + (bar_index % 11) * 0.01
        narrow = bar_index >= narrow_from
        high = 100.60 if narrow else 110.0
        low = 99.40 if narrow else 90.0
        for within in range(48):
            index = len(rows)
            open_ms = start_ms + (bar_index * 48 + within) * FIVE_MINUTES_MS
            rows.append(
                CandleWithTrades(
                    segment=segment,
                    open_ms=open_ms,
                    open=price,
                    high=max(price, high if within == 0 else price),
                    low=min(price, low if within == 0 else price),
                    close=price,
                    base_volume=1.0,
                    quote_volume=100.0,
                    source_row=index,
                    trade_count=2,
                )
            )
    return rows


def set_hour(
    rows: list[CandleWithTrades], start_ms: int, close: float, *, high: float | None = None
) -> list[CandleWithTrades]:
    changed = list(rows)
    for index, row in enumerate(changed):
        if start_ms <= row.open_ms < start_ms + ONE_HOUR_MS:
            value_high = max(close, high if high is not None else close)
            changed[index] = replace(row, open=close, high=value_high, low=close, close=close)
    return changed


def test_linear_quantile_is_frozen_linear_interpolation():
    assert linear_quantile([0.0, 10.0], 0.2) == 2.0
    with pytest.raises(BreakoutEventError):
        linear_quantile([], 0.2)


def test_range_is_strictly_before_activation_and_future_mutation_is_causal():
    rows = source_rows()
    first = catalogue(rows)
    assert first.episodes
    episode = first.episodes[0]

    activation_row = episode.activation_ms // FIVE_MINUTES_MS - 1
    changed = list(rows)
    changed[activation_row] = replace(changed[activation_row], high=500.0)
    replay = catalogue(changed)

    assert replay.episodes[0].activation_ms == episode.activation_ms
    assert replay.episodes[0].upper_boundary == episode.upper_boundary
    assert episode.upper_boundary == pytest.approx(100.60)
    assert episode.compression_duration_hours == 12
    assert episode.compression_percentile <= 0.20


def test_compression_percentile_uses_midrank_for_tied_widths():
    episode = catalogue(source_rows(narrow_from=0)).episodes[0]
    assert episode.compression_percentile == pytest.approx(0.5)


def test_confirmation_delay_is_causal_and_decision_cutoff_excludes_boundary_activation():
    base = source_rows()
    activation = catalogue(base).episodes[0].activation_ms
    rows = set_hour(base, activation, 101.0)
    rows = set_hour(rows, activation + ONE_HOUR_MS, 102.0)
    built = build_breakout_event_catalogue(
        rows,
        source_digest="a" * 64,
        experiment_id="fixture",
    )
    episode = built.episodes[0]
    assert episode.confirmation_delay_hours == (
        episode.confirmation_ms - episode.activation_ms
    ) // ONE_HOUR_MS
    cutoff = episode.activation_ms
    excluded = build_breakout_event_catalogue(
        rows,
        source_digest="a" * 64,
        experiment_id="fixture-cutoff",
        decision_end_exclusive_ms=cutoff,
    )
    assert all(item.activation_ms < cutoff for item in excluded.episodes)


def test_confirmation_uses_completed_hour_and_features_exclude_confirmation_volume():
    base = source_rows()
    activation = catalogue(base).episodes[0].activation_ms
    confirmed = set_hour(base, activation, 101.0)
    confirmed = set_hour(confirmed, activation + ONE_HOUR_MS, 102.0)
    fill_index = (activation + ONE_HOUR_MS) // FIVE_MINUTES_MS
    confirmed[fill_index] = replace(confirmed[fill_index], open=101.0, low=101.0)
    result = catalogue(confirmed)
    episode = result.episodes[0]

    assert episode.confirmation_ms == activation + ONE_HOUR_MS
    assert episode.first_eligible_5m_ms == episode.confirmation_ms
    assert episode.confirmation_hour_fraction_5m_closes_above_upper == 1.0
    assert episode.pre_sigma24 is not None and episode.pre_sigma24 > 0.0
    assert episode.pre_sigma7d is not None and episode.pre_sigma7d > 0.0
    assert episode.model_ready
    assert episode.augmented_diagnostic_ready
    assert episode.lagged_24h_quote_volume_surprise == pytest.approx(0.0)
    assert episode.lagged_24h_trade_count_surprise == pytest.approx(0.0)
    assert episode.first_continuation_target_ms == episode.confirmation_ms + ONE_HOUR_MS
    assert episode.competing_outcome == "continuation"
    assert episode.censor_reason is None
    assert [snapshot.horizon_hours for snapshot in episode.snapshots] == [24, 72, 168]
    assert all(snapshot.complete for snapshot in episode.snapshots)
    assert all(
        snapshot.time_to_maximum_favourable_excursion_hours is not None
        and snapshot.time_to_maximum_adverse_excursion_hours is not None
        for snapshot in episode.snapshots
    )

    # Trigger-hour volume is prohibited: changing it cannot alter the lagged feature.
    noisy = list(confirmed)
    for index, row in enumerate(noisy):
        if activation <= row.open_ms < activation + ONE_HOUR_MS:
            noisy[index] = replace(row, quote_volume=1_000_000.0, trade_count=1_000_000)
    replay = catalogue(noisy).episodes[0]
    assert replay.lagged_24h_quote_volume_surprise == episode.lagged_24h_quote_volume_surprise
    assert replay.lagged_24h_trade_count_surprise == episode.lagged_24h_trade_count_surprise


def test_reentry_is_hourly_and_has_adverse_tie_precedence():
    base = source_rows()
    activation = catalogue(base).episodes[0].activation_ms
    confirmed = set_hour(base, activation, 101.0)
    reentered = set_hour(confirmed, activation + ONE_HOUR_MS, 100.0, high=500.0)
    episode = catalogue(reentered).episodes[0]

    # A very high five-minute high is not a continuation label; labels use completed 1h closes.
    assert episode.first_continuation_target_ms is None
    assert episode.first_reentry_ms == episode.confirmation_ms + ONE_HOUR_MS
    assert episode.competing_outcome == "range_reentry"


def test_confirmed_episode_with_fill_not_above_upper_is_retained_but_not_model_ready():
    base = source_rows()
    activation = catalogue(base).episodes[0].activation_ms
    confirmed = set_hour(base, activation, 101.0)
    episode = catalogue(confirmed).episodes[0]
    assert episode.confirmation_ms is not None
    assert episode.first_eligible_price <= episode.upper_boundary
    assert not episode.model_ready
    assert "fill_not_above_frozen_upper" in episode.model_unavailable_reasons


def test_path_segment_end_is_censoring_and_missing_trade_count_is_diagnostic_only():
    base = source_rows()
    activation = catalogue(base).episodes[0].activation_ms
    confirmed = set_hour(base, activation, 101.0)
    cutoff = activation + 10 * ONE_HOUR_MS
    for hour_start in range(
        activation + ONE_HOUR_MS, cutoff, ONE_HOUR_MS
    ):
        confirmed = set_hour(confirmed, hour_start, 101.0)
    truncated = [row for row in confirmed if row.close_ms <= cutoff]
    without_trades = [
        # Use actual SourceCandle-compatible objects without the optional diagnostic field.
        type("Plain", (), {
            "segment": row.segment,
            "open_ms": row.open_ms,
            "open": row.open,
            "high": row.high,
            "low": row.low,
            "close": row.close,
            "base_volume": row.base_volume,
            "quote_volume": row.quote_volume,
            "source_row": row.source_row,
            "close_ms": row.close_ms,
        })()
        for row in truncated
    ]
    episode = catalogue(without_trades).episodes[0]

    assert episode.path_segment_censored
    assert episode.competing_outcome is None
    assert episode.censor_reason == "source_segment_end"
    assert episode.model_ready
    assert not episode.augmented_diagnostic_ready
    assert "trade_count_unavailable" in episode.augmented_diagnostic_unavailable_reasons
    assert not episode.snapshots[0].complete


def test_gap_fails_closed_and_segment_histories_never_bridge():
    rows = source_rows(300)
    gapped = rows[:100] + rows[101:]
    gapped = [replace(row, source_row=index) for index, row in enumerate(gapped)]
    with pytest.raises(BreakoutEventError, match="gap inside"):
        catalogue(gapped)

    first = source_rows(300, segment=1)
    second_start = first[-1].close_ms + FOUR_HOURS_MS
    second = source_rows(300, segment=2, start_ms=second_start)
    combined = first + [replace(row, source_row=len(first) + index) for index, row in enumerate(second)]
    result = catalogue(combined)
    assert result.episodes == ()


def test_confirmed_episode_paths_do_not_overlap_and_equality_is_allowed():
    base = source_rows(850)
    initial = catalogue(base)
    activation = initial.episodes[0].activation_ms
    confirmed = set_hour(base, activation, 101.0)
    result = catalogue(confirmed)
    confirmed_episodes = [episode for episode in result.episodes if episode.confirmation_ms]
    assert all(
        right.activation_ms >= left.confirmation_ms + PATH_LIFETIME_MS
        for left, right in zip(confirmed_episodes, confirmed_episodes[1:])
    )
    assert all(
        right.activation_ms >= left.confirmation_ms + PATH_LIFETIME_MS + 2 * FOUR_HOURS_MS
        for left, right in zip(confirmed_episodes, confirmed_episodes[1:])
    )


def test_milestones_cannot_be_recorded_after_downside_termination():
    base = source_rows()
    first = catalogue(base).episodes[0]
    invalidated = set_hour(base, first.activation_ms, 90.0)
    invalidated = set_hour(invalidated, first.activation_ms + ONE_HOUR_MS, 120.0)
    episode = catalogue(invalidated).episodes[0]
    assert episode.termination_reason == "downside_invalidation"
    assert episode.first_5m_touch_ms is None
    assert episode.first_5m_close_cross_ms is None


def test_confirmation_at_setup_deadline_is_eligible_and_gets_full_path():
    base = source_rows(800)
    first = catalogue(base).episodes[0]
    final_hour = first.activation_ms + PATH_LIFETIME_MS - ONE_HOUR_MS
    confirmed = set_hour(base, final_hour, 101.0)
    episode = catalogue(confirmed).episodes[0]
    assert episode.confirmation_ms == first.activation_ms + PATH_LIFETIME_MS
    assert episode.termination_reason == "upside_confirmation"
    assert episode.path_observed_until_ms == episode.confirmation_ms + PATH_LIFETIME_MS


def test_source_identity_and_optional_trade_count_fail_closed():
    rows = source_rows(10)
    changed = list(rows)
    changed[3] = replace(changed[3], source_row=99)
    with pytest.raises(BreakoutEventError, match="invalid source"):
        catalogue(changed)
    changed = list(rows)
    changed[3] = replace(changed[3], trade_count=-1)
    with pytest.raises(BreakoutEventError, match="invalid source"):
        catalogue(changed)


def test_isolated_loader_preserves_raw_trade_count_and_checksum(tmp_path):
    path = tmp_path / "development.csv.gz"
    header = (
        "segment_id,open_time_ms,close_time_ms,open,high,low,close,base_volume,quote_volume,trade_count\n"
    )
    body = "1,0,299999,100,101,99,100,1,100,7\n"
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        handle.write(header + body)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    rows, actual = load_breakout_source_candles(path, digest)
    assert actual == digest
    assert rows[0].trade_count == 7
    with pytest.raises(BreakoutEventError, match="checksum"):
        load_breakout_source_candles(path, "0" * 64)


def test_runner_requires_and_emits_exact_contract_experiment_id(tmp_path):
    source = tmp_path / "source.csv.gz"
    header = (
        "segment_id,open_time_ms,close_time_ms,open,high,low,close,base_volume,quote_volume,trade_count\n"
    )
    with gzip.open(source, "wt", encoding="utf-8", newline="") as handle:
        handle.write(header + "1,0,299999,100,101,99,100,1,100,7\n")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    experiment_id = "btc-upside-compression-breakout-v1-bex1-v3"
    contract = {
        "action_boundary": {"actionable_arm_id": "no_trade"},
        "bound_inputs": [{"path": "source.csv.gz", "sha256": digest}],
        "catalogue_rules": {
            "activation_expiry_hours": 168,
            "compression_quantile": 0.2,
            "compression_reference_widths": 540,
            "compression_required_consecutive_bars": 3,
            "range_bars": 42,
        },
        "experiment_id": experiment_id,
        "input_contract": {"expected_rows": 1},
        "label_rules": {
            "administrative_horizon_hours": 168,
            "event_tie_precedence": "range_reentry",
        },
        "outputs": {
            "catalogue": "out/events.jsonl.gz",
            "evidence_manifest": "out/manifest.json",
            "preflight_report": "out/report.json",
        },
        "status": "frozen_before_historical_event_outcomes",
    }
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(contract), encoding="utf-8")
    runner = load_runner()
    result = runner.run(contract_path, experiment_id, tmp_path)
    assert result["experiment_id"] == experiment_id
    assert result["episode_count"] == 0
    assert result["confirmed_episode_count"] == 0
    assert result["continuation_count"] == 0
    assert result["range_reentry_count"] == 0
    assert result["right_censored_count"] == 0
    assert result["source_last_close_before_2026"]
    assert (tmp_path / "out/events.jsonl.gz").exists()
    assert (tmp_path / "out/report.json").exists()
    assert (tmp_path / "out/manifest.json").exists()
    with pytest.raises(BreakoutEventError, match="refusing to overwrite"):
        runner.run(contract_path, experiment_id, tmp_path)
    with pytest.raises(BreakoutEventError, match="does not exactly match"):
        runner.run(contract_path, "wrong-id", tmp_path)


def test_runner_materializes_the_checksummed_v3_successor_without_source_access():
    runner = load_runner()
    experiment_id = "btc-upside-compression-breakout-v1-bex1-v3"
    contract = runner._contract(
        ROOT / "research/btc/contracts/btc-breakout-event-catalogue-v3.json",
        experiment_id,
        ROOT,
    )
    assert contract["experiment_id"] == experiment_id
    assert contract["status"] == "frozen_validated_successor_before_historical_event_outcomes"
    assert contract["action_boundary"]["actionable_arm_id"] == "no_trade"


def test_catalogue_and_record_digests_are_deterministic_and_non_actionable():
    rows = source_rows()
    first = catalogue(rows)
    second = catalogue(rows)
    assert first.catalogue_digest == second.catalogue_digest
    assert first.episodes[0].record_digest == second.episodes[0].record_digest
    assert first.as_dict()["actionable_arm_id"] == "no_trade"


def test_module_is_offline_and_cannot_import_execution_or_runtime_clients():
    path = ROOT / "src/trading_platform/btc_breakout_events.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    forbidden = {
        "ccxt",
        "httpx",
        "nats",
        "psycopg",
        "requests",
        "trading_platform.execution_model",
    }
    assert not imports.intersection(forbidden)
