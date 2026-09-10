"""Causal BTC compression-breakout event catalogue for offline research.

This module identifies independent historical *events*.  It does not create a strategy,
position, order, signal payload, or PnL.  Every calculation is reset at the source segment
boundary and uses only completed candles available at the recorded decision time.
"""

from __future__ import annotations

import csv
import gzip
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from trading_platform.research_ledger import (
    DAY_MS,
    FIVE_MINUTES_MS,
    FOUR_HOURS_MS,
    AggregateCandle,
    SourceCandle,
    aggregate_candles,
    iso_ms,
    reject_symlink_tree,
    sha256_file,
)
from trading_platform.research_routing import canonical_digest


ONE_HOUR_MS = 12 * FIVE_MINUTES_MS
RANGE_BARS_4H = 42
REFERENCE_WIDTHS = 540
COMPRESSION_RUN = 3
COMPRESSION_QUANTILE = 0.20
SETUP_LIFETIME_MS = 7 * DAY_MS
PATH_LIFETIME_MS = 7 * DAY_MS
PATH_HORIZONS_HOURS = (24, 72, 168)


class BreakoutEventError(ValueError):
    """Raised when source data or event construction is ambiguous or non-causal."""


@dataclass(frozen=True, slots=True)
class BreakoutSourceCandle:
    """SourceCandle-compatible row which retains the canonical raw trade count."""

    segment: int
    open_ms: int
    raw_close_time_ms: int
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
        """Causal availability boundary, one millisecond after the raw inclusive close."""

        return self.open_ms + FIVE_MINUTES_MS

def load_breakout_source_candles(
    path: Path, expected_sha256: str
) -> tuple[list[BreakoutSourceCandle], str]:
    """Load the local canonical gzip CSV while preserving its raw ``trade_count``.

    This deliberately does not call the general ledger loader, whose narrower SourceCandle
    record predates the trade-count diagnostic.  It has the same checksum, symlink and sealed
    partition protections and performs no network or service access.
    """

    reject_symlink_tree(path)
    resolved = path.resolve(strict=True)
    lowered = resolved.name.lower()
    if "holdout" in lowered or "2026-01-07" in lowered:
        raise BreakoutEventError("sealed holdout input is prohibited")
    digest = sha256_file(resolved)
    if digest != expected_sha256:
        raise BreakoutEventError(
            f"source checksum mismatch: expected {expected_sha256}, got {digest}"
        )
    required = {
        "segment_id",
        "open_time_ms",
        "close_time_ms",
        "open",
        "high",
        "low",
        "close",
        "base_volume",
        "quote_volume",
        "trade_count",
    }
    rows: list[BreakoutSourceCandle] = []
    with gzip.open(resolved, "rt", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = sorted(required - set(reader.fieldnames or ()))
        if missing:
            raise BreakoutEventError(f"breakout source lacks columns: {missing}")
        for source_row, raw in enumerate(reader):
            try:
                row = BreakoutSourceCandle(
                    segment=int(raw["segment_id"]),
                    open_ms=int(raw["open_time_ms"]),
                    raw_close_time_ms=int(raw["close_time_ms"]),
                    open=float(raw["open"]),
                    high=float(raw["high"]),
                    low=float(raw["low"]),
                    close=float(raw["close"]),
                    base_volume=float(raw["base_volume"]),
                    quote_volume=float(raw["quote_volume"]),
                    source_row=source_row,
                    trade_count=int(raw["trade_count"]),
                )
            except (TypeError, ValueError) as exc:
                raise BreakoutEventError(
                    f"invalid breakout source value at line {source_row + 2}"
                ) from exc
            rows.append(row)
    _validate_source(rows, digest, "breakout-source-load-validation")
    if any(row.trade_count < 0 for row in rows):
        raise BreakoutEventError("source trade_count must be nonnegative")
    return rows, digest


def linear_quantile(values: Sequence[float], probability: float) -> float:
    """Return the deterministic, linearly interpolated sample quantile."""

    if not values or not 0.0 <= probability <= 1.0:
        raise BreakoutEventError("invalid quantile request")
    ordered = sorted(float(value) for value in values)
    if not all(math.isfinite(value) for value in ordered):
        raise BreakoutEventError("quantile values must be finite")
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


@dataclass(frozen=True, slots=True)
class BreakoutPathSnapshot:
    horizon_hours: int
    complete: bool
    observed_until_ms: int | None
    observation_count_5m: int
    displacement_log: float | None
    outside_fraction: float | None
    maximum_favourable_excursion_log: float | None
    maximum_adverse_excursion_log: float | None
    time_to_maximum_favourable_excursion_hours: float | None
    time_to_maximum_adverse_excursion_hours: float | None
    path_efficiency: float | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "complete": self.complete,
            "displacement_log": self.displacement_log,
            "horizon_hours": self.horizon_hours,
            "maximum_adverse_excursion_log": self.maximum_adverse_excursion_log,
            "maximum_favourable_excursion_log": self.maximum_favourable_excursion_log,
            "time_to_maximum_adverse_excursion_hours": (
                self.time_to_maximum_adverse_excursion_hours
            ),
            "time_to_maximum_favourable_excursion_hours": (
                self.time_to_maximum_favourable_excursion_hours
            ),
            "observation_count_5m": self.observation_count_5m,
            "observed_until": (
                iso_ms(self.observed_until_ms) if self.observed_until_ms is not None else None
            ),
            "outside_fraction": self.outside_fraction,
            "path_efficiency": self.path_efficiency,
        }


@dataclass(frozen=True, slots=True)
class BreakoutEpisode:
    experiment_id: str
    episode_id: str
    source_digest: str
    segment: int
    activation_ms: int
    upper_boundary: float
    lower_boundary: float
    range_width_log: float
    reference_q20: float
    compression_percentile: float
    compression_duration_bars: int
    compression_duration_hours: int
    confirmation_delay_hours: int | None
    first_5m_touch_ms: int | None
    first_5m_close_cross_ms: int | None
    termination_ms: int
    termination_reason: str
    confirmation_ms: int | None
    first_eligible_5m_ms: int | None
    first_eligible_price: float | None
    confirmation_close: float | None
    pre_sigma24: float | None
    pre_sigma7d: float | None
    range_width_over_sigma7d: float | None
    sigma24_over_sigma7d: float | None
    confirmation_log_penetration_over_sigma24: float | None
    confirmation_hour_fraction_5m_closes_above_upper: float | None
    lagged_24h_quote_volume: float | None
    lagged_24h_quote_volume_surprise: float | None
    lagged_24h_trade_count_surprise: float | None
    hour_of_week: int | None
    hour_of_week_sine: float | None
    hour_of_week_cosine: float | None
    model_ready: bool
    augmented_diagnostic_ready: bool
    model_unavailable_reasons: tuple[str, ...]
    augmented_diagnostic_unavailable_reasons: tuple[str, ...]
    continuation_target_price: float | None
    first_continuation_target_ms: int | None
    first_reentry_ms: int | None
    reentry_below_lower: bool
    competing_outcome: str | None
    competing_outcome_ms: int | None
    censor_reason: str | None
    censor_ms: int | None
    path_segment_censored: bool
    path_observed_until_ms: int | None
    snapshots: tuple[BreakoutPathSnapshot, ...]

    def _payload(self) -> dict[str, Any]:
        return {
            "activation_at": iso_ms(self.activation_ms),
            "competing_outcome": self.competing_outcome,
            "competing_outcome_at": (
                iso_ms(self.competing_outcome_ms)
                if self.competing_outcome_ms is not None
                else None
            ),
            "confirmation_at": (
                iso_ms(self.confirmation_ms) if self.confirmation_ms is not None else None
            ),
            "confirmation_close": self.confirmation_close,
            "feature_available_at": (
                iso_ms(self.confirmation_ms) if self.confirmation_ms is not None else None
            ),
            "feature_observed_at": (
                iso_ms(self.confirmation_ms) if self.confirmation_ms is not None else None
            ),
            "confirmation_hour_fraction_5m_closes_above_upper": (
                self.confirmation_hour_fraction_5m_closes_above_upper
            ),
            "confirmation_log_penetration_over_sigma24": (
                self.confirmation_log_penetration_over_sigma24
            ),
            "confirmation_delay_hours": self.confirmation_delay_hours,
            "compression_duration_hours": self.compression_duration_hours,
            "compression_duration_bars": self.compression_duration_bars,
            "compression_percentile": self.compression_percentile,
            "continuation_target_price": self.continuation_target_price,
            "episode_id": self.episode_id,
            "experiment_id": self.experiment_id,
            "first_5m_close_cross_at": (
                iso_ms(self.first_5m_close_cross_ms)
                if self.first_5m_close_cross_ms is not None
                else None
            ),
            "first_5m_touch_at": (
                iso_ms(self.first_5m_touch_ms) if self.first_5m_touch_ms is not None else None
            ),
            "first_continuation_target_at": (
                iso_ms(self.first_continuation_target_ms)
                if self.first_continuation_target_ms is not None
                else None
            ),
            "first_eligible_5m_at": (
                iso_ms(self.first_eligible_5m_ms)
                if self.first_eligible_5m_ms is not None
                else None
            ),
            "first_eligible_price": self.first_eligible_price,
            "first_reentry_at": (
                iso_ms(self.first_reentry_ms) if self.first_reentry_ms is not None else None
            ),
            "hour_of_week": self.hour_of_week,
            "hour_of_week_cosine": self.hour_of_week_cosine,
            "hour_of_week_sine": self.hour_of_week_sine,
            "lagged_24h_quote_volume": self.lagged_24h_quote_volume,
            "lagged_24h_quote_volume_surprise": self.lagged_24h_quote_volume_surprise,
            "lagged_24h_trade_count_surprise": self.lagged_24h_trade_count_surprise,
            "lower_boundary": self.lower_boundary,
            "path_observed_until": (
                iso_ms(self.path_observed_until_ms)
                if self.path_observed_until_ms is not None
                else None
            ),
            "path_segment_censored": self.path_segment_censored,
            "model_ready": self.model_ready,
            "augmented_diagnostic_ready": self.augmented_diagnostic_ready,
            "model_unavailable_reasons": list(self.model_unavailable_reasons),
            "augmented_diagnostic_unavailable_reasons": list(
                self.augmented_diagnostic_unavailable_reasons
            ),
            "pre_sigma24": self.pre_sigma24,
            "pre_sigma7d": self.pre_sigma7d,
            "range_width_log": self.range_width_log,
            "range_width_over_sigma7d": self.range_width_over_sigma7d,
            "reentry_below_lower": self.reentry_below_lower,
            "reference_q20": self.reference_q20,
            "sigma24_over_sigma7d": self.sigma24_over_sigma7d,
            "segment": str(self.segment),
            "snapshots": [snapshot.as_dict() for snapshot in self.snapshots],
            "source_digest": self.source_digest,
            "termination_at": iso_ms(self.termination_ms),
            "termination_reason": self.termination_reason,
            "upper_boundary": self.upper_boundary,
            "censor_at": iso_ms(self.censor_ms) if self.censor_ms is not None else None,
            "censor_reason": self.censor_reason,
        }

    @property
    def record_digest(self) -> str:
        return canonical_digest(self._payload())

    def as_dict(self) -> dict[str, Any]:
        return {**self._payload(), "record_digest": self.record_digest}


@dataclass(frozen=True, slots=True)
class BreakoutEventCatalogue:
    experiment_id: str
    source_digest: str
    source_rows: int
    aggregate_rows_1h: int
    aggregate_rows_4h: int
    episodes: tuple[BreakoutEpisode, ...]

    def _payload(self) -> dict[str, Any]:
        return {
            "actionable_arm_id": "no_trade",
            "aggregate_rows_1h": self.aggregate_rows_1h,
            "aggregate_rows_4h": self.aggregate_rows_4h,
            "episodes": [episode.as_dict() for episode in self.episodes],
            "experiment_id": self.experiment_id,
            "research_disposition": "development_event_catalogue_only",
            "source_digest": self.source_digest,
            "source_rows": self.source_rows,
        }

    @property
    def catalogue_digest(self) -> str:
        return canonical_digest(self._payload())

    def as_dict(self) -> dict[str, Any]:
        return {**self._payload(), "catalogue_digest": self.catalogue_digest}


def _validate_source(rows: list[SourceCandle], source_digest: str, experiment_id: str) -> None:
    if not experiment_id.strip():
        raise BreakoutEventError("experiment_id is required")
    if len(source_digest) != 64:
        raise BreakoutEventError("source_digest must be a 64-character SHA-256 digest")
    try:
        int(source_digest, 16)
    except ValueError as exc:
        raise BreakoutEventError("source_digest must be hexadecimal") from exc
    if source_digest != source_digest.lower():
        raise BreakoutEventError("source_digest must use lowercase hexadecimal")
    if not rows:
        raise BreakoutEventError("source candles are required")
    previous: SourceCandle | None = None
    closed_segments: set[int] = set()
    for index, row in enumerate(rows):
        prices = (row.open, row.high, row.low, row.close)
        trade_count = getattr(row, "trade_count", None)
        try:
            trade_count_invalid = trade_count is not None and (
                not math.isfinite(float(trade_count)) or float(trade_count) < 0.0
            )
        except (TypeError, ValueError):
            trade_count_invalid = True
        if (
            row.segment < 0
            or row.open_ms < 0
            or row.open_ms % FIVE_MINUTES_MS
            or row.close_ms != row.open_ms + FIVE_MINUTES_MS
            or (
                hasattr(row, "raw_close_time_ms")
                and getattr(row, "raw_close_time_ms") != row.open_ms + FIVE_MINUTES_MS - 1
            )
            or not all(math.isfinite(value) and value > 0 for value in prices)
            or row.low > min(row.open, row.close)
            or row.high < max(row.open, row.close)
            or not math.isfinite(row.base_volume)
            or not math.isfinite(row.quote_volume)
            or row.base_volume < 0
            or row.quote_volume < 0
            or trade_count_invalid
            or row.source_row != index
        ):
            raise BreakoutEventError(f"invalid source candle at row {index}")
        if previous is not None:
            if row.open_ms <= previous.open_ms:
                raise BreakoutEventError("source timestamps are reversed or duplicated")
            if row.segment == previous.segment:
                if row.open_ms != previous.open_ms + FIVE_MINUTES_MS:
                    raise BreakoutEventError("gap inside a source segment")
            else:
                closed_segments.add(previous.segment)
                if row.segment in closed_segments:
                    raise BreakoutEventError("a closed source segment reappears")
        previous = row


def _segment_end(rows: Sequence[SourceCandle]) -> int:
    return rows[-1].close_ms


def _preceding_four_hour_sigmas(
    bars: Sequence[AggregateCandle], confirmation_ms: int
) -> tuple[float | None, float | None]:
    """Use only complete 4h closes strictly before the confirmation timestamp."""

    preceding = [bar for bar in bars if bar.close_ms < confirmation_ms]
    if len(preceding) < 43:
        return None, None
    closes = [bar.close for bar in preceding[-43:]]
    returns = [math.log(right / left) for left, right in zip(closes, closes[1:])]
    sigma24 = math.sqrt(sum(value * value for value in returns[-6:]))
    sigma7d = math.sqrt(sum(value * value for value in returns))
    return sigma24, sigma7d


def _lagged_24h_surprises(
    rows: Sequence[SourceCandle], confirmation_ms: int
) -> tuple[float | None, float | None, float | None, tuple[str, ...]]:
    """Return frozen 24h totals/surprises excluding the entire confirmation hour.

    The final 24h block ends at the confirmation-hour open.  Its reference is the
    arithmetic mean of the immediately preceding 20 non-overlapping 24h blocks.
    ``trade_count`` is optional on SourceCandle-compatible inputs and is never inferred.
    """

    confirmation_hour_open = confirmation_ms - ONE_HOUR_MS
    required_rows = 21 * (DAY_MS // FIVE_MINUTES_MS)
    completed = [row for row in rows if row.close_ms <= confirmation_hour_open]
    if len(completed) < required_rows:
        return None, None, None, ("insufficient_lagged_504h_history",)
    selected = completed[-required_rows:]
    if selected[-1].close_ms != confirmation_hour_open or any(
        right.open_ms != left.close_ms for left, right in zip(selected, selected[1:])
    ):
        return None, None, None, ("noncontiguous_lagged_504h_history",)
    rows_per_day = DAY_MS // FIVE_MINUTES_MS
    blocks = [
        selected[offset : offset + rows_per_day]
        for offset in range(0, required_rows, rows_per_day)
    ]
    quote_totals = [sum(row.quote_volume for row in block) for block in blocks]
    quote_reference = sum(quote_totals[:-1]) / 20.0
    quote_surprise = (
        math.log(quote_totals[-1] / quote_reference)
        if quote_totals[-1] > 0.0 and quote_reference > 0.0
        else None
    )
    reasons: list[str] = []
    if quote_surprise is None:
        reasons.append("nonpositive_quote_volume_surprise_denominator")

    trade_values = [getattr(row, "trade_count", None) for row in selected]
    trade_surprise: float | None = None
    if any(value is None for value in trade_values):
        reasons.append("trade_count_unavailable")
    else:
        checked = [float(value) for value in trade_values]
        if any(not math.isfinite(value) or value < 0.0 for value in checked):
            reasons.append("invalid_trade_count")
        else:
            trade_blocks = [
                sum(checked[offset : offset + rows_per_day])
                for offset in range(0, required_rows, rows_per_day)
            ]
            trade_reference = sum(trade_blocks[:-1]) / 20.0
            if trade_blocks[-1] > 0.0 and trade_reference > 0.0:
                trade_surprise = math.log(trade_blocks[-1] / trade_reference)
            else:
                reasons.append("nonpositive_trade_count_surprise_denominator")
    return quote_totals[-1], quote_surprise, trade_surprise, tuple(reasons)


def _snapshot(
    path_rows: Sequence[SourceCandle],
    *,
    confirmation_ms: int,
    horizon_hours: int,
    fill_price: float | None,
    upper_boundary: float,
    segment_end_ms: int,
) -> BreakoutPathSnapshot:
    cutoff = confirmation_ms + horizon_hours * ONE_HOUR_MS
    selected = [row for row in path_rows if row.close_ms <= min(cutoff, segment_end_ms)]
    complete = segment_end_ms >= cutoff and bool(selected) and selected[-1].close_ms == cutoff
    if not selected or fill_price is None:
        return BreakoutPathSnapshot(
            horizon_hours=horizon_hours,
            complete=False,
            observed_until_ms=None,
            observation_count_5m=0,
            displacement_log=None,
            outside_fraction=None,
            maximum_favourable_excursion_log=None,
            maximum_adverse_excursion_log=None,
            time_to_maximum_favourable_excursion_hours=None,
            time_to_maximum_adverse_excursion_hours=None,
            path_efficiency=None,
        )
    closes = [fill_price, *(row.close for row in selected)]
    movement = sum(abs(math.log(right / left)) for left, right in zip(closes, closes[1:]))
    displacement = math.log(selected[-1].close / fill_price)
    efficiency = displacement / movement if movement > 0.0 else 0.0
    maximum_favourable_row = max(selected, key=lambda row: row.high)
    maximum_adverse_row = min(selected, key=lambda row: row.low)
    return BreakoutPathSnapshot(
        horizon_hours=horizon_hours,
        complete=complete,
        observed_until_ms=selected[-1].close_ms,
        observation_count_5m=len(selected),
        displacement_log=displacement,
        outside_fraction=sum(row.close > upper_boundary for row in selected) / len(selected),
        maximum_favourable_excursion_log=math.log(maximum_favourable_row.high / fill_price),
        maximum_adverse_excursion_log=math.log(maximum_adverse_row.low / fill_price),
        time_to_maximum_favourable_excursion_hours=(
            maximum_favourable_row.close_ms - confirmation_ms
        )
        / ONE_HOUR_MS,
        time_to_maximum_adverse_excursion_hours=(
            maximum_adverse_row.close_ms - confirmation_ms
        )
        / ONE_HOUR_MS,
        path_efficiency=efficiency,
    )


def _make_episode(
    *,
    experiment_id: str,
    source_digest: str,
    segment_rows: Sequence[SourceCandle],
    hour_bars: Sequence[AggregateCandle],
    four_hour_bars: Sequence[AggregateCandle],
    activation_ms: int,
    upper: float,
    lower: float,
    width: float,
    q20: float,
    compression_percentile: float,
    compression_duration_hours: int,
) -> BreakoutEpisode:
    segment = segment_rows[0].segment
    segment_end_ms = _segment_end(segment_rows)
    expiry_ms = activation_ms + SETUP_LIFETIME_MS
    setup_limit_ms = min(expiry_ms, segment_end_ms)
    termination_reason = "source_segment_end" if segment_end_ms <= expiry_ms else "seven_day_expiry"
    termination_ms = setup_limit_ms
    confirmation_ms: int | None = None
    for bar in hour_bars:
        if bar.close_ms <= activation_ms or bar.close_ms > setup_limit_ms:
            continue
        if bar.close > upper:
            confirmation_ms = bar.close_ms
            termination_ms = bar.close_ms
            termination_reason = "upside_confirmation"
            break
        if bar.close < lower:
            termination_ms = bar.close_ms
            termination_reason = "downside_invalidation"
            break
        if bar.close_ms >= expiry_ms:
            termination_ms = expiry_ms
            termination_reason = "seven_day_expiry"
            break

    setup_rows = [
        row
        for row in segment_rows
        if row.open_ms >= activation_ms and row.close_ms <= termination_ms
    ]
    first_touch = next((row.close_ms for row in setup_rows if row.high >= upper), None)
    first_cross = next((row.close_ms for row in setup_rows if row.close > upper), None)

    fill_row: SourceCandle | None = None
    if confirmation_ms is not None:
        fill_row = next(
            (row for row in segment_rows if row.open_ms == confirmation_ms),
            None,
        )
    fill_ms = fill_row.open_ms if fill_row is not None else None
    fill_price = fill_row.open if fill_row is not None else None
    confirmation_bar = next(
        (bar for bar in hour_bars if bar.close_ms == confirmation_ms), None
    )
    confirmation_close = confirmation_bar.close if confirmation_bar is not None else None
    sigma24, sigma7d = (
        _preceding_four_hour_sigmas(four_hour_bars, confirmation_ms)
        if confirmation_ms is not None
        else (None, None)
    )
    target_price = (
        fill_price * math.exp(sigma24)
        if fill_price is not None and sigma24 is not None
        else None
    )
    range_width_over_sigma7d = (
        width / sigma7d if sigma7d is not None and sigma7d > 0.0 else None
    )
    sigma24_over_sigma7d = (
        sigma24 / sigma7d
        if sigma24 is not None and sigma7d is not None and sigma7d > 0.0
        else None
    )
    penetration = (
        math.log(confirmation_close / upper) / sigma24
        if confirmation_close is not None and sigma24 is not None and sigma24 > 0.0
        else None
    )
    confirmation_rows = (
        [
            row
            for row in segment_rows
            if confirmation_ms is not None
            and confirmation_ms - ONE_HOUR_MS <= row.open_ms < confirmation_ms
        ]
        if confirmation_ms is not None
        else []
    )
    confirmation_fraction = (
        sum(row.close > upper for row in confirmation_rows) / 12.0
        if len(confirmation_rows) == 12
        else None
    )
    lagged_quote_total: float | None = None
    lagged_quote_surprise: float | None = None
    lagged_trade_surprise: float | None = None
    diagnostic_reasons: tuple[str, ...] = ()
    if confirmation_ms is not None:
        (
            lagged_quote_total,
            lagged_quote_surprise,
            lagged_trade_surprise,
            diagnostic_reasons,
        ) = _lagged_24h_surprises(segment_rows, confirmation_ms)
    hour_of_week = None
    if confirmation_ms is not None:
        utc_day = confirmation_ms // DAY_MS
        utc_hour = (confirmation_ms % DAY_MS) // ONE_HOUR_MS
        # Unix day zero is Thursday (Monday-based index 3).
        hour_of_week = ((utc_day + 3) % 7) * 24 + utc_hour
    hour_angle = (
        2.0 * math.pi * hour_of_week / (7 * 24)
        if hour_of_week is not None
        else None
    )
    hour_of_week_sine = math.sin(hour_angle) if hour_angle is not None else None
    hour_of_week_cosine = math.cos(hour_angle) if hour_angle is not None else None
    primary_reasons: list[str] = []
    if confirmation_ms is not None:
        if fill_row is None:
            primary_reasons.append("first_eligible_5m_unavailable")
        elif fill_row.open <= upper:
            primary_reasons.append("fill_not_above_frozen_upper")
        if confirmation_bar is None or len(confirmation_rows) != 12:
            primary_reasons.append("incomplete_confirmation_hour")
        if sigma24 is None or sigma24 <= 0.0:
            primary_reasons.append("pre_sigma24_unavailable_or_nonpositive")
        if sigma7d is None or sigma7d <= 0.0:
            primary_reasons.append("pre_sigma7d_unavailable_or_nonpositive")
        if penetration is None:
            primary_reasons.append("confirmation_penetration_unavailable")
    else:
        primary_reasons.append("not_confirmed")
    model_ready = not primary_reasons
    model_unavailable_reasons = tuple(primary_reasons)

    first_target_ms: int | None = None
    first_reentry_ms: int | None = None
    reentry_below_lower = False
    path_segment_censored = False
    path_observed_until: int | None = None
    snapshots: tuple[BreakoutPathSnapshot, ...] = ()
    competing_outcome: str | None = None
    competing_outcome_ms: int | None = None
    if confirmation_ms is not None:
        intended_end = confirmation_ms + PATH_LIFETIME_MS
        observed_end = min(intended_end, segment_end_ms)
        path_segment_censored = segment_end_ms < intended_end
        path_rows = [
            row
            for row in segment_rows
            if row.open_ms >= confirmation_ms and row.close_ms <= observed_end
        ]
        path_observed_until = path_rows[-1].close_ms if path_rows else None
        for bar in hour_bars:
            if bar.close_ms <= confirmation_ms or bar.close_ms > observed_end:
                continue
            reaches_target = (
                fill_price is not None
                and sigma24 is not None
                and math.log(bar.close / fill_price) >= sigma24
            )
            is_reentry = bar.close <= upper
            if is_reentry and first_reentry_ms is None:
                first_reentry_ms = bar.close_ms
                reentry_below_lower = bar.close < lower
            if reaches_target and first_target_ms is None:
                first_target_ms = bar.close_ms
            if first_target_ms is not None or first_reentry_ms is not None:
                break
        if first_reentry_ms is not None and (
            first_target_ms is None or first_reentry_ms <= first_target_ms
        ):
            # Equality is deliberately adverse-first.
            competing_outcome = "range_reentry"
            competing_outcome_ms = first_reentry_ms
        elif first_target_ms is not None:
            competing_outcome = "continuation"
            competing_outcome_ms = first_target_ms
        elif path_segment_censored:
            competing_outcome = None
            competing_outcome_ms = None
        else:
            competing_outcome = None
            competing_outcome_ms = None
        snapshots = tuple(
            _snapshot(
                path_rows,
                confirmation_ms=confirmation_ms,
                horizon_hours=horizon,
                fill_price=fill_price,
                upper_boundary=upper,
                segment_end_ms=segment_end_ms,
            )
            for horizon in PATH_HORIZONS_HOURS
        )

    episode_id = f"{experiment_id}:{segment}:{activation_ms}"
    return BreakoutEpisode(
        experiment_id=experiment_id,
        episode_id=episode_id,
        source_digest=source_digest,
        segment=segment,
        activation_ms=activation_ms,
        upper_boundary=upper,
        lower_boundary=lower,
        range_width_log=width,
        reference_q20=q20,
        compression_percentile=compression_percentile,
        compression_duration_bars=compression_duration_hours // 4,
        compression_duration_hours=compression_duration_hours,
        confirmation_delay_hours=(
            (confirmation_ms - activation_ms) // ONE_HOUR_MS
            if confirmation_ms is not None
            else None
        ),
        first_5m_touch_ms=first_touch,
        first_5m_close_cross_ms=first_cross,
        termination_ms=termination_ms,
        termination_reason=termination_reason,
        confirmation_ms=confirmation_ms,
        first_eligible_5m_ms=fill_ms,
        first_eligible_price=fill_price,
        confirmation_close=confirmation_close,
        pre_sigma24=sigma24,
        pre_sigma7d=sigma7d,
        range_width_over_sigma7d=range_width_over_sigma7d,
        sigma24_over_sigma7d=sigma24_over_sigma7d,
        confirmation_log_penetration_over_sigma24=penetration,
        confirmation_hour_fraction_5m_closes_above_upper=confirmation_fraction,
        lagged_24h_quote_volume=lagged_quote_total,
        lagged_24h_quote_volume_surprise=lagged_quote_surprise,
        lagged_24h_trade_count_surprise=lagged_trade_surprise,
        hour_of_week=hour_of_week,
        hour_of_week_sine=hour_of_week_sine,
        hour_of_week_cosine=hour_of_week_cosine,
        model_ready=model_ready,
        augmented_diagnostic_ready=model_ready and not diagnostic_reasons,
        model_unavailable_reasons=model_unavailable_reasons,
        augmented_diagnostic_unavailable_reasons=diagnostic_reasons,
        continuation_target_price=target_price,
        first_continuation_target_ms=first_target_ms,
        first_reentry_ms=first_reentry_ms,
        reentry_below_lower=reentry_below_lower,
        competing_outcome=competing_outcome,
        competing_outcome_ms=competing_outcome_ms,
        censor_reason=(
            "source_segment_end"
            if confirmation_ms is not None
            and competing_outcome is None
            and path_segment_censored
            else "seven_day_expiry"
            if confirmation_ms is not None and competing_outcome is None
            else None
        ),
        censor_ms=(
            observed_end
            if confirmation_ms is not None and competing_outcome is None
            else None
        ),
        path_segment_censored=path_segment_censored,
        path_observed_until_ms=path_observed_until,
        snapshots=snapshots,
    )


def build_breakout_event_catalogue(
    rows: Iterable[SourceCandle],
    *,
    source_digest: str,
    experiment_id: str,
    decision_end_exclusive_ms: int | None = None,
) -> BreakoutEventCatalogue:
    """Construct a deterministic, segment-safe catalogue without evaluating PnL."""

    source = list(rows)
    _validate_source(source, source_digest, experiment_id)
    one_hour, _ = aggregate_candles(source, ONE_HOUR_MS, "1h")
    four_hour, _ = aggregate_candles(source, FOUR_HOURS_MS, "4h")
    source_by_segment: dict[int, list[SourceCandle]] = {}
    hour_by_segment: dict[int, list[AggregateCandle]] = {}
    four_by_segment: dict[int, list[AggregateCandle]] = {}
    for row in source:
        source_by_segment.setdefault(row.segment, []).append(row)
    for bar in one_hour:
        hour_by_segment.setdefault(bar.segment, []).append(bar)
    for bar in four_hour:
        four_by_segment.setdefault(bar.segment, []).append(bar)

    episodes: list[BreakoutEpisode] = []
    for segment, bars in four_by_segment.items():
        widths: list[float | None] = [None] * len(bars)
        compression_run = 0
        suppressed_until = -1
        for index, bar in enumerate(bars):
            if decision_end_exclusive_ms is not None and bar.close_ms >= decision_end_exclusive_ms:
                compression_run = 0
                continue
            if index < RANGE_BARS_4H:
                continue
            # W_t is frozen from 42 completed 4h bars strictly before decision t.
            # The current decision bar is deliberately excluded even though it is complete.
            range_bars = bars[index - RANGE_BARS_4H : index]
            contiguous = all(
                right.open_ms == left.close_ms
                for left, right in zip(range_bars, range_bars[1:])
            )
            if not contiguous:
                compression_run = 0
                continue
            upper = max(item.high for item in range_bars)
            lower = min(item.low for item in range_bars)
            width = math.log(upper / lower)
            widths[index] = width
            historical = [
                value
                for value in widths[max(0, index - REFERENCE_WIDTHS) : index]
                if value is not None
            ]
            if len(historical) != REFERENCE_WIDTHS:
                compression_run = 0
                continue
            q20 = linear_quantile(historical, COMPRESSION_QUANTILE)
            compression_run = compression_run + 1 if width <= q20 else 0
            if bar.close_ms < suppressed_until:
                compression_run = 0
                continue
            if compression_run < COMPRESSION_RUN:
                continue
            episode = _make_episode(
                experiment_id=experiment_id,
                source_digest=source_digest,
                segment_rows=source_by_segment[segment],
                hour_bars=hour_by_segment.get(segment, ()),
                four_hour_bars=bars,
                activation_ms=bar.close_ms,
                upper=upper,
                lower=lower,
                width=width,
                q20=q20,
                compression_percentile=(
                    sum(value < width for value in historical)
                    + 0.5 * sum(value == width for value in historical)
                )
                / REFERENCE_WIDTHS,
                compression_duration_hours=compression_run * 4,
            )
            episodes.append(episode)
            if episode.confirmation_ms is not None:
                suppressed_until = min(
                    episode.confirmation_ms + PATH_LIFETIME_MS,
                    _segment_end(source_by_segment[segment]),
                )
            else:
                suppressed_until = episode.termination_ms
            compression_run = 0

    return BreakoutEventCatalogue(
        experiment_id=experiment_id,
        source_digest=source_digest,
        source_rows=len(source),
        aggregate_rows_1h=len(one_hour),
        aggregate_rows_4h=len(four_hour),
        episodes=tuple(episodes),
    )
