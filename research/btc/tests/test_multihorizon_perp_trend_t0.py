import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location(
    "trend_t0", ROOT / "scripts/audit_btc_multihorizon_perp_trend_t0.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class TrendT0Tests(unittest.TestCase):
    def test_continuity_detects_exact_gap(self):
        hour = MODULE.HOUR_MS
        self.assertEqual(MODULE.contiguous_missing({0, hour, 3 * hour}, 0, 3 * hour, hour), [2 * hour])

    def test_invalid_continuity_boundary_rejected(self):
        with self.assertRaises(ValueError):
            MODULE.contiguous_missing(set(), 1, MODULE.HOUR_MS, MODULE.HOUR_MS)

    def test_decision_uses_completed_history_and_next_01_open(self):
        hour = MODULE.HOUR_MS
        # Day boundary 72h: completed bar is 71h, 2h lookback begins 69h, fill is 73h.
        timestamps = set(range(69 * hour, 74 * hour, hour))
        eligible, _ = MODULE.eligible_daily_decisions(
            timestamps, 72 * hour, 73 * hour, horizon_hours=2
        )
        self.assertEqual(eligible, [72 * hour + 5 * 60_000])

    def test_missing_next_open_fails_closed(self):
        hour = MODULE.HOUR_MS
        timestamps = set(range(69 * hour, 73 * hour, hour))
        eligible, ineligible = MODULE.eligible_daily_decisions(
            timestamps, 72 * hour, 73 * hour, horizon_hours=2
        )
        self.assertEqual(eligible, [])
        self.assertEqual(len(ineligible), 1)


if __name__ == "__main__":
    unittest.main()
