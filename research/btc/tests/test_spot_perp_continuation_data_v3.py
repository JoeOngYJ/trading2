import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


ACQUIRE = load("spot_perp_acquisition_v3", ROOT / "scripts/acquire_btc_spot_perp_continuation_data_v3.py")
AUDIT = load("spot_perp_audit_v3", ROOT / "scripts/audit_btc_spot_perp_continuation_data_v3.py")


class SpotPerpContinuationDataV3Tests(unittest.TestCase):
    def test_archive_month_counts(self):
        self.assertEqual(len(ACQUIRE.month_sequence(2019, 9)), 76)
        self.assertEqual(len(ACQUIRE.month_sequence(2020, 1)), 72)

    def test_daily_millisecond_and_spot_microsecond_parsing(self):
        self.assertEqual(AUDIT.timestamp_ms("1735689600000", spot=False), 1735689600000)
        self.assertEqual(AUDIT.timestamp_ms("1735689600000000", spot=True), 1735689600000)
        self.assertEqual(AUDIT.timestamp_ms("1735775999999999", spot=True, close_time=True), 1735775999999)

    def test_perpetual_microseconds_and_bad_spot_remainders_fail(self):
        with self.assertRaises(ValueError):
            AUDIT.timestamp_ms("1735689600000000", spot=False)
        with self.assertRaises(ValueError):
            AUDIT.timestamp_ms("1735689600000001", spot=True)

    def test_parse_exact_daily_bar(self):
        row = [
            1577836800000,
            "100",
            "102",
            "99",
            "101",
            "2",
            1577923199999,
            "201",
            3,
            "1",
            "101",
            "0",
        ]
        self.assertEqual(AUDIT.parse_daily_kline(row, spot=False)[0], 1577836800000)

    def test_ninety_day_daily_readiness(self):
        start = datetime(2019, 9, 8, tzinfo=timezone.utc)
        end = start + timedelta(days=114)
        segments = [{
            "start_open_at": start.isoformat().replace("+00:00", "Z"),
            "end_open_at": end.isoformat().replace("+00:00", "Z"),
            "days": 115,
        }]
        by_year, _ = AUDIT.feature_ready_counts(segments, 90)
        # The final source day supports a decision on the following UTC day.
        self.assertEqual(sum(by_year.values()), 26)


if __name__ == "__main__":
    unittest.main()
