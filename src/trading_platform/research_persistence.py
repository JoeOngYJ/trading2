"""Offline, causal persistence-information evaluation for frozen BTC candle ledgers.

This module has no strategy, position, cost, exchange, database, message-bus, or network code.
It transforms a validated local candle ledger into descriptive scores and forward-return labels.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import math
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np


UTC = timezone.utc
FOUR_HOURS_SECONDS = 14_400


class PersistenceResearchError(ValueError):
    """Raised when frozen persistence inputs or causal calculations are invalid."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(value: object) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"


def canonical_line(value: object) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def parse_utc_z(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z") or "." in value:
        raise PersistenceResearchError(f"{label} must be canonical whole-second UTC Z")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as exc:
        raise PersistenceResearchError(f"invalid {label}") from exc
    return parsed


def iso_z(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
        raise PersistenceResearchError("timestamp must be UTC aware")
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True, slots=True)
class PersistenceCandle:
    segment: str
    open_at: datetime
    close_at: datetime
    close: float


@dataclass(frozen=True, slots=True)
class PersistenceRow:
    segment: str
    observed_at: datetime
    target_available_at: datetime
    horizon: str
    horizon_bars: int
    benchmark_score: float
    candidate_score: float
    target_return: float


def _reject_symlinks(path: Path) -> None:
    candidate = path.absolute()
    for item in (candidate, *candidate.parents):
        if item.is_symlink():
            raise PersistenceResearchError(f"symlinked frozen input is prohibited: {item}")


def load_candles(path: Path, expected_sha256: str, expected_rows: int) -> list[PersistenceCandle]:
    _reject_symlinks(path)
    resolved = path.resolve(strict=True)
    lowered = str(resolved).lower()
    if "holdout" in lowered or "2026" in resolved.name.lower():
        raise PersistenceResearchError("sealed or holdout input path is prohibited")
    actual = sha256_file(resolved)
    if actual != expected_sha256:
        raise PersistenceResearchError(
            f"candle checksum mismatch: expected {expected_sha256}, got {actual}"
        )
    rows: list[PersistenceCandle] = []
    previous: PersistenceCandle | None = None
    closed_segments: set[str] = set()
    with gzip.open(resolved, "rt", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            try:
                item = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise PersistenceResearchError(f"invalid JSON at candle line {line_number}") from exc
            required = {
                "available_at",
                "close",
                "close_at",
                "instrument",
                "interval",
                "observed_at",
                "open_at",
                "segment",
            }
            if not isinstance(item, dict) or not required.issubset(item):
                raise PersistenceResearchError(f"missing candle fields at line {line_number}")
            if item["instrument"] != "BTC/USDT" or item["interval"] != "4h":
                raise PersistenceResearchError(f"wrong instrument or interval at line {line_number}")
            observed = parse_utc_z(item["observed_at"], "observed_at")
            available = parse_utc_z(item["available_at"], "available_at")
            close_at = parse_utc_z(item["close_at"], "close_at")
            open_at = parse_utc_z(item["open_at"], "open_at")
            if observed != available or observed != close_at:
                raise PersistenceResearchError(f"non-causal availability at line {line_number}")
            if (close_at - open_at).total_seconds() != FOUR_HOURS_SECONDS:
                raise PersistenceResearchError(f"wrong candle width at line {line_number}")
            try:
                close = float(item["close"])
            except (TypeError, ValueError) as exc:
                raise PersistenceResearchError(f"invalid close at line {line_number}") from exc
            if not math.isfinite(close) or close <= 0:
                raise PersistenceResearchError(f"non-positive or non-finite close at line {line_number}")
            segment = item["segment"]
            if not isinstance(segment, str) or not segment:
                raise PersistenceResearchError(f"invalid segment at line {line_number}")
            row = PersistenceCandle(segment, open_at, close_at, close)
            if previous is not None:
                if row.close_at <= previous.close_at:
                    raise PersistenceResearchError(f"non-increasing close time at line {line_number}")
                if row.segment == previous.segment:
                    if row.open_at != previous.close_at:
                        raise PersistenceResearchError(f"gap inside segment at line {line_number}")
                else:
                    closed_segments.add(previous.segment)
                    if row.segment in closed_segments:
                        raise PersistenceResearchError(f"segment reappears at line {line_number}")
            rows.append(row)
            previous = row
    if len(rows) != expected_rows:
        raise PersistenceResearchError(
            f"candle row count mismatch: expected {expected_rows}, got {len(rows)}"
        )
    return rows


def build_rows(
    candles: Sequence[PersistenceCandle],
    horizons: Mapping[str, int],
    *,
    trailing_returns: int = 42,
) -> dict[str, list[PersistenceRow]]:
    if trailing_returns < 2 or not horizons or any(value <= 0 for value in horizons.values()):
        raise PersistenceResearchError("invalid persistence window or horizons")
    output = {name: [] for name in horizons}
    start = 0
    while start < len(candles):
        end = start + 1
        while end < len(candles) and candles[end].segment == candles[start].segment:
            end += 1
        segment = candles[start:end]
        closes = np.asarray([row.close for row in segment], dtype=float)
        returns = np.diff(np.log(closes))
        for local_index in range(trailing_returns, len(segment)):
            window = returns[local_index - trailing_returns : local_index]
            benchmark = float(window.sum())
            path_length = float(np.abs(window).sum())
            if not math.isfinite(benchmark) or path_length <= 0:
                continue
            candidate = benchmark / path_length
            observed = segment[local_index].close_at
            for name, bars in horizons.items():
                target_index = local_index + bars
                if target_index >= len(segment):
                    continue
                target = math.log(segment[target_index].close / segment[local_index].close)
                if not math.isfinite(target):
                    raise PersistenceResearchError("non-finite forward return")
                output[name].append(
                    PersistenceRow(
                        segment=segment[local_index].segment,
                        observed_at=observed,
                        target_available_at=segment[target_index].close_at,
                        horizon=name,
                        horizon_bars=bars,
                        benchmark_score=benchmark,
                        candidate_score=candidate,
                        target_return=target,
                    )
                )
        start = end
    return output


def ols_coefficients(y: Sequence[float], columns: Sequence[Sequence[float]]) -> np.ndarray:
    dependent = np.asarray(y, dtype=float)
    design = np.column_stack([np.ones(len(dependent)), *[np.asarray(x) for x in columns]])
    if len(dependent) < design.shape[1] + 2 or not np.isfinite(design).all() or not np.isfinite(dependent).all():
        raise PersistenceResearchError("invalid or insufficient OLS inputs")
    coefficients, _, rank, _ = np.linalg.lstsq(design, dependent, rcond=None)
    if rank != design.shape[1]:
        raise PersistenceResearchError("rank-deficient OLS design")
    return coefficients


def ols_hac(
    y: Sequence[float], columns: Sequence[Sequence[float]], lag: int
) -> dict[str, Any]:
    dependent = np.asarray(y, dtype=float)
    design = np.column_stack([np.ones(len(dependent)), *[np.asarray(x) for x in columns]])
    if lag < 0 or lag >= len(dependent):
        raise PersistenceResearchError("invalid HAC lag")
    coefficients = ols_coefficients(dependent, columns)
    residual = dependent - design @ coefficients
    inverse = np.linalg.pinv(design.T @ design)
    meat = np.zeros((design.shape[1], design.shape[1]), dtype=float)
    for index in range(len(dependent)):
        xu = design[index] * residual[index]
        meat += np.outer(xu, xu)
    for offset in range(1, lag + 1):
        weight = 1.0 - offset / (lag + 1.0)
        cross = np.zeros_like(meat)
        for index in range(offset, len(dependent)):
            cross += np.outer(
                design[index] * residual[index],
                design[index - offset] * residual[index - offset],
            )
        meat += weight * (cross + cross.T)
    covariance = inverse @ meat @ inverse
    standard_errors = np.sqrt(np.maximum(np.diag(covariance), 0.0))
    return {
        "coefficients": coefficients.tolist(),
        "standard_errors": standard_errors.tolist(),
        "ci95": [
            [float(value - 1.96 * error), float(value + 1.96 * error)]
            for value, error in zip(coefficients, standard_errors, strict=True)
        ],
        "lag": lag,
        "observations": len(dependent),
    }


def _average_ranks(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values), dtype=float)
    start = 0
    while start < len(values):
        end = start + 1
        while end < len(values) and values[order[end]] == values[order[start]]:
            end += 1
        ranks[order[start:end]] = (start + end - 1) / 2.0
        start = end
    return ranks


def spearman_rank_correlation(x: Sequence[float], y: Sequence[float]) -> float:
    left = np.asarray(x, dtype=float)
    right = np.asarray(y, dtype=float)
    if len(left) < 3 or len(left) != len(right) or not np.isfinite(left).all() or not np.isfinite(right).all():
        raise PersistenceResearchError("invalid rank-correlation inputs")
    left_rank = _average_ranks(left)
    right_rank = _average_ranks(right)
    if left_rank.std() == 0 or right_rank.std() == 0:
        raise PersistenceResearchError("constant rank-correlation input")
    return float(np.corrcoef(left_rank, right_rank)[0, 1])


def percentile_interval(values: Sequence[float], confidence: float = 0.95) -> list[float]:
    observations = np.asarray(values, dtype=float)
    if len(observations) == 0 or not np.isfinite(observations).all():
        raise PersistenceResearchError("invalid interval values")
    tail = (1.0 - confidence) / 2.0
    return [float(np.quantile(observations, tail)), float(np.quantile(observations, 1 - tail))]


def month_block_bootstrap(
    month_statistics: Sequence[float], *, replications: int, seed: int
) -> dict[str, Any]:
    values = np.asarray(month_statistics, dtype=float)
    if len(values) < 2 or not np.isfinite(values).all() or replications <= 0:
        raise PersistenceResearchError("invalid month-block bootstrap inputs")
    rng = random.Random(seed)
    samples = []
    for _ in range(replications):
        samples.append(float(np.mean([values[rng.randrange(len(values))] for _ in values])))
    return {
        "estimate": float(values.mean()),
        "ci95": percentile_interval(samples),
        "month_blocks": len(values),
        "replications": replications,
        "valid_replications": len(samples),
    }


def month_key(value: datetime) -> str:
    return value.strftime("%Y-%m")


def month_start(value: datetime) -> datetime:
    return value.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _quintile_thresholds(values: Sequence[float]) -> list[float]:
    array = np.asarray(values, dtype=float)
    return [float(x) for x in np.quantile(array, [0.2, 0.4, 0.6, 0.8])]


def _bucket(value: float, thresholds: Sequence[float]) -> int:
    return 1 + sum(value > threshold for threshold in thresholds)


def walk_forward_forecasts(
    rows: Sequence[PersistenceRow],
    *,
    evaluation_start: datetime,
    evaluation_end: datetime,
    minimum_training_rows: int,
) -> list[dict[str, Any]]:
    ordered = sorted(rows, key=lambda row: row.observed_at)
    evaluation = [
        row
        for row in ordered
        if evaluation_start <= row.observed_at < evaluation_end
        and row.target_available_at < evaluation_end
    ]
    output: list[dict[str, Any]] = []
    models: dict[datetime, tuple[np.ndarray, np.ndarray, list[float], int]] = {}
    for row in evaluation:
        cutoff = month_start(row.observed_at)
        if cutoff not in models:
            training = [candidate for candidate in ordered if candidate.target_available_at < cutoff]
            if len(training) < minimum_training_rows:
                raise PersistenceResearchError(f"insufficient training rows at {iso_z(cutoff)}")
            y = [candidate.target_return for candidate in training]
            benchmark = [candidate.benchmark_score for candidate in training]
            score = [candidate.candidate_score for candidate in training]
            benchmark_coefficients = ols_coefficients(y, [benchmark])
            candidate_coefficients = ols_coefficients(y, [benchmark, score])
            models[cutoff] = (
                benchmark_coefficients,
                candidate_coefficients,
                _quintile_thresholds(score),
                len(training),
            )
        benchmark_coefficients, candidate_coefficients, thresholds, training_count = models[cutoff]
        benchmark_prediction = float(
            benchmark_coefficients @ np.asarray([1.0, row.benchmark_score])
        )
        candidate_prediction = float(
            candidate_coefficients
            @ np.asarray([1.0, row.benchmark_score, row.candidate_score])
        )
        output.append(
            {
                "benchmark_prediction": benchmark_prediction,
                "benchmark_score": row.benchmark_score,
                "candidate_prediction": candidate_prediction,
                "candidate_score": row.candidate_score,
                "fit_cutoff": iso_z(cutoff),
                "horizon": row.horizon,
                "horizon_bars": row.horizon_bars,
                "observed_at": iso_z(row.observed_at),
                "score_bucket": _bucket(row.candidate_score, thresholds),
                "segment": row.segment,
                "target_available_at": iso_z(row.target_available_at),
                "target_return": row.target_return,
                "training_rows": training_count,
            }
        )
    return output


def _group_values(rows: Sequence[Mapping[str, Any]], key: str) -> dict[str, list[Mapping[str, Any]]]:
    output: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        output.setdefault(str(row[key]), []).append(row)
    return output


def effective_observations(values: Sequence[float], lag: int) -> float:
    array = np.asarray(values, dtype=float)
    centered = array - array.mean()
    variance = float(np.mean(centered**2))
    if variance <= 0:
        return 0.0
    long_run = variance
    for offset in range(1, min(lag, len(array) - 1) + 1):
        covariance = float(np.mean(centered[offset:] * centered[:-offset]))
        long_run += 2.0 * (1.0 - offset / (lag + 1.0)) * covariance
    if long_run <= 0:
        return float(len(array))
    return float(min(len(array), max(1.0, len(array) * variance / long_run)))


def evaluate_forecasts(
    rows: Sequence[Mapping[str, Any]], *, replications: int, seed: int
) -> dict[str, Any]:
    if not rows:
        raise PersistenceResearchError("forecast ledger is empty")
    target = np.asarray([float(row["target_return"]) for row in rows])
    benchmark_score = np.asarray([float(row["benchmark_score"]) for row in rows])
    candidate_score = np.asarray([float(row["candidate_score"]) for row in rows])
    benchmark_prediction = np.asarray([float(row["benchmark_prediction"]) for row in rows])
    candidate_prediction = np.asarray([float(row["candidate_prediction"]) for row in rows])
    horizon_bars = int(rows[0]["horizon_bars"])
    hac = ols_hac(target, [benchmark_score, candidate_score], horizon_bars)
    squared_error_improvement = (target - benchmark_prediction) ** 2 - (
        target - candidate_prediction
    ) ** 2
    by_month = _group_values(rows, "target_available_at")
    # Regroup the ISO timestamps into UTC calendar-month blocks.
    month_rows: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        month_rows.setdefault(str(row["target_available_at"])[:7], []).append(row)
    monthly_rank_ic: list[float] = []
    monthly_error_improvement: list[float] = []
    monthly_top_bottom: list[float] = []
    for month in sorted(month_rows):
        group = month_rows[month]
        scores = [float(row["candidate_score"]) for row in group]
        outcomes = [float(row["target_return"]) for row in group]
        if len(group) >= 3 and len(set(scores)) > 1 and len(set(outcomes)) > 1:
            monthly_rank_ic.append(spearman_rank_correlation(scores, outcomes))
        monthly_error_improvement.append(
            float(
                np.mean(
                    [
                        (float(row["target_return"]) - float(row["benchmark_prediction"])) ** 2
                        - (float(row["target_return"]) - float(row["candidate_prediction"])) ** 2
                        for row in group
                    ]
                )
            )
        )
        top = [float(row["target_return"]) for row in group if int(row["score_bucket"]) == 5]
        bottom = [float(row["target_return"]) for row in group if int(row["score_bucket"]) == 1]
        if top and bottom:
            monthly_top_bottom.append(float(np.mean(top) - np.mean(bottom)))
    bucket_means = {
        str(bucket): float(
            np.mean([float(row["target_return"]) for row in rows if int(row["score_bucket"]) == bucket])
        )
        for bucket in range(1, 6)
    }
    by_year: dict[int, list[Mapping[str, Any]]] = {}
    for row in rows:
        by_year.setdefault(int(str(row["target_available_at"])[:4]), []).append(row)
    annual_coefficients: dict[str, float] = {}
    for year, group in sorted(by_year.items()):
        annual_coefficients[str(year)] = float(
            ols_coefficients(
                [float(row["target_return"]) for row in group],
                [
                    [float(row["benchmark_score"]) for row in group],
                    [float(row["candidate_score"]) for row in group],
                ],
            )[2]
        )
    leave_one_year_out: dict[str, float] = {}
    for year in sorted(by_year):
        group = [row for row in rows if int(str(row["target_available_at"])[:4]) != year]
        leave_one_year_out[str(year)] = float(
            ols_coefficients(
                [float(row["target_return"]) for row in group],
                [
                    [float(row["benchmark_score"]) for row in group],
                    [float(row["candidate_score"]) for row in group],
                ],
            )[2]
        )
    return {
        "annual_incremental_candidate_coefficients": annual_coefficients,
        "benchmark_mse": float(np.mean((target - benchmark_prediction) ** 2)),
        "candidate_mse": float(np.mean((target - candidate_prediction) ** 2)),
        "candidate_rank_ic_pooled": spearman_rank_correlation(candidate_score, target),
        "effective_observations_hac": effective_observations(target, horizon_bars),
        "expanded_regression_hac": hac,
        "leave_one_year_out_incremental_candidate_coefficients": leave_one_year_out,
        "month_block_error_improvement": month_block_bootstrap(
            monthly_error_improvement, replications=replications, seed=seed
        ),
        "month_block_rank_ic": month_block_bootstrap(
            monthly_rank_ic, replications=replications, seed=seed
        ),
        "month_block_top_minus_bottom": month_block_bootstrap(
            monthly_top_bottom, replications=replications, seed=seed
        ),
        "observations": len(rows),
        "quintile_forward_return_means": bucket_means,
        "squared_error_improvement_mean": float(squared_error_improvement.mean()),
    }


def coverage_report(
    candles: Sequence[PersistenceCandle],
    valid_rows: Sequence[PersistenceRow],
    *,
    horizon_bars: int,
    evaluation_start: datetime,
    evaluation_end: datetime,
) -> dict[str, Any]:
    denominator = [
        row
        for row in candles
        if evaluation_start <= row.close_at < evaluation_end
        and row.close_at.timestamp() + horizon_bars * FOUR_HOURS_SECONDS
        < evaluation_end.timestamp()
    ]
    valid = [
        row
        for row in valid_rows
        if evaluation_start <= row.observed_at < evaluation_end
        and row.target_available_at < evaluation_end
    ]
    denom_by_year: dict[int, int] = {}
    for row in denominator:
        target_year = datetime.fromtimestamp(
            row.close_at.timestamp() + horizon_bars * FOUR_HOURS_SECONDS, tz=UTC
        ).year
        denom_by_year[target_year] = denom_by_year.get(target_year, 0) + 1
    valid_by_year: dict[int, int] = {}
    for row in valid:
        year = row.target_available_at.year
        valid_by_year[year] = valid_by_year.get(year, 0) + 1
    years = sorted(set(denom_by_year) | set(valid_by_year))
    return {
        "denominator_rows": len(denominator),
        "overall": len(valid) / len(denominator) if denominator else 0.0,
        "per_year": {
            str(year): {
                "denominator": denom_by_year.get(year, 0),
                "fraction": valid_by_year.get(year, 0) / denom_by_year[year]
                if denom_by_year.get(year, 0)
                else 0.0,
                "valid": valid_by_year.get(year, 0),
            }
            for year in years
        },
        "valid_rows": len(valid),
    }


def write_jsonl_gzip(path: Path, rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    count = 0
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            for row in rows:
                compressed.write((canonical_line(dict(row)) + "\n").encode())
                count += 1
    return {"bytes": path.stat().st_size, "rows": count, "sha256": sha256_file(path)}
