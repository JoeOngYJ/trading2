"""Successor XLON calendar with moved Christmas/New-Year half-days."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import date, time
from pathlib import Path
from typing import Any, Iterable, Mapping

from trading_platform.cross_asset_xlon_calendar import (
    END,
    START,
    ExchangeSession,
    XlonCalendarError,
    _load_evidence,
    _utc_stamp,
    canonical_json,
    canonical_json_line,
    sessions as v1_sessions,
    sha256_file,
)


CALENDAR_ID = "xlon-uk-rules-2009-2025-v2"
SCHEMA_VERSION = "xlon-session-calendar-v2"


def half_day_dates() -> frozenset[str]:
    by_year: dict[int, list[date]] = defaultdict(list)
    for item in v1_sessions():
        by_year[date.fromisoformat(item.session_date).year].append(date.fromisoformat(item.session_date))
    result: set[str] = set()
    for year, values in by_year.items():
        christmas_candidates = [day for day in values if day < date(year, 12, 25)]
        year_end_candidates = [day for day in values if day <= date(year, 12, 31)]
        if christmas_candidates:
            result.add(max(christmas_candidates).isoformat())
        if year_end_candidates:
            result.add(max(year_end_candidates).isoformat())
    return frozenset(result)


def sessions() -> tuple[ExchangeSession, ...]:
    half_days = half_day_dates()
    result: list[ExchangeSession] = []
    for base in v1_sessions():
        day = date.fromisoformat(base.session_date)
        half_day = base.session_date in half_days
        result.append(
            ExchangeSession(
                mic="XLON",
                session_date=base.session_date,
                open_at=_utc_stamp(day, time(8, 0)),
                close_at=_utc_stamp(day, time(12, 30) if half_day else time(16, 30)),
                half_day=half_day,
            )
        )
    return tuple(result)


def _records_digest(values: Iterable[Mapping[str, Any]]) -> str:
    raw = "\n".join(canonical_json_line(value) for value in values) + "\n"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def calendar_payload(evidence_path: Path, repo_root: Path) -> dict[str, Any]:
    _load_evidence(evidence_path, repo_root)
    values = sessions()
    half_days = [item.session_date for item in values if item.half_day]
    return {
        "boundary": {"end_inclusive": END.isoformat(), "start_inclusive": START.isoformat()},
        "calendar_id": CALENDAR_ID,
        "evidence": {
            "path": str(evidence_path.relative_to(repo_root)),
            "sha256": sha256_file(evidence_path),
        },
        "half_day_close_local": "12:30:00",
        "half_day_count": len(half_days),
        "half_day_rule": "last valid XLON session before Christmas and last valid XLON session of the calendar year",
        "half_days": half_days,
        "mic": "XLON",
        "regular_close_local": "16:30:00",
        "regular_open_local": "08:00:00",
        "schema_version": SCHEMA_VERSION,
        "session_count": len(values),
        "session_records_sha256": _records_digest(item.as_dict() for item in values),
        "supersedes": {
            "path": "config/research/xlon-calendar-2009-2025-v1.json",
            "reason": "v1 did not move half-days when 24 or 31 December was not a valid session",
            "sha256": "d0c3e2226a3873690c149d61d2fa001ba788cbffd83eecc244136b92e21b10db",
        },
        "timezone": "Europe/London",
    }


def load_calendar(path: Path, evidence_path: Path, repo_root: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
        payload = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise XlonCalendarError(f"cannot read XLON v2 calendar: {path}") from exc
    expected = calendar_payload(evidence_path, repo_root)
    if not isinstance(payload, dict) or raw != canonical_json(payload) or payload != expected:
        raise XlonCalendarError("XLON v2 calendar is stale, changed, or noncanonical")
    return {**payload, "sessions": sessions()}
