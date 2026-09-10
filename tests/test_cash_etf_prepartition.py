from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from trading_platform.cash_etf_prepartition import (
    CashEtfPrepartitionError,
    _copy_one,
    Boundary,
    extract_date,
)


def test_extract_date_reads_only_selected_routing_field():
    line = b'{"close":"not-a-number","session":"2020-01-02"}\n'
    assert extract_date(line, "session").isoformat() == "2020-01-02"
    with pytest.raises(CashEtfPrepartitionError, match="exactly one"):
        extract_date(b'{"session":"2020-01-02","session":"2020-01-03"}\n', "session")


def test_copy_partitions_original_bytes_and_leaves_empty_actions(tmp_path):
    source = tmp_path / "source.jsonl"
    source.write_bytes(
        b'{"action_date":"2018-12-31","amount":"1"}\n'
        b'{"action_date":"2019-01-02","amount":"2"}\n'
    )
    outputs = {"development": tmp_path / "dev", "validation": tmp_path / "val", "historical_confirmation": tmp_path / "hold"}
    boundaries = (
        Boundary("development", __import__("datetime").date(2009, 1, 2), __import__("datetime").date(2019, 1, 1)),
        Boundary("validation", __import__("datetime").date(2019, 1, 1), __import__("datetime").date(2024, 1, 1)),
        Boundary("historical_confirmation", __import__("datetime").date(2024, 1, 1), __import__("datetime").date(2026, 1, 1)),
    )
    summaries = _copy_one(source, outputs, "action_date", boundaries)
    assert outputs["development"].read_bytes().endswith(b'"1"}\n')
    assert summaries["validation"]["rows"] == 1
    assert outputs["historical_confirmation"].read_bytes() == b""


def test_copy_rejects_excluded_2026_row(tmp_path):
    source = tmp_path / "source.jsonl"
    source.write_bytes(b'{"session":"2026-01-02","close":"1"}\n')
    outputs = {"development": tmp_path / "dev", "validation": tmp_path / "val", "historical_confirmation": tmp_path / "hold"}
    boundaries = (
        Boundary("development", __import__("datetime").date(2009, 1, 2), __import__("datetime").date(2019, 1, 1)),
        Boundary("validation", __import__("datetime").date(2019, 1, 1), __import__("datetime").date(2024, 1, 1)),
        Boundary("historical_confirmation", __import__("datetime").date(2024, 1, 1), __import__("datetime").date(2026, 1, 1)),
    )
    with pytest.raises(CashEtfPrepartitionError, match="excluded 2026"):
        _copy_one(source, outputs, "session", boundaries)
