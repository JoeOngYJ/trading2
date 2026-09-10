from __future__ import annotations

import json
from pathlib import Path

import pytest

from trading_platform.cross_asset_data_audit import (
    CrossAssetDataAuditError,
    load_frozen_contract,
    parse_stooq_daily_csv,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/experiments/cross-asset-a1-lse-source-pilot-v1.json"


def csv_bytes(sessions: list[str]) -> bytes:
    rows = ["Date,Open,High,Low,Close,Volume"]
    rows.extend(f"{session},100,102,99,101,1000" for session in sessions)
    return ("\n".join(rows) + "\n").encode()


def sessions() -> list[str]:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))["boundaries"][
        "expected_lse_sessions"
    ]


def test_frozen_a1_contract_is_canonical_and_safe():
    contract = load_frozen_contract(CONTRACT)
    assert contract["pilot_id"] == "cross-asset-a1-lse-source-pilot-v1"
    assert contract["prohibitions"]["pnl_allowed"] is False
    assert contract["sources"]["stooq_daily_csv"]["maximum_requests"] == 4


def test_daily_csv_accepts_only_exact_frozen_session_coverage():
    expected = sessions()
    result = parse_stooq_daily_csv(csv_bytes(expected), ticker="SWDA", expected_sessions=expected)
    assert result.rows == 22
    assert result.first_session == "2025-01-02"
    assert result.last_session == "2025-01-31"

    with pytest.raises(CrossAssetDataAuditError, match="coverage mismatch"):
        parse_stooq_daily_csv(
            csv_bytes(expected[:-1]), ticker="SWDA", expected_sessions=expected
        )


@pytest.mark.parametrize(
    "row,error",
    [
        ("2025-01-02,100,102,99,101,", "missing"),
        ("2025-01-02,100,98,99,101,1000", "OHLC"),
        ("2025-01-02,100,102,99,101,-1", "volume"),
        ("2025-01-02,NaN,102,99,101,1000", "non-finite"),
    ],
)
def test_daily_csv_rejects_missing_invalid_and_non_finite_values(row: str, error: str):
    payload = f"Date,Open,High,Low,Close,Volume\n{row}\n".encode()
    with pytest.raises(CrossAssetDataAuditError, match=error):
        parse_stooq_daily_csv(payload, ticker="SWDA", expected_sessions=["2025-01-02"])


def test_daily_csv_rejects_unknown_ticker_and_schema():
    with pytest.raises(CrossAssetDataAuditError, match="unexpected ticker"):
        parse_stooq_daily_csv(csv_bytes(sessions()), ticker="FAKE", expected_sessions=sessions())
    with pytest.raises(CrossAssetDataAuditError, match="unexpected columns"):
        parse_stooq_daily_csv(b"Date,Close\n2025-01-02,100\n", ticker="SWDA", expected_sessions=sessions())


def test_daily_csv_rejects_an_http_200_browser_challenge_as_non_data():
    challenge = b"<!DOCTYPE html><html><body>This site requires JavaScript</body></html>"
    with pytest.raises(CrossAssetDataAuditError, match="unexpected columns"):
        parse_stooq_daily_csv(challenge, ticker="SWDA", expected_sessions=sessions())
