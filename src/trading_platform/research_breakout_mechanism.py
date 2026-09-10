"""Causal mechanism diagnostics for the fixed BTC breakout development control."""

from __future__ import annotations

import math
import random
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence


FIVE_MINUTES_MS = 300_000
SEVEN_DAYS_MS = 604_800_000
UTC = timezone.utc


class ResearchBreakoutMechanismError(ValueError):
    """Raised when frozen S5 inputs or calculations are invalid."""


def parse_utc_ms(value: str) -> int:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise ResearchBreakoutMechanismError(f"invalid UTC timestamp: {value}") from exc
    if parsed.tzinfo is None or parsed.utcoffset().total_seconds() != 0:
        raise ResearchBreakoutMechanismError(f"timestamp is not explicit UTC: {value}")
    return int(parsed.timestamp() * 1000)


def linear_quantile(values: Sequence[float], probability: float) -> float:
    if not values or not 0 <= probability <= 1:
        raise ResearchBreakoutMechanismError("invalid quantile input")
    ordered = sorted(float(value) for value in values)
    if any(not math.isfinite(value) for value in ordered):
        raise ResearchBreakoutMechanismError("quantile input is non-finite")
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def validate_candles(
    bars_4h: Sequence[Mapping[str, Any]], candles_5m: Sequence[Any]
) -> None:
    if not bars_4h or not candles_5m:
        raise ResearchBreakoutMechanismError("candle inputs cannot be empty")
    previous_close: int | None = None
    previous_segment: str | None = None
    closed_segments: set[str] = set()
    for index, row in enumerate(candles_5m):
        if int(row.source_row) != index:
            raise ResearchBreakoutMechanismError("five-minute row identity changed")
        open_ms = int(row.open_ms)
        close_ms = open_ms + FIVE_MINUTES_MS
        segment = str(row.segment)
        if close_ms - open_ms != FIVE_MINUTES_MS:
            raise ResearchBreakoutMechanismError("invalid five-minute interval")
        if previous_close is not None and segment == previous_segment and open_ms != previous_close:
            raise ResearchBreakoutMechanismError("five-minute same-segment gap")
        if previous_segment is not None and segment != previous_segment:
            closed_segments.add(previous_segment)
            if open_ms <= previous_close or segment in closed_segments:
                raise ResearchBreakoutMechanismError("five-minute segment order changed")
        prices = [float(getattr(row, key)) for key in ("open", "high", "low", "close")]
        if any(not math.isfinite(value) or value <= 0 for value in prices):
            raise ResearchBreakoutMechanismError("invalid five-minute price")
        previous_close, previous_segment = close_ms, segment
    previous_decision: int | None = None
    for row in bars_4h:
        if row.get("interval") != "4h":
            raise ResearchBreakoutMechanismError("four-hour interval identity changed")
        decision_ms = parse_utc_ms(str(row["close_at"]))
        if previous_decision is not None and decision_ms <= previous_decision:
            raise ResearchBreakoutMechanismError("four-hour decisions are not increasing")
        start = int(row["start_source_row"])
        end = int(row["end_source_row"])
        if not 0 <= start <= end < len(candles_5m):
            raise ResearchBreakoutMechanismError("four-hour source lineage is invalid")
        if (
            str(candles_5m[start].segment) != str(row["segment"])
            or str(candles_5m[end].segment) != str(row["segment"])
            or int(candles_5m[end].open_ms) + FIVE_MINUTES_MS != decision_ms
        ):
            raise ResearchBreakoutMechanismError("four-hour source lineage mismatch")
        previous_decision = decision_ms


def build_directional_efficiency(
    bars_4h: Sequence[Mapping[str, Any]], *, lookback: int = 120, cutoff_history: int = 720
) -> list[dict[str, Any]]:
    """Build point-in-time efficiencies and past-only terciles for every valid 4h bar."""

    history: dict[str, list[float]] = defaultdict(list)
    output: list[dict[str, Any]] = []
    for index, bar in enumerate(bars_4h):
        if index < lookback:
            continue
        window = bars_4h[index - lookback : index + 1]
        segment = str(bar["segment"])
        if any(str(item["segment"]) != segment for item in window):
            continue
        closes = [float(item["close"]) for item in window]
        changes = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
        denominator = sum(abs(value) for value in changes)
        if denominator <= 0 or not math.isfinite(denominator):
            continue
        value = abs(math.log(closes[-1] / closes[0])) / denominator
        prior = history[segment]
        lower = upper = None
        classification = "unknown"
        if len(prior) >= cutoff_history:
            exact = prior[-cutoff_history:]
            lower = linear_quantile(exact, 1.0 / 3.0)
            upper = linear_quantile(exact, 2.0 / 3.0)
            if value <= lower:
                classification = "low"
            elif value >= upper:
                classification = "high"
            else:
                classification = "middle"
        output.append(
            {
                "bar_index": index,
                "classification": classification,
                "decision_at": str(bar["close_at"]),
                "decision_ms": parse_utc_ms(str(bar["close_at"])),
                "lower_tercile_cutoff": lower,
                "preceding_cutoff_observations": min(len(prior), cutoff_history),
                "segment": segment,
                "upper_tercile_cutoff": upper,
                "value": value,
            }
        )
        prior.append(value)
    return output


def fixed_seven_day_return(
    candles_5m: Sequence[Any], entry_row: int, expected_segment: str
) -> float | None:
    endpoint_row = entry_row + SEVEN_DAYS_MS // FIVE_MINUTES_MS
    if entry_row < 0 or endpoint_row >= len(candles_5m):
        return None
    entry = candles_5m[entry_row]
    endpoint = candles_5m[endpoint_row]
    entry_ms = int(entry.open_ms)
    if (
        str(entry.segment) != expected_segment
        or str(endpoint.segment) != expected_segment
        or int(endpoint.open_ms) != entry_ms + SEVEN_DAYS_MS
    ):
        return None
    # validate_candles proves same-segment continuity and prohibits a segment from reopening;
    # equal endpoint segment plus the exact row/time displacement therefore proves every
    # intervening candle is consecutive and belongs to that segment.
    return math.log(float(endpoint.open) / float(entry.open))


def eligible_random_candidates(
    bars_4h: Sequence[Mapping[str, Any]],
    candles_5m: Sequence[Any],
    *,
    start_ms: int,
    end_ms: int,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for index, bar in enumerate(bars_4h):
        decision_ms = parse_utc_ms(str(bar["close_at"]))
        if not start_ms <= decision_ms < end_ms:
            continue
        entry_row = int(bar["end_source_row"]) + 1
        if entry_row >= len(candles_5m):
            continue
        entry = candles_5m[entry_row]
        if (
            str(entry.segment) != str(bar["segment"])
            or int(entry.open_ms) != decision_ms
        ):
            continue
        value = fixed_seven_day_return(candles_5m, entry_row, str(bar["segment"]))
        if value is not None:
            output.append(
                {
                    "bar_index": index,
                    "decision_ms": decision_ms,
                    "fixed_7d_log_return": value,
                    "year": datetime.fromtimestamp(decision_ms / 1000, tz=UTC).year,
                }
            )
    return output


def matched_random_control(
    candidates: Sequence[Mapping[str, Any]],
    breakout_returns: Sequence[Mapping[str, Any]],
    *,
    seed: int,
    replications: int,
) -> dict[str, Any]:
    by_year: dict[int, list[float]] = defaultdict(list)
    counts: dict[int, int] = defaultdict(int)
    for row in candidates:
        by_year[int(row["year"])].append(float(row["fixed_7d_log_return"]))
    observed_values: list[float] = []
    for row in breakout_returns:
        counts[int(row["entry_year"])] += 1
        observed_values.append(float(row["fixed_7d_log_return"]))
    if not observed_values:
        raise ResearchBreakoutMechanismError("no valid breakout seven-day returns")
    for year, count in counts.items():
        if len(by_year[year]) < count:
            raise ResearchBreakoutMechanismError(f"insufficient random candidates in {year}")
    generator = random.Random(seed)
    values: list[float] = []
    rows: list[dict[str, Any]] = []
    for replication in range(replications):
        sampled: list[float] = []
        for year in sorted(counts):
            sampled.extend(generator.sample(by_year[year], counts[year]))
        mean = statistics.fmean(sampled)
        values.append(mean)
        rows.append({"mean_fixed_7d_log_return": mean, "replication": replication + 1})
    observed = statistics.fmean(observed_values)
    percentile = (1 + sum(value <= observed for value in values)) / (replications + 1)
    return {
        "breakout_mean_fixed_7d_log_return": observed,
        "breakout_observations": len(observed_values),
        "candidate_counts_by_year": {
            str(year): len(by_year[year]) for year in sorted(by_year)
        },
        "empirical_percentile": percentile,
        "random_mean": statistics.fmean(values),
        "random_mean_ci95": [linear_quantile(values, 0.025), linear_quantile(values, 0.975)],
        "replication_rows": rows,
        "sample_counts_by_year": {str(year): counts[year] for year in sorted(counts)},
    }


def month_block_efficiency_difference(
    trades: Sequence[Mapping[str, Any]], *, seed: int, replications: int
) -> dict[str, Any]:
    selected = [row for row in trades if row.get("efficiency_class") in {"high", "low"}]
    high = [float(row["return_on_allocated"]) for row in selected if row["efficiency_class"] == "high"]
    low = [float(row["return_on_allocated"]) for row in selected if row["efficiency_class"] == "low"]
    if not high or not low:
        return {"ci95": None, "difference": None, "valid_replications": 0}
    by_month: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in selected:
        by_month[str(row["entry_month"])].append(row)
    months = sorted(by_month)
    generator = random.Random(seed)
    values: list[float] = []
    for _ in range(replications):
        sampled = [row for _month in range(len(months)) for row in by_month[generator.choice(months)]]
        sample_high = [float(row["return_on_allocated"]) for row in sampled if row["efficiency_class"] == "high"]
        sample_low = [float(row["return_on_allocated"]) for row in sampled if row["efficiency_class"] == "low"]
        if sample_high and sample_low:
            values.append(statistics.fmean(sample_high) - statistics.fmean(sample_low))
    return {
        "ci95": [linear_quantile(values, 0.025), linear_quantile(values, 0.975)] if values else None,
        "difference": statistics.fmean(high) - statistics.fmean(low),
        "high_mean": statistics.fmean(high),
        "high_trades": len(high),
        "low_mean": statistics.fmean(low),
        "low_trades": len(low),
        "months": len(months),
        "valid_replications": len(values),
    }


def concentration(trades: Sequence[Mapping[str, Any]]) -> dict[str, float | None]:
    positives = sorted(
        (float(row["return_on_allocated"]) for row in trades if float(row["return_on_allocated"]) > 0),
        reverse=True,
    )
    monthly: dict[str, float] = defaultdict(float)
    for row in trades:
        monthly[str(row["entry_month"])] += float(row["pnl_quote"])
    positive_months = sorted((value for value in monthly.values() if value > 0), reverse=True)
    return {
        "best_three_profitable_months_share": (
            sum(positive_months[:3]) / sum(positive_months) if positive_months else None
        ),
        "top_three_profitable_trades_share": (
            sum(positives[:3]) / sum(positives) if positives else None
        ),
    }


def grouped_attribution(
    trades: Sequence[Mapping[str, Any]], key: str
) -> dict[str, dict[str, float | int | None]]:
    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in trades:
        groups[str(row[key])].append(row)
    return {
        name: {
            "mean_net_trade_return": statistics.fmean(
                float(row["return_on_allocated"]) for row in rows
            ),
            "pnl_quote": sum(float(row["pnl_quote"]) for row in rows),
            "trades": len(rows),
            "win_rate": sum(float(row["return_on_allocated"]) > 0 for row in rows) / len(rows),
        }
        for name, rows in sorted(groups.items())
    }
