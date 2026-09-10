"""Offline completed-displacement unwind research; never strategy or execution logic."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Mapping, Sequence

import numpy as np

from trading_platform.research_persistence import (
    PersistenceCandle,
    PersistenceResearchError,
    month_block_bootstrap,
)


class ReversionResearchError(PersistenceResearchError):
    """Raised for invalid causal displacement, event, or control construction."""


@dataclass(frozen=True, slots=True)
class DisplacementRow:
    segment: str
    observed_at: datetime
    target_available_at: datetime
    horizon: str
    horizon_bars: int
    displacement: float
    displacement_z: float
    candidate_score: float
    past_realized_variance: float
    forward_return: float
    signed_reversal: float

    @property
    def direction(self) -> int:
        return 1 if self.displacement > 0 else -1


@dataclass(frozen=True, slots=True)
class MatchedEvent:
    event: DisplacementRow
    control: DisplacementRow | None


def build_displacement_rows(
    candles: Sequence[PersistenceCandle],
    horizons: Mapping[str, int],
    *,
    displacement_bars: int = 6,
    reference_observations: int = 126,
) -> dict[str, list[DisplacementRow]]:
    if displacement_bars < 1 or reference_observations < 2:
        raise ReversionResearchError("invalid displacement or reference window")
    if not horizons or any(value <= 0 for value in horizons.values()):
        raise ReversionResearchError("invalid horizons")
    output = {name: [] for name in horizons}
    start = 0
    while start < len(candles):
        end = start + 1
        while end < len(candles) and candles[end].segment == candles[start].segment:
            end += 1
        segment = candles[start:end]
        closes = np.asarray([row.close for row in segment], dtype=float)
        returns = np.diff(np.log(closes))
        displacements = np.full(len(segment), np.nan)
        for index in range(displacement_bars, len(segment)):
            displacements[index] = float(np.sum(returns[index - displacement_bars : index]))
        first_index = displacement_bars + reference_observations
        for index in range(first_index, len(segment)):
            reference = displacements[index - reference_observations : index]
            if not np.isfinite(reference).all():
                continue
            scale = float(np.std(reference, ddof=1))
            if not math.isfinite(scale) or scale <= 0:
                continue
            displacement = float(displacements[index])
            z_score = (displacement - float(np.mean(reference))) / scale
            past_returns = returns[index - displacement_bars : index]
            past_rv = float(np.sum(past_returns**2))
            if not math.isfinite(z_score) or not math.isfinite(past_rv) or past_rv <= 0:
                continue
            for horizon, bars in horizons.items():
                target_index = index + bars
                if target_index >= len(segment):
                    continue
                forward = math.log(segment[target_index].close / segment[index].close)
                if not math.isfinite(forward) or displacement == 0:
                    continue
                direction = 1 if displacement > 0 else -1
                output[horizon].append(
                    DisplacementRow(
                        segment=segment[index].segment,
                        observed_at=segment[index].close_at,
                        target_available_at=segment[target_index].close_at,
                        horizon=horizon,
                        horizon_bars=bars,
                        displacement=displacement,
                        displacement_z=z_score,
                        candidate_score=-z_score,
                        past_realized_variance=past_rv,
                        forward_return=forward,
                        signed_reversal=-direction * forward,
                    )
                )
        start = end
    return output


def feature_coverage(
    candles: Sequence[PersistenceCandle],
    rows: Sequence[DisplacementRow],
    *,
    evaluation_start: datetime,
    evaluation_end: datetime,
) -> dict[str, Any]:
    denominator = [row for row in candles if evaluation_start <= row.close_at < evaluation_end]
    observed = {
        row.observed_at for row in rows if evaluation_start <= row.observed_at < evaluation_end
    }
    by_year_denominator: dict[int, int] = {}
    for row in denominator:
        by_year_denominator[row.close_at.year] = by_year_denominator.get(row.close_at.year, 0) + 1
    by_year_valid: dict[int, int] = {}
    for timestamp in observed:
        by_year_valid[timestamp.year] = by_year_valid.get(timestamp.year, 0) + 1
    return {
        "denominator_rows": len(denominator),
        "overall": len(observed) / len(denominator) if denominator else 0.0,
        "per_year": {
            str(year): {
                "denominator": by_year_denominator[year],
                "fraction": by_year_valid.get(year, 0) / by_year_denominator[year],
                "valid": by_year_valid.get(year, 0),
            }
            for year in sorted(by_year_denominator)
        },
        "valid_rows": len(observed),
    }


def select_nonoverlapping_events(
    rows: Sequence[DisplacementRow],
    *,
    threshold: float,
    evaluation_start: datetime,
    evaluation_end: datetime,
) -> list[DisplacementRow]:
    if threshold <= 0:
        raise ReversionResearchError("event threshold must be positive")
    eligible = sorted(
        (
            row
            for row in rows
            if evaluation_start <= row.observed_at < evaluation_end
            and row.target_available_at < evaluation_end
            and abs(row.displacement_z) >= threshold
        ),
        key=lambda row: row.observed_at,
    )
    selected: list[DisplacementRow] = []
    available_after: datetime | None = None
    for row in eligible:
        if available_after is None or row.observed_at >= available_after:
            selected.append(row)
            available_after = row.target_available_at
    return selected


def _overlap(left: DisplacementRow, right: DisplacementRow) -> bool:
    return left.observed_at < right.target_available_at and right.observed_at < left.target_available_at


def match_completed_controls(
    events: Sequence[DisplacementRow],
    all_rows: Sequence[DisplacementRow],
    *,
    quiet_absolute_z_maximum: float,
    maximum_lookback_days: int,
    maximum_variance_ratio: float,
) -> list[MatchedEvent]:
    if quiet_absolute_z_maximum < 0 or maximum_lookback_days <= 0 or maximum_variance_ratio < 1:
        raise ReversionResearchError("invalid control matching parameters")
    ordered_events = sorted(events, key=lambda row: row.observed_at)
    for left, right in zip(ordered_events, ordered_events[1:], strict=False):
        if _overlap(left, right):
            raise ReversionResearchError("event targets overlap")
    used_controls: list[DisplacementRow] = []
    output: list[MatchedEvent] = []
    maximum_age = timedelta(days=maximum_lookback_days)
    for event in ordered_events:
        candidates: list[tuple[float, float, str, DisplacementRow]] = []
        for control in all_rows:
            if abs(control.displacement_z) > quiet_absolute_z_maximum:
                continue
            if control.direction != event.direction or control.horizon != event.horizon:
                continue
            if control.target_available_at >= event.observed_at:
                continue
            if event.observed_at - control.observed_at > maximum_age:
                continue
            if any(_overlap(control, other) for other in ordered_events):
                continue
            if any(_overlap(control, other) for other in used_controls):
                continue
            ratio = max(event.past_realized_variance, control.past_realized_variance) / min(
                event.past_realized_variance, control.past_realized_variance
            )
            if ratio > maximum_variance_ratio:
                continue
            distance = abs(
                math.log(event.past_realized_variance)
                - math.log(control.past_realized_variance)
            )
            candidates.append((distance, -control.observed_at.timestamp(), control.segment, control))
        if candidates:
            control = min(candidates, key=lambda value: value[:3])[3]
            used_controls.append(control)
            output.append(MatchedEvent(event, control))
        else:
            output.append(MatchedEvent(event, None))
    return output


def _month_means(values: Sequence[tuple[str, float]]) -> dict[str, float]:
    grouped: dict[str, list[float]] = {}
    for month, value in values:
        grouped.setdefault(month, []).append(value)
    return {month: float(np.mean(grouped[month])) for month in sorted(grouped)}


def _year_means(values: Sequence[tuple[int, float]]) -> dict[str, float]:
    grouped: dict[int, list[float]] = {}
    for year, value in values:
        grouped.setdefault(year, []).append(value)
    return {str(year): float(np.mean(grouped[year])) for year in sorted(grouped)}


def evaluate_matched_events(
    matched: Sequence[MatchedEvent], *, replications: int, seed: int
) -> dict[str, Any]:
    if not matched:
        raise ReversionResearchError("event cohort is empty")
    events = [item.event for item in matched]
    matched_only = [item for item in matched if item.control is not None]
    event_months = _month_means(
        [(row.target_available_at.strftime("%Y-%m"), row.signed_reversal) for row in events]
    )
    delta_months = _month_means(
        [
            (
                item.event.target_available_at.strftime("%Y-%m"),
                item.event.signed_reversal - item.control.signed_reversal,
            )
            for item in matched_only
            if item.control is not None
        ]
    )
    event_interval = month_block_bootstrap(
        list(event_months.values()), replications=replications, seed=seed
    )
    delta_interval = (
        month_block_bootstrap(list(delta_months.values()), replications=replications, seed=seed)
        if len(delta_months) >= 2
        else None
    )
    annual_event = _year_means(
        [(row.target_available_at.year, row.signed_reversal) for row in events]
    )
    annual_delta = _year_means(
        [
            (
                item.event.target_available_at.year,
                item.event.signed_reversal - item.control.signed_reversal,
            )
            for item in matched_only
            if item.control is not None
        ]
    )
    event_count_by_year: dict[str, int] = {}
    matched_count_by_year: dict[str, int] = {}
    for item in matched:
        year = str(item.event.target_available_at.year)
        event_count_by_year[year] = event_count_by_year.get(year, 0) + 1
        if item.control is not None:
            matched_count_by_year[year] = matched_count_by_year.get(year, 0) + 1
    side_rows = {
        "negative_displacement": [row for row in events if row.direction < 0],
        "positive_displacement": [row for row in events if row.direction > 0],
    }
    ordered_months = sorted(event_months.items(), key=lambda item: (-item[1], item[0]))
    excluded = {month for month, _ in ordered_months[:3]}
    without_best = [
        row.signed_reversal
        for row in events
        if row.target_available_at.strftime("%Y-%m") not in excluded
    ]
    return {
        "annual_event_mean_reversal": annual_event,
        "annual_matched_event_minus_control": annual_delta,
        "best_three_months": sorted(excluded),
        "event_count": len(events),
        "event_count_by_year": event_count_by_year,
        "event_mean_reversal": float(np.mean([row.signed_reversal for row in events])),
        "event_month_block_mean_reversal": event_interval,
        "event_months_excluding_best_three_mean_reversal": float(np.mean(without_best))
        if without_best
        else None,
        "matched_control_count": len(matched_only),
        "matched_control_coverage": len(matched_only) / len(events),
        "matched_control_coverage_by_year": {
            year: matched_count_by_year.get(year, 0) / count
            for year, count in event_count_by_year.items()
        },
        "matched_event_minus_control_month_block": delta_interval,
        "side_statistics": {
            side: {
                "count": len(rows),
                "fraction": len(rows) / len(events),
                "mean_reversal": float(np.mean([row.signed_reversal for row in rows]))
                if rows
                else None,
            }
            for side, rows in side_rows.items()
        },
    }


def matched_event_as_dict(item: MatchedEvent) -> dict[str, Any]:
    event = item.event
    control = item.control
    return {
        "candidate_score": event.candidate_score,
        "control_observed_at": control.observed_at.strftime("%Y-%m-%dT%H:%M:%SZ")
        if control
        else None,
        "control_past_realized_variance": control.past_realized_variance if control else None,
        "control_signed_reversal": control.signed_reversal if control else None,
        "control_target_available_at": control.target_available_at.strftime("%Y-%m-%dT%H:%M:%SZ")
        if control
        else None,
        "displacement": event.displacement,
        "displacement_direction": event.direction,
        "displacement_z": event.displacement_z,
        "forward_return": event.forward_return,
        "horizon": event.horizon,
        "horizon_bars": event.horizon_bars,
        "observed_at": event.observed_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "past_realized_variance": event.past_realized_variance,
        "segment": event.segment,
        "signed_reversal": event.signed_reversal,
        "target_available_at": event.target_available_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
