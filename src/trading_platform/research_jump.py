"""Causal four-hour jump/change information research for BTC MCS3-J only."""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Sequence

from trading_platform.research_condition_scores import realized_variation_components
from trading_platform.research_downside import month_block_bootstrap
from trading_platform.research_ledger import FIVE_MINUTES_MS, sha256_file
from trading_platform.research_persistence import (
    canonical_json,
    effective_observations,
    spearman_rank_correlation,
    write_jsonl_gzip,
)
from trading_platform.research_routing import canonical_digest
from trading_platform.research_volatility import CandlePoint, parse_utc_ms


UTC = timezone.utc
FOUR_HOURS_MS = 48 * FIVE_MINUTES_MS


class JumpResearchError(ValueError):
    """Raised when MCS3-J inputs, chronology, or score domains fail closed."""


def _finite(value: float, label: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise JumpResearchError(f"{label} must be finite")
    return number


def _probability(value: float, label: str) -> float:
    number = _finite(value, label)
    if not 0 <= number <= 1:
        raise JumpResearchError(f"{label} must be within [0, 1]")
    return number


def _month(timestamp_ms: int) -> str:
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC).strftime("%Y-%m")


def _year(timestamp_ms: int) -> int:
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC).year


@dataclass(frozen=True, slots=True)
class JumpObservation:
    observed_ms: int
    segment: str
    realized_variance: float
    bipower_variation: float
    nonnegative_jump_variation: float
    jump_share: float
    event_indicator: int
    source_digest: str

    def __post_init__(self) -> None:
        if self.observed_ms % FOUR_HOURS_MS or not self.segment or not self.source_digest:
            raise JumpResearchError("jump observation identity is invalid")
        for value in (
            self.realized_variance,
            self.bipower_variation,
            self.nonnegative_jump_variation,
        ):
            if _finite(value, "variation component") < 0:
                raise JumpResearchError("variation component must be nonnegative")
        _probability(self.jump_share, "jump share")
        if self.event_indicator not in (0, 1):
            raise JumpResearchError("event indicator must be binary")

    @property
    def digest(self) -> str:
        return canonical_digest(self.as_dict(include_digest=False))

    def as_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        result = {
            "bipower_variation": self.bipower_variation,
            "event_indicator": self.event_indicator,
            "instrument": "BTC/USDT",
            "interval": "4h",
            "jump_share": self.jump_share,
            "nonnegative_jump_variation": self.nonnegative_jump_variation,
            "observed_ms": self.observed_ms,
            "realized_variance": self.realized_variance,
            "segment": self.segment,
            "source_digest": self.source_digest,
        }
        if include_digest:
            result["digest"] = self.digest
        return result


@dataclass(frozen=True, slots=True)
class JumpForecast:
    decision_ms: int
    target_end_ms: int
    horizon_blocks: int
    segment: str
    control_probability: float
    candidate_probability: float
    control_intensity: float
    candidate_intensity: float
    target_event: int
    target_intensity: float
    source_digest: str

    def __post_init__(self) -> None:
        if self.horizon_blocks not in (1, 6):
            raise JumpResearchError("unsupported jump horizon")
        if self.target_end_ms != self.decision_ms + self.horizon_blocks * FOUR_HOURS_MS:
            raise JumpResearchError("jump forecast horizon is invalid")
        if not self.segment or not self.source_digest:
            raise JumpResearchError("jump forecast identity is invalid")
        for value in (self.control_probability, self.candidate_probability):
            _probability(value, "forecast probability")
        for value in (
            self.control_intensity,
            self.candidate_intensity,
            self.target_intensity,
        ):
            _probability(value, "jump intensity")
        if self.target_event not in (0, 1):
            raise JumpResearchError("target event must be binary")

    @property
    def digest(self) -> str:
        return canonical_digest(self.as_dict(include_digest=False))

    def as_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        result = {
            "candidate_intensity": self.candidate_intensity,
            "candidate_probability": self.candidate_probability,
            "control_intensity": self.control_intensity,
            "control_probability": self.control_probability,
            "decision_ms": self.decision_ms,
            "horizon_blocks": self.horizon_blocks,
            "segment": self.segment,
            "source_digest": self.source_digest,
            "target_end_ms": self.target_end_ms,
            "target_event": self.target_event,
            "target_intensity": self.target_intensity,
        }
        if include_digest:
            result["digest"] = self.digest
        return result


def build_four_hour_jump_observations(
    candles: Sequence[CandlePoint],
    *,
    start_ms: int,
    end_ms: int,
    source_digest: str,
    event_threshold: float = 0.5,
) -> tuple[list[JumpObservation], dict[str, Any]]:
    if start_ms % FOUR_HOURS_MS or end_ms % FOUR_HOURS_MS or start_ms >= end_ms:
        raise JumpResearchError("four-hour boundary is invalid")
    threshold = _probability(event_threshold, "event threshold")
    open_index = {item.open_ms: index for index, item in enumerate(candles)}
    if len(open_index) != len(candles):
        raise JumpResearchError("duplicate candle open time")
    output: list[JumpObservation] = []
    excluded: dict[str, int] = defaultdict(int)
    for block_start in range(start_ms, end_ms, FOUR_HOURS_MS):
        first_index = open_index.get(block_start)
        prior_index = open_index.get(block_start - FIVE_MINUTES_MS)
        if first_index is None:
            excluded["block_start_missing"] += 1
            continue
        if prior_index is None or prior_index + 1 != first_index:
            excluded["prior_close_missing_or_noncontiguous"] += 1
            continue
        if prior_index + 48 >= len(candles):
            excluded["incomplete_or_cross_segment_block"] += 1
            continue
        segment = candles[first_index].segment
        window = [candles[prior_index + offset] for offset in range(49)]
        if any(
            item.segment != segment
            or item.open_ms != block_start - FIVE_MINUTES_MS + offset * FIVE_MINUTES_MS
            for offset, item in enumerate(window)
        ):
            excluded["incomplete_or_cross_segment_block"] += 1
            continue
        returns = [
            math.log(current.close / previous.close)
            for previous, current in zip(window, window[1:], strict=False)
        ]
        components = realized_variation_components(returns)
        output.append(
            JumpObservation(
                observed_ms=block_start + FOUR_HOURS_MS,
                segment=segment,
                realized_variance=components.realized_variance,
                bipower_variation=components.bipower_variation,
                nonnegative_jump_variation=components.nonnegative_jump_variation,
                jump_share=components.jump_share,
                event_indicator=int(components.jump_share >= threshold),
                source_digest=source_digest,
            )
        )
    if any(right.observed_ms <= left.observed_ms for left, right in zip(output, output[1:], strict=False)):
        raise JumpResearchError("jump observations are not strictly ordered")
    return output, {
        "excluded": dict(sorted(excluded.items())),
        "expected_blocks": (end_ms - start_ms) // FOUR_HOURS_MS,
        "valid_blocks": len(output),
    }


def build_jump_forecasts(
    observations: Sequence[JumpObservation],
    horizon_blocks: int,
    *,
    lookback_blocks: int = 180,
    decay_lambda: float = 0.94,
    threshold: float = 0.5,
    probability_alpha: float = 0.5,
    probability_beta: float = 0.5,
) -> list[JumpForecast]:
    if horizon_blocks not in (1, 6):
        raise JumpResearchError("unsupported jump horizon")
    if lookback_blocks != 180 or decay_lambda != 0.94 or threshold != 0.5:
        raise JumpResearchError("frozen jump forecast configuration changed")
    if probability_alpha != 0.5 or probability_beta != 0.5:
        raise JumpResearchError("frozen probability smoothing changed")
    output: list[JumpForecast] = []
    segment_start = 0
    state_probability: float | None = None
    state_intensity: float | None = None
    previous: JumpObservation | None = None
    for index, current in enumerate(observations):
        contiguous = (
            previous is not None
            and current.segment == previous.segment
            and current.observed_ms == previous.observed_ms + FOUR_HOURS_MS
        )
        if not contiguous:
            segment_start = index
            state_probability = None
            state_intensity = None
        segment_count = index - segment_start + 1
        if segment_count >= lookback_blocks:
            history = observations[index - lookback_blocks + 1 : index + 1]
            if any(
                item.segment != current.segment
                or item.observed_ms
                != current.observed_ms - (lookback_blocks - 1 - offset) * FOUR_HOURS_MS
                for offset, item in enumerate(history)
            ):
                raise JumpResearchError("rolling jump history crossed a gap or segment")
            control_probability = (
                sum(item.event_indicator for item in history) + probability_alpha
            ) / (lookback_blocks + probability_alpha + probability_beta)
            control_intensity = statistics.fmean(item.jump_share for item in history)
            if state_probability is None or state_intensity is None:
                state_probability = control_probability
                state_intensity = control_intensity
            else:
                state_probability = (
                    decay_lambda * state_probability
                    + (1 - decay_lambda) * current.event_indicator
                )
                state_intensity = (
                    decay_lambda * state_intensity
                    + (1 - decay_lambda) * current.jump_share
                )
            future = observations[index + 1 : index + horizon_blocks + 1]
            if len(future) == horizon_blocks and all(
                item.segment == current.segment
                and item.observed_ms == current.observed_ms + offset * FOUR_HOURS_MS
                for offset, item in enumerate(future, start=1)
            ):
                candidate_probability = state_probability
                horizon_control_probability = control_probability
                if horizon_blocks == 6:
                    candidate_probability = 1 - (1 - candidate_probability) ** 6
                    horizon_control_probability = 1 - (1 - horizon_control_probability) ** 6
                output.append(
                    JumpForecast(
                        decision_ms=current.observed_ms,
                        target_end_ms=current.observed_ms + horizon_blocks * FOUR_HOURS_MS,
                        horizon_blocks=horizon_blocks,
                        segment=current.segment,
                        control_probability=horizon_control_probability,
                        candidate_probability=candidate_probability,
                        control_intensity=control_intensity,
                        candidate_intensity=state_intensity,
                        target_event=int(any(item.event_indicator for item in future)),
                        target_intensity=statistics.fmean(item.jump_share for item in future),
                        source_digest=canonical_digest(
                            {
                                "history_digests": [item.digest for item in history],
                                "target_digests": [item.digest for item in future],
                            }
                        ),
                    )
                )
        previous = current
    return output


def brier_loss(probability: float, target: int) -> float:
    forecast = _probability(probability, "Brier probability")
    if target not in (0, 1):
        raise JumpResearchError("Brier target must be binary")
    return (forecast - target) ** 2


def log_loss(
    probability: float, target: int, clip: float = 1e-6
) -> float:
    forecast = _probability(probability, "log-loss probability")
    if target not in (0, 1) or not 0 < clip < 0.5:
        raise JumpResearchError("log-loss target or clip is invalid")
    clipped = min(1 - clip, max(clip, forecast))
    return -(target * math.log(clipped) + (1 - target) * math.log(1 - clipped))


def average_precision(probabilities: Sequence[float], targets: Sequence[int]) -> float:
    if len(probabilities) != len(targets) or not probabilities:
        raise JumpResearchError("average-precision inputs are invalid")
    checked = [(_probability(probability, "AP probability"), int(target), index) for index, (probability, target) in enumerate(zip(probabilities, targets, strict=True))]
    if any(target not in (0, 1) for _, target, _ in checked):
        raise JumpResearchError("AP target must be binary")
    positives = sum(target for _, target, _ in checked)
    if positives == 0 or positives == len(checked):
        raise JumpResearchError("average precision requires positive and negative targets")
    ordered = sorted(checked, key=lambda item: (-item[0], item[2]))
    true_positives = 0
    seen = 0
    result = 0.0
    index = 0
    while index < len(ordered):
        probability = ordered[index][0]
        end = index
        group_positives = 0
        while end < len(ordered) and ordered[end][0] == probability:
            group_positives += ordered[end][1]
            end += 1
        true_positives += group_positives
        seen = end
        result += (group_positives / positives) * (true_positives / seen)
        index = end
    return result


def calibration_bins(
    probabilities: Sequence[float], targets: Sequence[int], bins: int = 5
) -> dict[str, Any]:
    if len(probabilities) != len(targets) or len(probabilities) < bins or bins < 2:
        raise JumpResearchError("calibration inputs are invalid")
    ordered = sorted(
        [(_probability(probability, "calibration probability"), int(target), index) for index, (probability, target) in enumerate(zip(probabilities, targets, strict=True))],
        key=lambda item: (item[0], item[2]),
    )
    if any(target not in (0, 1) for _, target, _ in ordered):
        raise JumpResearchError("calibration target must be binary")
    output: list[dict[str, Any]] = []
    weighted_error = 0.0
    for bucket in range(bins):
        start = len(ordered) * bucket // bins
        end = len(ordered) * (bucket + 1) // bins
        selected = ordered[start:end]
        mean_probability = statistics.fmean(item[0] for item in selected)
        event_rate = statistics.fmean(item[1] for item in selected)
        weighted_error += len(selected) * abs(mean_probability - event_rate)
        output.append({
            "count": len(selected),
            "event_rate": event_rate,
            "mean_probability": mean_probability,
        })
    return {"bins": output, "ece": weighted_error / len(ordered)}


def _wilson_interval(successes: int, count: int, z: float) -> list[float]:
    if count <= 0 or not 0 <= successes <= count:
        raise JumpResearchError("invalid Wilson interval counts")
    proportion = successes / count
    denominator = 1 + z * z / count
    center = (proportion + z * z / (2 * count)) / denominator
    radius = z * math.sqrt(
        proportion * (1 - proportion) / count + z * z / (4 * count * count)
    ) / denominator
    return [center - radius, center + radius]


def _losses(item: JumpForecast) -> dict[str, float]:
    return {
        "candidate_brier": brier_loss(item.candidate_probability, item.target_event),
        "candidate_intensity_mae": abs(item.candidate_intensity - item.target_intensity),
        "candidate_intensity_mse": (item.candidate_intensity - item.target_intensity) ** 2,
        "candidate_log_loss": log_loss(item.candidate_probability, item.target_event),
        "control_brier": brier_loss(item.control_probability, item.target_event),
        "control_intensity_mae": abs(item.control_intensity - item.target_intensity),
        "control_intensity_mse": (item.control_intensity - item.target_intensity) ** 2,
        "control_log_loss": log_loss(item.control_probability, item.target_event),
    }


def score_jump_forecasts(
    rows: Sequence[JumpForecast],
    *,
    bootstrap_replications: int,
    bootstrap_seed: int,
    wilson_z: float = 1.959963984540054,
) -> dict[str, Any]:
    if not rows:
        raise JumpResearchError("cannot score empty jump forecasts")
    enriched = [(item, _losses(item)) for item in rows]
    targets = [item.target_event for item in rows]
    event_count = sum(targets)
    if event_count == 0 or event_count == len(rows):
        raise JumpResearchError("jump scoring requires positive and negative events")
    probabilities = [item.candidate_probability for item in rows]
    control_probabilities = [item.control_probability for item in rows]
    prevalence = event_count / len(rows)
    means = {
        key: statistics.fmean(loss[key] for _, loss in enriched)
        for key in enriched[0][1]
    }
    calibration = calibration_bins(probabilities, targets, 5)
    by_month: dict[str, list[tuple[JumpForecast, dict[str, float]]]] = defaultdict(list)
    by_year: dict[int, list[tuple[JumpForecast, dict[str, float]]]] = defaultdict(list)
    for item in enriched:
        by_month[_month(item[0].target_end_ms)].append(item)
        by_year[_year(item[0].target_end_ms)].append(item)
    metric_keys = {
        "brier": ("control_brier", "candidate_brier"),
        "intensity_mse": ("control_intensity_mse", "candidate_intensity_mse"),
        "log_loss": ("control_log_loss", "candidate_log_loss"),
    }
    monthly: dict[str, dict[str, float]] = {}
    for month, group in by_month.items():
        monthly[month] = {
            name: statistics.fmean(loss[control] - loss[candidate] for _, loss in group)
            for name, (control, candidate) in metric_keys.items()
        }
    annual: dict[str, dict[str, float | int]] = {}
    for year, group in sorted(by_year.items()):
        annual[str(year)] = {
            "brier_improvement": statistics.fmean(loss["control_brier"] - loss["candidate_brier"] for _, loss in group),
            "event_count": sum(item.target_event for item, _ in group),
            "intensity_mse_improvement": statistics.fmean(loss["control_intensity_mse"] - loss["candidate_intensity_mse"] for _, loss in group),
            "log_loss_improvement": statistics.fmean(loss["control_log_loss"] - loss["candidate_log_loss"] for _, loss in group),
            "observations": len(group),
        }
    leave_one_out: dict[str, dict[str, float]] = {}
    for excluded_year in sorted(by_year):
        selected = [item for item in enriched if _year(item[0].target_end_ms) != excluded_year]
        leave_one_out[str(excluded_year)] = (
            {
                "brier_improvement": statistics.fmean(loss["control_brier"] - loss["candidate_brier"] for _, loss in selected),
                "intensity_mse_improvement": statistics.fmean(loss["control_intensity_mse"] - loss["candidate_intensity_mse"] for _, loss in selected),
                "log_loss_improvement": statistics.fmean(loss["control_log_loss"] - loss["candidate_log_loss"] for _, loss in selected),
            }
            if selected
            else {
                "brier_improvement": None,
                "intensity_mse_improvement": None,
                "log_loss_improvement": None,
            }
        )
    exclusions: dict[str, Any] = {}
    for name in metric_keys:
        removed = set(sorted(monthly, key=lambda key: (-monthly[key][name], key))[:3])
        remaining = [value[name] for month, value in monthly.items() if month not in removed]
        exclusions[f"{name}_improvement"] = (
            statistics.fmean(remaining)
            if remaining
            else statistics.fmean(value[name] for value in monthly.values())
        )
        exclusions[f"{name}_removed_months"] = sorted(removed)
    probability_order = sorted(
        range(len(rows)), key=lambda index: (rows[index].candidate_probability, rows[index].decision_ms)
    )
    probability_quintiles: dict[str, dict[str, float | int]] = {}
    assignments: dict[int, int] = {}
    for bucket in range(5):
        start = len(rows) * bucket // 5
        end = len(rows) * (bucket + 1) // 5
        selected_indices = probability_order[start:end]
        for index in selected_indices:
            assignments[index] = bucket + 1
        probability_quintiles[str(bucket + 1)] = {
            "event_rate": statistics.fmean(rows[index].target_event for index in selected_indices),
            "mean_probability": statistics.fmean(rows[index].candidate_probability for index in selected_indices),
            "observations": len(selected_indices),
        }
    monthly_top_bottom: list[float] = []
    month_indices: dict[str, list[int]] = defaultdict(list)
    for index, item in enumerate(rows):
        month_indices[_month(item.target_end_ms)].append(index)
    for month in sorted(month_indices):
        top = [rows[index].target_event for index in month_indices[month] if assignments[index] == 5]
        bottom = [rows[index].target_event for index in month_indices[month] if assignments[index] == 1]
        if top and bottom:
            monthly_top_bottom.append(statistics.fmean(top) - statistics.fmean(bottom))
    intensity_order = sorted(
        rows, key=lambda item: (item.candidate_intensity, item.decision_ms)
    )
    intensity_quartiles: dict[str, dict[str, float | int]] = {}
    for bucket in range(4):
        start = len(rows) * bucket // 4
        end = len(rows) * (bucket + 1) // 4
        selected = intensity_order[start:end]
        intensity_quartiles[str(bucket + 1)] = {
            "mean_forecast_intensity": statistics.fmean(item.candidate_intensity for item in selected),
            "mean_realized_intensity": statistics.fmean(item.target_intensity for item in selected),
            "observations": len(selected),
        }
    return {
        "annual": annual,
        "average_precision": {
            "candidate": average_precision(probabilities, targets),
            "control": average_precision(control_probabilities, targets),
            "prevalence": prevalence,
        },
        "calibration": calibration,
        "candidate": {
            "average_precision": average_precision(probabilities, targets),
            "average_precision_ratio_to_prevalence": average_precision(probabilities, targets) / prevalence,
            "brier_skill": 1 - means["candidate_brier"] / means["control_brier"],
            "forecast_mean": statistics.fmean(probabilities),
            "mean_brier": means["candidate_brier"],
            "mean_intensity_mae": means["candidate_intensity_mae"],
            "mean_intensity_mse": means["candidate_intensity_mse"],
            "mean_log_loss": means["candidate_log_loss"],
        },
        "control": {
            "average_precision": average_precision(control_probabilities, targets),
            "mean_brier": means["control_brier"],
            "mean_intensity_mae": means["control_intensity_mae"],
            "mean_intensity_mse": means["control_intensity_mse"],
            "mean_log_loss": means["control_log_loss"],
        },
        "effective_observations": effective_observations(targets, 6),
        "event_count": event_count,
        "event_count_by_year": {str(year): sum(item.target_event for item, _ in group) for year, group in sorted(by_year.items())},
        "event_fraction_wilson_95": _wilson_interval(event_count, len(rows), wilson_z),
        "event_prevalence": prevalence,
        "excluding_best_three_months": exclusions,
        "intensity_quartiles": intensity_quartiles,
        "intensity_spearman": spearman_rank_correlation(
            [item.candidate_intensity for item in rows],
            [item.target_intensity for item in rows],
        ),
        "leave_one_year_out": leave_one_out,
        "month_block_brier_improvement": month_block_bootstrap(
            [monthly[key]["brier"] for key in sorted(monthly)],
            replications=bootstrap_replications,
            seed=bootstrap_seed,
        ),
        "month_block_intensity_mse_improvement": month_block_bootstrap(
            [monthly[key]["intensity_mse"] for key in sorted(monthly)],
            replications=bootstrap_replications,
            seed=bootstrap_seed,
        ),
        "month_block_log_loss_improvement": month_block_bootstrap(
            [monthly[key]["log_loss"] for key in sorted(monthly)],
            replications=bootstrap_replications,
            seed=bootstrap_seed,
        ),
        "month_block_top_minus_bottom_probability_quintile_event_rate": month_block_bootstrap(
            monthly_top_bottom,
            replications=bootstrap_replications,
            seed=bootstrap_seed,
        ),
        "observations": len(rows),
        "probability_quintiles": probability_quintiles,
    }


def calendar_coverage(
    rows: Sequence[JumpForecast],
    *,
    evaluation_start_ms: int,
    evaluation_end_ms: int,
    horizon_blocks: int,
) -> dict[str, Any]:
    if horizon_blocks not in (1, 6):
        raise JumpResearchError("unsupported coverage horizon")
    last_decision_exclusive = evaluation_end_ms - horizon_blocks * FOUR_HOURS_MS
    denominator = list(range(evaluation_start_ms, last_decision_exclusive, FOUR_HOURS_MS))
    valid = [
        item
        for item in rows
        if evaluation_start_ms <= item.decision_ms < last_decision_exclusive
        and item.target_end_ms < evaluation_end_ms
    ]
    denominator_by_year: dict[int, int] = defaultdict(int)
    valid_by_year: dict[int, int] = defaultdict(int)
    for decision_ms in denominator:
        denominator_by_year[_year(decision_ms + horizon_blocks * FOUR_HOURS_MS)] += 1
    for item in valid:
        valid_by_year[_year(item.target_end_ms)] += 1
    years = sorted(set(denominator_by_year) | set(valid_by_year))
    return {
        "denominator_rows": len(denominator),
        "overall": len(valid) / len(denominator) if denominator else 0.0,
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
    "FOUR_HOURS_MS",
    "JumpForecast",
    "JumpObservation",
    "JumpResearchError",
    "average_precision",
    "brier_loss",
    "build_four_hour_jump_observations",
    "build_jump_forecasts",
    "calendar_coverage",
    "calibration_bins",
    "canonical_json",
    "log_loss",
    "month_block_bootstrap",
    "parse_utc_ms",
    "score_jump_forecasts",
    "sha256_file",
    "write_jsonl_gzip",
]
