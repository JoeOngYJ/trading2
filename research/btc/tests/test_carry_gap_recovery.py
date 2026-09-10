import importlib.util
import json
from pathlib import Path
import unittest


MODULE_PATH = Path(__file__).resolve().parents[3] / "scripts/recover_btc_carry_gaps.py"
SPEC = importlib.util.spec_from_file_location("carry_gap_recovery", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def row(opened, opening="100", high="102", low="99", close="101"):
    return [opened, opening, high, low, close, "0", opened + MODULE.HOUR_MS - 1, "0", 0, "0", "0", "0"]


class CarryGapRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads(MODULE.CONTRACT_PATH.read_text(encoding="utf-8"))
        cls.spec = cls.contract["frozen_requests"][0]

    def test_contract_matches_exact_b2_gaps(self):
        MODULE.verify_contract(self.contract)

    def test_request_url_is_public_exact_and_allowlisted(self):
        url = MODULE.request_url(self.contract, self.spec)
        self.assertTrue(url.startswith("https://fapi.binance.com/fapi/v1/markPriceKlines?symbol=BTCUSDT"))
        self.assertIn("interval=1h", url)
        self.assertIn("limit=24", url)
        self.assertNotIn("apiKey", url)
        self.assertNotIn("signature", url)

    def test_exact_response_passes(self):
        rows = [row(timestamp) for timestamp in MODULE.expected_times(self.spec)]
        validated = MODULE.validate_response_rows(json.dumps(rows).encode(), self.spec)
        self.assertEqual(len(validated), 24)

    def test_empty_response_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "expected 24 rows"):
            MODULE.validate_response_rows(b"[]", self.spec)

    def test_extra_or_missing_timestamp_fails_closed(self):
        rows = [row(timestamp) for timestamp in MODULE.expected_times(self.spec)]
        rows[-1][0] += MODULE.HOUR_MS
        rows[-1][6] += MODULE.HOUR_MS
        with self.assertRaisesRegex(ValueError, "do not exactly match"):
            MODULE.validate_response_rows(json.dumps(rows).encode(), self.spec)

    def test_duplicate_timestamp_fails_closed(self):
        rows = [row(timestamp) for timestamp in MODULE.expected_times(self.spec)]
        rows[-1] = list(rows[-2])
        with self.assertRaisesRegex(ValueError, "do not exactly match"):
            MODULE.validate_response_rows(json.dumps(rows).encode(), self.spec)

    def test_invalid_hour_boundary_fails_closed(self):
        rows = [row(timestamp) for timestamp in MODULE.expected_times(self.spec)]
        rows[0][6] += 1
        with self.assertRaisesRegex(ValueError, "exact one-hour"):
            MODULE.validate_response_rows(json.dumps(rows).encode(), self.spec)

    def test_nonfinite_and_invalid_ohlc_fail_closed(self):
        rows = [row(timestamp) for timestamp in MODULE.expected_times(self.spec)]
        rows[0][2] = "NaN"
        with self.assertRaisesRegex(ValueError, "not finite"):
            MODULE.validate_response_rows(json.dumps(rows).encode(), self.spec)
        rows[0][2] = "98"
        with self.assertRaisesRegex(ValueError, "ordering"):
            MODULE.validate_response_rows(json.dumps(rows).encode(), self.spec)

    def test_naive_reversed_and_misaligned_timestamps_fail(self):
        with self.assertRaisesRegex(ValueError, "explicit UTC"):
            MODULE.parse_utc_ms("2021-01-01T00:00:00")
        reversed_spec = dict(self.spec, start_open_at=self.spec["end_open_at"], end_open_at=self.spec["start_open_at"])
        with self.assertRaisesRegex(ValueError, "reversed"):
            MODULE.expected_times(reversed_spec)
        with self.assertRaisesRegex(ValueError, "exact UTC hour"):
            MODULE.parse_utc_ms("2021-01-01T00:00:01Z")

    def test_gap_blocks_are_exact(self):
        start = MODULE.parse_utc_ms("2021-01-01T00:00:00Z")
        end = MODULE.parse_utc_ms("2021-01-01T04:00:00Z")
        present = {start, start + MODULE.HOUR_MS, end}
        self.assertEqual(
            MODULE.gap_blocks(present, start, end),
            [{
                "first_missing_open_at": "2021-01-01T02:00:00Z",
                "last_missing_open_at": "2021-01-01T03:00:00Z",
                "missing_hours": 2,
            }],
        )


if __name__ == "__main__":
    unittest.main()
