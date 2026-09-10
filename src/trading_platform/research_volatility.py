"""Causal EWMA risk estimates and locked-cohort sizing for offline research only."""

from __future__ import annotations

import bisect
import math
import random
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from trading_platform.research_ledger import DAY_MS, FIVE_MINUTES_MS, iter_jsonl_gzip, sha256_file
from trading_platform.research_routing import RegimeFeatureObservation, canonical_digest


UTC = timezone.utc


class ResearchVolatilityError(ValueError):
    """Raised when an S2 input or calculation is non-causal, incomplete, or unsafe."""


def parse_utc_ms(value: str) -> int:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ResearchVolatilityError(f"timestamp must use canonical UTC Z form: {value!r}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ResearchVolatilityError(f"invalid timestamp: {value}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ResearchVolatilityError(f"timestamp is not UTC: {value}")
    return int(parsed.timestamp() * 1000)


def iso_ms(value: int) -> str:
    return datetime.fromtimestamp(value / 1000, tz=UTC).isoformat().replace("+00:00", "Z")


def _finite(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ResearchVolatilityError(f"invalid {label}") from exc
    if not math.isfinite(number):
        raise ResearchVolatilityError(f"non-finite {label}")
    return number


def _require_input(path: Path, expected_sha256: str, label: str) -> Path:
    absolute = path.absolute()
    for component in (absolute, *absolute.parents):
        if component.is_symlink():
            raise ResearchVolatilityError(f"symlinked {label} is prohibited: {component}")
    resolved = path.resolve(strict=True)
    lowered = resolved.name.lower()
    if "holdout" in lowered or "2026-01-07" in lowered:
        raise ResearchVolatilityError(f"sealed input is prohibited: {resolved}")
    observed = sha256_file(resolved)
    if observed != expected_sha256:
        raise ResearchVolatilityError(
            f"{label} checksum mismatch: expected {expected_sha256}, got {observed}"
        )
    return resolved


@dataclass(frozen=True, slots=True)
class DailyFeature:
    segment: str
    observed_ms: int
    available_ms: int
    close_to_close_log_return: float | None
    feature_digest: str
    source_digest: str


@dataclass(frozen=True, slots=True)
class CandlePoint:
    segment: str
    open_ms: int
    open: float
    high: float
    low: float
    close: float
    source_row: int


@dataclass(frozen=True, slots=True)
class Opportunity:
    opportunity_id: str
    signal_ms: int
    entry_ms: int
    exit_ms: int
    entry_row: int
    exit_row: int
    segment: str
    entry_reference: float
    exit_reference: float
    exit_reason: str

    @property
    def holding_seconds(self) -> float:
        return (self.exit_ms - self.entry_ms) / 1000


@dataclass(frozen=True, slots=True)
class EWMAConfig:
    variant_id: str
    decay_lambda: float
    target_annualized_volatility: float
    annualization_days: int = 365
    initialization_returns: int = 30

    def __post_init__(self) -> None:
        if not self.variant_id:
            raise ResearchVolatilityError("variant_id is required")
        if not 0 < self.decay_lambda < 1:
            raise ResearchVolatilityError("EWMA decay must be within (0, 1)")
        if self.target_annualized_volatility <= 0:
            raise ResearchVolatilityError("target volatility must be positive")
        if self.annualization_days <= 0 or self.initialization_returns <= 1:
            raise ResearchVolatilityError("invalid annualization or initialization")

    @property
    def digest(self) -> str:
        return canonical_digest(self.as_dict())

    def as_dict(self) -> dict[str, Any]:
        return {
            "annualization_days": self.annualization_days,
            "decay_lambda": self.decay_lambda,
            "initialization_returns": self.initialization_returns,
            "target_annualized_volatility": self.target_annualized_volatility,
            "variant_id": self.variant_id,
        }


@dataclass(frozen=True, slots=True)
class EWMARiskObservation:
    variant_id: str
    segment: str
    observed_ms: int
    available_ms: int
    forecast_daily_variance: float | None
    expanding_daily_variance: float | None
    annualized_volatility: float | None
    exposure_multiplier: float
    return_count: int
    unknown_reason: str | None
    source_feature_digest: str
    source_digest: str
    config_digest: str

    @property
    def usable(self) -> bool:
        return self.unknown_reason is None

    def _payload(self) -> dict[str, Any]:
        return {
            "annualized_volatility": self.annualized_volatility,
            "available_at": iso_ms(self.available_ms),
            "config_digest": self.config_digest,
            "expanding_daily_variance": self.expanding_daily_variance,
            "exposure_multiplier": self.exposure_multiplier,
            "forecast_daily_variance": self.forecast_daily_variance,
            "instrument": "BTC/USDT",
            "interval": "1d",
            "observed_at": iso_ms(self.observed_ms),
            "return_count": self.return_count,
            "segment": self.segment,
            "source_digest": self.source_digest,
            "source_feature_digest": self.source_feature_digest,
            "unknown_reason": self.unknown_reason,
            "variant_id": self.variant_id,
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self._payload())

    def as_dict(self) -> dict[str, Any]:
        return {**self._payload(), "digest": self.digest}


def load_daily_features(
    path: Path, expected_sha256: str, expected_rows: int
) -> list[DailyFeature]:
    resolved = _require_input(path, expected_sha256, "S1 daily feature ledger")
    result: list[DailyFeature] = []
    previous: DailyFeature | None = None
    seen_segments: set[str] = set()
    for raw in iter_jsonl_gzip(resolved):
        observed = parse_utc_ms(raw.get("observed_at"))
        available = parse_utc_ms(raw.get("available_at"))
        values = raw.get("feature_values")
        if not isinstance(values, dict):
            raise ResearchVolatilityError("daily feature_values must be an object")
        observation = RegimeFeatureObservation(
            instrument=raw.get("instrument"),
            interval=raw.get("interval"),
            segment=raw.get("segment"),
            observed_at=datetime.fromtimestamp(observed / 1000, tz=UTC),
            available_at=datetime.fromtimestamp(available / 1000, tz=UTC),
            feature_values=values,
            source_digest=raw.get("source_digest"),
        )
        if observation.interval != "1d" or observation.instrument != "BTC/USDT":
            raise ResearchVolatilityError("unexpected instrument or interval in daily ledger")
        if raw.get("feature_digest") != observation.feature_digest:
            raise ResearchVolatilityError("daily feature digest mismatch")
        value = values.get("close_to_close_log_return")
        item = DailyFeature(
            segment=observation.segment,
            observed_ms=observed,
            available_ms=available,
            close_to_close_log_return=None if value is None else _finite(value, "daily return"),
            feature_digest=observation.feature_digest,
            source_digest=observation.source_digest,
        )
        if available != observed or observed % DAY_MS:
            raise ResearchVolatilityError("daily observation is not available at its UTC close")
        if previous is not None:
            if observed <= previous.observed_ms:
                raise ResearchVolatilityError("daily observations are not strictly ordered")
            if item.segment == previous.segment:
                if observed != previous.observed_ms + DAY_MS:
                    raise ResearchVolatilityError("gap inside daily source segment")
                if item.close_to_close_log_return is None:
                    raise ResearchVolatilityError("return missing inside daily source segment")
            else:
                seen_segments.add(previous.segment)
                if item.segment in seen_segments:
                    raise ResearchVolatilityError("daily source segment reappears")
                if item.close_to_close_log_return is not None:
                    raise ResearchVolatilityError("first daily observation in segment has a return")
        elif item.close_to_close_log_return is not None:
            raise ResearchVolatilityError("first daily observation has a return")
        result.append(item)
        previous = item
    if len(result) != expected_rows:
        raise ResearchVolatilityError(
            f"daily feature row count mismatch: {len(result)} != {expected_rows}"
        )
    return result


def load_direct_close_features(
    path: Path,
    expected_sha256: str,
    expected_rows: int,
    *,
    source_segment: str,
) -> list[DailyFeature]:
    """Load a continuous official daily-close ledger with next-midnight availability."""
    if not source_segment:
        raise ResearchVolatilityError("direct daily source segment is required")
    resolved = _require_input(path, expected_sha256, "direct daily close ledger")
    result: list[DailyFeature] = []
    previous_open: int | None = None
    previous_close: float | None = None
    previous_archive_digest: str | None = None
    for raw in iter_jsonl_gzip(resolved):
        open_ms = parse_utc_ms(raw.get("open_at"))
        available_ms = parse_utc_ms(raw.get("available_at"))
        if open_ms % DAY_MS or available_ms != open_ms + DAY_MS:
            raise ResearchVolatilityError("direct daily row has invalid UTC availability")
        if previous_open is not None and open_ms != previous_open + DAY_MS:
            raise ResearchVolatilityError("gap inside direct daily close source")
        close = _finite(raw.get("close"), "direct daily close")
        if close <= 0:
            raise ResearchVolatilityError("direct daily close must be positive")
        archive_digest = str(raw.get("source_archive_sha256", ""))
        if len(archive_digest) != 64:
            raise ResearchVolatilityError("invalid direct daily archive digest")
        try:
            int(archive_digest, 16)
        except ValueError as exc:
            raise ResearchVolatilityError("invalid direct daily archive digest") from exc
        source_digest = canonical_digest(
            {
                "current_archive_sha256": archive_digest,
                "dataset_sha256": expected_sha256,
                "previous_archive_sha256": previous_archive_digest,
            }
        )
        value = None if previous_close is None else math.log(close / previous_close)
        values = {"close": close}
        if value is not None:
            values["close_to_close_log_return"] = value
        observation = RegimeFeatureObservation(
            instrument="BTC/USDT",
            interval="1d",
            segment=source_segment,
            observed_at=datetime.fromtimestamp(available_ms / 1000, tz=UTC),
            available_at=datetime.fromtimestamp(available_ms / 1000, tz=UTC),
            feature_values=values,
            source_digest=source_digest,
        )
        result.append(
            DailyFeature(
                segment=source_segment,
                observed_ms=available_ms,
                available_ms=available_ms,
                close_to_close_log_return=value,
                feature_digest=observation.feature_digest,
                source_digest=source_digest,
            )
        )
        previous_open = open_ms
        previous_close = close
        previous_archive_digest = archive_digest
    if len(result) != expected_rows:
        raise ResearchVolatilityError(
            f"direct daily row count mismatch: {len(result)} != {expected_rows}"
        )
    return result


def load_candles(path: Path, expected_sha256: str, expected_rows: int) -> list[CandlePoint]:
    resolved = _require_input(path, expected_sha256, "S1 five-minute candle ledger")
    result: list[CandlePoint] = []
    previous: CandlePoint | None = None
    for expected_row, raw in enumerate(iter_jsonl_gzip(resolved)):
        row = int(raw.get("source_row"))
        item = CandlePoint(
            segment=str(raw.get("segment")),
            open_ms=parse_utc_ms(raw.get("open_at")),
            open=_finite(raw.get("open"), "candle open"),
            high=_finite(raw.get("high"), "candle high"),
            low=_finite(raw.get("low"), "candle low"),
            close=_finite(raw.get("close"), "candle close"),
            source_row=row,
        )
        if row != expected_row or item.open_ms % FIVE_MINUTES_MS:
            raise ResearchVolatilityError("five-minute source-row identity mismatch")
        if item.low <= 0 or item.low > min(item.open, item.close) or item.high < max(
            item.open, item.close
        ):
            raise ResearchVolatilityError("invalid five-minute OHLC")
        if previous is not None:
            if item.open_ms <= previous.open_ms:
                raise ResearchVolatilityError("five-minute observations are not ordered")
            if item.segment == previous.segment and item.open_ms != previous.open_ms + FIVE_MINUTES_MS:
                raise ResearchVolatilityError("gap inside five-minute source segment")
        result.append(item)
        previous = item
    if len(result) != expected_rows:
        raise ResearchVolatilityError(
            f"five-minute row count mismatch: {len(result)} != {expected_rows}"
        )
    return result


def build_ewma_observations(
    features: Sequence[DailyFeature], config: EWMAConfig
) -> list[EWMARiskObservation]:
    output: list[EWMARiskObservation] = []
    segment: str | None = None
    history: list[float] = []
    variance: float | None = None
    expanding_sum = 0.0
    for feature in features:
        if feature.segment != segment:
            segment = feature.segment
            history = []
            variance = None
            expanding_sum = 0.0
        value = feature.close_to_close_log_return
        if value is not None:
            squared = value * value
            history.append(value)
            expanding_sum += squared
            if len(history) == config.initialization_returns:
                variance = expanding_sum / len(history)
            elif len(history) > config.initialization_returns:
                assert variance is not None
                variance = config.decay_lambda * variance + (1 - config.decay_lambda) * squared
        if variance is None:
            annualized = None
            multiplier = 0.0
            reason = "insufficient_same_segment_returns"
            expanding = None
        else:
            if variance < 0 or not math.isfinite(variance):
                raise ResearchVolatilityError("invalid EWMA variance")
            expanding = expanding_sum / len(history)
            annualized = math.sqrt(config.annualization_days * variance)
            multiplier = (
                1.0
                if annualized == 0
                else min(1.0, config.target_annualized_volatility / annualized)
            )
            reason = None
        output.append(
            EWMARiskObservation(
                variant_id=config.variant_id,
                segment=feature.segment,
                observed_ms=feature.observed_ms,
                available_ms=feature.available_ms,
                forecast_daily_variance=variance,
                expanding_daily_variance=expanding,
                annualized_volatility=annualized,
                exposure_multiplier=multiplier,
                return_count=len(history),
                unknown_reason=reason,
                source_feature_digest=feature.feature_digest,
                source_digest=feature.source_digest,
                config_digest=config.digest,
            )
        )
    return output


class RiskLookup:
    def __init__(
        self,
        observations: Sequence[EWMARiskObservation],
        max_age_ms: int,
        *,
        independent_source: bool = False,
    ):
        self.max_age_ms = max_age_ms
        grouped: dict[str, list[EWMARiskObservation]] = defaultdict(list)
        for item in observations:
            grouped[item.segment].append(item)
        self._groups = {key: tuple(value) for key, value in grouped.items()}
        self._times = {
            key: tuple(item.available_ms for item in value) for key, value in self._groups.items()
        }
        if independent_source and len(self._groups) != 1:
            raise ResearchVolatilityError(
                "independent risk source must contain exactly one continuous segment"
            )
        self._independent_segment = next(iter(self._groups)) if independent_source else None

    def at(self, decision_ms: int, segment: str) -> tuple[EWMARiskObservation | None, str | None]:
        lookup_segment = self._independent_segment or segment
        group = self._groups.get(lookup_segment)
        if not group:
            return None, "segment_has_no_risk_observations"
        index = bisect.bisect_right(self._times[lookup_segment], decision_ms) - 1
        if index < 0:
            return None, "risk_not_yet_available"
        item = group[index]
        age = decision_ms - item.available_ms
        if age < 0:
            raise ResearchVolatilityError("future risk observation selected")
        if age >= self.max_age_ms:
            return None, "risk_observation_stale"
        if not item.usable:
            return item, item.unknown_reason
        return item, None


def load_opportunities(
    path: Path,
    expected_sha256: str,
    expected_rows: int,
    scenario_ids: Sequence[str],
    expected_per_scenario: int,
    candles: Sequence[CandlePoint],
) -> tuple[list[Opportunity], dict[str, float]]:
    resolved = _require_input(path, expected_sha256, "S1 breakout trade ledger")
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    row_count = 0
    for raw in iter_jsonl_gzip(resolved):
        grouped[str(raw.get("scenario_id"))].append(raw)
        row_count += 1
    if row_count != expected_rows or set(grouped) != set(scenario_ids):
        raise ResearchVolatilityError("S1 trade ledger scenario or row-count mismatch")
    for scenario_id in scenario_ids:
        if len(grouped[scenario_id]) != expected_per_scenario:
            raise ResearchVolatilityError("unexpected S1 opportunity count")
    reference = grouped[scenario_ids[0]]
    core_keys = (
        "signal_ms",
        "entry_ms",
        "exit_ms",
        "entry_row",
        "exit_row",
        "entry_reference",
        "exit_reference",
        "exit_reason",
    )
    for index, baseline in enumerate(reference):
        identity = {key: baseline[key] for key in core_keys}
        for scenario_id in scenario_ids[1:]:
            compared = {key: grouped[scenario_id][index][key] for key in core_keys}
            if compared != identity:
                raise ResearchVolatilityError("S1 opportunities differ across cost scenarios")
    side_costs: dict[str, float] = {}
    for scenario_id in scenario_ids:
        first = grouped[scenario_id][0]
        entry_cost = (float(first["entry_fill"]) / float(first["entry_reference"]) - 1) * 10_000
        exit_cost = (1 - float(first["exit_fill"]) / float(first["exit_reference"])) * 10_000
        if not math.isclose(entry_cost, exit_cost, rel_tol=0, abs_tol=1e-9):
            raise ResearchVolatilityError("asymmetric S1 side costs")
        side_costs[scenario_id] = entry_cost
    opportunities: list[Opportunity] = []
    previous_exit = -1
    for raw in reference:
        entry_row = int(raw["entry_row"])
        exit_row = int(raw["exit_row"])
        if not 0 <= entry_row <= exit_row < len(candles) or entry_row <= previous_exit:
            raise ResearchVolatilityError("S1 opportunities are overlapping or out of range")
        candle = candles[entry_row]
        if candle.open_ms != int(raw["entry_ms"]):
            raise ResearchVolatilityError("S1 opportunity entry does not match candle ledger")
        payload = {key: raw[key] for key in core_keys}
        opportunities.append(
            Opportunity(
                opportunity_id=canonical_digest(payload),
                signal_ms=int(raw["signal_ms"]),
                entry_ms=int(raw["entry_ms"]),
                exit_ms=int(raw["exit_ms"]),
                entry_row=entry_row,
                exit_row=exit_row,
                segment=candle.segment,
                entry_reference=_finite(raw["entry_reference"], "entry reference"),
                exit_reference=_finite(raw["exit_reference"], "exit reference"),
                exit_reason=str(raw["exit_reason"]),
            )
        )
        previous_exit = exit_row
    return opportunities, side_costs


def allocations_for_opportunities(
    opportunities: Sequence[Opportunity],
    observations: Sequence[EWMARiskObservation],
    *,
    base_allocation: float,
    max_age_ms: int,
    independent_risk_source: bool = False,
) -> list[dict[str, Any]]:
    if not 0 <= base_allocation <= 0.1:
        raise ResearchVolatilityError("base allocation exceeds S2 cap")
    lookup = RiskLookup(
        observations, max_age_ms, independent_source=independent_risk_source
    )
    output: list[dict[str, Any]] = []
    for item in opportunities:
        risk, reason = lookup.at(item.signal_ms, item.segment)
        multiplier = 0.0 if reason is not None or risk is None else risk.exposure_multiplier
        allocation = base_allocation * multiplier
        if not 0 <= multiplier <= 1 or not 0 <= allocation <= 0.1:
            raise ResearchVolatilityError("EWMA sizing violates downward-only allocation")
        output.append(
            {
                "allocation_fraction": allocation,
                "opportunity_id": item.opportunity_id,
                "risk_digest": None if risk is None else risk.digest,
                "risk_observed_at": None if risk is None else iso_ms(risk.observed_ms),
                "signal_at": iso_ms(item.signal_ms),
                "unknown_reason": reason,
                "variant_id": observations[0].variant_id if observations else "unknown",
            }
        )
    return output


def coverage_report(
    opportunities: Sequence[Opportunity], allocations: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    if len(opportunities) != len(allocations):
        raise ResearchVolatilityError("opportunity allocation count mismatch")
    annual: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "usable": 0})
    reasons: dict[str, int] = defaultdict(int)
    usable = 0
    for item, allocation in zip(opportunities, allocations, strict=True):
        year = str(datetime.fromtimestamp(item.signal_ms / 1000, tz=UTC).year)
        annual[year]["total"] += 1
        reason = allocation.get("unknown_reason")
        if reason is None:
            annual[year]["usable"] += 1
            usable += 1
        else:
            reasons[str(reason)] += 1
    annual_output = {
        year: {
            **counts,
            "coverage": counts["usable"] / counts["total"] if counts["total"] else 0.0,
        }
        for year, counts in sorted(annual.items())
    }
    return {
        "annual": annual_output,
        "overall": usable / len(opportunities) if opportunities else 0.0,
        "reasons": dict(sorted(reasons.items())),
        "total": len(opportunities),
        "usable": usable,
    }


def realized_variance(
    candles: Sequence[CandlePoint],
    start_ms: int,
    segment: str,
    horizon_days: int,
    open_index: Mapping[int, int] | None = None,
) -> float | None:
    if open_index is None:
        opens = [item.open_ms for item in candles]
        start = bisect.bisect_left(opens, start_ms)
    else:
        start = open_index.get(start_ms, -1)
    count = horizon_days * 288
    if start == 0 or start >= len(candles) or candles[start].open_ms != start_ms:
        return None
    if start + count > len(candles):
        return None
    prior = candles[start - 1]
    if prior.segment != segment or prior.open_ms + FIVE_MINUTES_MS != start_ms:
        return None
    total = 0.0
    previous = prior
    for offset in range(count):
        item = candles[start + offset]
        if item.segment != segment or item.open_ms != start_ms + offset * FIVE_MINUTES_MS:
            return None
        value = math.log(item.close / previous.close)
        total += value * value
        previous = item
    return total


def _correlation(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) < 2 or len(left) != len(right):
        return None
    mean_left = statistics.fmean(left)
    mean_right = statistics.fmean(right)
    covariance = sum((a - mean_left) * (b - mean_right) for a, b in zip(left, right))
    variance_left = sum((a - mean_left) ** 2 for a in left)
    variance_right = sum((b - mean_right) ** 2 for b in right)
    if variance_left == 0 or variance_right == 0:
        return None
    return covariance / math.sqrt(variance_left * variance_right)


def forecast_diagnostics(
    observations: Sequence[EWMARiskObservation],
    candles: Sequence[CandlePoint],
    *,
    evaluation_start_ms: int,
    evaluation_end_ms: int,
    horizons_days: Sequence[int],
    independent_risk_source: bool = False,
) -> dict[str, Any]:
    output: dict[str, Any] = {}
    open_index = {item.open_ms: index for index, item in enumerate(candles)}
    for horizon in horizons_days:
        rows: list[tuple[float, float, float]] = []
        excluded = defaultdict(int)
        for item in observations:
            if not evaluation_start_ms <= item.observed_ms < evaluation_end_ms:
                continue
            if item.observed_ms + horizon * DAY_MS > evaluation_end_ms:
                excluded["crosses_development_end"] += 1
                continue
            if not item.usable or item.forecast_daily_variance is None:
                excluded["forecast_unknown"] += 1
                continue
            if independent_risk_source:
                candle_index = open_index.get(item.observed_ms)
                label_segment = (
                    None if candle_index is None else candles[candle_index].segment
                )
            else:
                label_segment = item.segment
            realized = (
                None
                if label_segment is None
                else realized_variance(
                    candles, item.observed_ms, label_segment, horizon, open_index
                )
            )
            if realized is None:
                excluded["label_not_contiguous_same_segment"] += 1
                continue
            forecast = item.forecast_daily_variance * horizon
            expanding = (item.expanding_daily_variance or 0.0) * horizon
            if forecast <= 0 or expanding <= 0:
                excluded["nonpositive_forecast"] += 1
                continue
            rows.append((forecast, expanding, realized))
        forecasts = [row[0] for row in rows]
        expandings = [row[1] for row in rows]
        realized_values = [row[2] for row in rows]
        qlike = [math.log(forecast) + realized / forecast for forecast, _, realized in rows]
        control_qlike = [
            math.log(expanding) + realized / expanding for _, expanding, realized in rows
        ]
        mse = [(forecast - realized) ** 2 for forecast, _, realized in rows]
        control_mse = [(expanding - realized) ** 2 for _, expanding, realized in rows]
        ordered = sorted(range(len(rows)), key=lambda index: forecasts[index])
        quartiles: dict[str, dict[str, float | int]] = {}
        for quartile in range(4):
            start = len(ordered) * quartile // 4
            end = len(ordered) * (quartile + 1) // 4
            selected = ordered[start:end]
            quartiles[str(quartile + 1)] = {
                "mean_forecast_variance": statistics.fmean(forecasts[index] for index in selected)
                if selected
                else 0.0,
                "mean_realized_variance": statistics.fmean(
                    realized_values[index] for index in selected
                )
                if selected
                else 0.0,
                "observations": len(selected),
            }
        output[f"{horizon}d"] = {
            "correlation": _correlation(forecasts, realized_values),
            "excluded": dict(sorted(excluded.items())),
            "expanding_mean_mse": statistics.fmean(control_mse) if control_mse else None,
            "expanding_mean_qlike": statistics.fmean(control_qlike) if control_qlike else None,
            "observations": len(rows),
            "primary_mean_mse": statistics.fmean(mse) if mse else None,
            "primary_mean_qlike": statistics.fmean(qlike) if qlike else None,
            "quartiles": quartiles,
        }
    return output


def matched_allocation(
    opportunities: Sequence[Opportunity], allocations: Sequence[Mapping[str, Any]]
) -> float:
    if len(opportunities) != len(allocations) or not opportunities:
        raise ResearchVolatilityError("cannot exposure-match empty or mismatched opportunities")
    denominator = sum(item.holding_seconds for item in opportunities)
    if denominator <= 0:
        raise ResearchVolatilityError("opportunity holding time must be positive")
    result = sum(
        float(allocation["allocation_fraction"]) * item.holding_seconds
        for item, allocation in zip(opportunities, allocations, strict=True)
    ) / denominator
    if not 0 <= result <= 0.1:
        raise ResearchVolatilityError("matched allocation exceeds S2 bounds")
    return result


def segmented_participation_opportunities(
    candles: Sequence[CandlePoint], evaluation_start_ms: int, evaluation_end_ms: int
) -> list[Opportunity]:
    grouped: dict[str, list[CandlePoint]] = defaultdict(list)
    for candle in candles:
        if evaluation_start_ms <= candle.open_ms < evaluation_end_ms:
            grouped[candle.segment].append(candle)
    ordered = sorted(grouped.values(), key=lambda values: values[0].open_ms)
    output: list[Opportunity] = []
    for values in ordered:
        first, last = values[0], values[-1]
        payload = {
            "entry_ms": first.open_ms,
            "entry_reference": first.open,
            "entry_row": first.source_row,
            "exit_ms": last.open_ms,
            "exit_reason": "source_segment_end",
            "exit_reference": last.close,
            "exit_row": last.source_row,
            "signal_ms": first.open_ms,
        }
        output.append(
            Opportunity(
                opportunity_id=canonical_digest(payload),
                signal_ms=first.open_ms,
                entry_ms=first.open_ms,
                exit_ms=last.open_ms,
                entry_row=first.source_row,
                exit_row=last.source_row,
                segment=first.segment,
                entry_reference=first.open,
                exit_reference=last.close,
                exit_reason="source_segment_end",
            )
        )
    return output


def _metrics_from_returns(returns: Sequence[float], years_elapsed: float) -> dict[str, Any]:
    equity = 1.0
    peak = 1.0
    maximum_drawdown = 0.0
    for value in returns:
        equity *= 1 + value
        peak = max(peak, equity)
        maximum_drawdown = min(maximum_drawdown, equity / peak - 1)
    mean = statistics.fmean(returns) if returns else 0.0
    volatility = statistics.pstdev(returns) if len(returns) > 1 else 0.0
    downside = math.sqrt(statistics.fmean(min(value, 0.0) ** 2 for value in returns)) if returns else 0.0
    cagr = equity ** (1 / years_elapsed) - 1 if years_elapsed > 0 else 0.0
    return {
        "cagr": cagr,
        "calmar": cagr / abs(maximum_drawdown) if maximum_drawdown < 0 else None,
        "daily_volatility_annualized": volatility * math.sqrt(365),
        "maximum_drawdown_fraction": -maximum_drawdown,
        "net_return": equity - 1,
        "sharpe": mean / volatility * math.sqrt(365) if volatility else None,
        "sortino": mean / downside * math.sqrt(365) if downside else None,
    }


def simulate_locked_cohorts(
    candles: Sequence[CandlePoint],
    opportunities: Sequence[Opportunity],
    allocations: Sequence[float],
    *,
    side_cost_bps: float,
    evaluation_start_ms: int,
    evaluation_end_ms: int,
) -> dict[str, Any]:
    if len(opportunities) != len(allocations):
        raise ResearchVolatilityError("locked simulation allocation count differs")
    cash = 1000.0
    side_cost = side_cost_bps / 10_000
    trades: list[dict[str, Any]] = []
    total_cost = 0.0
    for opportunity, allocation in zip(opportunities, allocations, strict=True):
        if not 0 <= allocation <= 0.1:
            raise ResearchVolatilityError("locked simulation allocation is outside [0, 0.1]")
        budget = cash * allocation
        entry_fill = opportunity.entry_reference * (1 + side_cost)
        quantity = budget / entry_fill if budget else 0.0
        remaining = cash - budget
        exit_fill = opportunity.exit_reference * (1 - side_cost)
        proceeds = quantity * exit_fill
        cash_after = remaining + proceeds
        entry_cost = quantity * (entry_fill - opportunity.entry_reference)
        exit_cost = quantity * (opportunity.exit_reference - exit_fill)
        total_cost += entry_cost + exit_cost
        trades.append(
            {
                "allocation_fraction": allocation,
                "cash_after": cash_after,
                "cash_before": cash,
                "entry_fill": entry_fill,
                "entry_ms": opportunity.entry_ms,
                "entry_reference": opportunity.entry_reference,
                "entry_row": opportunity.entry_row,
                "exit_fill": exit_fill,
                "exit_ms": opportunity.exit_ms,
                "exit_reason": opportunity.exit_reason,
                "exit_reference": opportunity.exit_reference,
                "exit_row": opportunity.exit_row,
                "opportunity_id": opportunity.opportunity_id,
                "pnl_quote": cash_after - cash,
                "quantity": quantity,
                "remaining_cash": remaining,
                "return_on_allocated": proceeds / budget - 1 if budget else None,
                "signal_ms": opportunity.signal_ms,
                "transaction_cost_quote": entry_cost + exit_cost,
            }
        )
        cash = cash_after

    eval_indices = [
        index
        for index, candle in enumerate(candles)
        if evaluation_start_ms <= candle.open_ms < evaluation_end_ms
    ]
    trade_index = 0
    current = trades[0] if trades else None
    settled_cash = 1000.0
    peak = 1000.0
    maximum_drawdown = 0.0
    active_rows = 0
    allocation_time_sum = 0.0
    daily_end: dict[date, float] = {}
    for index in eval_indices:
        candle = candles[index]
        while current is not None and index > current["exit_row"]:
            settled_cash = current["cash_after"]
            trade_index += 1
            current = trades[trade_index] if trade_index < len(trades) else None
        if current is not None and current["entry_row"] <= index <= current["exit_row"]:
            equity = (
                current["cash_after"]
                if index == current["exit_row"]
                else current["remaining_cash"] + current["quantity"] * candle.close
            )
            if current["allocation_fraction"] > 0:
                active_rows += 1
                allocation_time_sum += current["allocation_fraction"]
        else:
            equity = settled_cash
        peak = max(peak, equity)
        maximum_drawdown = min(maximum_drawdown, equity / peak - 1)
        daily_end[datetime.fromtimestamp(candle.open_ms / 1000, tz=UTC).date()] = equity

    start_day = datetime.fromtimestamp(evaluation_start_ms / 1000, tz=UTC).date()
    end_day = datetime.fromtimestamp(evaluation_end_ms / 1000, tz=UTC).date()
    daily_equity: list[tuple[date, float]] = []
    prior_equity = 1000.0
    day = start_day
    while day < end_day:
        if day in daily_end:
            prior_equity = daily_end[day]
        daily_equity.append((day, prior_equity))
        day += timedelta(days=1)
    daily_returns: list[tuple[str, float]] = []
    prior = 1000.0
    for day, equity in daily_equity:
        daily_returns.append((day.isoformat(), equity / prior - 1))
        prior = equity
    values = [value for _, value in daily_returns]
    years_elapsed = (evaluation_end_ms - evaluation_start_ms) / (365.2425 * DAY_MS)
    return_metrics = _metrics_from_returns(values, years_elapsed)
    net_return = cash / 1000.0 - 1.0
    cagr = (cash / 1000.0) ** (1.0 / years_elapsed) - 1.0
    intraday_drawdown = -maximum_drawdown
    return_metrics["daily_maximum_drawdown_fraction"] = return_metrics[
        "maximum_drawdown_fraction"
    ]
    return_metrics["net_return"] = net_return
    return_metrics["cagr"] = cagr
    return_metrics["maximum_drawdown_fraction"] = intraday_drawdown
    return_metrics["calmar"] = cagr / intraday_drawdown if intraday_drawdown else None
    returns_on_allocated = [
        float(item["return_on_allocated"])
        for item in trades
        if item["return_on_allocated"] is not None
    ]
    gains = sum(max(float(item["pnl_quote"]), 0.0) for item in trades)
    losses = -sum(min(float(item["pnl_quote"]), 0.0) for item in trades)
    rolling = [
        daily_equity[index][1] / daily_equity[index - 90][1] - 1
        for index in range(90, len(daily_equity))
    ]
    monthly_returns: dict[str, float] = {}
    monthly_equity: dict[str, float] = {}
    for day, equity in daily_equity:
        monthly_equity[day.strftime("%Y-%m")] = equity
    prior = 1000.0
    for month, equity in monthly_equity.items():
        monthly_returns[month] = equity / prior - 1
        prior = equity
    positive_pnl = [float(item["pnl_quote"]) for item in trades if item["pnl_quote"] > 0]
    return {
        **return_metrics,
        "active_position_time_fraction": active_rows / len(eval_indices) if eval_indices else 0.0,
        "average_allocation_fraction_over_all_time": allocation_time_sum / len(eval_indices)
        if eval_indices
        else 0.0,
        "daily_returns": daily_returns,
        "ending_equity": cash,
        "intraday_maximum_drawdown_fraction": -maximum_drawdown,
        "mean_net_trade_bps": statistics.fmean(returns_on_allocated) * 10_000
        if returns_on_allocated
        else None,
        "monthly_returns": monthly_returns,
        "nonzero_trade_count": len(returns_on_allocated),
        "profit_factor": gains / losses if losses else None,
        "side_cost_bps": side_cost_bps,
        "top_three_profitable_trades_share": sum(sorted(positive_pnl, reverse=True)[:3])
        / sum(positive_pnl)
        if positive_pnl
        else None,
        "total_transaction_cost_quote": total_cost,
        "trade_count": len(trades),
        "trades": trades,
        "turnover_on_starting_equity": sum(
            float(item["cash_before"]) * float(item["allocation_fraction"]) * 2
            for item in trades
        )
        / 1000.0,
        "win_rate": sum(value > 0 for value in returns_on_allocated) / len(returns_on_allocated)
        if returns_on_allocated
        else None,
        "worst_rolling_90_day_return": min(rolling) if rolling else None,
    }


def paired_month_bootstrap(
    primary_monthly: Mapping[str, float],
    fixed_monthly: Mapping[str, float],
    *,
    seed: int,
    replications: int,
) -> list[float | None]:
    months = sorted(set(primary_monthly) & set(fixed_monthly))
    if not months:
        return [None, None]
    differences = [primary_monthly[month] - fixed_monthly[month] for month in months]
    generator = random.Random(seed)
    samples = sorted(
        statistics.fmean(generator.choice(differences) for _ in differences)
        for _ in range(replications)
    )
    return [samples[int(0.025 * (len(samples) - 1))], samples[int(0.975 * (len(samples) - 1))]]


def neutralize_best_relative_months(
    primary_daily: Sequence[tuple[str, float]],
    fixed_daily: Sequence[tuple[str, float]],
    *,
    count: int = 3,
) -> dict[str, Any]:
    if [day for day, _ in primary_daily] != [day for day, _ in fixed_daily]:
        raise ResearchVolatilityError("daily return timelines differ")
    monthly_primary: dict[str, float] = defaultdict(float)
    monthly_fixed: dict[str, float] = defaultdict(float)
    for (day, primary), (_, fixed) in zip(primary_daily, fixed_daily, strict=True):
        month = day[:7]
        monthly_primary[month] += primary
        monthly_fixed[month] += fixed
    removed = sorted(
        monthly_primary,
        key=lambda month: (monthly_primary[month] - monthly_fixed[month], month),
        reverse=True,
    )[:count]
    removed_set = set(removed)
    primary_values = [0.0 if day[:7] in removed_set else value for day, value in primary_daily]
    fixed_values = [0.0 if day[:7] in removed_set else value for day, value in fixed_daily]
    years = len(primary_values) / 365.2425
    return {
        "fixed": _metrics_from_returns(fixed_values, years),
        "primary": _metrics_from_returns(primary_values, years),
        "removed_months": sorted(removed),
    }


def leave_one_year_out(daily_returns: Sequence[tuple[str, float]]) -> dict[str, dict[str, Any]]:
    years = sorted({day[:4] for day, _ in daily_returns})
    output: dict[str, dict[str, Any]] = {}
    for year in years:
        selected = [value for day, value in daily_returns if not day.startswith(year)]
        output[year] = _metrics_from_returns(selected, len(selected) / 365.2425)
    return output


def check_planned_risk(
    allocation_fraction: float,
    protective_stop_fraction: float,
    round_trip_cost_bps: float,
    maximum_planned_risk_fraction: float,
) -> float:
    planned = allocation_fraction * (
        protective_stop_fraction + round_trip_cost_bps / 10_000
    )
    if planned > maximum_planned_risk_fraction + 1e-15:
        raise ResearchVolatilityError(
            f"planned risk {planned} exceeds {maximum_planned_risk_fraction}"
        )
    return planned
