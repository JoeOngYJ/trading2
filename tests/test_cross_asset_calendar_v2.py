from datetime import date
from pathlib import Path

import pytest

from trading_platform.cross_asset_calendar_v2 import (
    CrossAssetCalendarV2Error,
    calendar_payload,
    load_calendar,
    us_exchange_closures,
    us_exchange_sessions,
)


ROOT = Path(__file__).resolve().parents[1]
CALENDAR = ROOT / "config/research/cross-asset-a1-calendars-2008-2025-v2.json"


def test_memorial_day_uses_last_monday_and_preserves_session_count():
    sessions = set(us_exchange_sessions())
    assert date(2024, 5, 27) in us_exchange_closures(2024)
    assert "2024-05-20" in sessions
    assert "2024-05-27" not in sessions
    assert len(sessions) == 4529


def test_compact_calendar_artifact_is_deterministic_and_fail_closed(tmp_path):
    loaded = load_calendar(CALENDAR)
    assert loaded["us_exchange"]["session_count"] == 4529
    assert len(loaded["fx_sessions"]) == 4671
    stale = tmp_path / "calendar.json"
    stale.write_text("{}\n", encoding="utf-8")
    with pytest.raises(CrossAssetCalendarV2Error):
        load_calendar(stale)
    assert calendar_payload()["calendar_id"].endswith("v2")
