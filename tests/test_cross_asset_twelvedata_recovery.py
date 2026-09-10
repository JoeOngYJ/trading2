from __future__ import annotations

import json
from pathlib import Path

import pytest

from trading_platform.cross_asset_twelvedata_audit import canonical_json
from trading_platform.cross_asset_twelvedata_history import TwelveDataHistoryError
from trading_platform.cross_asset_twelvedata_recovery import (
    build_request_specs,
    inherited_split_lines,
    load_contract,
    merge_dividend_windows,
    merge_price_windows,
    phase_offsets,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/experiments/cross-asset-a1-twelvedata-recovery-v3.json"


def _instrument(symbol: str):
    _, pilot, _ = load_contract(CONTRACT, ROOT)
    return next(item for item in pilot["instruments"] if item["symbol"] == symbol)


def _price_payload(symbol: str, rows: list[dict[str, str]]):
    instrument = _instrument(symbol)
    meta = {"interval": "1day", "symbol": symbol, "type": instrument["expected_type"]}
    if symbol == "GBP/USD":
        meta.update({"currency_base": "British Pound", "currency_quote": "US Dollar"})
    else:
        meta.update({"currency": instrument["expected_currency"], "exchange": instrument["expected_exchange_values"][0], "mic_code": instrument["expected_mic_code"]})
    return {"meta": meta, "values": rows}


def _row(day: str, close: str = "100"):
    return {"close": close, "datetime": day, "high": "102", "low": "98", "open": "99", "volume": "1000"}


def _write(path: Path, value: object) -> Path:
    path.write_text(canonical_json(value), encoding="utf-8")
    return path


def test_v3_contract_freezes_51_calls_507_credits_and_13_phases():
    contract, _, calendar = load_contract(CONTRACT, ROOT)
    specs = build_request_specs(contract)
    assert len(specs) == 51
    assert sum(item.weight for item in specs) == 507
    assert phase_offsets(contract)[13] == 732
    assert len(calendar["us_sessions"]) == 4529
    assert contract["decision_rule"]["instrument_decisions_are_independent"] is True
    assert contract["decision_rule"]["a1_stage_passed_by_recovery"] is False


def test_price_windows_require_exact_overlap_and_quarantine_extra_dates(tmp_path):
    instrument = _instrument("SPY")
    p1 = _write(tmp_path / "p1.json", _price_payload("SPY", [_row("2025-01-02"), _row("2025-01-03")]))
    p2 = _write(tmp_path / "p2.json", _price_payload("SPY", [_row("2025-01-03"), _row("2025-01-04")]))
    result, lines = merge_price_windows([p1, p2], instrument, ["2025-01-02", "2025-01-03"], fx=False)
    assert result["quarantined_dates"] == ["2025-01-04"]
    assert len(lines) == 2
    bad = _write(tmp_path / "bad.json", _price_payload("SPY", [_row("2025-01-03", "101")]))
    with pytest.raises(TwelveDataHistoryError, match="conflicting overlap"):
        merge_price_windows([p1, bad], instrument, ["2025-01-02", "2025-01-03"], fx=False)


def test_internal_duplicate_dates_fail_instead_of_deduplicating(tmp_path):
    instrument = _instrument("EEM")
    payload = _price_payload("EEM", [_row("2025-01-02"), _row("2025-01-02", "100.1")])
    path = _write(tmp_path / "eem.json", payload)
    with pytest.raises(Exception, match="session sequence mismatch"):
        merge_price_windows([path], instrument, ["2025-01-02"], fx=False)


def test_fx_gaps_are_bounded_and_never_filled(tmp_path):
    instrument = _instrument("GBP/USD")
    path = _write(tmp_path / "fx.json", _price_payload("GBP/USD", [_row("2025-01-02"), _row("2025-01-06")]))
    expected = ["2025-01-02", "2025-01-03", "2025-01-06"]
    result, lines = merge_price_windows([path], instrument, expected, fx=True, maximum_missing_fraction=__import__("decimal").Decimal("0.5"), maximum_gap=1)
    assert result["missing_sessions"] == ["2025-01-03"]
    assert len(lines) == 2
    with pytest.raises(TwelveDataHistoryError, match="consecutive gap"):
        merge_price_windows([path], instrument, expected, fx=True, maximum_missing_fraction=__import__("decimal").Decimal("0.5"), maximum_gap=0)


def test_dividend_cap_and_overlap_conflicts_fail(tmp_path):
    instrument = _instrument("SPY")
    meta = {"currency": "USD", "mic_code": "ARCX", "symbol": "SPY"}
    p1 = _write(tmp_path / "d1.json", {"dividends": [{"amount": 1, "ex_date": "2025-01-02"}], "meta": meta})
    p2 = _write(tmp_path / "d2.json", {"dividends": [{"amount": 2, "ex_date": "2025-01-02"}], "meta": meta})
    with pytest.raises(TwelveDataHistoryError, match="conflicting dividend overlap"):
        merge_dividend_windows([p1, p2], instrument, 100, None)
    capped = _write(tmp_path / "cap.json", {"dividends": [{"amount": 1, "ex_date": f"2025-01-{(i % 28) + 1:02d}"} for i in range(100)], "meta": meta})
    with pytest.raises(TwelveDataHistoryError, match="reaches frozen cap"):
        merge_dividend_windows([capped], instrument, 100, None)


def test_split_semantics_distinguish_price_and_unit_multipliers():
    contract, _, _ = load_contract(CONTRACT, ROOT)
    _, lines = inherited_split_lines(ROOT, contract, _instrument("EEM"))
    row = json.loads(lines[0])
    assert row["price_multiplier"] == "0.33333"
    assert row["unit_multiplier"] == "3"
