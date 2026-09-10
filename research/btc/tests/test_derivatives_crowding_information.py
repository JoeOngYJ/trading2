from datetime import date
import importlib.util
from pathlib import Path
import unittest


MODULE_PATH = Path(__file__).resolve().parents[1] / "evaluators/evaluate_derivatives_crowding_information.py"
SPEC = importlib.util.spec_from_file_location("crowding_information", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class DerivativesCrowdingInformationTests(unittest.TestCase):
    def test_past_zscore_excludes_current(self):
        prior = list(range(1, 61))
        actual = MODULE.past_zscore(100.0, prior, window=90, minimum=60)
        expected = (100.0 - 30.5) / MODULE.np.std(MODULE.np.asarray(prior), ddof=1)
        self.assertAlmostEqual(actual, expected)

    def test_past_zscore_fails_closed_without_minimum(self):
        self.assertIsNone(MODULE.past_zscore(3.0, [1.0, 2.0], window=90, minimum=3))

    def test_cftc_tuesday_is_not_available_until_saturday(self):
        report_date = date(2023, 12, 26)
        self.assertEqual(MODULE.cftc_available_at(report_date).isoformat(), "2023-12-30T00:00:00+00:00")

    def test_frozen_funding_source_accepts_subsecond_schedule_jitter(self):
        funding, audit = MODULE.load_funding(
            MODULE.ROOT / "artifacts/agent-level-experiment/btc-focused/derivatives-crowding-data-audit-v1/funding.json"
        )
        self.assertEqual(audit["invalid_days"], [])
        self.assertEqual(audit["complete_days"], 1461)

    def test_non_tuesday_cftc_rows_fail_closed(self):
        _, audit = MODULE.load_cftc(
            MODULE.ROOT / "artifacts/agent-level-experiment/btc-focused/derivatives-crowding-data-audit-v2/cftc-bitcoin-tff.json"
        )
        self.assertEqual(audit["excluded_non_tuesday_report_dates"], ["2020-12-21", "2023-07-03"])

    def test_future_labels_use_exactly_next_seven_days(self):
        start = date(2023, 1, 1)
        returns = {start + MODULE.timedelta(days=index): value for index, value in enumerate([0.1, -0.2, 0.05, 0.01, -0.01, 0.02, 0.03])}
        labels = MODULE.future_labels(returns, start)
        self.assertIsNotNone(labels)
        self.assertAlmostEqual(labels["next_7d_log_return"], 0.0)
        self.assertAlmostEqual(labels["next_7d_downside_path_loss"], 0.1)
        self.assertAlmostEqual(labels["next_7d_realized_variance"], 0.054)

    def test_future_labels_fail_closed_on_gap(self):
        self.assertIsNone(MODULE.future_labels({date(2023, 1, 1): 0.1}, date(2023, 1, 1)))


if __name__ == "__main__":
    unittest.main()
