"""Causal downside-semivariance and tail-risk research for BTC MCS3-D only."""

from __future__ import annotations

import math
import random
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from trading_platform.research_ledger import DAY_MS, FIVE_MINUTES_MS, sha256_file
from trading_platform.research_persistence import canonical_json, write_jsonl_gzip
from trading_platform.research_routing import canonical_digest
from trading_platform.research_volatility import CandlePoint, parse_utc_ms


UTC = timezone.utc


class DownsideResearchError(ValueError):
    """Raised when MCS3-D data, chronology, or score domains fail closed."""


def _finite(value: float, label: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise DownsideResearchError(f"{label} must be finite")
    return number


def _nonnegative(value: float, label: str) -> float:
    number = _finite(value, label)
    if number < 0:
        raise DownsideResearchError(f"{label} must be nonnegative")
    return number


def _positive(value: float, label: str) -> float:
    number = _finite(value, label)
    if number <= 0:
        raise DownsideResearchError(f"{label} must be positive")
    return number


def _month_cutoff(timestamp_ms: int) -> int:
    value = datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC)
    return int(datetime(value.year, value.month, 1, tzinfo=UTC).timestamp() * 1000)


def _month(timestamp_ms: int) -> str:
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC).strftime("%Y-%m")


def _year(timestamp_ms: int) -> int:
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC).year


def _quantile(values: Sequence[float], probability: float) -> float:
    if not values or not 0 <= probability <= 1:
        raise DownsideResearchError("invalid quantile request")
    ordered = sorted(_finite(value, "quantile value") for value in values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


@dataclass(frozen=True, slots=True)
class DailyDownsideObservation:
    observed_ms: int
    segment: str
    daily_log_return: float
    negative_semivariance: float
    source_digest: str

    def __post_init__(self) -> None:
        if self.observed_ms % DAY_MS or not self.segment or not self.source_digest:
            raise DownsideResearchError("daily downside observation has invalid identity")
        _finite(self.daily_log_return, "daily log return")
        _nonnegative(self.negative_semivariance, "daily negative semivariance")

    @property
    def digest(self) -> str:
        return canonical_digest(self.as_dict(include_digest=False))

    def as_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        result = {
            "daily_log_return": self.daily_log_return,
            "instrument": "BTC/USDT",
            "interval": "1d",
            "negative_semivariance": self.negative_semivariance,
            "observed_ms": self.observed_ms,
            "segment": self.segment,
            "source_digest": self.source_digest,
        }
        if include_digest:
            result["digest"] = self.digest
        return result


@dataclass(frozen=True, slots=True)
class DownsideSample:
    decision_ms: int
    target_end_ms: int
    horizon_days: int
    segment: str
    features: tuple[float, float, float]
    target_negative_semivariance: float
    target_tail_loss: float
    source_digest: str

    def __post_init__(self) -> None:
        if self.horizon_days not in (1, 7):
            raise DownsideResearchError("unsupported downside horizon")
        if self.decision_ms % DAY_MS or self.target_end_ms != self.decision_ms + self.horizon_days * DAY_MS:
            raise DownsideResearchError("downside sample has invalid causal horizon")
        if len(self.features) != 3 or not self.segment or not self.source_digest:
            raise DownsideResearchError("downside sample identity is invalid")
        for value in self.features:
            _nonnegative(value, "downside feature")
        _nonnegative(self.target_negative_semivariance, "target negative semivariance")
        _finite(self.target_tail_loss, "target tail loss")


@dataclass(frozen=True, slots=True)
class HorizonTailLoss:
    target_end_ms: int
    horizon_days: int
    segment: str
    tail_loss: float
    source_digest: str

    def __post_init__(self) -> None:
        if self.horizon_days not in (1, 7) or self.target_end_ms % DAY_MS:
            raise DownsideResearchError("historical tail loss has invalid horizon")
        if not self.segment or not self.source_digest:
            raise DownsideResearchError("historical tail loss has invalid identity")
        _finite(self.tail_loss, "historical tail loss")


@dataclass(frozen=True, slots=True)
class DownsideModel:
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
        result = {
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
            result["digest"] = self.digest
        return result

    def predict(self, features: Sequence[float], log_floor: float) -> float:
        if len(features) != 3:
            raise DownsideResearchError("downside prediction feature count changed")
        transformed = [math.log(max(_nonnegative(value, "downside feature"), log_floor)) for value in features]
        standardized = [
            (value - mean) / scale
            for value, mean, scale in zip(transformed, self.feature_means, self.feature_scales, strict=True)
        ]
        predicted_log = self.coefficients[0] + sum(
            coefficient * value
            for coefficient, value in zip(self.coefficients[1:], standardized, strict=True)
        )
        try:
            forecast = math.exp(predicted_log) * self.smearing_factor
        except OverflowError as exc:
            raise DownsideResearchError("downside prediction overflow") from exc
        _positive(forecast, "downside forecast")
        return min(self.forecast_ceiling, max(self.forecast_floor, forecast))


@dataclass(frozen=True, slots=True)
class DownsideForecast:
    decision_ms: int
    target_end_ms: int
    horizon_days: int
    segment: str
    target_negative_semivariance: float
    target_tail_loss: float
    benchmark_negative_semivariance: float
    candidate_negative_semivariance: float
    benchmark_var_95: float
    benchmark_es_95: float
    candidate_var_95: float
    candidate_es_95: float
    tail_history_count: int
    model_cutoff_ms: int
    model_digest: str
    source_digest: str

    def __post_init__(self) -> None:
        for value in (
            self.benchmark_negative_semivariance,
            self.candidate_negative_semivariance,
            self.benchmark_var_95,
            self.benchmark_es_95,
            self.candidate_var_95,
            self.candidate_es_95,
        ):
            _positive(value, "forecast value")
        if self.benchmark_es_95 < self.benchmark_var_95 or self.candidate_es_95 < self.candidate_var_95:
            raise DownsideResearchError("expected shortfall must be at least VaR")
        if self.tail_history_count != 500 or self.model_cutoff_ms > self.decision_ms:
            raise DownsideResearchError("forecast lineage or chronology is invalid")

    @property
    def digest(self) -> str:
        return canonical_digest(self.as_dict(include_digest=False))

    def as_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        result = {
            "benchmark_es_95": self.benchmark_es_95,
            "benchmark_negative_semivariance": self.benchmark_negative_semivariance,
            "benchmark_var_95": self.benchmark_var_95,
            "candidate_es_95": self.candidate_es_95,
            "candidate_negative_semivariance": self.candidate_negative_semivariance,
            "candidate_var_95": self.candidate_var_95,
            "decision_ms": self.decision_ms,
            "horizon_days": self.horizon_days,
            "model_cutoff_ms": self.model_cutoff_ms,
            "model_digest": self.model_digest,
            "segment": self.segment,
            "source_digest": self.source_digest,
            "tail_history_count": self.tail_history_count,
            "target_end_ms": self.target_end_ms,
            "target_negative_semivariance": self.target_negative_semivariance,
            "target_tail_loss": self.target_tail_loss,
        }
        if include_digest:
            result["digest"] = self.digest
        return result


def build_daily_downside_observations(
    candles: Sequence[CandlePoint],
    *,
    start_ms: int,
    end_ms: int,
    source_digest: str,
) -> tuple[list[DailyDownsideObservation], dict[str, Any]]:
    """Build exact complete UTC-day downside observations including the prior close."""
    if start_ms % DAY_MS or end_ms % DAY_MS or start_ms >= end_ms:
        raise DownsideResearchError("daily downside boundary is invalid")
    open_index = {item.open_ms: index for index, item in enumerate(candles)}
    if len(open_index) != len(candles):
        raise DownsideResearchError("duplicate candle open time")
    output: list[DailyDownsideObservation] = []
    excluded: dict[str, int] = defaultdict(int)
    for day_start in range(start_ms, end_ms, DAY_MS):
        first_index = open_index.get(day_start)
        prior_index = open_index.get(day_start - FIVE_MINUTES_MS)
        if first_index is None:
            excluded["day_start_missing"] += 1
            continue
        if prior_index is None or prior_index + 1 != first_index:
            excluded["prior_close_missing_or_noncontiguous"] += 1
            continue
        segment = candles[first_index].segment
        indices = [prior_index + offset for offset in range(289)]
        if indices[-1] >= len(candles):
            excluded["incomplete_or_cross_segment_day"] += 1
            continue
        window = [candles[index] for index in indices]
        if any(
            item.segment != segment
            or item.open_ms != day_start - FIVE_MINUTES_MS + offset * FIVE_MINUTES_MS
            for offset, item in enumerate(window)
        ):
            excluded["incomplete_or_cross_segment_day"] += 1
            continue
        returns = [math.log(current.close / previous.close) for previous, current in zip(window, window[1:], strict=False)]
        if len(returns) != 288 or not all(math.isfinite(value) for value in returns):
            excluded["invalid_return"] += 1
            continue
        output.append(
            DailyDownsideObservation(
                observed_ms=day_start + DAY_MS,
                segment=segment,
                daily_log_return=sum(returns),
                negative_semivariance=sum(value * value for value in returns if value < 0),
                source_digest=source_digest,
            )
        )
    if any(right.observed_ms <= left.observed_ms for left, right in zip(output, output[1:], strict=False)):
        raise DownsideResearchError("daily downside observations are not strictly ordered")
    return output, {
        "excluded": dict(sorted(excluded.items())),
        "expected_calendar_days": (end_ms - start_ms) // DAY_MS,
        "valid_days": len(output),
    }


def build_downside_samples(
    observations: Sequence[DailyDownsideObservation], horizon_days: int
) -> list[DownsideSample]:
    if horizon_days not in (1, 7):
        raise DownsideResearchError("unsupported downside horizon")
    output: list[DownsideSample] = []
    for index in range(21, len(observations) - horizon_days):
        history = observations[index - 21 : index + 1]
        future = observations[index + 1 : index + horizon_days + 1]
        current = history[-1]
        history_start = current.observed_ms - 21 * DAY_MS
        if any(
            item.segment != current.segment or item.observed_ms != history_start + offset * DAY_MS
            for offset, item in enumerate(history)
        ):
            continue
        if any(
            item.segment != current.segment or item.observed_ms != current.observed_ms + offset * DAY_MS
            for offset, item in enumerate(future, start=1)
        ):
            continue
        output.append(
            DownsideSample(
                decision_ms=current.observed_ms,
                target_end_ms=current.observed_ms + horizon_days * DAY_MS,
                horizon_days=horizon_days,
                segment=current.segment,
                features=(
                    current.negative_semivariance,
                    statistics.fmean(item.negative_semivariance for item in history[-5:]),
                    statistics.fmean(item.negative_semivariance for item in history),
                ),
                target_negative_semivariance=sum(item.negative_semivariance for item in future),
                target_tail_loss=-sum(item.daily_log_return for item in future),
                source_digest=canonical_digest(
                    {
                        "feature_digests": [item.digest for item in history],
                        "target_digests": [item.digest for item in future],
                    }
                ),
            )
        )
    return output


def build_horizon_tail_losses(
    observations: Sequence[DailyDownsideObservation], horizon_days: int
) -> list[HorizonTailLoss]:
    """Build individually valid losses without requiring model-feature eligibility."""
    if horizon_days not in (1, 7):
        raise DownsideResearchError("unsupported tail-loss horizon")
    output: list[HorizonTailLoss] = []
    for end_index in range(horizon_days - 1, len(observations)):
        window = observations[end_index - horizon_days + 1 : end_index + 1]
        last = window[-1]
        first_ms = last.observed_ms - (horizon_days - 1) * DAY_MS
        if any(
            item.segment != last.segment or item.observed_ms != first_ms + offset * DAY_MS
            for offset, item in enumerate(window)
        ):
            continue
        output.append(
            HorizonTailLoss(
                target_end_ms=last.observed_ms,
                horizon_days=horizon_days,
                segment=last.segment,
                tail_loss=-sum(item.daily_log_return for item in window),
                source_digest=canonical_digest(
                    {"target_digests": [item.digest for item in window]}
                ),
            )
        )
    return output


def _solve(matrix: Sequence[Sequence[float]], vector: Sequence[float]) -> tuple[float, ...]:
    size = len(vector)
    work = [list(row) + [float(value)] for row, value in zip(matrix, vector, strict=True)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(work[row][column]))
        if abs(work[pivot][column]) < 1e-12:
            raise DownsideResearchError("downside normal equations are singular")
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
    result = tuple(work[index][-1] for index in range(size))
    if not all(math.isfinite(value) for value in result):
        raise DownsideResearchError("downside coefficients are non-finite")
    return result


def fit_downside_model(
    samples: Sequence[DownsideSample],
    *,
    cutoff_ms: int,
    horizon_days: int,
    minimum_training_samples: int,
    ridge_penalty: float,
    log_floor: float,
) -> DownsideModel | None:
    training = [
        item
        for item in samples
        if item.horizon_days == horizon_days and item.target_end_ms < cutoff_ms
    ]
    if len(training) < minimum_training_samples:
        return None
    transformed = [tuple(math.log(max(value, log_floor)) for value in item.features) for item in training]
    targets = [math.log(max(item.target_negative_semivariance, log_floor)) for item in training]
    means = tuple(statistics.fmean(row[column] for row in transformed) for column in range(3))
    scales = tuple(
        math.sqrt(statistics.fmean((row[column] - means[column]) ** 2 for row in transformed))
        for column in range(3)
    )
    if any(value <= 1e-12 or not math.isfinite(value) for value in scales):
        raise DownsideResearchError("downside training feature has zero or invalid scale")
    rows = [
        (1.0,) + tuple(
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
    target_values = [max(item.target_negative_semivariance, log_floor) for item in training]
    return DownsideModel(
        horizon_days=horizon_days,
        cutoff_ms=cutoff_ms,
        coefficients=(coefficients[0], coefficients[1], coefficients[2], coefficients[3]),
        feature_means=(means[0], means[1], means[2]),
        feature_scales=(scales[0], scales[1], scales[2]),
        smearing_factor=_positive(smearing, "downside smearing factor"),
        forecast_floor=_positive(_quantile(target_values, 0.01), "forecast floor"),
        forecast_ceiling=_positive(_quantile(target_values, 0.99), "forecast ceiling"),
        training_samples=len(training),
        ridge_penalty=ridge_penalty,
    )


def historical_var_es(
    losses: Sequence[float], confidence: float = 0.95
) -> tuple[float, float]:
    if not 0 < confidence < 1:
        raise DownsideResearchError("tail confidence must be within (0, 1)")
    var = _quantile(losses, confidence)
    tail = [_finite(value, "tail loss") for value in losses if value >= var]
    if not tail:
        raise DownsideResearchError("historical ES tail is empty")
    es = statistics.fmean(tail)
    if var <= 0 or es < var or not math.isfinite(es):
        raise DownsideResearchError("historical VaR/ES domain is invalid")
    return var, es


def qlike_loss(realized: float, forecast: float) -> float:
    return math.log(_positive(forecast, "QLIKE forecast")) + _nonnegative(realized, "QLIKE realized") / forecast


def pinball_loss(loss: float, var: float, confidence: float = 0.95) -> float:
    observed = _finite(loss, "tail loss")
    threshold = _positive(var, "VaR")
    if not 0 < confidence < 1:
        raise DownsideResearchError("pinball confidence must be within (0, 1)")
    return (confidence - (1.0 if observed < threshold else 0.0)) * (observed - threshold)


def fz0_loss(loss: float, var: float, es: float, tail_probability: float = 0.05) -> float:
    observed = _finite(loss, "tail loss")
    threshold = _positive(var, "VaR")
    shortfall = _positive(es, "ES")
    if shortfall < threshold or not 0 < tail_probability < 1:
        raise DownsideResearchError("FZ0 domain is invalid")
    exceedance = 1.0 if observed >= threshold else 0.0
    return math.log(shortfall) + threshold / shortfall + exceedance * (observed - threshold) / (tail_probability * shortfall) - 1.0


def es_calibration_moment(
    loss: float, var: float, es: float, tail_probability: float = 0.05
) -> float:
    observed = _finite(loss, "tail loss")
    threshold = _positive(var, "VaR")
    shortfall = _positive(es, "ES")
    if shortfall < threshold or not 0 < tail_probability < 1:
        raise DownsideResearchError("ES calibration domain is invalid")
    return (1.0 if observed >= threshold else 0.0) * (observed - threshold) - tail_probability * (shortfall - threshold)


def month_block_bootstrap(
    values: Sequence[float], *, replications: int, seed: int
) -> dict[str, Any]:
    if not values or replications <= 0:
        raise DownsideResearchError("invalid month-block bootstrap request")
    checked = [_finite(value, "month-block value") for value in values]
    generator = random.Random(seed)
    draws = sorted(
        statistics.fmean(generator.choice(checked) for _ in checked)
        for _ in range(replications)
    )
    return {
        "ci95": [_quantile(draws, 0.025), _quantile(draws, 0.975)],
        "lower_95": _quantile(draws, 0.025),
        "months": len(checked),
        "point_estimate": statistics.fmean(checked),
        "upper_95": _quantile(draws, 0.975),
        "valid_replications": len(draws),
    }


def build_forecasts(
    samples: Sequence[DownsideSample],
    *,
    historical_losses: Sequence[HorizonTailLoss],
    evaluation_start_ms: int,
    evaluation_end_ms: int,
    minimum_training_samples: int,
    ridge_penalty: float,
    log_floor: float,
    tail_history_observations: int,
) -> tuple[list[DownsideForecast], dict[str, Any], list[DownsideModel]]:
    if not samples:
        return [], {"excluded": {"no_samples": 1}, "monthly_refits": 0}, []
    horizon = samples[0].horizon_days
    if any(item.horizon_days != horizon for item in samples):
        raise DownsideResearchError("mixed horizons in downside forecasts")
    if tail_history_observations != 500:
        raise DownsideResearchError("frozen tail-history count changed")
    if any(item.horizon_days != horizon for item in historical_losses):
        raise DownsideResearchError("mixed horizons in historical tail losses")
    models: dict[int, DownsideModel | None] = {}
    excluded: dict[str, int] = defaultdict(int)
    output: list[DownsideForecast] = []
    ordered_losses = sorted(
        historical_losses, key=lambda item: (item.target_end_ms, item.source_digest)
    )
    for item in samples:
        if not evaluation_start_ms <= item.decision_ms < evaluation_end_ms:
            continue
        if item.target_end_ms >= evaluation_end_ms:
            excluded["target_not_before_evaluation_end"] += 1
            continue
        cutoff = _month_cutoff(item.decision_ms)
        if cutoff not in models:
            models[cutoff] = fit_downside_model(
                samples,
                cutoff_ms=cutoff,
                horizon_days=horizon,
                minimum_training_samples=minimum_training_samples,
                ridge_penalty=ridge_penalty,
                log_floor=log_floor,
            )
        model = models[cutoff]
        if model is None:
            excluded["insufficient_training_samples"] += 1
            continue
        historical = [
            prior.tail_loss
            for prior in ordered_losses
            if prior.target_end_ms <= item.decision_ms
        ]
        if len(historical) < tail_history_observations:
            excluded["insufficient_tail_history"] += 1
            continue
        historical = historical[-tail_history_observations:]
        try:
            benchmark_var, benchmark_es = historical_var_es(historical, 0.95)
            benchmark_nsv = _positive(item.features[2] * horizon, "benchmark negative semivariance")
            candidate_nsv = model.predict(item.features, log_floor)
            ratio = math.sqrt(candidate_nsv / benchmark_nsv)
            candidate_var = _positive(benchmark_var * ratio, "candidate VaR")
            candidate_es = _positive(benchmark_es * ratio, "candidate ES")
        except DownsideResearchError:
            excluded["forecast_or_score_domain_failure"] += 1
            continue
        output.append(
            DownsideForecast(
                decision_ms=item.decision_ms,
                target_end_ms=item.target_end_ms,
                horizon_days=horizon,
                segment=item.segment,
                target_negative_semivariance=item.target_negative_semivariance,
                target_tail_loss=item.target_tail_loss,
                benchmark_negative_semivariance=benchmark_nsv,
                candidate_negative_semivariance=candidate_nsv,
                benchmark_var_95=benchmark_var,
                benchmark_es_95=benchmark_es,
                candidate_var_95=candidate_var,
                candidate_es_95=candidate_es,
                tail_history_count=len(historical),
                model_cutoff_ms=model.cutoff_ms,
                model_digest=model.digest,
                source_digest=item.source_digest,
            )
        )
    return output, {
        "excluded": dict(sorted(excluded.items())),
        "monthly_refits": len([value for value in models.values() if value is not None]),
        "requested_refit_months": len(models),
    }, [model for _, model in sorted(models.items()) if model is not None]


def _losses(item: DownsideForecast) -> dict[str, float]:
    return {
        "benchmark_qlike": qlike_loss(item.target_negative_semivariance, item.benchmark_negative_semivariance),
        "candidate_qlike": qlike_loss(item.target_negative_semivariance, item.candidate_negative_semivariance),
        "benchmark_mse": (item.benchmark_negative_semivariance - item.target_negative_semivariance) ** 2,
        "candidate_mse": (item.candidate_negative_semivariance - item.target_negative_semivariance) ** 2,
        "benchmark_pinball": pinball_loss(item.target_tail_loss, item.benchmark_var_95),
        "candidate_pinball": pinball_loss(item.target_tail_loss, item.candidate_var_95),
        "benchmark_fz0": fz0_loss(item.target_tail_loss, item.benchmark_var_95, item.benchmark_es_95),
        "candidate_fz0": fz0_loss(item.target_tail_loss, item.candidate_var_95, item.candidate_es_95),
        "candidate_es_moment": es_calibration_moment(item.target_tail_loss, item.candidate_var_95, item.candidate_es_95),
    }


def _wilson_interval(successes: int, count: int, z: float) -> list[float]:
    if count <= 0 or not 0 <= successes <= count:
        raise DownsideResearchError("invalid Wilson interval counts")
    proportion = successes / count
    denominator = 1 + z * z / count
    center = (proportion + z * z / (2 * count)) / denominator
    radius = z * math.sqrt(proportion * (1 - proportion) / count + z * z / (4 * count * count)) / denominator
    return [center - radius, center + radius]


def score_forecasts(
    rows: Sequence[DownsideForecast],
    *,
    bootstrap_replications: int,
    bootstrap_seed: int,
    wilson_z: float = 1.959963984540054,
) -> dict[str, Any]:
    if not rows:
        raise DownsideResearchError("cannot score empty downside forecasts")
    enriched = [(item, _losses(item)) for item in rows]
    means = {
        key: statistics.fmean(loss[key] for _, loss in enriched)
        for key in enriched[0][1]
        if key != "candidate_es_moment"
    }
    by_month: dict[str, list[tuple[DownsideForecast, dict[str, float]]]] = defaultdict(list)
    by_year: dict[int, list[tuple[DownsideForecast, dict[str, float]]]] = defaultdict(list)
    for item in enriched:
        by_month[_month(item[0].target_end_ms)].append(item)
        by_year[_year(item[0].target_end_ms)].append(item)
    monthly_qlike = {
        month: statistics.fmean(loss["benchmark_qlike"] - loss["candidate_qlike"] for _, loss in group)
        for month, group in by_month.items()
    }
    monthly_fz0 = {
        month: statistics.fmean(loss["benchmark_fz0"] - loss["candidate_fz0"] for _, loss in group)
        for month, group in by_month.items()
    }
    monthly_es = {
        month: statistics.fmean(loss["candidate_es_moment"] for _, loss in group)
        for month, group in by_month.items()
    }
    annual = {
        str(year): {
            "fz0_improvement": statistics.fmean(loss["benchmark_fz0"] - loss["candidate_fz0"] for _, loss in group),
            "observations": len(group),
            "qlike_improvement": statistics.fmean(loss["benchmark_qlike"] - loss["candidate_qlike"] for _, loss in group),
        }
        for year, group in sorted(by_year.items())
    }
    leave_one_out: dict[str, dict[str, float]] = {}
    for excluded_year in sorted(by_year):
        selected = [item for item in enriched if _year(item[0].target_end_ms) != excluded_year]
        leave_one_out[str(excluded_year)] = {
            "fz0_improvement": statistics.fmean(loss["benchmark_fz0"] - loss["candidate_fz0"] for _, loss in selected),
            "qlike_improvement": statistics.fmean(loss["benchmark_qlike"] - loss["candidate_qlike"] for _, loss in selected),
        }
    best_qlike = set(sorted(monthly_qlike, key=lambda key: (-monthly_qlike[key], key))[:3])
    best_fz0 = set(sorted(monthly_fz0, key=lambda key: (-monthly_fz0[key], key))[:3])
    excluded_best = {
        "fz0_improvement": statistics.fmean(value for month, value in monthly_fz0.items() if month not in best_fz0),
        "fz0_removed_months": sorted(best_fz0),
        "qlike_improvement": statistics.fmean(value for month, value in monthly_qlike.items() if month not in best_qlike),
        "qlike_removed_months": sorted(best_qlike),
    }
    ordered = sorted(rows, key=lambda item: (item.candidate_negative_semivariance, item.decision_ms))
    quartiles: dict[str, dict[str, float | int]] = {}
    for quartile in range(4):
        start = len(ordered) * quartile // 4
        end = len(ordered) * (quartile + 1) // 4
        selected = ordered[start:end]
        quartiles[str(quartile + 1)] = {
            "mean_forecast_negative_semivariance": statistics.fmean(item.candidate_negative_semivariance for item in selected),
            "mean_realized_negative_semivariance": statistics.fmean(item.target_negative_semivariance for item in selected),
            "observations": len(selected),
        }
    exceedances = sum(item.target_tail_loss >= item.candidate_var_95 for item in rows)
    exceedance_fraction = exceedances / len(rows)
    return {
        "annual": annual,
        "benchmark": {
            "mean_fz0": means["benchmark_fz0"],
            "mean_mse": means["benchmark_mse"],
            "mean_pinball": means["benchmark_pinball"],
            "mean_qlike": means["benchmark_qlike"],
        },
        "candidate": {
            "mean_fz0": means["candidate_fz0"],
            "mean_mse": means["candidate_mse"],
            "mean_pinball": means["candidate_pinball"],
            "mean_qlike": means["candidate_qlike"],
            "mse_ratio_to_benchmark": means["candidate_mse"] / means["benchmark_mse"],
        },
        "calibration_quartiles": quartiles,
        "es_calibration_month_block": month_block_bootstrap(
            [monthly_es[key] for key in sorted(monthly_es)],
            replications=bootstrap_replications,
            seed=bootstrap_seed,
        ),
        "excluding_best_three_months": excluded_best,
        "leave_one_year_out": leave_one_out,
        "month_block_fz0_improvement": month_block_bootstrap(
            [monthly_fz0[key] for key in sorted(monthly_fz0)],
            replications=bootstrap_replications,
            seed=bootstrap_seed,
        ),
        "month_block_qlike_improvement": month_block_bootstrap(
            [monthly_qlike[key] for key in sorted(monthly_qlike)],
            replications=bootstrap_replications,
            seed=bootstrap_seed,
        ),
        "observations": len(rows),
        "var_exceedance": {
            "count": exceedances,
            "fraction": exceedance_fraction,
            "wilson_95": _wilson_interval(exceedances, len(rows), wilson_z),
        },
    }


def calendar_coverage(
    rows: Sequence[DownsideForecast],
    *,
    evaluation_start_ms: int,
    evaluation_end_ms: int,
    horizon_days: int,
) -> dict[str, Any]:
    last_decision_exclusive = evaluation_end_ms - horizon_days * DAY_MS
    denominator_ms = list(range(evaluation_start_ms, last_decision_exclusive, DAY_MS))
    valid = [
        item
        for item in rows
        if evaluation_start_ms <= item.decision_ms < last_decision_exclusive
        and item.target_end_ms < evaluation_end_ms
    ]
    denominator_by_year: dict[int, int] = defaultdict(int)
    valid_by_year: dict[int, int] = defaultdict(int)
    for decision_ms in denominator_ms:
        denominator_by_year[_year(decision_ms + horizon_days * DAY_MS)] += 1
    for item in valid:
        valid_by_year[_year(item.target_end_ms)] += 1
    years = sorted(set(denominator_by_year) | set(valid_by_year))
    return {
        "denominator_rows": len(denominator_ms),
        "overall": len(valid) / len(denominator_ms) if denominator_ms else 0.0,
        "per_year": {
            str(year): {
                "denominator": denominator_by_year[year],
                "fraction": valid_by_year[year] / denominator_by_year[year] if denominator_by_year[year] else 0.0,
                "valid": valid_by_year[year],
            }
            for year in years
        },
        "valid_rows": len(valid),
    }


__all__ = [
    "DailyDownsideObservation",
    "DownsideForecast",
    "DownsideModel",
    "DownsideResearchError",
    "DownsideSample",
    "HorizonTailLoss",
    "build_daily_downside_observations",
    "build_downside_samples",
    "build_forecasts",
    "build_horizon_tail_losses",
    "calendar_coverage",
    "canonical_json",
    "es_calibration_moment",
    "fit_downside_model",
    "fz0_loss",
    "historical_var_es",
    "month_block_bootstrap",
    "parse_utc_ms",
    "pinball_loss",
    "qlike_loss",
    "sha256_file",
    "write_jsonl_gzip",
]
