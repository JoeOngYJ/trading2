"""Offline causal BTC Page-CUSUM trend-onset event infrastructure.

Trigger construction and label materialization are deliberately separate.  The trigger phase
never computes a post-trigger outcome.  Nothing in this module creates a strategy, position,
order, executable signal, cost, return, or PnL.
"""

from __future__ import annotations

import csv
import gzip
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from trading_platform.research_ledger import (
    FIVE_MINUTES_MS,
    SourceCandle,
    aggregate_candles,
    iso_ms,
    reject_symlink_tree,
    sha256_file,
)
from trading_platform.research_routing import canonical_digest


ONE_HOUR_MS = 12 * FIVE_MINUTES_MS
SIGMA_RETURNS = 168
CUSUM_DRIFT = 0.25
CUSUM_THRESHOLD = 4.5
Z_CLIP = 2.0
MINIMUM_POSITIVE_CONTRIBUTORS = 3
MINIMUM_ACTIVE_HOURS = 3
SUPPRESSION_HOURS = 72
LABEL_HOURS = 72
DAILY_SCALE_HOURS = 24


class CusumTrendEventError(ValueError):
    """Raised when TNE1 data or chronology is invalid or ambiguous."""


def page_update(state: float, z_value: float) -> tuple[float, float, float]:
    """Return ``(next_state, clipped_z, contribution)`` for one frozen Page step."""

    if not math.isfinite(state) or state < 0.0 or not math.isfinite(z_value):
        raise CusumTrendEventError("Page state and z value must be finite")
    clipped = min(Z_CLIP, max(-Z_CLIP, z_value))
    contribution = clipped - CUSUM_DRIFT
    return max(0.0, state + contribution), clipped, contribution


@dataclass(frozen=True, slots=True)
class CusumSourceCandle:
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
        return self.open_ms + FIVE_MINUTES_MS


def _validate_digest(value: str, label: str) -> None:
    if not isinstance(value, str) or len(value) != 64 or value != value.lower():
        raise CusumTrendEventError(f"{label} must be a lowercase SHA-256 digest")
    try:
        int(value, 16)
    except ValueError as exc:
        raise CusumTrendEventError(f"{label} must be hexadecimal") from exc


def _validate_source(rows: Sequence[SourceCandle], source_digest: str) -> None:
    _validate_digest(source_digest, "source_digest")
    if not rows:
        raise CusumTrendEventError("source candles are required")
    previous: SourceCandle | None = None
    closed_segments: set[int] = set()
    for index, row in enumerate(rows):
        raw_close = getattr(row, "raw_close_time_ms", row.open_ms + FIVE_MINUTES_MS - 1)
        trade_count = getattr(row, "trade_count", None)
        try:
            invalid_trade_count = trade_count is not None and (
                not math.isfinite(float(trade_count)) or float(trade_count) < 0.0
            )
        except (TypeError, ValueError):
            invalid_trade_count = True
        if (
            row.segment < 0
            or row.source_row != index
            or row.open_ms < 0
            or row.open_ms % FIVE_MINUTES_MS
            or row.close_ms != row.open_ms + FIVE_MINUTES_MS
            or raw_close != row.open_ms + FIVE_MINUTES_MS - 1
            or not all(
                math.isfinite(value) and value > 0.0
                for value in (row.open, row.high, row.low, row.close)
            )
            or row.high < max(row.open, row.close)
            or row.low > min(row.open, row.close)
            or not math.isfinite(row.base_volume)
            or not math.isfinite(row.quote_volume)
            or row.base_volume < 0.0
            or row.quote_volume < 0.0
            or invalid_trade_count
        ):
            raise CusumTrendEventError(f"invalid source candle at row {index}")
        if previous is not None:
            if row.open_ms <= previous.open_ms:
                raise CusumTrendEventError("source timestamps are reversed or duplicated")
            if row.segment == previous.segment:
                if row.open_ms != previous.open_ms + FIVE_MINUTES_MS:
                    raise CusumTrendEventError("gap inside a source segment")
            else:
                closed_segments.add(previous.segment)
                if row.segment in closed_segments:
                    raise CusumTrendEventError("a closed source segment reappears")
        previous = row


def load_cusum_source_candles(
    path: Path, expected_sha256: str
) -> tuple[list[CusumSourceCandle], str]:
    """Load a local checksummed development gzip CSV without external access."""

    reject_symlink_tree(path)
    resolved = path.resolve(strict=True)
    lowered = resolved.name.lower()
    if "holdout" in lowered or "2026-01-07" in lowered:
        raise CusumTrendEventError("sealed holdout input is prohibited")
    _validate_digest(expected_sha256, "expected_sha256")
    digest = sha256_file(resolved)
    if digest != expected_sha256:
        raise CusumTrendEventError("source checksum mismatch")
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
    rows: list[CusumSourceCandle] = []
    with gzip.open(resolved, "rt", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = sorted(required - set(reader.fieldnames or ()))
        if missing:
            raise CusumTrendEventError(f"source lacks columns: {missing}")
        for source_row, raw in enumerate(reader):
            try:
                rows.append(
                    CusumSourceCandle(
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
                )
            except (TypeError, ValueError) as exc:
                raise CusumTrendEventError(
                    f"invalid source value at line {source_row + 2}"
                ) from exc
    _validate_source(rows, digest)
    return rows, digest


@dataclass(frozen=True, slots=True)
class CusumTrigger:
    experiment_id: str
    trigger_id: str
    source_digest: str
    segment: int
    trigger_ms: int
    trigger_close: float
    sigma_hourly: float
    current_return: float
    z_raw: float
    z_clipped: float
    contribution: float
    cusum_before: float
    cusum_after: float
    threshold_excess: float
    active_hours: int
    positive_contributors: int
    run_started_ms: int
    momentum_24h_log: float
    momentum_72h_log: float
    momentum_24h_z: float
    momentum_72h_z: float
    sigma24_over_sigma7d: float
    hour_of_week_sine: float
    hour_of_week_cosine: float
    max_one_hour_positive_contribution_fraction: float
    first_eligible_5m_ms: int | None
    first_eligible_price: float | None
    model_ready: bool
    unavailable_reason: str | None
    suppression_until_ms: int

    def _payload(self) -> dict[str, Any]:
        return {
            "actionable_arm_id": "no_trade",
            "active_hours": self.active_hours,
            "available_at": iso_ms(self.trigger_ms),
            "contribution": self.contribution,
            "current_return": self.current_return,
            "cusum_after": self.cusum_after,
            "cusum_before": self.cusum_before,
            "experiment_id": self.experiment_id,
            "first_eligible_5m_at": (
                iso_ms(self.first_eligible_5m_ms)
                if self.first_eligible_5m_ms is not None
                else None
            ),
            "first_eligible_price": self.first_eligible_price,
            "model_ready": self.model_ready,
            "momentum_24h_log": self.momentum_24h_log,
            "momentum_24h_z": self.momentum_24h_z,
            "momentum_72h_log": self.momentum_72h_log,
            "momentum_72h_z": self.momentum_72h_z,
            "sigma24_over_sigma7d": self.sigma24_over_sigma7d,
            "hour_of_week_sine": self.hour_of_week_sine,
            "hour_of_week_cosine": self.hour_of_week_cosine,
            "max_one_hour_positive_contribution_fraction": (
                self.max_one_hour_positive_contribution_fraction
            ),
            "observed_at": iso_ms(self.trigger_ms),
            "positive_contributors": self.positive_contributors,
            "run_started_at": iso_ms(self.run_started_ms),
            "segment": str(self.segment),
            "sigma_hourly": self.sigma_hourly,
            "source_digest": self.source_digest,
            "suppression_until": iso_ms(self.suppression_until_ms),
            "threshold_excess": self.threshold_excess,
            "trigger_close": self.trigger_close,
            "trigger_id": self.trigger_id,
            "unavailable_reason": self.unavailable_reason,
            "z_clipped": self.z_clipped,
            "z_raw": self.z_raw,
        }

    @property
    def record_digest(self) -> str:
        return canonical_digest(self._payload())

    def as_dict(self) -> dict[str, Any]:
        return {**self._payload(), "record_digest": self.record_digest}


@dataclass(frozen=True, slots=True)
class CusumTriggerCatalogue:
    experiment_id: str
    source_digest: str
    source_rows: int
    aggregate_rows_1h: int
    triggers: tuple[CusumTrigger, ...]

    def _payload(self) -> dict[str, Any]:
        return {
            "actionable_arm_id": "no_trade",
            "aggregate_rows_1h": self.aggregate_rows_1h,
            "experiment_id": self.experiment_id,
            "phase": "trigger",
            "source_digest": self.source_digest,
            "source_rows": self.source_rows,
            "triggers": [trigger.as_dict() for trigger in self.triggers],
        }

    @property
    def catalogue_digest(self) -> str:
        return canonical_digest(self._payload())

    def as_dict(self) -> dict[str, Any]:
        return {**self._payload(), "catalogue_digest": self.catalogue_digest}


def build_cusum_trigger_catalogue(
    rows: Iterable[SourceCandle],
    *,
    source_digest: str,
    experiment_id: str,
    decision_end_exclusive_ms: int | None = None,
) -> CusumTriggerCatalogue:
    """Build causal triggers only; no post-trigger label is read or emitted."""

    if not isinstance(experiment_id, str) or not experiment_id.strip():
        raise CusumTrendEventError("experiment_id is required")
    source = list(rows)
    _validate_source(source, source_digest)
    hours, _ = aggregate_candles(source, ONE_HOUR_MS, "1h")
    source_by_segment: dict[int, list[SourceCandle]] = {}
    hours_by_segment: dict[int, list[Any]] = {}
    for row in source:
        source_by_segment.setdefault(row.segment, []).append(row)
    for bar in hours:
        hours_by_segment.setdefault(bar.segment, []).append(bar)

    triggers: list[CusumTrigger] = []
    for segment, segment_hours in hours_by_segment.items():
        returns: list[float | None] = [None]
        returns.extend(
            math.log(right.close / left.close)
            for left, right in zip(segment_hours, segment_hours[1:])
        )
        state = 0.0
        active_hours = 0
        positive_contributors = 0
        max_positive_contribution = 0.0
        run_started_ms: int | None = None
        suppressed_until = -1
        segment_rows = source_by_segment[segment]
        by_open_ms = {row.open_ms: row for row in segment_rows}
        for index, bar in enumerate(segment_hours):
            if decision_end_exclusive_ms is not None and bar.close_ms >= decision_end_exclusive_ms:
                break
            # The 72-hour label endpoint remains inside suppression.  A fresh Page run may
            # consume its first return only at the completed hour ending trigger+73h.
            if bar.close_ms <= suppressed_until:
                continue
            if suppressed_until >= 0:
                state = 0.0
                active_hours = 0
                positive_contributors = 0
                max_positive_contribution = 0.0
                run_started_ms = None
                suppressed_until = -1
            current_return = returns[index]
            if current_return is None or index < SIGMA_RETURNS + 1:
                continue
            preceding = returns[index - SIGMA_RETURNS : index]
            if len(preceding) != SIGMA_RETURNS or any(value is None for value in preceding):
                state = 0.0
                active_hours = 0
                positive_contributors = 0
                max_positive_contribution = 0.0
                run_started_ms = None
                continue
            checked = [float(value) for value in preceding]
            sigma = math.sqrt(sum(value * value for value in checked) / SIGMA_RETURNS)
            if not math.isfinite(sigma) or sigma <= 0.0:
                state = 0.0
                active_hours = 0
                positive_contributors = 0
                max_positive_contribution = 0.0
                run_started_ms = None
                continue
            z_raw = current_return / sigma
            before = state
            state, z_clipped, contribution = page_update(state, z_raw)
            if state == 0.0:
                active_hours = 0
                positive_contributors = 0
                max_positive_contribution = 0.0
                run_started_ms = None
                continue
            if before == 0.0:
                run_started_ms = bar.close_ms
            active_hours += 1
            if contribution > 0.0:
                positive_contributors += 1
                max_positive_contribution = max(max_positive_contribution, contribution)
            crossed = before < CUSUM_THRESHOLD <= state
            if not (
                crossed
                and positive_contributors >= MINIMUM_POSITIVE_CONTRIBUTORS
                and active_hours >= MINIMUM_ACTIVE_HOURS
            ):
                continue
            if index < 72:
                raise CusumTrendEventError("trigger lacks causal momentum endpoints")
            momentum_24h = math.log(bar.close / segment_hours[index - 24].close)
            momentum_72h = math.log(bar.close / segment_hours[index - 72].close)
            sigma24 = math.sqrt(sum(value * value for value in checked[-24:]) / 24)
            sigma7d = sigma
            if sigma24 <= 0.0 or sigma7d <= 0.0:
                raise CusumTrendEventError("trigger volatility-ratio denominator is invalid")
            hour_of_week = (
                (((bar.close_ms // (24 * ONE_HOUR_MS)) + 3) % 7) * 24
                + (bar.close_ms % (24 * ONE_HOUR_MS)) // ONE_HOUR_MS
            )
            hour_angle = 2.0 * math.pi * hour_of_week / (7 * 24)
            fill = by_open_ms.get(bar.close_ms)
            ready = fill is not None
            trigger_id = f"{experiment_id}:{segment}:{bar.close_ms}"
            trigger = CusumTrigger(
                experiment_id=experiment_id,
                trigger_id=trigger_id,
                source_digest=source_digest,
                segment=segment,
                trigger_ms=bar.close_ms,
                trigger_close=bar.close,
                sigma_hourly=sigma,
                current_return=current_return,
                z_raw=z_raw,
                z_clipped=z_clipped,
                contribution=contribution,
                cusum_before=before,
                cusum_after=state,
                threshold_excess=state - CUSUM_THRESHOLD,
                active_hours=active_hours,
                positive_contributors=positive_contributors,
                run_started_ms=run_started_ms if run_started_ms is not None else bar.close_ms,
                momentum_24h_log=momentum_24h,
                momentum_72h_log=momentum_72h,
                momentum_24h_z=momentum_24h / (sigma * math.sqrt(24)),
                momentum_72h_z=momentum_72h / (sigma * math.sqrt(72)),
                sigma24_over_sigma7d=sigma24 / sigma7d,
                hour_of_week_sine=math.sin(hour_angle),
                hour_of_week_cosine=math.cos(hour_angle),
                max_one_hour_positive_contribution_fraction=(
                    max_positive_contribution / state
                ),
                first_eligible_5m_ms=fill.open_ms if fill is not None else None,
                first_eligible_price=fill.open if fill is not None else None,
                model_ready=ready,
                unavailable_reason=None if ready else "first_eligible_5m_unavailable",
                suppression_until_ms=bar.close_ms + SUPPRESSION_HOURS * ONE_HOUR_MS,
            )
            triggers.append(trigger)
            suppressed_until = trigger.suppression_until_ms
            state = 0.0
            active_hours = 0
            positive_contributors = 0
            max_positive_contribution = 0.0
            run_started_ms = None
    return CusumTriggerCatalogue(
        experiment_id=experiment_id,
        source_digest=source_digest,
        source_rows=len(source),
        aggregate_rows_1h=len(hours),
        triggers=tuple(triggers),
    )


@dataclass(frozen=True, slots=True)
class CusumTrendLabel:
    experiment_id: str
    trigger_id: str
    trigger_digest: str
    source_digest: str
    segment: int
    fill_ms: int
    endpoint_ms: int | None
    observed_hours: int
    censored: bool
    censor_reason: str | None
    target_normalized_72h: float | None
    diagnostic_first_passage: str | None
    diagnostic_first_passage_ms: int | None

    def _payload(self) -> dict[str, Any]:
        return {
            "actionable_arm_id": "no_trade",
            "available_at": iso_ms(self.endpoint_ms) if self.endpoint_ms is not None else None,
            "censor_reason": self.censor_reason,
            "censored": self.censored,
            "diagnostic_first_passage": self.diagnostic_first_passage,
            "diagnostic_first_passage_at": (
                iso_ms(self.diagnostic_first_passage_ms)
                if self.diagnostic_first_passage_ms is not None
                else None
            ),
            "endpoint_at": iso_ms(self.endpoint_ms) if self.endpoint_ms is not None else None,
            "experiment_id": self.experiment_id,
            "fill_at": iso_ms(self.fill_ms),
            "observed_hours": self.observed_hours,
            "segment": str(self.segment),
            "source_digest": self.source_digest,
            "target_normalized_72h": self.target_normalized_72h,
            "trigger_digest": self.trigger_digest,
            "trigger_id": self.trigger_id,
        }

    @property
    def record_digest(self) -> str:
        return canonical_digest(self._payload())

    def as_dict(self) -> dict[str, Any]:
        return {**self._payload(), "record_digest": self.record_digest}


def materialize_cusum_labels(
    rows: Iterable[SourceCandle],
    triggers: Iterable[CusumTrigger],
    *,
    source_digest: str,
    experiment_id: str,
) -> tuple[CusumTrendLabel, ...]:
    """Materialize fixed 72h labels after an external count gate has passed."""

    source = list(rows)
    _validate_source(source, source_digest)
    ordered = tuple(triggers)
    if any(trigger.experiment_id != experiment_id for trigger in ordered):
        raise CusumTrendEventError("trigger experiment ID mismatch")
    hours, _ = aggregate_candles(source, ONE_HOUR_MS, "1h")
    hours_by_identity = {(bar.segment, bar.close_ms): bar for bar in hours}
    segment_end: dict[int, int] = {}
    for row in source:
        segment_end[row.segment] = row.close_ms
    labels: list[CusumTrendLabel] = []
    previous_key: tuple[int, str] | None = None
    final_segment = source[-1].segment
    for trigger in ordered:
        key = (trigger.trigger_ms, trigger.trigger_id)
        if previous_key is not None and key <= previous_key:
            raise CusumTrendEventError("triggers are duplicated or not ordered")
        previous_key = key
        if trigger.source_digest != source_digest:
            raise CusumTrendEventError("trigger source digest mismatch")
        if not trigger.model_ready or trigger.first_eligible_5m_ms is None or trigger.first_eligible_price is None:
            raise CusumTrendEventError("label phase received a non-ready trigger")
        intended = trigger.first_eligible_5m_ms + LABEL_HOURS * ONE_HOUR_MS
        end = segment_end.get(trigger.segment)
        endpoint = hours_by_identity.get((trigger.segment, intended))
        daily_scale = trigger.sigma_hourly * math.sqrt(DAILY_SCALE_HOURS)
        if not math.isfinite(daily_scale) or daily_scale <= 0.0:
            raise CusumTrendEventError("trigger daily volatility scale is invalid")
        observed_until = min(intended, end) if end is not None else trigger.first_eligible_5m_ms
        observed_hours = max(
            0, min(LABEL_HOURS, (observed_until - trigger.first_eligible_5m_ms) // ONE_HOUR_MS)
        )
        first_passage: str | None = None
        first_passage_ms: int | None = None
        for hour in hours:
            if (
                hour.segment != trigger.segment
                or hour.close_ms <= trigger.first_eligible_5m_ms
                or hour.close_ms > observed_until
            ):
                continue
            normalized = math.log(hour.close / trigger.first_eligible_price) / daily_scale
            if normalized <= -1.0:
                first_passage = "negative_one_daily_vol"
                first_passage_ms = hour.close_ms
                break
            if normalized >= 1.0:
                first_passage = "positive_one_daily_vol"
                first_passage_ms = hour.close_ms
                break
        if endpoint is None:
            labels.append(
                CusumTrendLabel(
                    experiment_id=experiment_id,
                    trigger_id=trigger.trigger_id,
                    trigger_digest=trigger.record_digest,
                    source_digest=source_digest,
                    segment=trigger.segment,
                    fill_ms=trigger.first_eligible_5m_ms,
                    endpoint_ms=None,
                    observed_hours=int(observed_hours),
                    censored=True,
                    censor_reason=(
                        "source_end" if trigger.segment == final_segment else "source_segment_end"
                    ),
                    target_normalized_72h=None,
                    diagnostic_first_passage=first_passage,
                    diagnostic_first_passage_ms=first_passage_ms,
                )
            )
            continue
        target = math.log(endpoint.close / trigger.first_eligible_price) / daily_scale
        labels.append(
            CusumTrendLabel(
                experiment_id=experiment_id,
                trigger_id=trigger.trigger_id,
                trigger_digest=trigger.record_digest,
                source_digest=source_digest,
                segment=trigger.segment,
                fill_ms=trigger.first_eligible_5m_ms,
                endpoint_ms=endpoint.close_ms,
                observed_hours=LABEL_HOURS,
                censored=False,
                censor_reason=None,
                target_normalized_72h=target,
                diagnostic_first_passage=first_passage,
                diagnostic_first_passage_ms=first_passage_ms,
            )
        )
    return tuple(labels)


def trigger_from_record(record: Mapping[str, Any]) -> CusumTrigger:
    """Validate and reconstruct one checksummed trigger artifact record."""

    expected = record.get("record_digest")
    payload = {key: value for key, value in record.items() if key != "record_digest"}
    if expected != canonical_digest(payload):
        raise CusumTrendEventError("trigger record digest mismatch")
    if record.get("actionable_arm_id") != "no_trade":
        raise CusumTrendEventError("trigger record is not research-only no_trade")
    if not isinstance(record.get("model_ready"), bool):
        raise CusumTrendEventError("trigger model_ready must be boolean")

    def ms(value: Any) -> int | None:
        if value is None:
            return None
        if not isinstance(value, str) or not value.endswith("Z"):
            raise CusumTrendEventError("trigger timestamp must be canonical UTC Z")
        from datetime import datetime, timezone

        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
        if parsed.tzinfo != timezone.utc:
            raise CusumTrendEventError("trigger timestamp must use UTC")
        return int(parsed.timestamp() * 1000)

    trigger_ms = ms(record.get("observed_at"))
    run_started = ms(record.get("run_started_at"))
    suppression = ms(record.get("suppression_until"))
    fill = ms(record.get("first_eligible_5m_at"))
    if trigger_ms is None or run_started is None or suppression is None:
        raise CusumTrendEventError("trigger timestamps are required")
    return CusumTrigger(
        experiment_id=str(record.get("experiment_id")),
        trigger_id=str(record.get("trigger_id")),
        source_digest=str(record.get("source_digest")),
        segment=int(record.get("segment")),
        trigger_ms=trigger_ms,
        trigger_close=float(record.get("trigger_close")),
        sigma_hourly=float(record.get("sigma_hourly")),
        current_return=float(record.get("current_return")),
        z_raw=float(record.get("z_raw")),
        z_clipped=float(record.get("z_clipped")),
        contribution=float(record.get("contribution")),
        cusum_before=float(record.get("cusum_before")),
        cusum_after=float(record.get("cusum_after")),
        threshold_excess=float(record.get("threshold_excess")),
        active_hours=int(record.get("active_hours")),
        positive_contributors=int(record.get("positive_contributors")),
        run_started_ms=run_started,
        momentum_24h_log=float(record.get("momentum_24h_log")),
        momentum_72h_log=float(record.get("momentum_72h_log")),
        momentum_24h_z=float(record.get("momentum_24h_z")),
        momentum_72h_z=float(record.get("momentum_72h_z")),
        sigma24_over_sigma7d=float(record.get("sigma24_over_sigma7d")),
        hour_of_week_sine=float(record.get("hour_of_week_sine")),
        hour_of_week_cosine=float(record.get("hour_of_week_cosine")),
        max_one_hour_positive_contribution_fraction=float(
            record.get("max_one_hour_positive_contribution_fraction")
        ),
        first_eligible_5m_ms=fill,
        first_eligible_price=(
            float(record["first_eligible_price"])
            if record.get("first_eligible_price") is not None
            else None
        ),
        model_ready=record["model_ready"],
        unavailable_reason=(
            str(record["unavailable_reason"])
            if record.get("unavailable_reason") is not None
            else None
        ),
        suppression_until_ms=suppression,
    )
