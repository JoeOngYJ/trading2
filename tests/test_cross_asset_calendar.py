from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from trading_platform.cross_asset_calendar import (
    CrossAssetCalendarError,
    calendar_payload,
    fx_weekday_sessions,
    load_calendar,
    us_exchange_sessions,
)


ROOT = Path(__file__).resolve().parents[1]
CALENDAR_PATH = ROOT / "config/research/cross-asset-a1-calendars-2008-2025-v1.json"


def test_frozen_calendar_is_canonical_and_reproducible():
    assert load_calendar(CALENDAR_PATH) == calendar_payload()


def test_us_calendar_applies_regular_and_special_closures():
    sessions = set(us_exchange_sessions())
    for closed in (
        "2012-04-06",
        "2012-10-29",
        "2012-10-30",
        "2018-12-05",
        "2025-01-09",
        "2025-06-19",
    ):
        assert closed not in sessions
    for open_day in ("2008-01-02", "2012-10-31", "2025-12-31"):
        assert open_day in sessions


def test_fx_calendar_is_weekday_rule_not_us_exchange_calendar():
    sessions = set(fx_weekday_sessions())
    assert "2025-02-17" in sessions
    assert "2025-01-01" not in sessions
    assert "2025-12-25" not in sessions
    assert "2025-01-09" in sessions


def test_calendar_rejects_reversed_boundary():
    with pytest.raises(CrossAssetCalendarError, match="start"):
        us_exchange_sessions(date(2025, 1, 2), date(2025, 1, 1))
