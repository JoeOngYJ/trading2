import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


ACQUIRE = load("spot_perp_acquisition_v2", ROOT / "scripts/acquire_btc_spot_perp_continuation_data_v2.py")
AUDIT = load("spot_perp_audit_v2", ROOT / "scripts/audit_btc_spot_perp_continuation_data_v2.py")


class SpotPerpContinuationDataV2Tests(unittest.TestCase):
    def test_month_sequence_is_exact(self):
        months = ACQUIRE.month_sequence()
        self.assertEqual(len(months), 76)
        self.assertEqual(months[0], (2019, 9))
        self.assertEqual(months[-1], (2025, 12))

    def test_spot_millisecond_and_microsecond_timestamps(self):
        self.assertEqual(AUDIT.spot_timestamp_ms("1735689600000"), 1735689600000)
        self.assertEqual(AUDIT.spot_timestamp_ms("1735689600000000"), 1735689600000)
        self.assertEqual(AUDIT.spot_timestamp_ms("1735693199999999", close_time=True), 1735693199999)

    def test_spot_timestamp_remainders_fail_closed(self):
        with self.assertRaises(ValueError):
            AUDIT.spot_timestamp_ms("1735689600000001")
        with self.assertRaises(ValueError):
            AUDIT.spot_timestamp_ms("1735693199999000", close_time=True)

    def test_parse_post_2025_microsecond_spot_kline(self):
        row = [
            "1735689600000000",
            "100",
            "102",
            "99",
            "101",
            "2",
            "1735693199999999",
            "201",
            "3",
            "1",
            "101",
            "0",
        ]
        parsed = AUDIT.parse_spot_kline(row)
        self.assertEqual(parsed[0], 1735689600000)
        self.assertEqual(parsed[6], 1735693199999)


if __name__ == "__main__":
    unittest.main()
