from __future__ import annotations

from pathlib import Path

import pytest

from trading_platform.cross_asset_a1_expansion import load_contract
from trading_platform.cross_asset_lse_history import (
    LseHistoryError,
    normalize_actions,
    normalize_prices,
)
from trading_platform.cross_asset_xlon_calendar import ExchangeSession


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/experiments/cross-asset-a1-lse-futures-expansion-v1.json"


def instrument(symbol: str = "SWDA") -> dict:
    contract = load_contract(CONTRACT, ROOT)
    return next(item for item in contract["listed_funds"] if item["symbol"] == symbol)


def session(day: str, *, half_day: bool = False) -> ExchangeSession:
    return ExchangeSession(
        mic="XLON",
        session_date=day,
        open_at=f"{day}T08:00:00Z",
        close_at=f"{day}T12:30:00Z" if half_day else f"{day}T16:30:00Z",
        half_day=half_day,
    )


def price_payload(days: list[str]) -> dict:
    return {
        "meta": {"currency": "GBp", "exchange": "LSE", "mic_code": "XLON", "symbol": "SWDA"},
        "values": [
            {"close": "100", "datetime": day, "high": "102", "low": "98", "open": "99", "volume": "10"}
            for day in days
        ],
    }


def test_price_normalization_preserves_raw_unit_and_half_day_without_returns():
    lines = normalize_prices(
        price_payload(["2025-12-24"]),
        instrument(),
        [session("2025-12-24", half_day=True)],
        "a" * 64,
    )
    assert len(lines) == 1
    assert '"close_gbp":"1"' in lines[0]
    assert '"raw_quote_unit":"GBp"' in lines[0]
    assert '"half_day":true' in lines[0]
    assert "return" not in lines[0] and "signal" not in lines[0]


def test_prices_reject_gap_duplicate_and_off_calendar_rows():
    expected = [session("2025-02-03"), session("2025-02-04")]
    with pytest.raises(LseHistoryError, match="missing 1"):
        normalize_prices(price_payload(["2025-02-03"]), instrument(), expected, "a" * 64)
    with pytest.raises(LseHistoryError, match="duplicate"):
        normalize_prices(
            price_payload(["2025-02-03", "2025-02-03"]),
            instrument(),
            [expected[0]],
            "a" * 64,
        )
    with pytest.raises(LseHistoryError, match="off-calendar"):
        normalize_prices(price_payload(["2025-02-05"]), instrument(), expected, "a" * 64)


def test_provider_actions_are_never_cash_credited_before_issuer_reconciliation():
    vags = instrument("VAGS")
    payload = {
        "dividends": [{"amount": "0.063699", "ex_date": "2025-02-13"}],
        "meta": {"currency": "GBP", "exchange": "LSE", "mic_code": "XLON", "symbol": "VAGS"},
    }
    lines = normalize_actions(payload, vags, "dividends", "b" * 64)
    assert '"cash_credit_eligible":false' in lines[0]
    assert '"issuer_reconciliation_status":"pending"' in lines[0]


def test_action_identity_and_boundary_fail_closed():
    payload = {
        "dividends": [{"amount": "1", "ex_date": "2008-01-01"}],
        "meta": {"currency": "GBp", "exchange": "LSE", "mic_code": "XLON", "symbol": "SWDA"},
    }
    with pytest.raises(LseHistoryError, match="outside"):
        normalize_actions(payload, instrument(), "dividends", "b" * 64)
