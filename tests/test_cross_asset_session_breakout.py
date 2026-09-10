from __future__ import annotations

import ast
import copy
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from trading_platform.cross_asset_oanda_hourly import OandaHourlyError, canonical_json
from trading_platform.cross_asset_session_breakout import (
    Bar,
    Session,
    build_outcome,
    load_contract,
    session_direction,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/experiments/cross-asset-a2-session-breakout-continuation-v1.json"


def bar(at: datetime, o: str, h: str, low: str, c: str, spread: str = "0.2") -> Bar:
    half = Decimal(spread) / 2
    values = {"o": Decimal(o), "h": Decimal(h), "l": Decimal(low), "c": Decimal(c)}
    return Bar(
        at,
        {key: value - half for key, value in values.items()},
        {key: value + half for key, value in values.items()},
    )


def session() -> Session:
    start = datetime(2023, 1, 3, 14, tzinfo=timezone.utc)  # 09:00 New York
    values = {
        9: ("100", "101", "99", "100.5"),
        10: ("100.5", "102", "100", "101.5"),
        11: ("101.5", "103.2", "101.4", "103"),
        12: ("103", "104", "102.8", "103.8"),
        13: ("103.8", "104.5", "103.5", "104"),
        14: ("104", "105", "103.9", "104.8"),
        15: ("104.8", "105.5", "104.5", "105"),
        16: ("105", "105.2", "104.8", "105"),
    }
    return Session(
        "SPX500_USD",
        date(2023, 1, 3),
        "new_york",
        {hour: bar(start + timedelta(hours=hour - 9), *row) for hour, row in values.items()},
    )


def profile() -> dict:
    return {
        "confirmation_local_hour": 11,
        "entry_local_hour": 12,
        "exit_local_hour": 16,
        "opening_range_local_hours": [9, 10],
        "timezone": "America/New_York",
    }


def conversion_rows(current: Session) -> dict[datetime, Bar]:
    return {
        item.observed_at: bar(item.observed_at, "1.25", "1.25", "1.25", "1.25", "0.00")
        for item in current.bars.values()
    }


def test_frozen_a2_contract_is_canonical_costed_and_final_sealed():
    contract = load_contract(CONTRACT, ROOT)
    assert CONTRACT.read_text() == canonical_json(json.loads(CONTRACT.read_text()))
    assert contract["partitions"]["initial_run_may_read_final_sealed_values"] is False
    assert contract["costs"]["additional_round_trip_slippage_bps"] == [0, 5, 15]
    assert contract["accounting"]["no_leverage"] is True
    assert contract["controls"]["random_direction_seed"] == 20260830


def test_breakout_direction_uses_only_completed_opening_and_confirmation_bars():
    current = session()
    assert session_direction(current, profile()) == 1
    changed = dict(current.bars)
    changed[15] = bar(changed[15].observed_at, "104", "200", "1", "2")
    assert session_direction(Session(current.instrument_id, current.local_date, current.profile_id, changed), profile()) == 1


def test_historical_spread_and_cost_stress_reduce_long_outcome():
    current = session()
    conversion = conversion_rows(current)
    zero = build_outcome(current, profile(), 1, 0, conversion, {})
    stress = build_outcome(current, profile(), 1, 15, conversion, {})
    assert zero is not None and stress is not None
    assert zero.unit_return > stress.unit_return
    assert zero.entry_time == current.bars[12].observed_at
    assert zero.exit_time == current.bars[16].observed_at


def test_protective_stop_fails_at_adverse_price_and_missing_conversion_fails_closed():
    current = session()
    changed = dict(current.bars)
    changed[13] = bar(changed[13].observed_at, "98", "99", "97", "98")
    stopped_session = Session(current.instrument_id, current.local_date, current.profile_id, changed)
    conversion = conversion_rows(stopped_session)
    outcome = build_outcome(stopped_session, profile(), 1, 5, conversion, {})
    assert outcome is not None
    assert outcome.exit_reason == "protective_stop"
    assert outcome.unit_return < 0
    with pytest.raises(OandaHourlyError, match="missing GBP conversion"):
        build_outcome(current, profile(), 1, 5, {}, {})


def test_contract_rejects_final_partition_or_parameter_drift(tmp_path: Path):
    value = json.loads(CONTRACT.read_text())
    value["partitions"]["initial_run_may_read_final_sealed_values"] = True
    unsafe = tmp_path / "unsafe.json"
    unsafe.write_text(canonical_json(value))
    with pytest.raises(OandaHourlyError, match="partitions changed"):
        load_contract(unsafe, ROOT)


def test_a2_module_is_offline_and_has_no_runtime_payloads():
    source = (ROOT / "src/trading_platform/cross_asset_session_breakout.py").read_text()
    tree = ast.parse(source)
    imports = {
        alias.name
        for node in ast.walk(tree)
        for alias in (node.names if isinstance(node, ast.Import) else ())
    }
    imports.update(
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module
    )
    assert not any(name.startswith(("urllib", "requests", "psycopg", "nats", "freqtrade")) for name in imports)
    assert "SignalPayload" not in source
    assert "OrderIntent" not in source
