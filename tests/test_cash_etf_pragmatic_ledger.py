from __future__ import annotations

import json
from pathlib import Path

import pytest

from trading_platform.cash_etf_pragmatic_ledger import (
    CashEtfPragmaticLedgerError,
    build_ledger_rows,
    convert_ledger_to_gbp,
    parse_fred_dexusuk_patch,
    read_price_rows,
    split_candidates,
)


def price(session: str, open_price: str, close: str, available_at: str) -> dict[str, str]:
    return {
        "available_at": available_at,
        "close": close,
        "high": str(max(float(open_price), float(close))),
        "instrument_id": "US-ARCX-BIL-USD",
        "low": str(min(float(open_price), float(close))),
        "observed_at": f"{session}T00:00:00Z",
        "open": open_price,
        "session": session,
        "source_lineage_sha256": "a" * 64,
        "symbol": "BIL",
        "volume": "1",
    }


def test_split_candidate_finds_two_for_one_discontinuity() -> None:
    rows = [
        price("2017-11-29", "50", "50", "2017-11-30T05:00:00Z"),
        price("2017-11-30", "100", "101", "2017-12-01T05:00:00Z"),
    ]
    assert split_candidates(rows, ["2", "3"], "0.05", "0.25") == [
        {
            "date": "2017-11-30",
            "observed_open_previous_close_ratio": "2",
            "relative_distance": "0",
            "suspected_ratio": "2",
        }
    ]


def test_reverse_split_multiplier_removes_false_return() -> None:
    rows = [
        price("2017-11-29", "50", "50", "2017-11-30T05:00:00Z"),
        price("2017-11-30", "100", "100", "2017-12-01T05:00:00Z"),
    ]
    ledger = build_ledger_rows(
        "BIL",
        rows,
        [],
        [{"action_date": "2017-11-30", "from_factor": "1", "to_factor": "2"}],
    )
    assert ledger[1]["price_return"] == "0"
    assert ledger[1]["total_return"] == "0"
    assert ledger[1]["wealth_index"] == "1"


def test_distribution_is_credited_on_ex_date() -> None:
    rows = [
        price("2023-01-02", "100", "100", "2023-01-03T05:00:00Z"),
        price("2023-01-03", "99", "99", "2023-01-04T05:00:00Z"),
    ]
    ledger = build_ledger_rows(
        "BIL",
        rows,
        [
            {
                "amount_per_share": "1",
                "ex_date": "2023-01-03",
                "source_role": "official_issuer_history",
            }
        ],
        [],
    )
    assert ledger[1]["price_return"] == "-0.01"
    assert ledger[1]["total_return"] == "0"


def test_usd_total_return_converts_causally_to_gbp() -> None:
    rows = [
        price("2023-01-02", "100", "100", "2023-01-03T05:00:00Z"),
        price("2023-01-03", "110", "110", "2023-01-04T05:00:00Z"),
    ]
    usd = build_ledger_rows("BIL", rows, [], [])
    fx = [
        {**price("2023-01-02", "2", "2", "2023-01-03T05:00:00Z"), "symbol": "GBP/USD"},
        {**price("2023-01-03", "2.2", "2.2", "2023-01-04T05:00:00Z"), "symbol": "GBP/USD"},
    ]
    gbp = convert_ledger_to_gbp(usd, fx)
    assert gbp[1]["total_return_usd"] == "0.1"
    assert gbp[1]["total_return"] == "0"
    assert gbp[1]["wealth_index"] == "1"


def test_price_reader_never_deserializes_post_boundary_row(tmp_path: Path) -> None:
    path = tmp_path / "prices.jsonl"
    valid = price("2023-12-29", "100", "100", "2023-12-30T05:00:00Z")
    path.write_text(
        json.dumps(valid, separators=(",", ":"))
        + '\n{"session":"2024-01-02","this_is_not_valid_json":}\n',
        encoding="utf-8",
    )
    rows, post_boundary = read_price_rows(path, "BIL", "2023-12-29", "2023-12-31")
    assert len(rows) == 1
    assert post_boundary == 0


def test_price_reader_rejects_naive_availability(tmp_path: Path) -> None:
    path = tmp_path / "prices.jsonl"
    row = price("2023-12-29", "100", "100", "2023-12-30T05:00:00Z")
    row["available_at"] = "2023-12-30T05:00:00"
    path.write_text(json.dumps(row, separators=(",", ":")) + "\n", encoding="utf-8")
    with pytest.raises(CashEtfPragmaticLedgerError, match="explicit UTC"):
        read_price_rows(path, "BIL", "2023-12-29", "2023-12-31")


def fred_config() -> dict[str, object]:
    return {
        "availability_policy": "observation_date_plus_10_calendar_days_at_23_59_59Z",
        "expected_dates": ["2011-04-15", "2013-10-08"],
        "expected_series_id": "DEXUSUK",
        "expected_units": "USD_per_GBP",
        "maximum_response_bytes": 1000,
        "release_policy_evidence_url": "https://www.federalreserve.gov/Releases/h10/",
        "source_url": "https://fred.stlouisfed.org/",
    }


def test_fred_patch_selects_only_frozen_dates_with_delayed_availability() -> None:
    response = (
        b"observation_date,DEXUSUK\n"
        b"2011-04-15,1.6320\n"
        b"2011-04-18,1.6280\n"
        b"2013-10-08,1.6085\n"
    )
    patch = parse_fred_dexusuk_patch(response, fred_config())
    assert [row["session"] for row in patch["rows"]] == ["2011-04-15", "2013-10-08"]
    assert patch["rows"][0]["available_at"] == "2011-04-25T23:59:59Z"
    assert patch["rows"][0]["close"] == "1.632"


def test_fred_patch_rejects_missing_frozen_date() -> None:
    response = b"observation_date,DEXUSUK\n2011-04-15,1.6320\n"
    with pytest.raises(CashEtfPragmaticLedgerError, match="missing FRED"):
        parse_fred_dexusuk_patch(response, fred_config())
