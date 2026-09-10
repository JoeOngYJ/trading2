import importlib.util
import io
from pathlib import Path
import sys
import zipfile

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "extract_btc_taker_flow.py"
SPEC = importlib.util.spec_from_file_location("extract_btc_taker_flow", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def row(open_ts="1704067200000", close_ts="1704067499999", **changes):
    values = [open_ts, "100.00000000", "105.00000000", "95.00000000", "102.00000000",
              "10.00000000", close_ts, "1000.00000000", "20", "6.00000000", "600.00000000", "0"]
    indexes = {"open":1,"high":2,"low":3,"close":4,"base":5,"quote":7,"trades":8,"buy_base":9,"buy_quote":10,"ignore":11}
    for key, value in changes.items():
        values[indexes[key]] = value
    return values


def test_parses_and_derives_trade_flow_exactly():
    parsed = MODULE.parse_row(row(), "milliseconds")
    assert parsed.open_ms == 1704067200000
    assert parsed.values[11] == "4.00000000"
    assert parsed.values[13] == "0.600000000000000000"
    assert parsed.values[15] == "0.200000000000000000"
    assert parsed.values[17] == "0.500000000000000000"


def test_microseconds_normalize_exactly():
    parsed = MODULE.parse_row(row("1735689600000000", "1735689899999999"), "microseconds")
    assert parsed.open_ms == 1735689600000
    assert parsed.close_ms == 1735689899999


@pytest.mark.parametrize("changes", [
    {"buy_base":"11"}, {"buy_quote":"1001"}, {"low":"106"}, {"open":"0"},
    {"trades":"1.5"}, {"ignore":"1"},
])
def test_invalid_rows_are_rejected(changes):
    with pytest.raises(MODULE.ValidationError):
        MODULE.parse_row(row(**changes), "milliseconds")


def test_wrong_column_count_is_rejected():
    with pytest.raises(MODULE.ValidationError, match="12 columns"):
        MODULE.parse_row(row()[:-1], "milliseconds")


def test_zero_denominators_are_empty():
    parsed = MODULE.parse_row(row(base="0", quote="0", trades="0", buy_base="0", buy_quote="0"), "milliseconds")
    assert parsed.values[13:] == ("", "", "", "", "", "")


def test_mixed_timestamp_unit_is_rejected():
    with pytest.raises(MODULE.ValidationError, match="mixed timestamp unit"):
        MODULE.parse_row(row("1735689600000000", "1735689899999999"), "milliseconds")


def test_misaligned_and_wrong_duration_are_rejected():
    with pytest.raises(MODULE.ValidationError, match="aligned"):
        MODULE.parse_row(row("1704067200001", "1704067500000"), "milliseconds")
    with pytest.raises(MODULE.ValidationError, match="duration"):
        MODULE.parse_row(row(close_ts="1704067499998"), "milliseconds")


def test_zip_requires_exact_expected_csv_member():
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("wrong.csv", ",".join(row()) + "\n")
    with pytest.raises(MODULE.ValidationError, match="unexpected ZIP contents"):
        list(MODULE.iter_csv_rows(payload.getvalue(), "BTCUSDT-5m-2024-01.zip"))


def test_valid_zip_rows_are_streamed():
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("BTCUSDT-5m-2024-01.csv", ",".join(row()) + "\n")
    assert list(MODULE.iter_csv_rows(payload.getvalue(), "BTCUSDT-5m-2024-01.zip")) == [row()]
