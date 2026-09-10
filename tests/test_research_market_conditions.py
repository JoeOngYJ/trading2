from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.audit_btc_market_condition_inputs import DEFAULT_CONTRACT, run
from trading_platform.research_market_conditions import (
    InputAvailabilityMatrix,
    InputAvailabilityRecord,
    MarketConditionError,
    MarketConditionObservation,
    validate_observation_sequence,
)


UTC = timezone.utc
NOW = datetime(2025, 1, 2, 12, tzinfo=UTC)
DIGEST = "a" * 64


def observation(**updates: object) -> MarketConditionObservation:
    values = {
        "instrument": "BTCUSDT",
        "venue": "BINANCE_SPOT_RESEARCH",
        "axis": "persistence",
        "interval": "4h",
        "segment": "segment-1",
        "window_started_at": NOW - timedelta(hours=4),
        "observed_at": NOW,
        "available_at": NOW,
        "field_values": {"past_return": 0.01},
        "lineage_digests": {"source": DIGEST},
    }
    values.update(updates)
    return MarketConditionObservation(**values)  # type: ignore[arg-type]


def availability(**updates: object) -> InputAvailabilityRecord:
    values = {
        "dataset_id": "btc-candles",
        "instrument": "BTCUSDT",
        "status": "available_consumed_development",
        "intervals": ("5m",),
        "supported_axes": ("persistence",),
        "candidate_axes": (),
        "coverage_start": NOW - timedelta(days=30),
        "coverage_end_exclusive": NOW,
        "manifest_path": "artifacts/manifest.json",
        "manifest_sha256": DIGEST,
        "point_in_time_ready": True,
        "segment_policy": "no_crossing",
        "blockers": (),
    }
    values.update(updates)
    return InputAvailabilityRecord(**values)  # type: ignore[arg-type]


def test_observation_is_immutable_canonical_and_point_in_time():
    first = observation(field_values=(("z", 2.0), ("a", 1.0)))
    second = observation(field_values={"a": 1.0, "z": 2.0})
    assert first.as_dict() == second.as_dict()
    assert first.available_for(NOW)
    assert not first.available_for(NOW - timedelta(microseconds=1))
    with pytest.raises(TypeError):
        first.field_values["a"] = 3.0  # type: ignore[index]


def test_observation_rejects_noncausal_unknown_and_invalid_values():
    with pytest.raises(MarketConditionError, match="timestamps"):
        observation(available_at=NOW - timedelta(seconds=1))
    with pytest.raises(MarketConditionError, match="timezone-aware"):
        observation(observed_at=NOW.replace(tzinfo=None))
    with pytest.raises(MarketConditionError, match="unknown observation"):
        observation(unknown_reason="gap", field_values={"x": 1.0})
    with pytest.raises(MarketConditionError, match="known observation"):
        observation(field_values={})
    with pytest.raises(MarketConditionError, match="finite"):
        observation(field_values={"x": float("nan")})
    with pytest.raises(MarketConditionError, match="unsupported"):
        observation(axis="bull_bear")


def test_sequence_rejects_duplicates_reordering_and_segment_crossing():
    first = observation()
    second = observation(
        window_started_at=NOW,
        observed_at=NOW + timedelta(hours=4),
        available_at=NOW + timedelta(hours=4),
    )
    assert validate_observation_sequence((first, second)) == (first, second)
    with pytest.raises(MarketConditionError, match="duplicate"):
        validate_observation_sequence((first, first))
    with pytest.raises(MarketConditionError, match="segment"):
        validate_observation_sequence((first, observation(segment="segment-2")))
    with pytest.raises(MarketConditionError, match="strictly increasing"):
        validate_observation_sequence((second, first), require_single_segment=False)


def test_availability_fails_closed_for_blocked_and_ambiguous_sources():
    blocked = availability(
        status="blocked",
        supported_axes=(),
        candidate_axes=("liquidity_cost",),
        coverage_start=None,
        coverage_end_exclusive=None,
        point_in_time_ready=False,
        blockers=("OB1_not_accepted",),
    )
    assert blocked.as_dict()["supported_axes"] == []
    with pytest.raises(MarketConditionError, match="cannot support"):
        availability(status="blocked", blockers=("gap",))
    with pytest.raises(MarketConditionError, match="requires point-in-time"):
        availability(point_in_time_ready=False)
    with pytest.raises(MarketConditionError, match="both be present"):
        availability(coverage_end_exclusive=None)
    with pytest.raises(MarketConditionError, match="repository-relative"):
        availability(manifest_path="../secret")


def test_matrix_sorts_records_and_keeps_ready_proxy_and_blocked_separate():
    proxy = availability(
        dataset_id="proxy",
        status="proxy_only",
        supported_axes=(),
        candidate_axes=("liquidity_cost",),
        blockers=("no_cost_target",),
    )
    blocked = availability(
        dataset_id="book",
        status="blocked",
        supported_axes=(),
        candidate_axes=("liquidity_cost",),
        coverage_start=None,
        coverage_end_exclusive=None,
        point_in_time_ready=False,
        blockers=("OB1_not_accepted",),
    )
    matrix = InputAvailabilityMatrix((proxy, availability(), blocked))
    assert [item.dataset_id for item in matrix.records] == ["book", "btc-candles", "proxy"]
    assert matrix.axis_summary()["persistence"]["research_ready"] == ["btc-candles"]
    assert matrix.axis_summary()["liquidity_cost"] == {
        "blocked_or_absent": ["book"],
        "proxy_only": ["proxy"],
        "research_ready": [],
    }


def test_mcs1_audit_is_metadata_only_and_deterministic(tmp_path: Path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    run(DEFAULT_CONTRACT, first)
    run(DEFAULT_CONTRACT, second)
    assert (first / "availability-report.json").read_bytes() == (
        second / "availability-report.json"
    ).read_bytes()
    assert (first / "evidence-manifest.json").read_bytes() == (
        second / "evidence-manifest.json"
    ).read_bytes()
    report = json.loads((first / "availability-report.json").read_text())
    assert report["decision"] == "mcs1_passed_metadata_only"
    assert report["invariants"]["market_data_feature_label_or_pnl_files_opened"] == 0
    assert report["invariants"]["models_or_scores_fitted"] is False
    assert report["accepted_strategy_arms"] == []
    assert report["actionable_arm_id"] == "no_trade"


def test_module_has_no_production_or_external_client_imports():
    root = Path(__file__).resolve().parents[1]
    source = (root / "src/trading_platform/research_market_conditions.py").read_text()
    for forbidden in (
        "ccxt",
        "freqtrade",
        "nats",
        "psycopg",
        "requests",
        "sqlalchemy",
        "trading_platform.signals",
    ):
        assert forbidden not in source.lower()
