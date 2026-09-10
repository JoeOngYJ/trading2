"""Causal offline evaluator for the frozen cross-asset A2 session breakout."""

from __future__ import annotations

import hashlib
import json
import math
import random
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

from trading_platform.cross_asset_oanda_hourly import (
    OandaHourlyError,
    _load_canonical,
    _repo_file,
    _utc,
    canonical_json,
    sha256_file,
)


CONTRACT_SCHEMA = "cross-asset-a2-session-breakout-contract-v1"
EXPERIMENT_ID = "cross-asset-a2-session-breakout-continuation-v1"
INSTRUMENTS = (
    "SPX500_USD",
    "NAS100_USD",
    "DE30_EUR",
    "UK100_GBP",
    "XAU_USD",
    "EUR_USD",
    "USD_JPY",
)
PROFILE_BY_INSTRUMENT = {
    "SPX500_USD": "new_york",
    "NAS100_USD": "new_york",
    "DE30_EUR": "london",
    "UK100_GBP": "london",
    "XAU_USD": "new_york",
    "EUR_USD": "new_york",
    "USD_JPY": "new_york",
}
QUOTE_CURRENCY = {
    "SPX500_USD": "USD",
    "NAS100_USD": "USD",
    "DE30_EUR": "EUR",
    "UK100_GBP": "GBP",
    "XAU_USD": "USD",
    "EUR_USD": "USD",
    "USD_JPY": "JPY",
}


@dataclass(frozen=True, slots=True)
class Bar:
    observed_at: datetime
    bid: Mapping[str, Decimal]
    ask: Mapping[str, Decimal]

    def midpoint(self, field: str) -> Decimal:
        return (self.bid[field] + self.ask[field]) / Decimal(2)


@dataclass(frozen=True, slots=True)
class Session:
    instrument_id: str
    local_date: date
    profile_id: str
    bars: Mapping[int, Bar]


@dataclass(frozen=True, slots=True)
class Outcome:
    direction: int
    entry_time: datetime
    exit_time: datetime
    instrument_id: str
    local_date: str
    stop_fraction: float
    unit_return: float
    worst_path_returns: tuple[tuple[datetime, float], ...]
    exit_reason: str


def load_contract(path: Path, repo_root: Path) -> dict[str, Any]:
    contract = _load_canonical(path, "A2 session-breakout contract")
    if (
        contract.get("schema_version"),
        contract.get("experiment_id"),
        contract.get("status"),
    ) != (CONTRACT_SCHEMA, EXPERIMENT_ID, "frozen"):
        raise OandaHourlyError("unexpected or unfrozen A2 contract")
    if tuple(contract.get("instrument_universe", ())) != INSTRUMENTS:
        raise OandaHourlyError("A2 instrument universe changed")
    for key, value in contract.get("prohibitions", {}).items():
        if value is not False:
            raise OandaHourlyError(f"unsafe A2 permission: {key}")
    partitions = contract.get("partitions", {})
    if partitions != {
        "development": {
            "end_exclusive": "2022-01-01T00:00:00Z",
            "start_inclusive": "2010-01-01T00:00:00Z",
        },
        "final_sealed": {
            "end_exclusive": "2026-01-01T00:00:00Z",
            "start_inclusive": "2024-01-01T00:00:00Z",
        },
        "initial_run_may_read_final_sealed_values": False,
        "validation": {
            "end_exclusive": "2024-01-01T00:00:00Z",
            "start_inclusive": "2022-01-01T00:00:00Z",
        },
    }:
        raise OandaHourlyError("A2 partitions changed")
    logic = contract.get("session_logic", {})
    for profile, expected in {
        "london": ([8, 9], 10, 11, 15, "Europe/London"),
        "new_york": ([9, 10], 11, 12, 16, "America/New_York"),
    }.items():
        row = logic.get(profile, {})
        if (
            row.get("opening_range_local_hours"),
            row.get("confirmation_local_hour"),
            row.get("entry_local_hour"),
            row.get("exit_local_hour"),
            row.get("timezone"),
        ) != expected:
            raise OandaHourlyError(f"A2 {profile} session changed")
    if contract.get("costs", {}).get("additional_round_trip_slippage_bps") != [0, 5, 15]:
        raise OandaHourlyError("A2 cost scenarios changed")
    if contract.get("costs", {}).get("primary_round_trip_slippage_bps") != 5:
        raise OandaHourlyError("A2 primary cost changed")
    if contract.get("controls", {}).get("random_direction_seed") != 20260830:
        raise OandaHourlyError("A2 random control seed changed")
    if contract.get("statistics", {}).get("month_block_bootstrap_seed") != 20260831:
        raise OandaHourlyError("A2 bootstrap seed changed")
    for record in (
        contract["mandate"],
        contract["data_bindings"]["a1_hourly_evidence"],
        contract["data_bindings"]["data_contract"],
        contract["data_bindings"]["gbp_conversion_evidence"],
    ):
        bound = _repo_file(repo_root, record["path"], "A2 bound input")
        if sha256_file(bound) != record["sha256"]:
            raise OandaHourlyError("A2 bound input checksum changed")
    return contract


def _validate_artifacts(root: Path, evidence: Mapping[str, Any]) -> dict[str, Path]:
    result = {}
    for record in evidence.get("artifacts", ()):
        path = _repo_file(root, record.get("path"), "A2 evidence artifact")
        if sha256_file(path) != record.get("sha256"):
            raise OandaHourlyError(f"A2 evidence checksum changed: {record.get('path')}")
        result[str(record["path"])] = path
    if not result:
        raise OandaHourlyError("A2 evidence has no artifacts")
    return result


def resolve_inputs(contract: Mapping[str, Any], root: Path) -> tuple[dict[str, Path], dict[str, Path], Path]:
    a1 = _load_canonical(
        _repo_file(root, contract["data_bindings"]["a1_hourly_evidence"]["path"], "A1 evidence"),
        "A1 hourly evidence",
    )
    if a1.get("decision") != "a1_hourly_source_qualification_passed_with_no_trade_masks":
        raise OandaHourlyError("A1 hourly source is not accepted")
    a1_artifacts = _validate_artifacts(root, a1)
    predecessor_record = next(
        (record for record in a1["artifacts"] if record["path"].endswith("a1-oanda-hourly-history-v1/evidence-manifest.json")),
        None,
    )
    if predecessor_record is None:
        raise OandaHourlyError("A1 predecessor evidence is missing")
    predecessor = _load_canonical(_repo_file(root, predecessor_record["path"], "A1 predecessor"), "A1 predecessor")
    predecessor_artifacts = _validate_artifacts(root, predecessor)
    normalized = {}
    masks = {}
    for instrument in INSTRUMENTS:
        normalized_suffix = f"/normalized/{instrument.casefold()}-h1.jsonl"
        mask_suffix = f"/availability/{instrument.casefold()}-availability.jsonl"
        normalized[instrument] = next(
            (path for raw, path in predecessor_artifacts.items() if raw.endswith(normalized_suffix)),
            None,
        )
        masks[instrument] = next(
            (path for raw, path in a1_artifacts.items() if raw.endswith(mask_suffix)), None
        )
        if normalized[instrument] is None or masks[instrument] is None:
            raise OandaHourlyError(f"A2 input lineage incomplete for {instrument}")
    conversion = _load_canonical(
        _repo_file(root, contract["data_bindings"]["gbp_conversion_evidence"]["path"], "conversion evidence"),
        "GBP conversion evidence",
    )
    if conversion.get("qualified_for_gbp_conversion") is not True or conversion.get(
        "eligible_as_strategy_instrument"
    ) is not False:
        raise OandaHourlyError("GBP conversion evidence is not qualified conversion-only data")
    conversion_artifacts = _validate_artifacts(root, conversion)
    conversion_path = next(
        (path for raw, path in conversion_artifacts.items() if raw.endswith("normalized-gbp_usd-h1.jsonl")),
        None,
    )
    if conversion_path is None:
        raise OandaHourlyError("GBP conversion normalized data is missing")
    return normalized, masks, conversion_path


def _bar(raw: Mapping[str, Any]) -> Bar:
    observed = _utc(raw.get("observed_at"), "A2 observed_at")
    available = _utc(raw.get("available_at"), "A2 available_at")
    if available != observed + timedelta(hours=1):
        raise OandaHourlyError("A2 availability must follow the completed bar by one hour")
    sides = {}
    for side in ("bid", "ask"):
        values = raw.get(side)
        if not isinstance(values, Mapping):
            raise OandaHourlyError("A2 bar side is missing")
        sides[side] = {field: Decimal(str(values[field])) for field in "ohlc"}
    return Bar(observed, sides["bid"], sides["ask"])


def load_conversion(path: Path, end_exclusive: datetime) -> dict[datetime, Bar]:
    result = {}
    with path.open(encoding="utf-8") as rows:
        for line in rows:
            raw = json.loads(line)
            observed = _utc(raw.get("observed_at"), "GBP conversion observed_at")
            if observed >= end_exclusive:
                break
            result[observed] = _bar(raw)
    return result


def load_sessions(
    instrument: str,
    normalized_path: Path,
    mask_path: Path,
    profile: Mapping[str, Any],
    end_exclusive: datetime,
) -> list[Session]:
    eligible = set()
    with mask_path.open(encoding="utf-8") as rows:
        for line in rows:
            raw = json.loads(line)
            if raw.get("instrument_id") != instrument:
                raise OandaHourlyError("A2 availability-mask identity changed")
            if raw.get("disposition") == "eligible":
                eligible.add(date.fromisoformat(raw["local_date"]))
            elif raw.get("disposition") != "no_trade":
                raise OandaHourlyError("A2 mask has an unsafe disposition")
    zone = ZoneInfo(profile["timezone"])
    first = min(profile["opening_range_local_hours"])
    last = profile["exit_local_hour"]
    grouped: dict[date, dict[int, Bar]] = defaultdict(dict)
    with normalized_path.open(encoding="utf-8") as rows:
        for line in rows:
            raw = json.loads(line)
            observed = _utc(raw.get("observed_at"), "A2 source observed_at")
            if observed >= end_exclusive:
                break
            local = observed.astimezone(zone)
            if local.date() not in eligible or not first <= local.hour <= last:
                continue
            if local.hour in grouped[local.date()]:
                raise OandaHourlyError("A2 session repeats a local hour")
            grouped[local.date()][local.hour] = _bar(raw)
    required = set(range(first, last + 1))
    return [
        Session(instrument, local_date, PROFILE_BY_INSTRUMENT[instrument], bars)
        for local_date, bars in sorted(grouped.items())
        if set(bars) == required
    ]


def _mid_open(bar: Bar) -> Decimal:
    return bar.midpoint("o")


def quote_per_gbp(instrument: str, at: datetime, market_bar: Bar, conversion: Mapping[datetime, Bar]) -> Decimal:
    currency = QUOTE_CURRENCY[instrument]
    if currency == "GBP":
        return Decimal(1)
    gbp = conversion.get(at)
    if gbp is None:
        raise OandaHourlyError(f"missing GBP conversion at {at.isoformat()}")
    gbp_usd = _mid_open(gbp)
    if currency == "USD":
        return gbp_usd
    if currency == "EUR":
        # DE30 is EUR-quoted; EUR/USD at the same timestamp converts EUR to USD.
        raise OandaHourlyError("EUR conversion requires EUR_USD session lookup")
    if currency == "JPY":
        return gbp_usd * _mid_open(market_bar)
    raise OandaHourlyError(f"unsupported quote currency: {currency}")


def _quote_per_gbp_with_cross(
    instrument: str,
    at: datetime,
    market_bar: Bar,
    conversion: Mapping[datetime, Bar],
    eurusd: Mapping[datetime, Bar],
) -> Decimal:
    if QUOTE_CURRENCY[instrument] != "EUR":
        return quote_per_gbp(instrument, at, market_bar, conversion)
    gbp = conversion.get(at)
    eur = eurusd.get(at)
    if gbp is None or eur is None:
        raise OandaHourlyError(f"missing EUR/GBP cross input at {at.isoformat()}")
    return _mid_open(gbp) / _mid_open(eur)  # EUR per GBP


def session_direction(session: Session, profile: Mapping[str, Any]) -> int:
    opening = [session.bars[hour] for hour in profile["opening_range_local_hours"]]
    high = max(bar.midpoint("h") for bar in opening)
    low = min(bar.midpoint("l") for bar in opening)
    confirmation = session.bars[profile["confirmation_local_hour"]].midpoint("c")
    if confirmation > high:
        return 1
    if confirmation < low:
        return -1
    return 0


def confirmation_sign(session: Session, profile: Mapping[str, Any]) -> int:
    bar = session.bars[profile["confirmation_local_hour"]]
    return 1 if bar.midpoint("c") > bar.midpoint("o") else -1 if bar.midpoint("c") < bar.midpoint("o") else 0


def build_outcome(
    session: Session,
    profile: Mapping[str, Any],
    direction: int,
    round_trip_slippage_bps: int,
    conversion: Mapping[datetime, Bar],
    eurusd: Mapping[datetime, Bar],
    *,
    symmetric_stop_fraction: Decimal | None = None,
) -> Outcome | None:
    if direction not in {-1, 1}:
        return None
    opening = [session.bars[hour] for hour in profile["opening_range_local_hours"]]
    opening_high = max(bar.midpoint("h") for bar in opening)
    opening_low = min(bar.midpoint("l") for bar in opening)
    entry_bar = session.bars[profile["entry_local_hour"]]
    entry_mid = entry_bar.midpoint("o")
    if symmetric_stop_fraction is None:
        stop = opening_low if direction == 1 else opening_high
        if (direction == 1 and stop >= entry_mid) or (direction == -1 and stop <= entry_mid):
            return None
    else:
        stop = entry_mid * (Decimal(1) - symmetric_stop_fraction * direction)
    distance = abs(entry_mid - stop) / entry_mid
    if distance <= 0:
        return None
    half = Decimal(round_trip_slippage_bps) / Decimal(20000)
    if direction == 1:
        entry_price = entry_bar.ask["o"] * (Decimal(1) + half)
    else:
        entry_price = entry_bar.bid["o"] * (Decimal(1) - half)
    entry_time = entry_bar.observed_at
    q_entry = _quote_per_gbp_with_cross(
        session.instrument_id, entry_time, entry_bar, conversion, eurusd
    )
    units_per_gbp = q_entry / entry_price
    path = []
    final_price = None
    final_time = None
    exit_reason = "session_exit"
    for hour in range(profile["entry_local_hour"], profile["exit_local_hour"]):
        bar = session.bars[hour]
        if direction == 1:
            marked = bar.bid["l"] * (Decimal(1) - half)
            stop_hit = bar.bid["o"] <= stop or bar.bid["l"] <= stop
            stop_fill = min(bar.bid["o"], stop) * (Decimal(1) - half)
        else:
            marked = bar.ask["h"] * (Decimal(1) + half)
            stop_hit = bar.ask["o"] >= stop or bar.ask["h"] >= stop
            stop_fill = max(bar.ask["o"], stop) * (Decimal(1) + half)
        q_mark = _quote_per_gbp_with_cross(session.instrument_id, bar.observed_at, bar, conversion, eurusd)
        marked_return = units_per_gbp * Decimal(direction) * (marked - entry_price) / q_mark
        path.append((bar.observed_at, float(marked_return)))
        if stop_hit:
            final_price = stop_fill
            final_time = bar.observed_at
            exit_reason = "protective_stop"
            break
    if final_price is None:
        exit_bar = session.bars[profile["exit_local_hour"]]
        final_time = exit_bar.observed_at
        final_price = (
            exit_bar.bid["o"] * (Decimal(1) - half)
            if direction == 1
            else exit_bar.ask["o"] * (Decimal(1) + half)
        )
    exit_bar_for_fx = session.bars[
        next(
            hour
            for hour, bar in session.bars.items()
            if bar.observed_at == final_time
        )
    ]
    q_exit = _quote_per_gbp_with_cross(
        session.instrument_id, final_time, exit_bar_for_fx, conversion, eurusd
    )
    unit_return = units_per_gbp * Decimal(direction) * (final_price - entry_price) / q_exit
    path.append((final_time, float(unit_return)))
    return Outcome(
        direction=direction,
        entry_time=entry_time,
        exit_time=final_time,
        instrument_id=session.instrument_id,
        local_date=session.local_date.isoformat(),
        stop_fraction=float(abs(unit_return) if exit_reason == "protective_stop" else distance),
        unit_return=float(unit_return),
        worst_path_returns=tuple(path),
        exit_reason=exit_reason,
    )


def strategy_outcomes(
    sessions: Sequence[Session],
    profiles: Mapping[str, Any],
    cost_bps: int,
    conversion: Mapping[datetime, Bar],
    eurusd: Mapping[datetime, Bar],
) -> list[Outcome]:
    result = []
    for session in sessions:
        profile = profiles[session.profile_id]
        direction = session_direction(session, profile)
        outcome = build_outcome(session, profile, direction, cost_bps, conversion, eurusd)
        if outcome is not None:
            result.append(outcome)
    return result


def all_session_long_outcomes(
    sessions: Sequence[Session],
    profiles: Mapping[str, Any],
    cost_bps: int,
    conversion: Mapping[datetime, Bar],
    eurusd: Mapping[datetime, Bar],
) -> list[Outcome]:
    result = []
    for session in sessions:
        profile = profiles[session.profile_id]
        opening = [session.bars[hour] for hour in profile["opening_range_local_hours"]]
        width = max(bar.midpoint("h") for bar in opening) - min(
            bar.midpoint("l") for bar in opening
        )
        entry_mid = session.bars[profile["entry_local_hour"]].midpoint("o")
        if width <= 0 or entry_mid <= 0:
            continue
        outcome = build_outcome(
            session,
            profile,
            1,
            cost_bps,
            conversion,
            eurusd,
            symmetric_stop_fraction=width / entry_mid,
        )
        if outcome is not None:
            result.append(outcome)
    return result


def matched_control_outcomes(
    strategy: Sequence[Outcome],
    session_index: Mapping[tuple[str, str], Session],
    profiles: Mapping[str, Any],
    cost_bps: int,
    conversion: Mapping[datetime, Bar],
    eurusd: Mapping[datetime, Bar],
    mode: str,
) -> list[Outcome]:
    result = []
    for observed in strategy:
        session = session_index[(observed.instrument_id, observed.local_date)]
        profile = profiles[session.profile_id]
        direction = 1 if mode == "long" else -1 if mode == "short" else confirmation_sign(session, profile)
        symmetric = Decimal(str(max(observed.stop_fraction, 0.000001)))
        outcome = build_outcome(
            session,
            profile,
            direction,
            cost_bps,
            conversion,
            eurusd,
            symmetric_stop_fraction=symmetric,
        )
        if outcome is not None:
            result.append(outcome)
    return result


def simulate_shared_account(outcomes: Sequence[Outcome], contract: Mapping[str, Any]) -> dict[str, Any]:
    accounting = contract["accounting"]
    initial = float(accounting["initial_equity_gbp"])
    equity = initial
    peak = initial
    maximum_drawdown = 0.0
    gross_cap = float(accounting["maximum_gross_exposure_fraction"])
    position_cap = float(accounting["maximum_notional_per_position_fraction"])
    risk_fraction = float(accounting["maximum_planned_risk_per_position_fraction"])
    soft = float(accounting["soft_drawdown_stop_fraction"])
    hard = float(accounting["hard_drawdown_stop_fraction"])
    cohorts: dict[datetime, list[Outcome]] = defaultdict(list)
    for outcome in outcomes:
        cohorts[outcome.entry_time].append(outcome)
    trade_pnls = []
    trade_rows = []
    daily_equity = {}
    disabled = False
    daily_loss_blocked_cohorts = 0
    current_day = None
    day_start_equity = initial
    daily_loss_stop = float(accounting["daily_loss_stop_fraction"])
    for entry_time, candidates in sorted(cohorts.items()):
        if entry_time.date() != current_day:
            current_day = entry_time.date()
            day_start_equity = equity
        if equity <= day_start_equity * (1 - daily_loss_stop):
            daily_loss_blocked_cohorts += 1
            continue
        drawdown = equity / peak - 1
        if disabled or drawdown <= -soft or drawdown <= -hard:
            disabled = True
            continue
        raw_notionals = [
            min(equity * position_cap, equity * risk_fraction / max(item.stop_fraction, 1e-9))
            for item in candidates
        ]
        scale = min(1.0, equity * gross_cap / sum(raw_notionals)) if raw_notionals else 0.0
        notionals = [value * scale for value in raw_notionals]
        path_times = sorted({at for item in candidates for at, _ in item.worst_path_returns})
        for at in path_times:
            unrealized = 0.0
            for item, notional in zip(candidates, notionals):
                points = [value for point_at, value in item.worst_path_returns if point_at <= at]
                if points:
                    unrealized += notional * points[-1]
            marked_equity = equity + unrealized
            peak = max(peak, marked_equity)
            maximum_drawdown = min(maximum_drawdown, marked_equity / peak - 1)
        cohort_pnl = 0.0
        for item, notional in zip(candidates, notionals):
            pnl = notional * item.unit_return
            cohort_pnl += pnl
            trade_pnls.append(pnl)
            trade_rows.append(
                {
                    "direction": item.direction,
                    "entry_time": item.entry_time.isoformat().replace("+00:00", "Z"),
                    "exit_reason": item.exit_reason,
                    "exit_time": item.exit_time.isoformat().replace("+00:00", "Z"),
                    "instrument_id": item.instrument_id,
                    "local_date": item.local_date,
                    "notional_gbp": notional,
                    "pnl_gbp": pnl,
                    "unit_return": item.unit_return,
                }
            )
        equity += cohort_pnl
        peak = max(peak, equity)
        maximum_drawdown = min(maximum_drawdown, equity / peak - 1)
        daily_equity[entry_time.date().isoformat()] = equity
        if equity / peak - 1 <= -soft:
            disabled = True
    days = sorted(daily_equity)
    daily_returns = []
    previous = initial
    for day in days:
        value = daily_equity[day]
        daily_returns.append(value / previous - 1)
        previous = value
    sharpe = (
        statistics.fmean(daily_returns) / statistics.stdev(daily_returns) * math.sqrt(252)
        if len(daily_returns) > 1 and statistics.stdev(daily_returns) > 0
        else None
    )
    positive = sum(value for value in trade_pnls if value > 0)
    negative = -sum(value for value in trade_pnls if value < 0)
    elapsed_days = (
        (max(item.exit_time for item in outcomes) - min(item.entry_time for item in outcomes)).days
        if outcomes
        else 0
    )
    cagr = (equity / initial) ** (365.25 / elapsed_days) - 1 if elapsed_days > 0 and equity > 0 else None
    return {
        "cagr": cagr,
        "daily_loss_blocked_cohorts": daily_loss_blocked_cohorts,
        "disabled_by_drawdown_stop": disabled,
        "final_equity_gbp": equity,
        "filled_trades": len(trade_rows),
        "maximum_drawdown_fraction": -maximum_drawdown,
        "net_return_fraction": equity / initial - 1,
        "profit_factor": positive / negative if negative > 0 else None,
        "sharpe": sharpe,
        "trade_rows": trade_rows,
    }


def quantile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise OandaHourlyError("cannot take a quantile of no values")
    index = (len(ordered) - 1) * probability
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - index) + ordered[upper] * (index - lower)


def month_block_interval(outcomes: Sequence[Outcome], seed: int, replications: int) -> list[float] | None:
    blocks: dict[str, list[float]] = defaultdict(list)
    for item in outcomes:
        blocks[item.entry_time.strftime("%Y-%m")].append(item.unit_return)
    months = list(blocks.values())
    if not months:
        return None
    generator = random.Random(seed)
    estimates = []
    for _ in range(replications):
        sampled = [generator.choice(months) for _ in months]
        estimates.append(statistics.fmean(value for block in sampled for value in block))
    return [quantile(estimates, 0.025), quantile(estimates, 0.975)]


def random_direction_percentile(
    strategy: Sequence[Outcome],
    long_controls: Sequence[Outcome],
    short_controls: Sequence[Outcome],
    seed: int,
    replications: int,
) -> dict[str, Any]:
    long_map = {(x.instrument_id, x.local_date): x.unit_return for x in long_controls}
    short_map = {(x.instrument_id, x.local_date): x.unit_return for x in short_controls}
    keys = [(x.instrument_id, x.local_date) for x in strategy]
    observed = statistics.fmean(x.unit_return for x in strategy) if strategy else 0.0
    generator = random.Random(seed)
    means = []
    for _ in range(replications):
        values = [
            (long_map[key] if generator.random() < 0.5 else short_map[key])
            for key in keys
            if key in long_map and key in short_map
        ]
        means.append(statistics.fmean(values) if values else 0.0)
    percentile = sum(value <= observed for value in means) / len(means)
    return {
        "empirical_percentile": percentile,
        "observed_mean_bps": observed * 10000,
        "random_mean_bps": statistics.fmean(means) * 10000,
        "random_p95_bps": quantile(means, 0.95) * 10000,
    }


def attribution(outcomes: Sequence[Outcome], trade_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_instrument = defaultdict(float)
    by_month = defaultdict(float)
    for row in trade_rows:
        by_instrument[row["instrument_id"]] += float(row["pnl_gbp"])
        by_month[str(row["entry_time"])[:7]] += float(row["pnl_gbp"])
    positives = {key: value for key, value in by_month.items() if value > 0}
    total_positive = sum(positives.values())
    top_three = sum(sorted(positives.values(), reverse=True)[:3])
    instrument_positive = {key: max(value, 0.0) for key, value in by_instrument.items()}
    all_instrument_positive = sum(instrument_positive.values())
    us_positive = instrument_positive["SPX500_USD"] + instrument_positive["NAS100_USD"]
    return {
        "best_three_positive_month_profit_share": top_three / total_positive if total_positive else 1.0,
        "instrument_pnl_gbp": dict(sorted(by_instrument.items())),
        "instruments_with_positive_pnl": sum(value > 0 for value in by_instrument.values()),
        "monthly_pnl_gbp": dict(sorted(by_month.items())),
        "us_equity_pair_positive_profit_share": us_positive / all_instrument_positive if all_instrument_positive else 1.0,
    }


def partition_outcomes(outcomes: Iterable[Outcome], start: datetime, end: datetime) -> list[Outcome]:
    return [item for item in outcomes if start <= item.entry_time < end]
