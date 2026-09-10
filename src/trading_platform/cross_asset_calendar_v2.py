"""Corrected deterministic calendars for cross-asset A1 recovery.

This preserves the rejected v1 calendar and fixes only its last-weekday calculation.
"""

from __future__ import annotations

import calendar
import hashlib
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from trading_platform.cross_asset_calendar import END, SPECIAL_US_CLOSURES, START, _easter_sunday, _nth_weekday, _observed


CALENDAR_ID = "cross-asset-a1-calendars-2008-2025-v2"


class CrossAssetCalendarV2Error(ValueError):
    pass


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True, separators=(",", ": ")) + "\n"


def _last_weekday(year: int, month: int, weekday: int) -> date:
    days = [week[weekday] for week in calendar.monthcalendar(year, month) if week[weekday]]
    return date(year, month, days[-1])


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


def _days(start: date = START, end: date = END) -> tuple[date, ...]:
    if start > end:
        raise CrossAssetCalendarV2Error("calendar start must not follow end")
    return tuple(start + timedelta(days=i) for i in range((end - start).days + 1))


def us_exchange_sessions() -> tuple[str, ...]:
    return tuple(day.isoformat() for day in _days() if day.weekday() < 5 and day not in us_exchange_closures(day.year))


def fx_reference_sessions() -> tuple[str, ...]:
    return tuple(day.isoformat() for day in _days() if day.weekday() < 5 and (day.month, day.day) not in {(1, 1), (12, 25)})


def _session_digest(values: tuple[str, ...]) -> str:
    return hashlib.sha256(("\n".join(values) + "\n").encode()).hexdigest()


def calendar_payload() -> dict[str, Any]:
    us = us_exchange_sessions()
    fx = fx_reference_sessions()
    return {
        "boundary": {"end_inclusive": END.isoformat(), "start_inclusive": START.isoformat()},
        "calendar_id": CALENDAR_ID,
        "fx_reference": {
            "closure_rule": "weekends plus weekday January 1 and December 25; source gaps remain explicit",
            "session_count": len(fx),
            "session_sha256": _session_digest(fx),
        },
        "schema_version": "cross-asset-a1-independent-calendars-v2",
        "us_exchange": {
            "closure_rule": "NYSE/Nasdaq full-day holidays with corrected last-Monday Memorial Day and frozen special closures",
            "session_count": len(us),
            "session_sha256": _session_digest(us),
            "special_closures": sorted(day.isoformat() for day in SPECIAL_US_CLOSURES),
        },
    }


def load_calendar(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
        payload = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CrossAssetCalendarV2Error(f"cannot read corrected calendar: {path}") from exc
    if payload != calendar_payload() or raw != canonical_json(payload):
        raise CrossAssetCalendarV2Error("corrected calendar artifact is stale or noncanonical")
    return {**payload, "fx_sessions": fx_reference_sessions(), "us_sessions": us_exchange_sessions()}
