"""Causal offline evaluator for the frozen cross-asset A3 gap-reversion family."""

from __future__ import annotations

import json
import math
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

from trading_platform.cross_asset_oanda_hourly import (
    OandaHourlyError,
    _load_canonical,
    _repo_file,
    _utc,
    sha256_file,
)
from trading_platform.cross_asset_session_breakout import (
    Bar,
    Outcome,
    Session,
    _bar,
    _quote_per_gbp_with_cross,
    attribution,
    month_block_interval,
    random_direction_percentile,
    simulate_shared_account,
)


CONTRACT_SCHEMA = "cross-asset-a3-overnight-gap-reversion-contract-v2"
EXPERIMENT_ID = "cross-asset-a3-overnight-gap-reversion-v2"
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


@dataclass(frozen=True, slots=True)
class GapCandidate:
    direction: int
    median_range: Decimal
    normalized_gap: float
    prior_reference: Decimal
    session: Session


def load_contract(path: Path, repo_root: Path) -> dict[str, Any]:
    contract = _load_canonical(path, "A3 gap-reversion contract")
    if (
        contract.get("schema_version"),
        contract.get("experiment_id"),
        contract.get("status"),
    ) != (CONTRACT_SCHEMA, EXPERIMENT_ID, "frozen"):
        raise OandaHourlyError("unexpected or unfrozen A3 contract")
    if tuple(contract.get("instrument_universe", ())) != INSTRUMENTS:
        raise OandaHourlyError("A3 instrument universe changed")
    if contract.get("partitions") != {
        "development": {
            "end_exclusive": "2022-01-01T00:00:00Z",
            "start_inclusive": "2010-01-01T00:00:00Z",
        },
        "prospective_final": {
            "minimum_duration_months": 12,
            "minimum_filled_trades": 100,
            "price_data_available_to_this_run": False,
            "start_inclusive": "2026-08-31T00:00:00Z",
        },
        "validation": {
            "end_exclusive": "2026-01-01T00:00:00Z",
            "start_inclusive": "2022-01-01T00:00:00Z",
        },
    }:
        raise OandaHourlyError("A3 partitions changed")
    if contract.get("historical_result_policy", {}).get("historical_result_can_accept_strategy_arm") is not False:
        raise OandaHourlyError("A3 historical evidence cannot approve an arm")
    if contract.get("data_bindings", {}).get("source_files_outside_prepartitions_may_be_read") is not False:
        raise OandaHourlyError("A3 must read only prepartitioned sources")
    if contract.get("costs", {}).get("additional_round_trip_slippage_bps") != [0, 5, 15]:
        raise OandaHourlyError("A3 cost scenarios changed")
    if contract.get("robustness", {}).get("primary_lookback_complete_sessions") != 20:
        raise OandaHourlyError("A3 lookback changed")
    if contract.get("robustness", {}).get("primary_gap_threshold_multiplier") != "0.75":
        raise OandaHourlyError("A3 gap threshold changed")
    for key, value in contract.get("prohibitions", {}).items():
        if value is not False:
            raise OandaHourlyError(f"unsafe A3 permission: {key}")
    for record in (
        contract["mandate"],
        contract["predecessor_hypothesis"],
        contract["data_bindings"]["data_contract"],
        contract["data_bindings"]["prepartition_evidence"],
        contract["data_bindings"]["prepartition_manifest"],
    ):
        bound = _repo_file(repo_root, record["path"], "A3 bound input")
        if sha256_file(bound) != record["sha256"]:
            raise OandaHourlyError("A3 bound input checksum changed")
    return contract


def resolve_prepartitions(contract: Mapping[str, Any], root: Path) -> dict[tuple[str, str, str], Path]:
    evidence_path = _repo_file(
        root, contract["data_bindings"]["prepartition_evidence"]["path"], "A3 evidence"
    )
    evidence = _load_canonical(evidence_path, "A3 prepartition evidence")
    if (
        evidence.get("decision") != "a3_timestamp_prepartition_passed"
        or evidence.get("price_fields_deserialized") is not False
        or evidence.get("prospective_price_rows_present") is not False
    ):
        raise OandaHourlyError("A3 prepartition evidence is unsafe")
    artifact_hashes = {item["path"]: item["sha256"] for item in evidence.get("artifacts", ())}
    for raw, digest in artifact_hashes.items():
        if sha256_file(_repo_file(root, raw, "A3 prepartition artifact")) != digest:
            raise OandaHourlyError("A3 prepartition evidence checksum changed")
    manifest_path = _repo_file(
        root, contract["data_bindings"]["prepartition_manifest"]["path"], "A3 manifest"
    )
    manifest = _load_canonical(manifest_path, "A3 prepartition manifest")
    if (
        manifest.get("price_fields_deserialized") is not False
        or manifest.get("prospective_price_rows_present") is not False
        or len(manifest.get("partitions", ())) != 30
    ):
        raise OandaHourlyError("A3 prepartition manifest changed")
    result = {}
    for record in manifest["partitions"]:
        key = (str(record["partition_id"]), str(record["instrument_id"]), str(record["kind"]))
        if key in result:
            raise OandaHourlyError("A3 prepartition repeats an identity")
        path = _repo_file(root, record["path"], "A3 partition")
        if sha256_file(path) != record["sha256"] or artifact_hashes.get(record["path"]) != record["sha256"]:
            raise OandaHourlyError("A3 partition checksum changed")
        result[key] = path
    return result


def load_conversion_partition(path: Path) -> dict[datetime, Bar]:
    result = {}
    with path.open(encoding="utf-8") as rows:
        for line in rows:
            raw = json.loads(line)
            bar = _bar(raw)
            if bar.observed_at in result:
                raise OandaHourlyError("A3 conversion repeats a timestamp")
            result[bar.observed_at] = bar
    return result


def load_session_partition(
    instrument: str,
    market_path: Path,
    mask_path: Path,
    profile: Mapping[str, Any],
) -> list[Session]:
    eligible = set()
    with mask_path.open(encoding="utf-8") as rows:
        for line in rows:
            raw = json.loads(line)
            if raw.get("instrument_id") != instrument:
                raise OandaHourlyError("A3 availability identity changed")
            disposition = raw.get("disposition")
            if disposition == "eligible":
                eligible.add(date.fromisoformat(raw["local_date"]))
            elif disposition != "no_trade":
                raise OandaHourlyError("A3 availability has an unsafe disposition")
    zone = ZoneInfo(str(profile["timezone"]))
    first = int(profile["first_session_local_hour"])
    last = int(profile["prior_reference_local_hour"])
    grouped: dict[date, dict[int, Bar]] = defaultdict(dict)
    with market_path.open(encoding="utf-8") as rows:
        for line in rows:
            raw = json.loads(line)
            bar = _bar(raw)
            local = bar.observed_at.astimezone(zone)
            if local.date() not in eligible or not first <= local.hour <= last:
                continue
            if local.hour in grouped[local.date()]:
                raise OandaHourlyError("A3 session repeats a local hour")
            grouped[local.date()][local.hour] = bar
    required = set(range(first, last + 1))
    return [
        Session(instrument, local_date, PROFILE_BY_INSTRUMENT[instrument], bars)
        for local_date, bars in sorted(grouped.items())
        if set(bars) == required
    ]


def session_range(session: Session, profile: Mapping[str, Any]) -> Decimal:
    hours = range(
        int(profile["first_session_local_hour"]),
        int(profile["range_last_inclusive_local_hour"]) + 1,
    )
    high = max(session.bars[hour].midpoint("h") for hour in hours)
    low = min(session.bars[hour].midpoint("l") for hour in hours)
    return high - low


def candidate_for_session(
    sessions: Sequence[Session],
    index: int,
    profile: Mapping[str, Any],
    lookback: int,
    threshold: Decimal,
    *,
    require_confirmation: bool = True,
) -> GapCandidate | None:
    if index < lookback:
        return None
    history = sessions[index - lookback : index]
    ranges = [session_range(item, profile) for item in history]
    if any(value <= 0 for value in ranges):
        return None
    median_range = statistics.median(ranges)
    current = sessions[index]
    previous = sessions[index - 1]
    first_hour = int(profile["first_session_local_hour"])
    reference_hour = int(profile["prior_reference_local_hour"])
    entry_hour = int(profile["entry_local_hour"])
    prior_reference = previous.bars[reference_hour].midpoint("o")
    first = current.bars[first_hour]
    current_open = first.midpoint("o")
    gap = current_open - prior_reference
    if gap == 0 or abs(gap) < threshold * median_range:
        return None
    direction = -1 if gap > 0 else 1
    if require_confirmation:
        reverses = first.midpoint("c") < current_open if gap > 0 else first.midpoint("c") > current_open
        if not reverses:
            return None
    if gap > 0 and first.midpoint("l") <= prior_reference:
        return None
    if gap < 0 and first.midpoint("h") >= prior_reference:
        return None
    entry_mid = current.bars[entry_hour].midpoint("o")
    if gap > 0 and entry_mid <= prior_reference:
        return None
    if gap < 0 and entry_mid >= prior_reference:
        return None
    return GapCandidate(direction, median_range, float(abs(gap) / median_range), prior_reference, current)


def generate_candidates(
    sessions_by_instrument: Mapping[str, Sequence[Session]],
    profiles: Mapping[str, Any],
    lookback: int,
    threshold: Decimal,
    *,
    require_confirmation: bool = True,
) -> list[GapCandidate]:
    result = []
    for instrument in INSTRUMENTS:
        sessions = sessions_by_instrument[instrument]
        profile = profiles[PROFILE_BY_INSTRUMENT[instrument]]
        for index in range(len(sessions)):
            candidate = candidate_for_session(
                sessions, index, profile, lookback, threshold,
                require_confirmation=require_confirmation,
            )
            if candidate is not None:
                result.append(candidate)
    return sorted(result, key=lambda item: (item.session.bars[profiles[item.session.profile_id]["entry_local_hour"]].observed_at, item.session.instrument_id))


def build_outcome(
    candidate: GapCandidate,
    profile: Mapping[str, Any],
    direction: int,
    cost_bps: int,
    conversion: Mapping[datetime, Bar],
    eurusd: Mapping[datetime, Bar],
) -> Outcome:
    session = candidate.session
    entry_hour = int(profile["entry_local_hour"])
    exit_hour = int(profile["exit_local_hour"])
    entry_bar = session.bars[entry_hour]
    entry_mid = entry_bar.midpoint("o")
    stop = entry_mid - Decimal(direction) * candidate.median_range
    half = Decimal(cost_bps) / Decimal(20000)
    entry_price = (
        entry_bar.ask["o"] * (Decimal(1) + half)
        if direction == 1
        else entry_bar.bid["o"] * (Decimal(1) - half)
    )
    q_entry = _quote_per_gbp_with_cross(
        session.instrument_id, entry_bar.observed_at, entry_bar, conversion, eurusd
    )
    units_per_gbp = q_entry / entry_price
    path = []
    final_price = None
    final_time = None
    exit_reason = "timed_exit"
    for hour in range(entry_hour, exit_hour):
        bar = session.bars[hour]
        if direction == 1:
            marked = bar.bid["l"] * (Decimal(1) - half)
            stop_hit = bar.bid["o"] <= stop or bar.bid["l"] <= stop
            stop_fill = min(bar.bid["o"], stop) * (Decimal(1) - half)
        else:
            marked = bar.ask["h"] * (Decimal(1) + half)
            stop_hit = bar.ask["o"] >= stop or bar.ask["h"] >= stop
            stop_fill = max(bar.ask["o"], stop) * (Decimal(1) + half)
        q_mark = _quote_per_gbp_with_cross(
            session.instrument_id, bar.observed_at, bar, conversion, eurusd
        )
        marked_return = units_per_gbp * Decimal(direction) * (marked - entry_price) / q_mark
        path.append((bar.observed_at, float(marked_return)))
        if stop_hit:
            final_price = stop_fill
            final_time = bar.observed_at
            exit_reason = "protective_stop"
            break
    if final_price is None:
        exit_bar = session.bars[exit_hour]
        final_time = exit_bar.observed_at
        final_price = (
            exit_bar.bid["o"] * (Decimal(1) - half)
            if direction == 1
            else exit_bar.ask["o"] * (Decimal(1) + half)
        )
    fx_bar = next(bar for bar in session.bars.values() if bar.observed_at == final_time)
    q_exit = _quote_per_gbp_with_cross(
        session.instrument_id, final_time, fx_bar, conversion, eurusd
    )
    unit_return = units_per_gbp * Decimal(direction) * (final_price - entry_price) / q_exit
    path.append((final_time, float(unit_return)))
    return Outcome(
        direction=direction,
        entry_time=entry_bar.observed_at,
        exit_time=final_time,
        instrument_id=session.instrument_id,
        local_date=session.local_date.isoformat(),
        stop_fraction=float(candidate.median_range / entry_mid),
        unit_return=float(unit_return),
        worst_path_returns=tuple(path),
        exit_reason=exit_reason,
    )


def outcomes_for_candidates(
    candidates: Sequence[GapCandidate],
    profiles: Mapping[str, Any],
    cost_bps: int,
    conversion: Mapping[datetime, Bar],
    eurusd: Mapping[datetime, Bar],
    mode: str = "strategy",
) -> list[Outcome]:
    outcomes = []
    for candidate in candidates:
        if mode == "strategy":
            direction = candidate.direction
        elif mode == "long":
            direction = 1
        elif mode == "short":
            direction = -1
        elif mode == "continuation":
            direction = -candidate.direction
        else:
            raise OandaHourlyError(f"unknown A3 outcome mode: {mode}")
        outcomes.append(
            build_outcome(
                candidate,
                profiles[candidate.session.profile_id],
                direction,
                cost_bps,
                conversion,
                eurusd,
            )
        )
    return outcomes


def partition_outcomes(outcomes: Sequence[Outcome], start: datetime, end: datetime) -> list[Outcome]:
    return [item for item in outcomes if start <= item.entry_time < end]


def augmented_account(outcomes: Sequence[Outcome], contract: Mapping[str, Any]) -> dict[str, Any]:
    result = simulate_shared_account(outcomes, contract)
    rows = result["trade_rows"]
    initial = float(contract["accounting"]["initial_equity_gbp"])
    pnl_by_day: dict[str, float] = defaultdict(float)
    for row in rows:
        pnl_by_day[str(row["exit_time"])[:10]] += float(row["pnl_gbp"])
    equity = initial
    returns = []
    for day in sorted(pnl_by_day):
        pnl = pnl_by_day[day]
        returns.append(pnl / equity)
        equity += pnl
    downside = [min(value, 0.0) for value in returns]
    result.update(
        {
            "annualized_volatility": statistics.stdev(returns) * math.sqrt(252) if len(returns) > 1 else None,
            "sortino": (
                statistics.fmean(returns) / statistics.stdev(downside) * math.sqrt(252)
                if len(downside) > 1 and statistics.stdev(downside) > 0
                else None
            ),
            "total_turnover_fraction_of_initial_equity": sum(float(row["notional_gbp"]) for row in rows) / initial,
            "win_rate": sum(float(row["pnl_gbp"]) > 0 for row in rows) / len(rows) if rows else None,
        }
    )
    return result


def validation_year_pnl(trade_rows: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    result: dict[str, float] = defaultdict(float)
    for row in trade_rows:
        result[str(row["entry_time"])[:4]] += float(row["pnl_gbp"])
    return dict(sorted(result.items()))
