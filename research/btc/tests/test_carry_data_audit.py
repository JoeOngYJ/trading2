import importlib.util
from pathlib import Path
import unittest


MODULE_PATH = Path(__file__).resolve().parents[3] / "scripts/audit_btc_carry_data.py"
SPEC = importlib.util.spec_from_file_location("carry_audit", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class CarryDataAuditTests(unittest.TestCase):
    def test_millisecond_timestamp(self):
        self.assertEqual(MODULE.timestamp_ms("1577836800000"), (1577836800000, "milliseconds"))

    def test_aligned_microsecond_timestamp(self):
        self.assertEqual(MODULE.timestamp_ms("1735689600000000"), (1735689600000, "microseconds"))

    def test_unaligned_microsecond_timestamp_fails(self):
        with self.assertRaises(ValueError):
            MODULE.timestamp_ms("1735689600000001")

    def test_funding_jitter_normalizes_to_scheduled_event(self):
        scheduled = 1_735_689_600_000
        self.assertEqual(MODULE.scheduled_funding_timestamp(scheduled + 47), (scheduled, 47))

    def test_funding_jitter_at_one_second_fails_closed(self):
        scheduled = 1_735_689_600_000
        with self.assertRaises(ValueError):
            MODULE.scheduled_funding_timestamp(scheduled + 1_000)

    def test_frozen_source_manifest_has_no_archive_failure(self):
        source = MODULE.json.loads(MODULE.SOURCE_MANIFEST.read_text())
        self.assertEqual(source["archive_failures"], 0)
        self.assertEqual(len(source["archive_records"]), 360)


if __name__ == "__main__":
    unittest.main()
