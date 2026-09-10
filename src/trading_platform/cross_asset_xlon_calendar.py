"""Deterministic, evidence-bound XLON sessions for cross-asset A1.

This module is deliberately offline.  It generates sessions from frozen UK holiday
rules and exceptional closures, and binds the compact artifact to repository-owned
official LSE evidence.  Half-days remain valid sessions.
"""

from __future__ import annotations

import calendar
import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo


CALENDAR_ID = "xlon-uk-rules-2009-2025-v1"
SCHEMA_VERSION = "xlon-session-calendar-v1"
START = date(2009, 10, 5)
END = date(2025, 12, 31)
LONDON = ZoneInfo("Europe/London")
UTC = ZoneInfo("UTC")

# Dates not produced by the ordinary recurring rules.  Moved recurring holidays
# are represented here as well so that their displacement is explicit and frozen.
EXCEPTIONAL_CLOSURES: Mapping[date, str] = {
    date(2011, 4, 29): "royal_wedding",
    date(2012, 6, 4): "moved_spring_bank_holiday",
    date(2012, 6, 5): "diamond_jubilee",
    date(2020, 5, 8): "moved_early_may_bank_holiday",
    date(2022, 6, 2): "moved_spring_bank_holiday",
    date(2022, 6, 3): "platinum_jubilee",
    date(2022, 9, 19): "state_funeral_elizabeth_ii",
    date(2023, 5, 8): "coronation_charles_iii",
}


class XlonCalendarError(ValueError):
    """Raised when an XLON calendar or its evidence fails closed."""


@dataclass(frozen=True, slots=True)
class ExchangeSession:
    mic: str
    session_date: str
    open_at: str
    close_at: str
    half_day: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "close_at": self.close_at,
            "half_day": self.half_day,
            "mic": self.mic,
            "open_at": self.open_at,
            "session_date": self.session_date,
        }


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        indent=2,
        sort_keys=True,
        separators=(",", ": "),
    ) + "\n"


def canonical_json_line(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _observed(day: date) -> date:
    if day.weekday() == calendar.SATURDAY:
        return day + timedelta(days=2)
    if day.weekday() == calendar.SUNDAY:
        return day + timedelta(days=1)
    return day


def _nth_weekday(year: int, month: int, weekday: int, ordinal: int) -> date:
    matches = [
        week[weekday]
        for week in calendar.monthcalendar(year, month)
        if week[weekday]
    ]
    return date(year, month, matches[ordinal - 1])


def _last_weekday(year: int, month: int, weekday: int) -> date:
    matches = [
        week[weekday]
        for week in calendar.monthcalendar(year, month)
        if week[weekday]
    ]
    return date(year, month, matches[-1])


def _easter_sunday(year: int) -> date:
    # Anonymous Gregorian computus, valid throughout the frozen boundary.
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
    day = ((h + ell - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _christmas_boxing_observed(year: int) -> frozenset[date]:
    christmas = date(year, 12, 25)
    boxing = date(year, 12, 26)
    if christmas.weekday() == calendar.SATURDAY:
        return frozenset({date(year, 12, 27), date(year, 12, 28)})
    if christmas.weekday() == calendar.SUNDAY:
        return frozenset({date(year, 12, 26), date(year, 12, 27)})
    if boxing.weekday() == calendar.SATURDAY:
        return frozenset({christmas, date(year, 12, 28)})
    if boxing.weekday() == calendar.SUNDAY:
        return frozenset({christmas, date(year, 12, 27)})
    return frozenset({christmas, boxing})


def xlon_closures(year: int) -> frozenset[date]:
    easter = _easter_sunday(year)
    recurring = {
        _observed(date(year, 1, 1)),
        easter - timedelta(days=2),
        easter + timedelta(days=1),
        _nth_weekday(year, 5, calendar.MONDAY, 1),
        _last_weekday(year, 5, calendar.MONDAY),
        _last_weekday(year, 8, calendar.MONDAY),
        *_christmas_boxing_observed(year),
    }
    # These recurring dates were displaced by one-off statutory holidays.
    if year == 2012:
        recurring.discard(date(2012, 5, 28))
    if year == 2020:
        recurring.discard(date(2020, 5, 4))
    if year == 2022:
        recurring.discard(date(2022, 5, 30))
    return frozenset(
        recurring
        | {day for day in EXCEPTIONAL_CLOSURES if day.year == year}
    )


def _is_half_day(day: date) -> bool:
    return day.month == 12 and day.day in {24, 31}


def _utc_stamp(day: date, local_time: time) -> str:
    value = datetime.combine(day, local_time, tzinfo=LONDON).astimezone(UTC)
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def sessions(start: date = START, end: date = END) -> tuple[ExchangeSession, ...]:
    if start > end:
        raise XlonCalendarError("calendar start must not follow end")
    result: list[ExchangeSession] = []
    for offset in range((end - start).days + 1):
        day = start + timedelta(days=offset)
        if day.weekday() >= 5 or day in xlon_closures(day.year):
            continue
        half_day = _is_half_day(day)
        result.append(
            ExchangeSession(
                mic="XLON",
                session_date=day.isoformat(),
                open_at=_utc_stamp(day, time(8, 0)),
                close_at=_utc_stamp(day, time(12, 30) if half_day else time(16, 30)),
                half_day=half_day,
            )
        )
    return tuple(result)


def _records_digest(values: Iterable[Mapping[str, Any]]) -> str:
    raw = "\n".join(canonical_json_line(value) for value in values) + "\n"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _load_evidence(path: Path, repo_root: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
        payload = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise XlonCalendarError(f"cannot read XLON evidence registry: {path}") from exc
    if not isinstance(payload, dict) or raw != canonical_json(payload):
        raise XlonCalendarError("XLON evidence registry must be canonical JSON")
    if payload.get("schema_version") != "xlon-calendar-evidence-v1":
        raise XlonCalendarError("unsupported XLON evidence schema")
    official = payload.get("official_lse_artifact", {})
    raw_path = official.get("path")
    if not isinstance(raw_path, str) or Path(raw_path).is_absolute():
        raise XlonCalendarError("official XLON evidence path must be repository-relative")
    try:
        evidence_file = (repo_root / raw_path).resolve(strict=True)
        evidence_file.relative_to(repo_root.resolve(strict=True))
    except (OSError, ValueError) as exc:
        raise XlonCalendarError("official XLON evidence path is invalid") from exc
    if sha256_file(evidence_file) != official.get("sha256"):
        raise XlonCalendarError("official XLON evidence checksum mismatch")
    required_rules = {
        "uk_bank_holiday_rules",
        "lse_trading_calendar",
        "exceptional_closures",
        "half_day_sessions",
    }
    if {item.get("evidence_id") for item in payload.get("sources", ())} != required_rules:
        raise XlonCalendarError("XLON evidence registry is incomplete")
    return payload


def calendar_payload(evidence_path: Path, repo_root: Path) -> dict[str, Any]:
    evidence = _load_evidence(evidence_path, repo_root)
    values = sessions()
    records = tuple(value.as_dict() for value in values)
    half_days = [value.session_date for value in values if value.half_day]
    closures = [
        {
            "date": day.isoformat(),
            "reason": reason,
        }
        for day, reason in sorted(EXCEPTIONAL_CLOSURES.items())
    ]
    return {
        "boundary": {
            "end_inclusive": END.isoformat(),
            "start_inclusive": START.isoformat(),
        },
        "calendar_id": CALENDAR_ID,
        "evidence": {
            "path": str(evidence_path.relative_to(repo_root)),
            "sha256": sha256_file(evidence_path),
        },
        "exceptional_closures": closures,
        "half_day_close_local": "12:30:00",
        "half_day_count": len(half_days),
        "half_days": half_days,
        "mic": "XLON",
        "regular_close_local": "16:30:00",
        "regular_open_local": "08:00:00",
        "schema_version": SCHEMA_VERSION,
        "session_count": len(values),
        "session_records_sha256": _records_digest(records),
        "timezone": "Europe/London",
    }


def load_calendar(path: Path, evidence_path: Path, repo_root: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
        payload = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise XlonCalendarError(f"cannot read XLON calendar: {path}") from exc
    expected = calendar_payload(evidence_path, repo_root)
    if not isinstance(payload, dict) or raw != canonical_json(payload) or payload != expected:
        raise XlonCalendarError("XLON calendar is stale, changed, or noncanonical")
    return {**payload, "sessions": sessions()}
