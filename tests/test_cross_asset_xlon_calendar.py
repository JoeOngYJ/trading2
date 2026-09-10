from datetime import date
from pathlib import Path

import pytest

from trading_platform.cross_asset_xlon_calendar import (
    END,
    START,
    XlonCalendarError,
    calendar_payload,
    load_calendar,
    sessions,
    xlon_closures,
)


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "config/research/xlon-calendar-evidence-v1.json"
CALENDAR = ROOT / "config/research/xlon-calendar-2009-2025-v1.json"


def test_xlon_rules_include_moved_and_exceptional_closures():
    assert date(2011, 4, 29) in xlon_closures(2011)
    assert date(2012, 6, 4) in xlon_closures(2012)
    assert date(2012, 5, 28) not in xlon_closures(2012)
    assert date(2020, 5, 8) in xlon_closures(2020)
    assert date(2020, 5, 4) not in xlon_closures(2020)
    assert date(2022, 9, 19) in xlon_closures(2022)
    assert date(2023, 5, 8) in xlon_closures(2023)


def test_half_days_remain_valid_sessions_with_utc_times():
    by_date = {item.session_date: item for item in sessions()}
    christmas_eve = by_date["2020-12-24"]
    assert christmas_eve.half_day is True
    assert christmas_eve.close_at == "2020-12-24T12:30:00Z"
    assert "2022-12-24" not in by_date
    summer = by_date["2025-07-01"]
    assert summer.open_at == "2025-07-01T07:00:00Z"
    assert summer.close_at == "2025-07-01T15:30:00Z"


def test_calendar_boundary_checksum_and_official_evidence_fail_closed(tmp_path: Path):
    loaded = load_calendar(CALENDAR, EVIDENCE, ROOT)
    assert loaded["boundary"] == {
        "end_inclusive": END.isoformat(),
        "start_inclusive": START.isoformat(),
    }
    assert loaded["session_count"] == len(loaded["sessions"])
    assert loaded == {**calendar_payload(EVIDENCE, ROOT), "sessions": sessions()}

    changed = tmp_path / "calendar.json"
    changed.write_text("{}\n", encoding="utf-8")
    with pytest.raises(XlonCalendarError, match="stale"):
        load_calendar(changed, EVIDENCE, ROOT)
