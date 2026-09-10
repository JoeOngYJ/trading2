"""Deterministic, dependency-free calendars for the frozen cross-asset A1 history audit."""

from __future__ import annotations

import calendar
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any


CALENDAR_ID = "cross-asset-a1-calendars-2008-2025-v1"
START = date(2008, 1, 2)
END = date(2025, 12, 31)
SPECIAL_US_CLOSURES = frozenset(
    {
        date(2012, 10, 29),
        date(2012, 10, 30),
        date(2018, 12, 5),
        date(2025, 1, 9),
    }
)


class CrossAssetCalendarError(ValueError):
    """Raised when a frozen calendar cannot be generated or validated."""


def canonical_json(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True, separators=(",", ": ")
    ) + "\n"


def _observed(day: date) -> date:
    if day.weekday() == 5:
        return day - timedelta(days=1)
    if day.weekday() == 6:
        return day + timedelta(days=1)
    return day


def _nth_weekday(year: int, month: int, weekday: int, occurrence: int) -> date:
    days = [
        week[weekday]
        for week in calendar.monthcalendar(year, month)
        if week[weekday] != 0
    ]
    return date(year, month, days[occurrence - 1])


def _last_weekday(year: int, month: int, weekday: int) -> date:
    return _nth_weekday(year, month, weekday, -1)


def _easter_sunday(year: int) -> date:
    """Gregorian Easter, Anonymous Gregorian algorithm."""

    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    ell = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ell) // 451
    month = (h + ell - 7 * m + 114) // 31
    day = (h + ell - 7 * m + 114) % 31 + 1
    return date(year, month, day)


def us_exchange_closures(year: int) -> frozenset[date]:
    holidays = {
        _observed(date(year, 1, 1)),
        _nth_weekday(year, 1, calendar.MONDAY, 3),
        _nth_weekday(year, 2, calendar.MONDAY, 3),
        _easter_sunday(year) - timedelta(days=2),
        _last_weekday(year, 5, calendar.MONDAY),
        _observed(date(year, 7, 4)),
        _nth_weekday(year, 9, calendar.MONDAY, 1),
        _nth_weekday(year, 11, calendar.THURSDAY, 4),
        _observed(date(year, 12, 25)),
    }
    if year >= 2022:
        holidays.add(_observed(date(year, 6, 19)))
    return frozenset(holidays | {day for day in SPECIAL_US_CLOSURES if day.year == year})


def _dates(start: date, end: date) -> list[date]:
    if start > end:
        raise CrossAssetCalendarError("calendar start must not follow end")
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def us_exchange_sessions(start: date = START, end: date = END) -> tuple[str, ...]:
    sessions = [
        day.isoformat()
        for day in _dates(start, end)
        if day.weekday() < 5 and day not in us_exchange_closures(day.year)
    ]
    return tuple(sessions)


def fx_weekday_sessions(start: date = START, end: date = END) -> tuple[str, ...]:
    sessions = [
        day.isoformat()
        for day in _dates(start, end)
        if day.weekday() < 5 and (day.month, day.day) not in {(1, 1), (12, 25)}
    ]
    return tuple(sessions)


def calendar_payload() -> dict[str, Any]:
    us = us_exchange_sessions()
    fx = fx_weekday_sessions()
    return {
        "boundary": {"end_inclusive": END.isoformat(), "start_inclusive": START.isoformat()},
        "calendar_id": CALENDAR_ID,
        "fx": {
            "closure_rule": "Saturday and Sunday plus weekday January 1 and December 25",
            "session_count": len(fx),
            "sessions": list(fx),
        },
        "schema_version": "cross-asset-a1-independent-calendars-v1",
        "us_exchange": {
            "closure_rule": "NYSE/Nasdaq shared full-day holidays plus frozen special closures",
            "session_count": len(us),
            "sessions": list(us),
            "special_closures": sorted(day.isoformat() for day in SPECIAL_US_CLOSURES),
        },
    }


def load_calendar(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
        payload = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CrossAssetCalendarError(f"cannot read calendar: {path}") from exc
    expected = calendar_payload()
    if payload != expected or raw != canonical_json(payload):
        raise CrossAssetCalendarError("calendar does not match the frozen deterministic rules")
    return payload
