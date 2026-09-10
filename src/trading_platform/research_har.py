"""Causal standalone HAR-RV forecast evaluation for offline BTC research only."""

from __future__ import annotations

import math
import random
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from trading_platform.research_ledger import DAY_MS
from trading_platform.research_routing import canonical_digest
from trading_platform.research_volatility import (
    CandlePoint,
    EWMARiskObservation,
    realized_variance,
)


UTC = timezone.utc


class ResearchHARError(ValueError):
    """Raised when HAR-RV inputs, timing, or calculations fail closed."""


def _finite_positive(value: float, label: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ResearchHARError(f"{label} must be finite and positive")
    return number


def _month_cutoff(timestamp_ms: int) -> int:
    value = datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC)
    return int(datetime(value.year, value.month, 1, tzinfo=UTC).timestamp() * 1000)


def _year(timestamp_ms: int) -> int:
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC).year


def _month(timestamp_ms: int) -> str:
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC).strftime("%Y-%m")


@dataclass(frozen=True, slots=True)
class DailyRealizedVariance:
    observed_ms: int
    segment: str
    realized_variance: float
    source_digest: str

    def __post_init__(self) -> None:
        if self.observed_ms % DAY_MS or not self.segment:
            raise ResearchHARError("daily realized variance has invalid identity")
        _finite_positive(self.realized_variance, "daily realized variance")

    @property
    def digest(self) -> str:
        return canonical_digest(
            {
                "instrument": "BTC/USDT",
                "interval": "1d",
                "observed_ms": self.observed_ms,
                "realized_variance": self.realized_variance,
                "segment": self.segment,
                "source_digest": self.source_digest,
            }
        )


@dataclass(frozen=True, slots=True)
class HARSample:
    decision_ms: int
    target_end_ms: int
    horizon_days: int
    segment: str
    features: tuple[float, float, float]
    target_variance: float
    source_digest: str

    def __post_init__(self) -> None:
        if self.horizon_days not in (1, 7):
            raise ResearchHARError("unsupported HAR horizon")
        if self.decision_ms % DAY_MS or self.target_end_ms != self.decision_ms + self.horizon_days * DAY_MS:
            raise ResearchHARError("HAR sample has invalid causal horizon")
        if len(self.features) != 3:
            raise ResearchHARError("HAR sample must contain daily, weekly, and monthly features")
        for value in (*self.features, self.target_variance):
            _finite_positive(value, "HAR sample value")


@dataclass(frozen=True, slots=True)
class HARModel:
    horizon_days: int
    cutoff_ms: int
    coefficients: tuple[float, float, float, float]
    feature_means: tuple[float, float, float]
    feature_scales: tuple[float, float, float]
    smearing_factor: float
    forecast_floor: float
    forecast_ceiling: float
    training_samples: int
    ridge_penalty: float

    @property
    def digest(self) -> str:
        return canonical_digest(self.as_dict(include_digest=False))

    def as_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        output = {
            "coefficients": self.coefficients,
            "cutoff_ms": self.cutoff_ms,
            "feature_means": self.feature_means,
            "feature_scales": self.feature_scales,
            "forecast_ceiling": self.forecast_ceiling,
            "forecast_floor": self.forecast_floor,
            "horizon_days": self.horizon_days,
            "ridge_penalty": self.ridge_penalty,
            "smearing_factor": self.smearing_factor,
            "training_samples": self.training_samples,
        }
        if include_digest:
            output["digest"] = self.digest
        return output

    def predict(self, features: Sequence[float], variance_floor: float) -> float:
        if len(features) != 3:
            raise ResearchHARError("HAR prediction feature count changed")
        transformed = [math.log(max(_finite_positive(value, "HAR feature"), variance_floor)) for value in features]
        standardized = [
            (value - mean) / scale
            for value, mean, scale in zip(
                transformed, self.feature_means, self.feature_scales, strict=True
            )
        ]
        predicted_log = self.coefficients[0] + sum(
            coefficient * value
            for coefficient, value in zip(self.coefficients[1:], standardized, strict=True)
        )
        try:
            forecast = math.exp(predicted_log) * self.smearing_factor
        except OverflowError as exc:
            raise ResearchHARError("HAR prediction overflow") from exc
        if not math.isfinite(forecast) or forecast <= 0:
            raise ResearchHARError("HAR prediction is invalid")
        return min(self.forecast_ceiling, max(self.forecast_floor, forecast))


@dataclass(frozen=True, slots=True)
class ForecastComparison:
    decision_ms: int
    target_end_ms: int
    horizon_days: int
    realized_variance: float
    har_forecast: float
    close_ewma_forecast: float
    rv_ewma_forecast: float
    model_cutoff_ms: int
    model_digest: str
    source_digest: str

    @property
    def digest(self) -> str:
        return canonical_digest(self.as_dict(include_digest=False))

    def as_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        output = {
            "close_ewma_forecast": self.close_ewma_forecast,
            "decision_ms": self.decision_ms,
            "har_forecast": self.har_forecast,
            "horizon_days": self.horizon_days,
            "model_cutoff_ms": self.model_cutoff_ms,
            "model_digest": self.model_digest,
            "realized_variance": self.realized_variance,
            "rv_ewma_forecast": self.rv_ewma_forecast,
            "source_digest": self.source_digest,
            "target_end_ms": self.target_end_ms,
        }
        if include_digest:
            output["digest"] = self.digest
        return output


def build_daily_realized_variances(
    candles: Sequence[CandlePoint],
    *,
    start_ms: int,
    end_ms: int,
    source_digest: str,
) -> tuple[list[DailyRealizedVariance], dict[str, Any]]:
    """Aggregate complete UTC days without crossing a five-minute source segment."""
    if start_ms % DAY_MS or end_ms % DAY_MS or start_ms >= end_ms:
        raise ResearchHARError("daily realized-variance boundary is invalid")
    open_index = {item.open_ms: index for index, item in enumerate(candles)}
    output: list[DailyRealizedVariance] = []
    excluded: dict[str, int] = defaultdict(int)
    for day_start in range(start_ms, end_ms, DAY_MS):
        index = open_index.get(day_start)
        if index is None:
            excluded["day_start_missing"] += 1
            continue
        segment = candles[index].segment
        value = realized_variance(candles, day_start, segment, 1, open_index)
        if value is None:
            excluded["incomplete_or_cross_segment_day"] += 1
            continue
        if value <= 0 or not math.isfinite(value):
            excluded["nonpositive_or_nonfinite_day"] += 1
            continue
        output.append(
            DailyRealizedVariance(
                observed_ms=day_start + DAY_MS,
                segment=segment,
                realized_variance=value,
                source_digest=source_digest,
            )
        )
    if any(right.observed_ms <= left.observed_ms for left, right in zip(output, output[1:])):
        raise ResearchHARError("daily realized variances are not strictly ordered")
    return output, {
        "excluded": dict(sorted(excluded.items())),
        "expected_calendar_days": (end_ms - start_ms) // DAY_MS,
        "valid_days": len(output),
    }


def build_har_samples(
    observations: Sequence[DailyRealizedVariance],
    horizon_days: int,
) -> list[HARSample]:
    if horizon_days not in (1, 7):
        raise ResearchHARError("unsupported HAR horizon")
    output: list[HARSample] = []
    for index in range(21, len(observations) - horizon_days):
        history = observations[index - 21 : index + 1]
        future = observations[index + 1 : index + horizon_days + 1]
        current = history[-1]
        expected_history_start = current.observed_ms - 21 * DAY_MS
        if history[0].observed_ms != expected_history_start:
            continue
        if any(
            item.segment != current.segment
            or item.observed_ms != expected_history_start + offset * DAY_MS
            for offset, item in enumerate(history)
        ):
            continue
        if any(
            item.segment != current.segment
            or item.observed_ms != current.observed_ms + offset * DAY_MS
            for offset, item in enumerate(future, start=1)
        ):
            continue
        daily = current.realized_variance
        weekly = statistics.fmean(item.realized_variance for item in history[-5:])
        monthly = statistics.fmean(item.realized_variance for item in history)
        target = sum(item.realized_variance for item in future)
        output.append(
            HARSample(
                decision_ms=current.observed_ms,
                target_end_ms=current.observed_ms + horizon_days * DAY_MS,
                horizon_days=horizon_days,
                segment=current.segment,
                features=(daily, weekly, monthly),
                target_variance=target,
                source_digest=canonical_digest(
                    {
                        "feature_digests": [item.digest for item in history],
                        "target_digests": [item.digest for item in future],
                    }
                ),
            )
        )
    return output


def build_rv_ewma(
    observations: Sequence[DailyRealizedVariance],
    *,
    decay_lambda: float,
    initialization_observations: int,
) -> dict[int, float]:
    if not 0 < decay_lambda < 1 or initialization_observations < 2:
        raise ResearchHARError("invalid realized-variance EWMA configuration")
    output: dict[int, float] = {}
    history: list[float] = []
    forecast: float | None = None
    previous: DailyRealizedVariance | None = None
    for item in observations:
        if (
            previous is None
            or item.segment != previous.segment
            or item.observed_ms != previous.observed_ms + DAY_MS
        ):
            history = []
            forecast = None
        history.append(item.realized_variance)
        if len(history) == initialization_observations:
            forecast = statistics.fmean(history)
        elif len(history) > initialization_observations:
            assert forecast is not None
            forecast = decay_lambda * forecast + (1 - decay_lambda) * item.realized_variance
        if forecast is not None:
            output[item.observed_ms] = _finite_positive(forecast, "realized-variance EWMA")
        previous = item
    return output


def close_ewma_map(observations: Sequence[EWMARiskObservation]) -> dict[int, float]:
    output: dict[int, float] = {}
    for item in observations:
        if item.usable and item.forecast_daily_variance is not None:
            output[item.observed_ms] = _finite_positive(
                item.forecast_daily_variance, "close-return EWMA"
            )
    return output


def _quantile(values: Sequence[float], probability: float) -> float:
    if not values or not 0 <= probability <= 1:
        raise ResearchHARError("invalid quantile request")
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _solve(matrix: Sequence[Sequence[float]], vector: Sequence[float]) -> tuple[float, ...]:
    size = len(vector)
    work = [list(row) + [float(value)] for row, value in zip(matrix, vector, strict=True)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(work[row][column]))
        if abs(work[pivot][column]) < 1e-12:
            raise ResearchHARError("HAR normal equations are singular")
        work[column], work[pivot] = work[pivot], work[column]
        divisor = work[column][column]
        work[column] = [value / divisor for value in work[column]]
        for row in range(size):
            if row == column:
                continue
            factor = work[row][column]
            work[row] = [
                value - factor * pivot_value
                for value, pivot_value in zip(work[row], work[column], strict=True)
            ]
    result = tuple(work[row][-1] for row in range(size))
    if not all(math.isfinite(value) for value in result):
        raise ResearchHARError("HAR coefficients are non-finite")
    return result


def fit_har_model(
    samples: Sequence[HARSample],
    *,
    cutoff_ms: int,
    horizon_days: int,
    minimum_training_samples: int,
    ridge_penalty: float,
    variance_floor: float,
) -> HARModel | None:
    training = [
        item
        for item in samples
        if item.horizon_days == horizon_days and item.target_end_ms <= cutoff_ms
    ]
    if len(training) < minimum_training_samples:
        return None
    transformed = [
        tuple(math.log(max(value, variance_floor)) for value in item.features)
        for item in training
    ]
    targets = [math.log(max(item.target_variance, variance_floor)) for item in training]
    means = tuple(statistics.fmean(row[column] for row in transformed) for column in range(3))
    scales = tuple(
        math.sqrt(statistics.fmean((row[column] - means[column]) ** 2 for row in transformed))
        for column in range(3)
    )
    if any(value <= 1e-12 or not math.isfinite(value) for value in scales):
        raise ResearchHARError("HAR training feature has zero or invalid scale")
    rows = [
        (1.0,)
        + tuple(
            (value - mean) / scale
            for value, mean, scale in zip(row, means, scales, strict=True)
        )
        for row in transformed
    ]
    gram = [[0.0] * 4 for _ in range(4)]
    rhs = [0.0] * 4
    for row, target in zip(rows, targets, strict=True):
        for left in range(4):
            rhs[left] += row[left] * target
            for right in range(4):
                gram[left][right] += row[left] * row[right]
    for index in range(1, 4):
        gram[index][index] += ridge_penalty
    coefficients = _solve(gram, rhs)
    residuals = [
        target - sum(coefficient * value for coefficient, value in zip(coefficients, row, strict=True))
        for row, target in zip(rows, targets, strict=True)
    ]
    smearing = statistics.fmean(math.exp(value) for value in residuals)
    target_values = [item.target_variance for item in training]
    return HARModel(
        horizon_days=horizon_days,
        cutoff_ms=cutoff_ms,
        coefficients=(coefficients[0], coefficients[1], coefficients[2], coefficients[3]),
        feature_means=(means[0], means[1], means[2]),
        feature_scales=(scales[0], scales[1], scales[2]),
        smearing_factor=_finite_positive(smearing, "HAR smearing factor"),
        forecast_floor=_quantile(target_values, 0.01),
        forecast_ceiling=_quantile(target_values, 0.99),
        training_samples=len(training),
        ridge_penalty=ridge_penalty,
    )


def build_forecast_comparisons(
    samples: Sequence[HARSample],
    *,
    close_ewma: Mapping[int, float],
    rv_ewma: Mapping[int, float],
    evaluation_start_ms: int,
    evaluation_end_ms: int,
    minimum_training_samples: int,
    ridge_penalty: float,
    variance_floor: float,
) -> tuple[list[ForecastComparison], dict[str, Any], list[HARModel]]:
    if not samples:
        return [], {"excluded": {"no_samples": 1}, "monthly_refits": 0}, []
    horizon = samples[0].horizon_days
    if any(item.horizon_days != horizon for item in samples):
        raise ResearchHARError("mixed horizons in forecast comparison")
    models: dict[int, HARModel | None] = {}
    excluded: dict[str, int] = defaultdict(int)
    output: list[ForecastComparison] = []
    for item in samples:
        if not evaluation_start_ms <= item.decision_ms < evaluation_end_ms:
            continue
        if item.target_end_ms > evaluation_end_ms:
            excluded["target_crosses_evaluation_end"] += 1
            continue
        cutoff = _month_cutoff(item.decision_ms)
        if cutoff not in models:
            models[cutoff] = fit_har_model(
                samples,
                cutoff_ms=cutoff,
                horizon_days=horizon,
                minimum_training_samples=minimum_training_samples,
                ridge_penalty=ridge_penalty,
                variance_floor=variance_floor,
            )
        model = models[cutoff]
        if model is None:
            excluded["insufficient_training_samples"] += 1
            continue
        close_value = close_ewma.get(item.decision_ms)
        rv_value = rv_ewma.get(item.decision_ms)
        if close_value is None:
            excluded["close_ewma_unavailable"] += 1
            continue
        if rv_value is None:
            excluded["rv_ewma_unavailable"] += 1
            continue
        if model.cutoff_ms > item.decision_ms:
            raise ResearchHARError("future HAR model selected")
        output.append(
            ForecastComparison(
                decision_ms=item.decision_ms,
                target_end_ms=item.target_end_ms,
                horizon_days=horizon,
                realized_variance=item.target_variance,
                har_forecast=model.predict(item.features, variance_floor),
                close_ewma_forecast=close_value * horizon,
                rv_ewma_forecast=rv_value * horizon,
                model_cutoff_ms=model.cutoff_ms,
                model_digest=model.digest,
                source_digest=item.source_digest,
            )
        )
    fitted = [model for _, model in sorted(models.items()) if model is not None]
    return (
        output,
        {
            "excluded": dict(sorted(excluded.items())),
            "monthly_refits": len(fitted),
            "requested_refit_months": len(models),
        },
        fitted,
    )


def _qlike(forecast: float, realized: float) -> float:
    return math.log(forecast) + realized / forecast


def _paired_month_bootstrap(
    rows: Sequence[ForecastComparison],
    *,
    repetitions: int,
    seed: int,
) -> dict[str, float | int]:
    monthly: dict[str, list[float]] = defaultdict(list)
    for item in rows:
        monthly[_month(item.decision_ms)].append(
            _qlike(item.rv_ewma_forecast, item.realized_variance)
            - _qlike(item.har_forecast, item.realized_variance)
        )
    values = [statistics.fmean(monthly[key]) for key in sorted(monthly)]
    if not values:
        raise ResearchHARError("no monthly losses for bootstrap")
    generator = random.Random(seed)
    draws = sorted(
        statistics.fmean(generator.choice(values) for _ in values)
        for _ in range(repetitions)
    )
    return {
        "lower_95": _quantile(draws, 0.025),
        "months": len(values),
        "point_estimate": statistics.fmean(values),
        "upper_95": _quantile(draws, 0.975),
    }


def score_forecasts(
    rows: Sequence[ForecastComparison],
    *,
    bootstrap_replications: int,
    bootstrap_seed: int,
) -> dict[str, Any]:
    if not rows:
        raise ResearchHARError("cannot score empty HAR forecasts")
    har_qlike = [_qlike(item.har_forecast, item.realized_variance) for item in rows]
    close_qlike = [_qlike(item.close_ewma_forecast, item.realized_variance) for item in rows]
    rv_qlike = [_qlike(item.rv_ewma_forecast, item.realized_variance) for item in rows]
    har_mse = [(item.har_forecast - item.realized_variance) ** 2 for item in rows]
    close_mse = [(item.close_ewma_forecast - item.realized_variance) ** 2 for item in rows]
    rv_mse = [(item.rv_ewma_forecast - item.realized_variance) ** 2 for item in rows]
    annual: dict[str, dict[str, float | int | bool]] = {}
    years = sorted({_year(item.decision_ms) for item in rows})
    for year in years:
        selected = [item for item in rows if _year(item.decision_ms) == year]
        improvement = statistics.fmean(
            _qlike(item.rv_ewma_forecast, item.realized_variance)
            - _qlike(item.har_forecast, item.realized_variance)
            for item in selected
        )
        annual[str(year)] = {
            "har_qlike_win_vs_rv_ewma": improvement > 0,
            "mean_qlike_improvement_vs_rv_ewma": improvement,
            "observations": len(selected),
        }
    leave_one_out: dict[str, float | None] = {}
    for year in years:
        selected = [item for item in rows if _year(item.decision_ms) != year]
        leave_one_out[str(year)] = (
            statistics.fmean(
                _qlike(item.rv_ewma_forecast, item.realized_variance)
                - _qlike(item.har_forecast, item.realized_variance)
                for item in selected
            )
            if selected
            else None
        )
    ordered = sorted(rows, key=lambda item: item.har_forecast)
    quartiles: dict[str, dict[str, float | int]] = {}
    for quartile in range(4):
        start = len(ordered) * quartile // 4
        end = len(ordered) * (quartile + 1) // 4
        selected = ordered[start:end]
        quartiles[str(quartile + 1)] = {
            "mean_forecast_variance": statistics.fmean(item.har_forecast for item in selected),
            "mean_realized_variance": statistics.fmean(item.realized_variance for item in selected),
            "observations": len(selected),
        }
    return {
        "annual": annual,
        "calibration_quartiles": quartiles,
        "controls": {
            "close_ewma": {
                "mean_mse": statistics.fmean(close_mse),
                "mean_qlike": statistics.fmean(close_qlike),
            },
            "rv_ewma": {
                "mean_mse": statistics.fmean(rv_mse),
                "mean_qlike": statistics.fmean(rv_qlike),
            },
        },
        "har": {
            "mean_mse": statistics.fmean(har_mse),
            "mean_qlike": statistics.fmean(har_qlike),
            "mse_ratio_to_rv_ewma": statistics.fmean(har_mse) / statistics.fmean(rv_mse),
        },
        "leave_one_year_out_mean_qlike_improvement_vs_rv_ewma": leave_one_out,
        "month_bootstrap_qlike_improvement_vs_rv_ewma": _paired_month_bootstrap(
            rows,
            repetitions=bootstrap_replications,
            seed=bootstrap_seed,
        ),
        "observations": len(rows),
    }


def calendar_coverage(
    rows: Sequence[ForecastComparison],
    *,
    evaluation_start_ms: int,
    evaluation_end_ms: int,
    horizon_days: int,
) -> dict[str, Any]:
    available = defaultdict(int)
    for item in rows:
        available[str(_year(item.decision_ms))] += 1
    possible = defaultdict(int)
    decision = evaluation_start_ms
    while decision < evaluation_end_ms and decision + horizon_days * DAY_MS <= evaluation_end_ms:
        possible[str(_year(decision))] += 1
        decision += DAY_MS
    annual = {
        year: {
            "coverage": available.get(year, 0) / count,
            "possible": count,
            "usable": available.get(year, 0),
        }
        for year, count in sorted(possible.items())
    }
    total_possible = sum(possible.values())
    return {
        "annual": annual,
        "overall": len(rows) / total_possible,
        "possible": total_possible,
        "usable": len(rows),
    }
