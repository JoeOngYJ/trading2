import importlib.util
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


ACQUIRE = load("spot_perp_acquisition", ROOT / "scripts/acquire_btc_spot_perp_continuation_data.py")
AUDIT = load("spot_perp_audit", ROOT / "scripts/audit_btc_spot_perp_continuation_data.py")


class SpotPerpContinuationDataTests(unittest.TestCase):
    def test_sidecar_digest_requires_exact_filename(self):
        digest = "a" * 64
        payload = f"{digest}  BTCUSDT-1h-2019-12-31.zip\n".encode()
        self.assertEqual(
            ACQUIRE.expected_sidecar_digest(payload, "BTCUSDT-1h-2019-12-31.zip"),
            digest,
        )
        with self.assertRaises(ValueError):
            ACQUIRE.expected_sidecar_digest(payload, "wrong.zip")

    def test_allowlist_rejects_http_credentials_and_wrong_host(self):
        allowed = {"fapi.binance.com"}
        for url in (
            "http://fapi.binance.com/fapi/v1/klines",
            "https://user:pass@fapi.binance.com/fapi/v1/klines",
            "https://example.com/fapi/v1/klines",
        ):
            with self.assertRaises(ValueError):
                ACQUIRE.allowed_url(url, allowed)

    def test_output_must_be_new_and_below_repository(self):
        with self.assertRaises(ValueError):
            ACQUIRE.ensure_output_path(Path("/tmp/outside-repository"))
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            with self.assertRaises(FileExistsError):
                ACQUIRE.ensure_output_path(Path(directory))

    def test_parse_valid_hourly_kline(self):
        row = [
            1577836800000,
            "100",
            "102",
            "99",
            "101",
            "2",
            1577840399999,
            "201",
            3,
            "1",
            "101",
            "0",
        ]
        parsed = AUDIT.parse_kline(row)
        self.assertEqual(parsed[0], 1577836800000)
        self.assertEqual(parsed[4], Decimal("101"))

    def test_parse_rejects_bad_boundary_and_volume(self):
        base = [
            1577836800000,
            "100",
            "102",
            "99",
            "101",
            "2",
            1577840399999,
            "201",
            3,
            "1",
            "101",
        ]
        bad_boundary = list(base)
        bad_boundary[6] -= 1
        with self.assertRaises(ValueError):
            AUDIT.parse_kline(bad_boundary)
        bad_volume = list(base)
        bad_volume[7] = "-1"
        with self.assertRaises(ValueError):
            AUDIT.parse_kline(bad_volume)

    def test_conflicting_and_exact_duplicates_fail_closed(self):
        row = (1577836800000, Decimal("1"))
        target = {}
        AUDIT.add_unique(target, row, "first")
        with self.assertRaises(ValueError):
            AUDIT.add_unique(target, row, "duplicate")
        with self.assertRaises(ValueError):
            AUDIT.add_unique(target, (row[0], Decimal("2")), "conflict")

    def test_segments_split_discontinuities(self):
        start = 1577836800000
        segments = AUDIT.build_segments([
            start,
            start + AUDIT.HOUR_MS,
            start + 3 * AUDIT.HOUR_MS,
        ])
        self.assertEqual([item["hours"] for item in segments], [2, 1])

    def test_ninety_day_feature_readiness_is_past_only(self):
        start = datetime(2019, 9, 1, tzinfo=timezone.utc)
        end = start + timedelta(days=100) - timedelta(hours=1)
        segments = [{
            "start_open_at": start.isoformat().replace("+00:00", "Z"),
            "end_open_at": end.isoformat().replace("+00:00", "Z"),
            "hours": 100 * 24,
        }]
        by_year, _ = AUDIT.feature_ready_counts(segments, 90)
        # Decisions at day 90 through the segment-end boundary at day 100
        # each have 90 fully completed prior days.
        self.assertEqual(sum(by_year.values()), 11)


if __name__ == "__main__":
    unittest.main()
