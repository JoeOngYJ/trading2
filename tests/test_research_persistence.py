from __future__ import annotations

import gzip
import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from trading_platform.research_persistence import (
    PersistenceCandle,
    PersistenceResearchError,
    build_rows,
    canonical_line,
    load_candles,
    month_block_bootstrap,
    ols_hac,
    spearman_rank_correlation,
    walk_forward_forecasts,
)


UTC = timezone.utc


def candle(index: int, *, segment: str = "s1", close: float | None = None) -> PersistenceCandle:
    opened = datetime(2018, 1, 1, tzinfo=UTC) + timedelta(hours=4 * index)
    return PersistenceCandle(
        segment=segment,
        open_at=opened,
        close_at=opened + timedelta(hours=4),
        close=close if close is not None else 100.0 * math.exp(0.001 * index),
    )


def write_candle_ledger(path: Path, rows: list[dict[str, object]]) -> str:
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            for row in rows:
                compressed.write((canonical_line(row) + "\n").encode())
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ledger_row(index: int, *, segment: str = "s1", timestamp: str | None = None) -> dict[str, object]:
    opened = datetime(2018, 1, 1, tzinfo=UTC) + timedelta(hours=4 * index)
    closed = opened + timedelta(hours=4)
    close_at = timestamp or closed.strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "available_at": close_at,
        "close": 100.0 + index,
        "close_at": close_at,
        "instrument": "BTC/USDT",
        "interval": "4h",
        "observed_at": close_at,
        "open_at": opened.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "segment": segment,
    }


def test_loader_rejects_naive_or_noncanonical_time_and_inside_segment_gap(tmp_path: Path):
    path = tmp_path / "candles.jsonl.gz"
    rows = [ledger_row(0), ledger_row(1)]
    rows[1]["observed_at"] = "2018-01-01T08:00:00"
    digest = write_candle_ledger(path, rows)
    with pytest.raises(PersistenceResearchError, match="canonical"):
        load_candles(path, digest, 2)

    rows = [ledger_row(0), ledger_row(2)]
    digest = write_candle_ledger(path, rows)
    with pytest.raises(PersistenceResearchError, match="gap inside segment"):
        load_candles(path, digest, 2)


def test_loader_rejects_changed_digest_and_reappearing_segment(tmp_path: Path):
    path = tmp_path / "candles.jsonl.gz"
    rows = [ledger_row(0, segment="a"), ledger_row(1, segment="b"), ledger_row(2, segment="a")]
    digest = write_candle_ledger(path, rows)
    with pytest.raises(PersistenceResearchError, match="checksum"):
        load_candles(path, "0" * 64, 3)
    with pytest.raises(PersistenceResearchError, match="reappears"):
        load_candles(path, digest, 3)


def test_feature_and_target_windows_never_cross_segments():
    rows = [candle(index, segment="a") for index in range(100)]
    rows.extend(candle(index, segment="b") for index in range(100, 200))
    built = build_rows(rows, {"4h": 1, "1d": 6, "7d": 42}, trailing_returns=42)
    assert len(built["7d"]) == 2 * (100 - 42 - 42)
    assert sum(row.segment == "a" for row in built["7d"]) == 16
    assert sum(row.segment == "b" for row in built["7d"]) == 16
    assert all(row.target_available_at > row.observed_at for values in built.values() for row in values)


def test_signed_efficiency_and_targets_match_frozen_formula():
    closes = [100.0]
    returns = [0.02, -0.01, 0.03, -0.01]
    for value in returns:
        closes.append(closes[-1] * math.exp(value))
    rows = [candle(index, close=value) for index, value in enumerate(closes)]
    built = build_rows(rows, {"4h": 1}, trailing_returns=3)["4h"]
    first = built[0]
    assert first.benchmark_score == pytest.approx(sum(returns[:3]))
    assert first.candidate_score == pytest.approx(sum(returns[:3]) / sum(abs(x) for x in returns[:3]))
    assert first.target_return == pytest.approx(returns[3])


def test_walk_forward_fit_uses_only_labels_strictly_before_month_cutoff():
    closes = [100.0]
    for index in range(1, 1600):
        varying_return = 0.0005 + 0.002 * math.sin(index / 11) + 0.001 * math.cos(index / 37)
        closes.append(closes[-1] * math.exp(varying_return))
    rows = [candle(index, close=value) for index, value in enumerate(closes)]
    built = build_rows(rows, {"4h": 1}, trailing_returns=42)["4h"]
    forecasts = walk_forward_forecasts(
        built,
        evaluation_start=datetime(2018, 6, 1, tzinfo=UTC),
        evaluation_end=datetime(2018, 10, 1, tzinfo=UTC),
        minimum_training_rows=252,
    )
    assert forecasts
    for forecast in forecasts:
        cutoff = datetime.strptime(forecast["fit_cutoff"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        eligible = [row for row in built if row.target_available_at < cutoff]
        assert forecast["training_rows"] == len(eligible)
        assert cutoff <= datetime.strptime(forecast["observed_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def test_hac_rank_and_month_bootstrap_are_deterministic_and_positive():
    benchmark = [math.sin(index) for index in range(200)]
    candidate = [((index % 17) - 8) / 8 for index in range(200)]
    target = [0.1 * benchmark[index] + 0.5 * candidate[index] for index in range(200)]
    result = ols_hac(target, [benchmark, candidate], lag=6)
    assert result["coefficients"][2] == pytest.approx(0.5)
    assert result["ci95"][2][0] > 0
    assert spearman_rank_correlation(candidate, target) > 0
    first = month_block_bootstrap([0.1, 0.2, 0.3], replications=200, seed=7)
    second = month_block_bootstrap([0.1, 0.2, 0.3], replications=200, seed=7)
    assert first == second
    assert first["ci95"][0] > 0


def test_module_has_no_strategy_or_external_client_imports():
    source = (
        Path(__file__).resolve().parents[1]
        / "src/trading_platform/research_persistence.py"
    ).read_text(encoding="utf-8").lower()
    for forbidden in (
        "ccxt",
        "freqtrade",
        "httpx",
        "nats",
        "psycopg",
        "requests",
        "signalpayload",
        "orderintent",
    ):
        assert forbidden not in source
