from pathlib import Path

import pytest

from trading_platform.cross_asset_xlon_calendar import XlonCalendarError
from trading_platform.cross_asset_xlon_calendar_v2 import (
    calendar_payload,
    half_day_dates,
    load_calendar,
    sessions,
)


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "config/research/xlon-calendar-evidence-v1.json"
CALENDAR = ROOT / "config/research/xlon-calendar-2009-2025-v2.json"


def test_half_days_move_to_preceding_valid_session():
    dates = half_day_dates()
    assert {"2023-12-22", "2023-12-29", "2025-12-24", "2025-12-31"} <= dates
    assert "2023-12-24" not in dates and "2023-12-31" not in dates
    by_date = {item.session_date: item for item in sessions()}
    assert by_date["2023-12-22"].half_day is True
    assert by_date["2023-12-22"].close_at == "2023-12-22T12:30:00Z"


def test_v2_is_deterministic_and_preserves_session_count(tmp_path: Path):
    loaded = load_calendar(CALENDAR, EVIDENCE, ROOT)
    assert loaded["session_count"] == len(loaded["sessions"])
    assert loaded["half_day_count"] == 34
    assert loaded == {**calendar_payload(EVIDENCE, ROOT), "sessions": sessions()}
    stale = tmp_path / "stale.json"
    stale.write_text("{}\n", encoding="utf-8")
    with pytest.raises(XlonCalendarError):
        load_calendar(stale, EVIDENCE, ROOT)
