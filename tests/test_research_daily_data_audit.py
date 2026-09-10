import json
from pathlib import Path

import pytest

from scripts.audit_btc_regime_routing_s2_daily_data import affected_history, reconcile
from scripts.download_btc_regime_routing_daily_audit import (
    parse_official_checksum,
    periods,
    timestamp_ms,
)
from trading_platform.research_ledger import write_jsonl_gzip
from trading_platform.research_program import canonical_json


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT = REPO_ROOT / "config/experiments/btc-regime-routing-s2-daily-data-audit-v1.json"
S2_V1_CONTRACT = REPO_ROOT / "config/experiments/btc-regime-routing-s2-ewma-v1.json"
S2_V2_CONTRACT = REPO_ROOT / "config/experiments/btc-regime-routing-s2-ewma-v2.json"


def direct_row(open_at: str, available_at: str, close: str = "101") -> dict:
    return {
        "available_at": available_at,
        "base_volume": "12",
        "close": close,
        "high": "102",
        "low": "99",
        "open": "100",
        "open_at": open_at,
        "quote_volume": "1200",
        "source_archive": "fixture.zip",
        "source_archive_sha256": "a" * 64,
        "trade_count": 5,
    }


def test_frozen_daily_audit_contract_is_canonical_and_data_only():
    raw = CONTRACT.read_text(encoding="utf-8")
    payload = json.loads(raw)
    assert raw == canonical_json(payload)
    assert payload["output"]["economic_metrics_allowed"] is False
    assert payload["output"]["forecast_generation_allowed"] is False
    assert payload["boundaries"]["sealed_2026_access_allowed"] is False


def test_s2_v2_changes_source_not_frozen_model_or_gates():
    v1 = json.loads(S2_V1_CONTRACT.read_text(encoding="utf-8"))
    raw = S2_V2_CONTRACT.read_text(encoding="utf-8")
    v2 = json.loads(raw)
    assert raw == canonical_json(v2)
    for key in (
        "action_mapping",
        "controls",
        "economic_scorecard",
        "parameters",
        "robustness",
        "statistics",
        "validity_gates",
    ):
        assert v2[key] == v1[key]
    assert v2["data"]["daily_risk_source"]["feature_fields"] == ["close"]
    assert v2["isolation"]["holdout_access_allowed"] is False


def test_daily_archive_periods_and_checksum_parsing():
    assert len(periods("2017-08", "2025-12")) == 101
    assert parse_official_checksum(("f" * 64 + "  file.zip\n").encode(), "file.zip") == "f" * 64
    with pytest.raises(ValueError, match="invalid official checksum"):
        parse_official_checksum(b"short\n", "file.zip")


def test_timestamp_normalization_rejects_non_millisecond_microseconds():
    assert timestamp_ms("1735689600000000", "fixture.zip") == (
        1735689600000,
        "microseconds",
    )
    with pytest.raises(ValueError, match="unsupported timestamp"):
        timestamp_ms("1735689600000001", "fixture.zip")


def test_affected_history_counts_only_consecutive_completed_returns():
    direct = [
        direct_row("2020-01-01T00:00:00Z", "2020-01-02T00:00:00Z"),
        direct_row("2020-01-02T00:00:00Z", "2020-01-03T00:00:00Z"),
        direct_row("2020-01-03T00:00:00Z", "2020-01-04T00:00:00Z"),
    ]
    result = affected_history(
        direct, ["2020-01-03T00:00:00Z", "2020-01-05T00:00:00Z"]
    )
    assert result[0]["consecutive_completed_returns"] == 1
    assert result[1] == {
        "available": False,
        "consecutive_completed_returns": 0,
        "observation_at": "2020-01-05T00:00:00Z",
    }


def test_reconciliation_reports_price_mismatch_without_hiding_overlap(tmp_path):
    direct = [direct_row("2020-01-01T00:00:00Z", "2020-01-02T00:00:00Z")]
    s1_path = tmp_path / "s1.jsonl.gz"
    write_jsonl_gzip(
        s1_path,
        [
            {
                "base_volume": 12,
                "close": 101,
                "high": 102,
                "low": 99,
                "open": 100.5,
                "open_at": "2020-01-01T00:00:00Z",
                "quote_volume": 1200,
            }
        ],
    )
    result = reconcile(direct, s1_path, __import__("decimal").Decimal("0.000001"))
    assert result["overlapping_daily_bars"] == 1
    assert result["ohlc_mismatch_count"] == 1
    assert result["ohlc_mismatches"] == [
        {"fields": ["open"], "open_at": "2020-01-01T00:00:00Z"}
    ]
