"""Causal two-state Student-t HMM research utilities for BTC risk evaluation only."""

from __future__ import annotations

import bisect
import math
import random
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from trading_platform.research_ledger import DAY_MS, FIVE_MINUTES_MS, iter_jsonl_gzip
from trading_platform.research_routing import RegimeFeatureObservation, RegimeState, canonical_digest
from trading_platform.research_volatility import CandlePoint, Opportunity, iso_ms, parse_utc_ms


UTC = timezone.utc
FEATURE_IDS = (
    "downside_semivariance_share_20",
    "high_low_range_ratio_10_60",
    "normalized_jump_magnitude_1_60",
    "realized_volatility_ratio_10_60",
)


class ResearchHMMError(ValueError):
    """Raised when an S3 input, fit, or causal evaluation is invalid."""


@dataclass(frozen=True, slots=True)
class DailyOHLC:
    open_ms: int
    available_ms: int
    high: float
    low: float
    close: float
    archive_digest: str


@dataclass(frozen=True, slots=True)
class FeatureRow:
    observed_ms: int
    available_ms: int
    values: tuple[float, ...]
    feature_digest: str
    source_digest: str

    def as_dict(self) -> dict[str, Any]:
        observation = RegimeFeatureObservation(
            instrument="BTC/USDT",
            interval="1d",
            segment="binance-direct-daily-continuous-2017-2025-v1",
            observed_at=datetime.fromtimestamp(self.observed_ms / 1000, tz=UTC),
            available_at=datetime.fromtimestamp(self.available_ms / 1000, tz=UTC),
            feature_values=dict(zip(FEATURE_IDS, self.values, strict=True)),
            source_digest=self.source_digest,
        )
        if observation.feature_digest != self.feature_digest:
            raise ResearchHMMError("feature digest changed during serialization")
        return observation.as_dict()


@dataclass(frozen=True, slots=True)
class RobustScaler:
    medians: tuple[float, ...]
    dispersions: tuple[float, ...]
    clip: float

    @classmethod
    def fit(cls, values: Sequence[tuple[float, ...]], *, floor: float, clip: float) -> "RobustScaler":
        if not values or floor <= 0 or clip <= 0:
            raise ResearchHMMError("invalid robust-scaler input")
        dimensions = len(values[0])
        if dimensions != len(FEATURE_IDS) or any(len(row) != dimensions for row in values):
            raise ResearchHMMError("feature dimensionality changed")
        medians = tuple(statistics.median(row[index] for row in values) for index in range(dimensions))
        dispersions = tuple(
            max(
                floor,
                1.4826
                * statistics.median(abs(row[index] - medians[index]) for row in values),
            )
            for index in range(dimensions)
        )
        return cls(medians=medians, dispersions=dispersions, clip=clip)

    def transform(self, value: tuple[float, ...]) -> tuple[float, ...]:
        if len(value) != len(self.medians):
            raise ResearchHMMError("scaler dimensionality mismatch")
        output = tuple(
            max(-self.clip, min(self.clip, (item - center) / scale))
            for item, center, scale in zip(value, self.medians, self.dispersions, strict=True)
        )
        if any(not math.isfinite(item) for item in output):
            raise ResearchHMMError("non-finite scaled feature")
        return output

    def as_dict(self) -> dict[str, Any]:
        return {
            "clip": self.clip,
            "dispersions": dict(zip(FEATURE_IDS, self.dispersions, strict=True)),
            "medians": dict(zip(FEATURE_IDS, self.medians, strict=True)),
        }


@dataclass(frozen=True, slots=True)
class HMMFit:
    initial: tuple[float, float]
    transition: tuple[tuple[float, float], tuple[float, float]]
    locations: tuple[tuple[float, ...], tuple[float, ...]]
    variances: tuple[tuple[float, ...], tuple[float, ...]]
    log_likelihood: float
    iterations: int
    converged: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "converged": self.converged,
            "initial": list(self.initial),
            "iterations": self.iterations,
            "locations": [dict(zip(FEATURE_IDS, row, strict=True)) for row in self.locations],
            "log_likelihood": self.log_likelihood,
            "transition": [list(row) for row in self.transition],
            "variances": [dict(zip(FEATURE_IDS, row, strict=True)) for row in self.variances],
        }


@dataclass(frozen=True, slots=True)
class RefitSnapshot:
    cutoff_ms: int
    training_observations: int
    scaler: RobustScaler
    fit: HMMFit
    training_digest: str

    @property
    def digest(self) -> str:
        return canonical_digest(self.as_dict())

    def as_dict(self) -> dict[str, Any]:
        return {
            "cutoff_at": iso_ms(self.cutoff_ms),
            "fit": self.fit.as_dict(),
            "scaler": self.scaler.as_dict(),
            "training_digest": self.training_digest,
            "training_observations": self.training_observations,
        }


def _finite_positive(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ResearchHMMError(f"invalid {label}") from exc
    if not math.isfinite(number) or number <= 0:
        raise ResearchHMMError(f"{label} must be finite and positive")
    return number


def load_daily_ohlc(path: Path, expected_rows: int) -> list[DailyOHLC]:
    output: list[DailyOHLC] = []
    prior_open: int | None = None
    for raw in iter_jsonl_gzip(path.resolve(strict=True)):
        open_ms = parse_utc_ms(raw.get("open_at"))
        available_ms = parse_utc_ms(raw.get("available_at"))
        high = _finite_positive(raw.get("high"), "daily high")
        low = _finite_positive(raw.get("low"), "daily low")
        close = _finite_positive(raw.get("close"), "daily close")
        digest = str(raw.get("source_archive_sha256", ""))
        if open_ms % DAY_MS or available_ms != open_ms + DAY_MS:
            raise ResearchHMMError("daily bar has invalid UTC availability")
        if prior_open is not None and open_ms != prior_open + DAY_MS:
            raise ResearchHMMError("daily source contains a gap")
        if high < max(low, close) or len(digest) != 64:
            raise ResearchHMMError("invalid daily high/low or archive digest")
        output.append(DailyOHLC(open_ms, available_ms, high, low, close, digest))
        prior_open = open_ms
    if len(output) != expected_rows:
        raise ResearchHMMError(f"daily row count mismatch: {len(output)} != {expected_rows}")
    return output


def build_feature_rows(rows: Sequence[DailyOHLC], dataset_digest: str) -> list[FeatureRow]:
    returns: list[float] = []
    ranges: list[float] = []
    output: list[FeatureRow] = []
    for index, row in enumerate(rows):
        ranges.append(math.log(row.high / row.low) ** 2)
        if index:
            returns.append(math.log(row.close / rows[index - 1].close))
        if len(returns) < 60:
            continue
        last60 = returns[-60:]
        last20 = returns[-20:]
        short_variance = statistics.fmean(item * item for item in returns[-10:])
        long_variance = statistics.fmean(item * item for item in last60)
        short_range = statistics.fmean(ranges[-10:])
        long_range = statistics.fmean(ranges[-60:])
        total20 = sum(item * item for item in last20)
        if min(long_variance, long_range, total20) <= 0:
            continue
        values_by_id = {
            "downside_semivariance_share_20": sum(
                item * item for item in last20 if item < 0
            )
            / total20,
            "high_low_range_ratio_10_60": math.sqrt(short_range / long_range),
            "normalized_jump_magnitude_1_60": abs(returns[-1]) / math.sqrt(long_variance),
            "realized_volatility_ratio_10_60": math.sqrt(short_variance / long_variance),
        }
        source_digest = canonical_digest(
            {
                "dataset_sha256": dataset_digest,
                "latest_archive_sha256": row.archive_digest,
                "window_first_available_at": iso_ms(rows[index - 60].available_ms),
                "window_last_available_at": iso_ms(row.available_ms),
            }
        )
        observation = RegimeFeatureObservation(
            instrument="BTC/USDT",
            interval="1d",
            segment="binance-direct-daily-continuous-2017-2025-v1",
            observed_at=datetime.fromtimestamp(row.available_ms / 1000, tz=UTC),
            available_at=datetime.fromtimestamp(row.available_ms / 1000, tz=UTC),
            feature_values=values_by_id,
            source_digest=source_digest,
        )
        output.append(
            FeatureRow(
                observed_ms=row.available_ms,
                available_ms=row.available_ms,
                values=tuple(values_by_id[name] for name in FEATURE_IDS),
                feature_digest=observation.feature_digest,
                source_digest=source_digest,
            )
        )
    return output


def _logsumexp(values: Sequence[float]) -> float:
    maximum = max(values)
    if not math.isfinite(maximum):
        return maximum
    return maximum + math.log(sum(math.exp(value - maximum) for value in values))


def _emission_log(value: tuple[float, ...], location: tuple[float, ...], variance: tuple[float, ...], df: float) -> float:
    total = 0.0
    constant = math.lgamma((df + 1) / 2) - math.lgamma(df / 2)
    for item, center, scale2 in zip(value, location, variance, strict=True):
        total += constant - 0.5 * math.log(df * math.pi * scale2)
        total -= (df + 1) / 2 * math.log1p((item - center) ** 2 / (df * scale2))
    return total


def _forward_backward(values: Sequence[tuple[float, ...]], fit: HMMFit, df: float) -> tuple[list[tuple[float, float]], list[list[list[float]]], float]:
    emissions = [
        tuple(_emission_log(row, fit.locations[state], fit.variances[state], df) for state in range(2))
        for row in values
    ]
    alpha: list[tuple[float, float]] = [
        tuple(math.log(fit.initial[state]) + emissions[0][state] for state in range(2))  # type: ignore[arg-type]
    ]
    for index in range(1, len(values)):
        alpha.append(
            tuple(
                emissions[index][state]
                + _logsumexp(
                    [
                        alpha[index - 1][prior] + math.log(fit.transition[prior][state])
                        for prior in range(2)
                    ]
                )
                for state in range(2)
            )  # type: ignore[arg-type]
        )
    log_likelihood = _logsumexp(alpha[-1])
    beta: list[tuple[float, float]] = [(0.0, 0.0) for _ in values]
    for index in range(len(values) - 2, -1, -1):
        beta[index] = tuple(
            _logsumexp(
                [
                    math.log(fit.transition[state][nxt])
                    + emissions[index + 1][nxt]
                    + beta[index + 1][nxt]
                    for nxt in range(2)
                ]
            )
            for state in range(2)
        )  # type: ignore[assignment]
    gamma = [
        tuple(math.exp(alpha[index][state] + beta[index][state] - log_likelihood) for state in range(2))
        for index in range(len(values))
    ]
    xi = [[[0.0, 0.0], [0.0, 0.0]] for _ in range(max(0, len(values) - 1))]
    for index in range(len(values) - 1):
        for state in range(2):
            for nxt in range(2):
                xi[index][state][nxt] = math.exp(
                    alpha[index][state]
                    + math.log(fit.transition[state][nxt])
                    + emissions[index + 1][nxt]
                    + beta[index + 1][nxt]
                    - log_likelihood
                )
    return gamma, xi, log_likelihood


def _initial_fit(values: Sequence[tuple[float, ...]]) -> HMMFit:
    scores = [statistics.fmean(row) for row in values]
    threshold = statistics.median(scores)
    groups = [[], []]
    for row, score in zip(values, scores, strict=True):
        groups[0 if score <= threshold else 1].append(row)
    if min(map(len, groups)) < 2:
        raise ResearchHMMError("deterministic HMM initialization produced an empty state")
    locations = tuple(
        tuple(statistics.fmean(row[index] for row in group) for index in range(len(FEATURE_IDS)))
        for group in groups
    )
    variances = tuple(
        tuple(
            max(0.0001, statistics.fmean((row[index] - locations[state][index]) ** 2 for row in group))
            for index in range(len(FEATURE_IDS))
        )
        for state, group in enumerate(groups)
    )
    return HMMFit((0.5, 0.5), ((0.97, 0.03), (0.03, 0.97)), locations, variances, -math.inf, 0, False)


def _canonicalize(fit: HMMFit) -> HMMFit:
    keys = [
        (statistics.fmean(fit.locations[state]), sum(fit.variances[state]), state)
        for state in range(2)
    ]
    order = sorted(range(2), key=lambda state: keys[state])
    if order == [0, 1]:
        return fit
    return HMMFit(
        initial=(fit.initial[1], fit.initial[0]),
        transition=((fit.transition[1][1], fit.transition[1][0]), (fit.transition[0][1], fit.transition[0][0])),
        locations=(fit.locations[1], fit.locations[0]),
        variances=(fit.variances[1], fit.variances[0]),
        log_likelihood=fit.log_likelihood,
        iterations=fit.iterations,
        converged=fit.converged,
    )


def fit_student_t_hmm(
    values: Sequence[tuple[float, ...]],
    *,
    df: float = 5,
    max_iterations: int = 100,
    tolerance: float = 1e-6,
    self_pseudocount: float = 20,
    switch_pseudocount: float = 1,
    minimum_self_transition: float = 0.9,
    variance_floor: float = 0.0001,
    variance_ceiling: float = 100,
) -> HMMFit:
    if len(values) < 2:
        raise ResearchHMMError("HMM fit requires at least two observations")
    fit = _initial_fit(values)
    prior_likelihood: float | None = None
    for iteration in range(1, max_iterations + 1):
        gamma, xi, likelihood = _forward_backward(values, fit, df)
        locations: list[tuple[float, ...]] = []
        variances: list[tuple[float, ...]] = []
        for state in range(2):
            state_locations: list[float] = []
            state_variances: list[float] = []
            gamma_sum = sum(row[state] for row in gamma)
            if gamma_sum <= 0:
                raise ResearchHMMError("HMM state has zero posterior mass")
            for dimension in range(len(FEATURE_IDS)):
                weights = [
                    row[state]
                    * (df + 1)
                    / (
                        df
                        + (values[index][dimension] - fit.locations[state][dimension]) ** 2
                        / fit.variances[state][dimension]
                    )
                    for index, row in enumerate(gamma)
                ]
                denominator = sum(weights)
                center = sum(weights[index] * values[index][dimension] for index in range(len(values))) / denominator
                variance = sum(
                    gamma[index][state]
                    * (df + 1)
                    / (
                        df
                        + (values[index][dimension] - fit.locations[state][dimension]) ** 2
                        / fit.variances[state][dimension]
                    )
                    * (values[index][dimension] - center) ** 2
                    for index in range(len(values))
                ) / gamma_sum
                state_locations.append(center)
                state_variances.append(max(variance_floor, min(variance_ceiling, variance)))
            locations.append(tuple(state_locations))
            variances.append(tuple(state_variances))
        transition_rows: list[tuple[float, float]] = []
        for state in range(2):
            counts = [
                sum(item[state][nxt] for item in xi)
                + (self_pseudocount if state == nxt else switch_pseudocount)
                for nxt in range(2)
            ]
            row = [item / sum(counts) for item in counts]
            if row[state] < minimum_self_transition:
                row[state] = minimum_self_transition
                row[1 - state] = 1 - minimum_self_transition
            transition_rows.append((row[0], row[1]))
        initial_total = gamma[0][0] + gamma[0][1] + 2
        candidate = HMMFit(
            initial=((gamma[0][0] + 1) / initial_total, (gamma[0][1] + 1) / initial_total),
            transition=(transition_rows[0], transition_rows[1]),
            locations=(locations[0], locations[1]),
            variances=(variances[0], variances[1]),
            log_likelihood=likelihood,
            iterations=iteration,
            converged=False,
        )
        if prior_likelihood is not None and iteration >= 2 and abs(likelihood - prior_likelihood) / len(values) <= tolerance:
            return _canonicalize(
                HMMFit(
                    candidate.initial,
                    candidate.transition,
                    candidate.locations,
                    candidate.variances,
                    likelihood,
                    iteration,
                    True,
                )
            )
        prior_likelihood = likelihood
        fit = candidate
    return _canonicalize(fit)


def filter_step(prior: tuple[float, float], value: tuple[float, ...], fit: HMMFit, df: float) -> tuple[float, float]:
    predicted = tuple(sum(prior[source] * fit.transition[source][state] for source in range(2)) for state in range(2))
    logs = tuple(math.log(predicted[state]) + _emission_log(value, fit.locations[state], fit.variances[state], df) for state in range(2))
    normalizer = _logsumexp(logs)
    result = tuple(math.exp(item - normalizer) for item in logs)
    total = sum(result)
    normalized = (result[0] / total, result[1] / total)
    if any(not math.isfinite(item) or not 0 <= item <= 1 for item in normalized):
        raise ResearchHMMError("invalid filtered state probability")
    return normalized


def walk_forward_states(
    features: Sequence[FeatureRow],
    *,
    evaluation_start_ms: int,
    evaluation_end_ms: int,
    contract: Mapping[str, Any],
) -> tuple[list[RegimeState], list[RefitSnapshot]]:
    fitting = contract["fitting"]
    evaluation = [item for item in features if evaluation_start_ms <= item.available_ms < evaluation_end_ms]
    grouped: dict[str, list[FeatureRow]] = defaultdict(list)
    for item in evaluation:
        grouped[iso_ms(item.available_ms)[:7]].append(item)
    states: list[RegimeState] = []
    snapshots: list[RefitSnapshot] = []
    prior_hard: str | None = None
    state_age = 0
    for month in sorted(grouped):
        cutoff_ms = parse_utc_ms(f"{month}-01T00:00:00Z")
        training = [item for item in features if item.available_ms < cutoff_ms]
        unknown_reason: str | None = None
        snapshot: RefitSnapshot | None = None
        if len(training) < fitting["minimum_training_observations"]:
            unknown_reason = "insufficient_training_history"
        else:
            scaler = RobustScaler.fit(
                [item.values for item in training],
                floor=fitting["scaler"]["dispersion_floor"],
                clip=fitting["scaler"]["clip_absolute_scaled_value"],
            )
            scaled_training = [scaler.transform(item.values) for item in training]
            fit = fit_student_t_hmm(
                scaled_training,
                df=fitting["degrees_of_freedom"],
                max_iterations=fitting["maximum_em_iterations"],
                minimum_self_transition=fitting["minimum_self_transition_probability"],
                self_pseudocount=fitting["transition_pseudocounts"]["self"],
                switch_pseudocount=fitting["transition_pseudocounts"]["switch"],
                variance_floor=fitting["variance_floor"],
                variance_ceiling=fitting["variance_ceiling"],
            )
            snapshot = RefitSnapshot(
                cutoff_ms=cutoff_ms,
                training_observations=len(training),
                scaler=scaler,
                fit=fit,
                training_digest=canonical_digest([item.feature_digest for item in training]),
            )
            snapshots.append(snapshot)
            if not fit.converged:
                unknown_reason = "nonconverged_refit"
        if snapshot is not None and unknown_reason is None:
            posterior = snapshot.fit.initial
            for item in training:
                posterior = filter_step(
                    posterior,
                    snapshot.scaler.transform(item.values),
                    snapshot.fit,
                    fitting["degrees_of_freedom"],
                )
        else:
            posterior = (0.5, 0.5)
        for item in grouped[month]:
            if snapshot is not None and unknown_reason is None:
                prior = posterior
                posterior = filter_step(
                    posterior,
                    snapshot.scaler.transform(item.values),
                    snapshot.fit,
                    fitting["degrees_of_freedom"],
                )
                hard = "stress_risk" if posterior[1] >= 0.5 else "ordinary_risk"
                state_age = state_age + 1 if hard == prior_hard else 1
                reason = "hard_state_unchanged" if hard == prior_hard else (
                    "initial_known_state" if prior_hard is None else "hard_state_changed"
                )
                transition_probability = 1 - sum(
                    prior[state] * snapshot.fit.transition[state][state]
                    for state in range(2)
                )
                prior_hard = hard
                probabilities = {"ordinary_risk": posterior[0], "stress_risk": posterior[1]}
            else:
                probabilities = {"ordinary_risk": 0.5, "stress_risk": 0.5}
                state_age = 0
                transition_probability = 0.0
                reason = "unknown_refit"
                prior_hard = None
            entropy = -sum(value * math.log(value) for value in probabilities.values() if value > 0)
            state = RegimeState(
                model_id="btc-student-t-hmm-risk",
                model_version=str(contract["experiment_id"]),
                instrument="BTC/USDT",
                interval="1d",
                segment="binance-direct-daily-continuous-2017-2025-v1",
                observed_at=datetime.fromtimestamp(item.observed_ms / 1000, tz=UTC),
                available_at=datetime.fromtimestamp(item.available_ms / 1000, tz=UTC),
                fit_cutoff=datetime.fromtimestamp(cutoff_ms / 1000, tz=UTC),
                probabilities=probabilities,
                confidence=max(probabilities.values()),
                entropy=entropy,
                state_age=state_age,
                transition_probability=transition_probability,
                transition_reason=reason,
                cutoffs={"hard_stress_probability": 0.5, "minimum_known_multiplier": 0.5},
                unknown_reason=unknown_reason,
            )
            states.append(state)
    return states, snapshots


class StateLookup:
    def __init__(self, states: Sequence[RegimeState], max_age_ms: int):
        self.states = tuple(states)
        self.times = tuple(int(item.available_at.timestamp() * 1000) for item in states)
        self.max_age_ms = max_age_ms

    def at(self, decision_ms: int) -> tuple[RegimeState | None, str | None]:
        index = bisect.bisect_right(self.times, decision_ms) - 1
        if index < 0:
            return None, "state_not_yet_available"
        state = self.states[index]
        age = decision_ms - self.times[index]
        if age < 0:
            raise ResearchHMMError("future state selected")
        if age >= self.max_age_ms:
            return None, "state_stale"
        if not state.is_usable:
            return state, state.unknown_reason or state.stale_reason
        return state, None


def hmm_allocations(
    opportunities: Sequence[Opportunity],
    ewma_allocations: Sequence[float],
    states: Sequence[RegimeState],
    *,
    max_age_ms: int,
) -> list[dict[str, Any]]:
    if len(opportunities) != len(ewma_allocations):
        raise ResearchHMMError("opportunity and EWMA allocation counts differ")
    lookup = StateLookup(states, max_age_ms)
    output: list[dict[str, Any]] = []
    for opportunity, ewma in zip(opportunities, ewma_allocations, strict=True):
        state, reason = lookup.at(opportunity.signal_ms)
        stress = None if state is None else float(state.probabilities["stress_risk"])
        multiplier = 0.0 if reason is not None or stress is None else 1 - 0.5 * stress
        allocation = ewma * multiplier
        if not 0 <= allocation <= ewma <= 0.1 or (reason is None and not 0.5 <= multiplier <= 1):
            raise ResearchHMMError("HMM overlay violates downward-only mapping")
        output.append(
            {
                "allocation_fraction": allocation,
                "ewma_allocation_fraction": ewma,
                "multiplier": multiplier,
                "opportunity_id": opportunity.opportunity_id,
                "signal_at": iso_ms(opportunity.signal_ms),
                "state_digest": None if state is None else state.digest,
                "state_observed_at": None if state is None else state.as_dict()["observed_at"],
                "stress_risk_probability": stress,
                "unknown_reason": reason,
            }
        )
    return output


def state_path_statistics(states: Sequence[RegimeState]) -> dict[str, Any]:
    known = [item for item in states if item.is_usable]
    hard = ["stress_risk" if item.probabilities["stress_risk"] >= 0.5 else "ordinary_risk" for item in known]
    counts = {name: hard.count(name) for name in ("ordinary_risk", "stress_risk")}
    runs: list[tuple[str, int]] = []
    for name in hard:
        if runs and runs[-1][0] == name:
            runs[-1] = (name, runs[-1][1] + 1)
        else:
            runs.append((name, 1))
    dwell = {
        name: [length for state, length in runs if state == name]
        for name in ("ordinary_risk", "stress_risk")
    }
    return {
        "known_observations": len(known),
        "median_dwell": {name: statistics.median(values) if values else 0 for name, values in dwell.items()},
        "occupancy": {name: counts[name] / len(known) if known else 0.0 for name in counts},
        "one_day_run_fraction": sum(length == 1 for _, length in runs) / len(runs) if runs else 1.0,
        "run_count": len(runs),
        "transitions": max(0, len(runs) - 1),
    }


def forward_labels(states: Sequence[RegimeState], candles: Sequence[CandlePoint], *, horizon_days: int, evaluation_end_ms: int) -> list[dict[str, Any]]:
    open_index = {item.open_ms: index for index, item in enumerate(candles)}
    count = horizon_days * 288
    output: list[dict[str, Any]] = []
    for state in states:
        if not state.is_usable:
            continue
        start_ms = int(state.available_at.timestamp() * 1000)
        if start_ms + horizon_days * DAY_MS > evaluation_end_ms:
            continue
        start = open_index.get(start_ms, -1)
        if start <= 0 or start + count > len(candles):
            continue
        prior = candles[start - 1]
        segment = candles[start].segment
        if prior.segment != segment or prior.open_ms + FIVE_MINUTES_MS != start_ms:
            continue
        values: list[float] = []
        previous = prior
        valid = True
        for offset in range(count):
            candle = candles[start + offset]
            if candle.segment != segment or candle.open_ms != start_ms + offset * FIVE_MINUTES_MS:
                valid = False
                break
            values.append(math.log(candle.close / previous.close))
            previous = candle
        if not valid:
            continue
        hard = "stress_risk" if state.probabilities["stress_risk"] >= 0.5 else "ordinary_risk"
        output.append(
            {
                "downside_loss": max(0.0, -sum(values)),
                "label_month": iso_ms(start_ms)[:7],
                "observed_at": iso_ms(start_ms),
                "realized_variance": sum(item * item for item in values),
                "state": hard,
                "state_digest": state.digest,
            }
        )
    return output


def _quantile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)


def month_block_state_difference(
    labels: Sequence[Mapping[str, Any]],
    metric: str,
    *,
    seed: int,
    replications: int,
) -> dict[str, Any]:
    months: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in labels:
        months[str(row["label_month"])].append(row)
    ordered_months = sorted(months)

    def difference(sample: Sequence[Mapping[str, Any]]) -> float | None:
        values = {
            state: [float(row[metric]) for row in sample if row["state"] == state]
            for state in ("ordinary_risk", "stress_risk")
        }
        if not values["ordinary_risk"] or not values["stress_risk"]:
            return None
        return statistics.fmean(values["stress_risk"]) - statistics.fmean(values["ordinary_risk"])

    observed = difference(labels)
    if observed is None:
        raise ResearchHMMError("forward labels do not contain both states")
    generator = random.Random(seed)
    samples: list[float] = []
    for _ in range(replications):
        selected: list[Mapping[str, Any]] = []
        for _ in ordered_months:
            selected.extend(months[generator.choice(ordered_months)])
        value = difference(selected)
        if value is not None:
            samples.append(value)
    return {
        "ci95": [_quantile(samples, 0.025), _quantile(samples, 0.975)] if samples else None,
        "invalid_replications": replications - len(samples),
        "observed_difference": observed,
        "valid_replications": len(samples),
    }
