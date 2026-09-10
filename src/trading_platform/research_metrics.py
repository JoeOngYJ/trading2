"""Deterministic, offline-only evidence metrics for BTC strategy research.

The module intentionally has no network, database, message-bus, exchange-client, or
production-signal imports.  It consumes already validated mark-to-market and trade ledgers and
returns canonical, fail-closed research scorecards.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import statistics
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from statistics import NormalDist
from typing import Any, Iterable, Mapping, Sequence


UTC = timezone.utc
DAY_MS = 86_400_000
ANNUALIZATION_DAYS = 365.2425
SCHEMA_VERSION = "btc-backtest-scorecard-v1"


class ResearchMetricError(ValueError):
    """Raised when scorecard inputs are ambiguous, invalid, or non-causal."""


@dataclass(frozen=True, slots=True)
class EquityObservation:
    day_ms: int
    equity: float
    segment: str = "continuous"

    def __post_init__(self) -> None:
        if self.day_ms < 0 or self.day_ms % DAY_MS:
            raise ResearchMetricError("equity timestamp must be an exact UTC day")
        if not math.isfinite(self.equity) or self.equity <= 0:
            raise ResearchMetricError("equity must be finite and positive")
        if not self.segment:
            raise ResearchMetricError("equity segment is required")


@dataclass(frozen=True, slots=True)
class TradeObservation:
    trade_id: str
    entry_ms: int
    exit_ms: int
    pnl_quote: float
    allocated_quote: float
    cost_quote: float
    turnover_quote: float

    def __post_init__(self) -> None:
        if not self.trade_id or self.entry_ms < 0 or self.exit_ms < self.entry_ms:
            raise ResearchMetricError("trade identity and increasing timestamps are required")
        values = (self.pnl_quote, self.allocated_quote, self.cost_quote, self.turnover_quote)
        if not all(math.isfinite(value) for value in values):
            raise ResearchMetricError("trade values must be finite")
        if self.allocated_quote < 0 or self.cost_quote < 0 or self.turnover_quote < 0:
            raise ResearchMetricError("trade allocation, cost, and turnover cannot be negative")


@dataclass(frozen=True, slots=True)
class MetricEstimate:
    status: str
    value: float | int | None
    unit: str
    method: str
    observations: int
    effective_observations: float | None = None
    confidence_interval_95: tuple[float, float] | None = None
    reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(frozen=True, slots=True)
class GateResult:
    status: str
    observed: Any
    threshold: Any
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


def _clean(value: Any) -> Any:
    """Convert immutable values to strict JSON-compatible values and reject non-finite numbers."""

    if isinstance(value, dict):
        return {str(key): _clean(item) for key, item in sorted(value.items(), key=lambda row: str(row[0]))}
    if isinstance(value, (list, tuple)):
        return [_clean(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        raise ResearchMetricError("scorecards cannot serialize NaN or infinity")
    return value


def canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(_clean(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def sha256_digest(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def validate_equity_path(observations: Sequence[EquityObservation]) -> None:
    if not observations:
        raise ResearchMetricError("equity observations are required")
    previous: EquityObservation | None = None
    for item in observations:
        if previous is not None:
            if item.day_ms <= previous.day_ms:
                raise ResearchMetricError("equity timestamps are duplicated or reversed")
            if item.segment == previous.segment and item.day_ms != previous.day_ms + DAY_MS:
                raise ResearchMetricError("gap inside an equity segment")
            if item.segment != previous.segment and item.day_ms == previous.day_ms + DAY_MS:
                raise ResearchMetricError("segment changed without a time discontinuity")
        previous = item


def equity_from_returns(
    daily_returns: Sequence[tuple[str, float]], starting_equity: float = 1000.0
) -> list[EquityObservation]:
    if not math.isfinite(starting_equity) or starting_equity <= 0:
        raise ResearchMetricError("starting equity must be finite and positive")
    result: list[EquityObservation] = []
    equity = starting_equity
    for day, value in daily_returns:
        parsed = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=UTC)
        if not math.isfinite(value) or value <= -1:
            raise ResearchMetricError("daily return must be finite and greater than -100%")
        equity *= 1 + value
        result.append(EquityObservation(int(parsed.timestamp() * 1000), equity))
    validate_equity_path(result)
    return result


def returns_from_equity(
    observations: Sequence[EquityObservation], starting_equity: float
) -> list[tuple[int, float]]:
    validate_equity_path(observations)
    if not math.isfinite(starting_equity) or starting_equity <= 0:
        raise ResearchMetricError("starting equity must be finite and positive")
    output: list[tuple[int, float]] = []
    previous_equity = starting_equity
    previous: EquityObservation | None = None
    for item in observations:
        if previous is not None and item.segment != previous.segment:
            previous_equity = item.equity
            previous = item
            continue
        output.append((item.day_ms, item.equity / previous_equity - 1))
        previous_equity = item.equity
        previous = item
    return output


def _quantile(values: Sequence[float], probability: float) -> float:
    if not values or not 0 <= probability <= 1:
        raise ResearchMetricError("invalid quantile request")
    ordered = sorted(values)
    position = probability * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _long_run_variance(values: Sequence[float], lag: int) -> tuple[float, float, float]:
    if len(values) < 2:
        raise ResearchMetricError("at least two returns are required")
    mean = statistics.fmean(values)
    centered = [value - mean for value in values]
    gamma0 = sum(value * value for value in centered) / len(centered)
    lag = min(max(lag, 0), len(values) - 1)
    long_run = gamma0
    for offset in range(1, lag + 1):
        covariance = sum(
            centered[index] * centered[index - offset]
            for index in range(offset, len(centered))
        ) / len(centered)
        long_run += 2 * (1 - offset / (lag + 1)) * covariance
    return mean, gamma0, max(long_run, 0.0)


def _skew_kurtosis(values: Sequence[float]) -> tuple[float, float]:
    if len(values) < 4:
        raise ResearchMetricError("at least four observations are required")
    mean = statistics.fmean(values)
    variance = statistics.fmean((value - mean) ** 2 for value in values)
    if variance == 0:
        return 0.0, 3.0
    deviation = math.sqrt(variance)
    skew = statistics.fmean(((value - mean) / deviation) ** 3 for value in values)
    kurtosis = statistics.fmean(((value - mean) / deviation) ** 4 for value in values)
    return skew, kurtosis


def _probabilistic_sharpe(
    values: Sequence[float], benchmark_daily_sharpe: float, effective_n: float
) -> tuple[float | None, float | None]:
    if len(values) < 4 or effective_n <= 1:
        return None, None
    mean = statistics.fmean(values)
    deviation = statistics.stdev(values)
    if deviation == 0:
        return None, None
    sharpe = mean / deviation
    skew, kurtosis = _skew_kurtosis(values)
    denominator_squared = 1 - skew * sharpe + ((kurtosis - 1) / 4) * sharpe * sharpe
    if denominator_squared <= 0:
        return None, None
    z = (sharpe - benchmark_daily_sharpe) * math.sqrt(effective_n - 1) / math.sqrt(
        denominator_squared
    )
    probability = NormalDist().cdf(z)
    if sharpe <= benchmark_daily_sharpe:
        min_track = None
    else:
        target_z = NormalDist().inv_cdf(0.95)
        min_track = 1 + denominator_squared * (
            target_z / (sharpe - benchmark_daily_sharpe)
        ) ** 2
    return probability, min_track


def _deflated_sharpe(
    values: Sequence[float], annual_trial_sharpes: Sequence[float], effective_n: float
) -> tuple[float | None, float | None]:
    if not annual_trial_sharpes:
        return None, None
    daily = [value / math.sqrt(ANNUALIZATION_DAYS) for value in annual_trial_sharpes]
    if len(daily) == 1:
        expected_max = 0.0
    else:
        trial_deviation = statistics.stdev(daily)
        count = len(daily)
        euler_gamma = 0.5772156649015329
        expected_max = trial_deviation * (
            (1 - euler_gamma) * NormalDist().inv_cdf(1 - 1 / count)
            + euler_gamma * NormalDist().inv_cdf(1 - 1 / (count * math.e))
        )
    probability, _ = _probabilistic_sharpe(values, expected_max, effective_n)
    return probability, expected_max * math.sqrt(ANNUALIZATION_DAYS)


def _drawdown_statistics(equities: Sequence[float]) -> dict[str, float | int | None]:
    peak = equities[0]
    peak_index = 0
    maximum = 0.0
    maximum_duration = 0
    current_duration = 0
    recovery_duration: int | None = None
    trough_index: int | None = None
    maximum_peak_index: int | None = None
    underwater = 0
    for index, equity in enumerate(equities):
        if equity >= peak:
            if trough_index is not None and recovery_duration is None:
                recovery_duration = index - trough_index
            peak = equity
            peak_index = index
            current_duration = 0
        else:
            underwater += 1
            current_duration += 1
            maximum_duration = max(maximum_duration, current_duration)
            drawdown = 1 - equity / peak
            if drawdown > maximum:
                maximum = drawdown
                maximum_peak_index = peak_index
                trough_index = index
                recovery_duration = None
    return {
        "maximum_drawdown_fraction": maximum,
        "maximum_drawdown_duration_days": maximum_duration,
        "maximum_drawdown_peak_index": maximum_peak_index,
        "maximum_drawdown_recovery_days": recovery_duration,
        "time_underwater_fraction": underwater / len(equities),
    }


def _rolling_return(values: Sequence[float], window: int) -> float | None:
    if len(values) < window:
        return None
    cumulative = [1.0]
    for value in values:
        cumulative.append(cumulative[-1] * (1 + value))
    return min(cumulative[index] / cumulative[index - window] - 1 for index in range(window, len(cumulative)))


def _calendar_returns(returns: Sequence[tuple[int, float]], key_format: str) -> dict[str, float]:
    grouped: dict[str, float] = {}
    for timestamp, value in returns:
        key = datetime.fromtimestamp(timestamp / 1000, tz=UTC).strftime(key_format)
        grouped[key] = (1 + grouped.get(key, 0.0)) * (1 + value) - 1
    return dict(sorted(grouped.items()))


def _block_groups(length: int, block_days: int) -> list[range]:
    return [range(start, min(start + block_days, length)) for start in range(0, length, block_days)]


def block_bootstrap_mean_interval(
    values: Sequence[float], *, block_days: int, replications: int, seed: int
) -> tuple[tuple[float, float] | None, int]:
    if block_days <= 0 or replications <= 0:
        raise ResearchMetricError("bootstrap block and replication counts must be positive")
    groups = _block_groups(len(values), block_days)
    if len(groups) < 2:
        return None, len(groups)
    block_totals = [sum(values[index] for index in group) for group in groups]
    block_counts = [len(group) for group in groups]
    rng = random.Random(seed)
    samples: list[float] = []
    for _ in range(replications):
        sampled_total = 0.0
        sampled_count = 0
        for _ in groups:
            selected = rng.randrange(len(groups))
            sampled_total += block_totals[selected]
            sampled_count += block_counts[selected]
        samples.append(sampled_total / sampled_count)
    return (_quantile(samples, 0.025), _quantile(samples, 0.975)), len(groups)


def _alpha_beta(strategy: Sequence[float], control: Sequence[float]) -> tuple[float, float]:
    if len(strategy) != len(control) or len(strategy) < 3:
        raise ResearchMetricError("alpha/beta inputs must be aligned")
    x_mean = statistics.fmean(control)
    y_mean = statistics.fmean(strategy)
    variance = statistics.fmean((value - x_mean) ** 2 for value in control)
    beta = 0.0 if variance == 0 else statistics.fmean(
        (x - x_mean) * (y - y_mean) for x, y in zip(control, strategy, strict=True)
    ) / variance
    return y_mean - beta * x_mean, beta


def _trade_metrics(trades: Sequence[TradeObservation]) -> dict[str, Any]:
    if not trades:
        return {
            "trade_count": MetricEstimate("insufficient", 0, "count", "closed trades", 0, reason="no trades").as_dict()
        }
    ordered = sorted(trades, key=lambda item: (item.entry_ms, item.trade_id))
    previous_exit = -1
    cohorts = 0
    for trade in ordered:
        if trade.entry_ms > previous_exit:
            cohorts += 1
        previous_exit = max(previous_exit, trade.exit_ms)
    pnl = [item.pnl_quote for item in ordered]
    positive = [value for value in pnl if value > 0]
    negative = [-value for value in pnl if value < 0]
    allocated_returns = [
        item.pnl_quote / item.allocated_quote for item in ordered if item.allocated_quote > 0
    ]
    losses_in_row = 0
    maximum_loss_streak = 0
    for value in pnl:
        losses_in_row = losses_in_row + 1 if value < 0 else 0
        maximum_loss_streak = max(maximum_loss_streak, losses_in_row)
    total_positive = sum(positive)
    return {
        "average_holding_days": statistics.fmean(
            (item.exit_ms - item.entry_ms) / DAY_MS for item in ordered
        ),
        "best_trade_positive_pnl_fraction": max(positive) / total_positive if positive else None,
        "independent_trade_cohorts": cohorts,
        "maximum_loss_streak": maximum_loss_streak,
        "mean_expectancy_fraction_of_allocated": statistics.fmean(allocated_returns) if allocated_returns else None,
        "median_expectancy_fraction_of_allocated": statistics.median(allocated_returns) if allocated_returns else None,
        "payoff_ratio": statistics.fmean(positive) / statistics.fmean(negative) if positive and negative else None,
        "profit_factor": sum(positive) / sum(negative) if negative else None,
        "top_three_trades_positive_pnl_fraction": sum(sorted(positive, reverse=True)[:3]) / total_positive if positive else None,
        "trade_count": len(ordered),
        "win_rate": len(positive) / len(ordered),
        "worst_trade_quote": min(pnl),
    }


def _metric(value: float | int | None, unit: str, method: str, observations: int) -> dict[str, Any]:
    if value is None:
        return MetricEstimate("insufficient", None, unit, method, observations, reason="insufficient observations or zero denominator").as_dict()
    return MetricEstimate("available", value, unit, method, observations).as_dict()


def _performance_metrics(
    equity: Sequence[EquityObservation], starting_equity: float, dependence_days: int
) -> tuple[dict[str, Any], list[tuple[int, float]], float]:
    returns = returns_from_equity(equity, starting_equity)
    values = [value for _, value in returns]
    equities = [item.equity for item in equity]
    years = len(values) / ANNUALIZATION_DAYS
    net = equities[-1] / starting_equity - 1
    cagr = (equities[-1] / starting_equity) ** (1 / years) - 1 if years > 0 else None
    mean, gamma0, long_run = _long_run_variance(values, dependence_days)
    sample_deviation = statistics.stdev(values) if len(values) > 1 else 0.0
    raw_sharpe = mean / sample_deviation * math.sqrt(ANNUALIZATION_DAYS) if sample_deviation else None
    adjusted_sharpe = mean / math.sqrt(long_run) * math.sqrt(ANNUALIZATION_DAYS) if long_run > 0 else None
    effective_n = min(float(len(values)), len(values) * gamma0 / long_run) if long_run > 0 and gamma0 > 0 else float(len(values))
    downside = math.sqrt(statistics.fmean(min(value, 0.0) ** 2 for value in values)) if values else 0.0
    drawdown = _drawdown_statistics([starting_equity, *equities])
    maximum_drawdown = float(drawdown["maximum_drawdown_fraction"])
    losses = [-value for value in values]
    tail: dict[str, Any] = {}
    for confidence in (0.95, 0.975):
        var = _quantile(losses, confidence)
        exceedances = [loss for loss in losses if loss >= var]
        suffix = "95" if confidence == 0.95 else "97_5"
        tail[f"historical_var_{suffix}"] = var
        tail[f"historical_expected_shortfall_{suffix}"] = statistics.fmean(exceedances)
        tail[f"tail_observations_{suffix}"] = len(exceedances)
    monthly = _calendar_returns(returns, "%Y-%m")
    annual = _calendar_returns(returns, "%Y")
    positive_months = [value for value in monthly.values() if value > 0]
    total_positive = sum(positive_months)
    return {
        "annual_returns": annual,
        "annualized_volatility": sample_deviation * math.sqrt(ANNUALIZATION_DAYS),
        "autocorrelation_adjusted_sharpe": adjusted_sharpe,
        "cagr": cagr,
        "calmar": cagr / maximum_drawdown if cagr is not None and maximum_drawdown > 0 else None,
        "conventional_sharpe": raw_sharpe,
        "drawdown": drawdown,
        "effective_daily_observations": effective_n,
        "monthly_returns": monthly,
        "net_return": net,
        "sortino": mean / downside * math.sqrt(ANNUALIZATION_DAYS) if downside > 0 else None,
        "tail": tail,
        "top_three_months_positive_return_fraction": sum(sorted(positive_months, reverse=True)[:3]) / total_positive if total_positive > 0 else None,
        "worst_day_return": min(values),
        "worst_month_return": min(monthly.values()) if monthly else None,
        "worst_rolling_30_day_return": _rolling_return(values, 30),
        "worst_rolling_90_day_return": _rolling_return(values, 90),
        "worst_rolling_365_day_return": _rolling_return(values, 365),
        "worst_week_return": _rolling_return(values, 7),
    }, returns, effective_n


def _gate(status: str, observed: Any, threshold: Any, reason: str) -> dict[str, Any]:
    return GateResult(status, observed, threshold, reason).as_dict()


def build_backtest_scorecard(
    *,
    experiment_id: str,
    strategy_family: str,
    evaluation_role: str,
    evidence_partition: str,
    source_digest: str,
    result_digest: str,
    original_disposition: str,
    equity: Sequence[EquityObservation],
    starting_equity: float,
    trades: Sequence[TradeObservation],
    controls: Mapping[str, Sequence[EquityObservation]],
    required_control_ids: Sequence[str],
    dependence_days: int,
    severe_cost_net_return: float | None,
    cost_summary: Mapping[str, float | int | None],
    trial_history_complete: bool,
    annual_trial_sharpes: Sequence[float],
    strategy_specific_gates: Mapping[str, bool],
    continuous_exposure: bool = False,
    bootstrap_replications: int = 10_000,
) -> dict[str, Any]:
    """Build a deterministic layered evidence scorecard.

    Existing verdicts are lineage only.  The supplemental disposition can never promote or
    authorize a strategy.
    """

    if evaluation_role not in {"alpha_strategy", "risk_overlay", "control"}:
        raise ResearchMetricError("unsupported evaluation role")
    if not experiment_id or not strategy_family or not evidence_partition:
        raise ResearchMetricError("scorecard identity is incomplete")
    if len(source_digest) != 64 or len(result_digest) != 64:
        raise ResearchMetricError("source and result SHA-256 digests are required")
    if dependence_days <= 0:
        raise ResearchMetricError("dependence horizon must be positive")
    validate_equity_path(equity)
    primary, returns, effective_n = _performance_metrics(equity, starting_equity, dependence_days)
    values = [value for _, value in returns]
    seed = int.from_bytes(hashlib.sha256(f"{SCHEMA_VERSION}:{experiment_id}".encode()).digest()[:8], "big")
    mean_interval, block_count = block_bootstrap_mean_interval(
        values,
        block_days=dependence_days,
        replications=bootstrap_replications,
        seed=seed,
    )
    psr, min_track = _probabilistic_sharpe(values, 0.0, effective_n)
    dsr, deflated_benchmark = (
        _deflated_sharpe(values, annual_trial_sharpes, effective_n)
        if trial_history_complete
        else (None, None)
    )
    statistics_output = {
        "bootstrap_block_count": block_count,
        "bootstrap_block_days": dependence_days,
        "bootstrap_mean_daily_return_ci95": mean_interval,
        "bootstrap_replications": bootstrap_replications,
        "bootstrap_seed": seed,
        "deflated_sharpe_benchmark_annualized": deflated_benchmark,
        "deflated_sharpe_probability": dsr,
        "minimum_track_record_daily_observations_95pct": min_track,
        "probabilistic_sharpe_probability_vs_zero": psr,
        "trial_count": len(annual_trial_sharpes),
        "trial_history_complete": trial_history_complete,
    }
    metric_estimates = {
        "annualized_volatility": MetricEstimate(
            "available", primary["annualized_volatility"], "fraction_per_sqrt_year",
            "sample daily volatility annualized by sqrt(365.2425)", len(values)
        ).as_dict(),
        "autocorrelation_adjusted_sharpe": MetricEstimate(
            "available" if primary["autocorrelation_adjusted_sharpe"] is not None else "insufficient",
            primary["autocorrelation_adjusted_sharpe"], "ratio",
            "Bartlett/Newey-West long-run variance", len(values), effective_n,
            reason=None if primary["autocorrelation_adjusted_sharpe"] is not None else "zero long-run variance",
        ).as_dict(),
        "cagr": MetricEstimate(
            "available" if primary["cagr"] is not None else "insufficient", primary["cagr"],
            "fraction_per_year", "geometric return over UTC daily marked equity", len(values),
            reason=None if primary["cagr"] is not None else "zero evaluation duration",
        ).as_dict(),
        "conventional_sharpe": MetricEstimate(
            "available" if primary["conventional_sharpe"] is not None else "insufficient",
            primary["conventional_sharpe"], "ratio", "sample daily Sharpe annualized by sqrt(365.2425)",
            len(values), reason=None if primary["conventional_sharpe"] is not None else "zero daily volatility",
        ).as_dict(),
        "historical_expected_shortfall_95": MetricEstimate(
            "available", primary["tail"]["historical_expected_shortfall_95"], "daily_loss_fraction",
            "mean loss at or beyond empirical 95% VaR", len(values),
        ).as_dict(),
        "historical_expected_shortfall_97_5": MetricEstimate(
            "available", primary["tail"]["historical_expected_shortfall_97_5"], "daily_loss_fraction",
            "mean loss at or beyond empirical 97.5% VaR", len(values),
        ).as_dict(),
        "maximum_drawdown": MetricEstimate(
            "available", primary["drawdown"]["maximum_drawdown_fraction"], "fraction",
            "UTC daily mark-to-market peak-to-trough", len(values),
        ).as_dict(),
        "mean_daily_return": MetricEstimate(
            "available", statistics.fmean(values), "daily_fraction", "arithmetic UTC daily return",
            len(values), effective_n, mean_interval,
        ).as_dict(),
        "net_return": MetricEstimate(
            "available", primary["net_return"], "fraction", "ending equity divided by starting equity minus one",
            len(values),
        ).as_dict(),
    }

    control_output: dict[str, Any] = {}
    paired_lower_bounds: dict[str, float | None] = {}
    strategy_days = [timestamp for timestamp, _ in returns]
    for identifier, path in sorted(controls.items()):
        control_metrics, control_returns, _ = _performance_metrics(path, starting_equity, dependence_days)
        control_days = [timestamp for timestamp, _ in control_returns]
        if strategy_days != control_days:
            raise ResearchMetricError(f"control timeline differs: {identifier}")
        control_values = [value for _, value in control_returns]
        difference = [left - right for left, right in zip(values, control_values, strict=True)]
        interval, control_blocks = block_bootstrap_mean_interval(
            difference,
            block_days=dependence_days,
            replications=bootstrap_replications,
            seed=seed ^ int.from_bytes(hashlib.sha256(identifier.encode()).digest()[:8], "big"),
        )
        alpha, beta = _alpha_beta(values, control_values)
        paired_lower_bounds[identifier] = None if interval is None else interval[0]
        control_output[identifier] = {
            "alpha_daily": alpha,
            "beta": beta,
            "block_count": control_blocks,
            "paired_mean_daily_excess_ci95": interval,
            "paired_mean_daily_excess_return": statistics.fmean(difference),
            "performance": control_metrics,
        }

    universal: dict[str, Any] = {
        "daily_history": _gate(
            "pass" if len(values) >= 730 else "insufficient",
            len(values),
            ">=730",
            "research-grade minimum daily history",
        ),
        "independent_blocks": _gate(
            "pass" if block_count >= 24 else "insufficient",
            block_count,
            ">=24",
            "non-overlapping dependence-horizon blocks",
        ),
        "required_controls": _gate(
            "pass" if set(required_control_ids).issubset(controls) else "fail",
            sorted(controls),
            sorted(required_control_ids),
            "flat, market, matched, and simple controls are contract requirements",
        ),
        "trial_history": _gate(
            "pass" if trial_history_complete else "insufficient",
            trial_history_complete,
            True,
            "deflated performance requires a complete family trial declaration",
        ),
    }
    trade_output = _trade_metrics(trades)
    evidence_count = len(values) // dependence_days if continuous_exposure else int(trade_output.get("independent_trade_cohorts", 0))
    evidence_threshold = 36 if continuous_exposure else 30
    universal["independent_economic_outcomes"] = _gate(
        "pass" if evidence_count >= evidence_threshold else "insufficient",
        evidence_count,
        f">={evidence_threshold}",
        "continuous strategies use monthly-scale blocks; event strategies use non-overlapping trade cohorts",
    )

    role_gates: dict[str, Any] = {}
    if evaluation_role == "alpha_strategy":
        role_gates = {
            "severe_cost_positive": _gate(
                "pass" if severe_cost_net_return is not None and severe_cost_net_return > 0 else "fail",
                severe_cost_net_return,
                ">0",
                "alpha must survive the frozen severe-cost scenario",
            ),
            "probabilistic_sharpe": _gate(
                "pass" if psr is not None and psr >= 0.95 else "insufficient" if psr is None else "fail",
                psr,
                ">=0.95",
                "probability that Sharpe exceeds zero",
            ),
            "deflated_sharpe": _gate(
                "pass" if dsr is not None and dsr >= 0.95 else "insufficient" if dsr is None else "fail",
                dsr,
                ">=0.95",
                "selection-bias-adjusted Sharpe probability",
            ),
            "paired_control_separation": _gate(
                "pass"
                if required_control_ids and all(
                    paired_lower_bounds.get(identifier) is not None
                    and float(paired_lower_bounds[identifier]) > 0
                    for identifier in required_control_ids
                )
                else "insufficient"
                if any(paired_lower_bounds.get(identifier) is None for identifier in required_control_ids)
                else "fail",
                {key: paired_lower_bounds.get(key) for key in required_control_ids},
                "all lower 95% bounds >0",
                "alpha must beat every required matched/simple control after costs",
            ),
        }
    elif evaluation_role == "risk_overlay":
        role_gates = {
            "not_alpha": _gate("pass", True, True, "risk overlay is never counted as an independent alpha arm")
        }
    else:
        role_gates = {
            "descriptive_only": _gate("pass", True, True, "controls cannot become accepted strategy arms")
        }

    frozen_gates = {
        key: _gate("pass" if value else "fail", bool(value), True, "frozen strategy-specific gate")
        for key, value in sorted(strategy_specific_gates.items())
    }
    all_gates = [*universal.values(), *role_gates.values(), *frozen_gates.values()]
    supplemental_disposition = (
        "supplemental_control_only"
        if evaluation_role == "control"
        else "supplemental_evidence_sufficient_not_promotion"
        if all(item["status"] == "pass" for item in all_gates)
        else "supplemental_evidence_insufficient"
        if any(item["status"] == "insufficient" for item in all_gates)
        else "supplemental_gates_failed"
    )

    gross_profit = cost_summary.get("gross_profit_quote")
    turnover = cost_summary.get("turnover_quote")
    break_even = (
        float(gross_profit) / float(turnover) * 10_000
        if isinstance(gross_profit, (int, float))
        and isinstance(turnover, (int, float))
        and turnover > 0
        else None
    )
    payload = _clean(
        {
            "actionable_arm_id": "no_trade",
            "accepted_strategy_arms": [],
            "controls": control_output,
            "costs": {**dict(cost_summary), "break_even_cost_bps_on_turnover": break_even},
            "evidence_partition": evidence_partition,
            "evaluation_role": evaluation_role,
            "experiment_id": experiment_id,
            "gates": {
                "role": role_gates,
                "strategy_specific_preserved": frozen_gates,
                "universal": universal,
            },
            "lineage": {
                "original_disposition": original_disposition,
                "result_digest": result_digest,
                "source_digest": source_digest,
            },
            "metric_estimates": metric_estimates,
            "performance": primary,
            "promotion_evidence": False,
            "schema_version": SCHEMA_VERSION,
            "statistics": statistics_output,
            "strategy_family": strategy_family,
            "supplemental_disposition": supplemental_disposition,
            "trades": trade_output,
        }
    )
    return {**payload, "scorecard_digest": sha256_digest(payload)}


def validate_trial_registry(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    seen: set[str] = set()
    families: dict[str, dict[str, Any]] = {}
    count = 0
    for expected_sequence, raw in enumerate(rows, start=1):
        row = dict(raw)
        count += 1
        if row.get("sequence") != expected_sequence:
            raise ResearchMetricError("trial registry sequences must be contiguous and one-based")
        experiment_id = row.get("experiment_id")
        family = row.get("strategy_family")
        if not isinstance(experiment_id, str) or not isinstance(family, str) or experiment_id in seen:
            raise ResearchMetricError("trial registry has an invalid or duplicate experiment")
        seen.add(experiment_id)
        if row.get("outcome_inspected") not in {True, False}:
            raise ResearchMetricError("trial outcome-inspection state must be explicit")
        if row.get("family_history_complete") not in {True, False}:
            raise ResearchMetricError("trial family completeness must be explicit")
        families.setdefault(family, {"complete": True, "trials": 0})
        families[family]["complete"] = families[family]["complete"] and row["family_history_complete"]
        families[family]["trials"] += 1
    if not count:
        raise ResearchMetricError("trial registry is empty")
    return {"families": dict(sorted(families.items())), "trials": count}
