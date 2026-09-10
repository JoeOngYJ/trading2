from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from trading_platform.cross_asset_gap_reversion import (
    GapCandidate,
    build_outcome,
    candidate_for_session,
)
from trading_platform.cross_asset_oanda_hourly import OandaHourlyError
from trading_platform.cross_asset_session_breakout import Bar, Session


UTC = timezone.utc
PROFILE = {
    "entry_local_hour": 9,
    "exit_local_hour": 11,
    "first_session_local_hour": 8,
    "prior_reference_local_hour": 15,
    "range_last_inclusive_local_hour": 14,
    "timezone": "UTC",
}


def _bar(hour: int, opened: str, high: str, low: str, close: str) -> Bar:
    observed = datetime(2021, 1, 1, hour, tzinfo=UTC)
    mid = {"o": Decimal(opened), "h": Decimal(high), "l": Decimal(low), "c": Decimal(close)}
    bid = {key: value - Decimal("0.01") for key, value in mid.items()}
    ask = {key: value + Decimal("0.01") for key, value in mid.items()}
    return Bar(observed, bid, ask)


def _session(day: int, first_open: str = "100", first_close: str = "100") -> Session:
    bars = {}
    for hour in range(8, 16):
        bars[hour] = _bar(hour, "100", "101", "99", "100")
    bars[8] = _bar(8, first_open, str(Decimal(first_open) + 1), str(Decimal(first_open) - 1), first_close)
    if first_open != "100":
        bars[9] = _bar(9, first_close, str(Decimal(first_close) + 1), str(Decimal(first_close) - 1), first_close)
    shift = timedelta(days=day - 1)
    bars = {
        hour: Bar(bar.observed_at + shift, bar.bid, bar.ask)
        for hour, bar in bars.items()
    }
    return Session("UK100_GBP", date(2021, 1, day), "london", bars)


def _history() -> list[Session]:
    return [_session(day) for day in range(1, 22)]


def test_first_hour_reversal_creates_fade_only_from_completed_information():
    sessions = _history()
    current = _session(22, "102", "101.5")
    sessions.append(current)
    candidate = candidate_for_session(sessions, 21, PROFILE, 20, Decimal("0.75"))
    assert candidate is not None
    assert candidate.direction == -1


def test_continuation_or_completed_reversion_fails_closed():
    sessions = _history() + [_session(22, "102", "102.5")]
    assert candidate_for_session(sessions, 21, PROFILE, 20, Decimal("0.75")) is None
    crossed = _session(22, "102", "101.5")
    first = crossed.bars[8]
    crossed_bars = dict(crossed.bars)
    crossed_bars[8] = Bar(first.observed_at, {**first.bid, "l": Decimal("98")}, {**first.ask, "l": Decimal("98.02")})
    sessions = _history() + [Session(crossed.instrument_id, crossed.local_date, crossed.profile_id, crossed_bars)]
    assert candidate_for_session(sessions, 21, PROFILE, 20, Decimal("0.75")) is None


def test_entry_is_next_hour_and_costs_are_monotone():
    session = _session(22, "102", "101.5")
    candidate = GapCandidate(-1, Decimal("2"), 1.0, Decimal("100"), session)
    conversion = {bar.observed_at: _bar(bar.observed_at.hour, "1", "1", "1", "1") for bar in session.bars.values()}
    low = build_outcome(candidate, PROFILE, -1, 0, conversion, conversion)
    high = build_outcome(candidate, PROFILE, -1, 15, conversion, conversion)
    assert low.entry_time.hour == 9
    assert low.exit_time.hour <= 11
    assert high.unit_return < low.unit_return


def test_protective_stop_has_priority_and_missing_conversion_fails_closed():
    session = _session(22, "102", "101.5")
    bars = dict(session.bars)
    stop_bar = bars[9]
    bars[9] = Bar(stop_bar.observed_at, stop_bar.bid, {**stop_bar.ask, "h": Decimal("105")})
    session = Session(session.instrument_id, session.local_date, session.profile_id, bars)
    candidate = GapCandidate(-1, Decimal("2"), 1.0, Decimal("100"), session)
    conversion = {bar.observed_at: _bar(bar.observed_at.hour, "1", "1", "1", "1") for bar in session.bars.values()}
    stopped = build_outcome(candidate, PROFILE, -1, 0, conversion, conversion)
    assert stopped.exit_reason == "protective_stop"
    with pytest.raises(OandaHourlyError, match="missing GBP conversion"):
        usd_session = Session("SPX500_USD", session.local_date, session.profile_id, session.bars)
        build_outcome(
            GapCandidate(-1, Decimal("2"), 1.0, Decimal("100"), usd_session),
            PROFILE,
            -1,
            0,
            {},
            {},
        )
