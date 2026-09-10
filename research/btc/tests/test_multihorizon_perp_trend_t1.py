import math
import unittest
from decimal import Decimal

from trading_platform.btc_multihorizon_trend import (
    SyntheticHour,
    TrendResearchError,
    ewma_daily_variance,
    funding_cashflow,
    multihorizon_score,
    risk_fraction,
    seeded_control_directions,
    shocked_margin_ratio,
    simulate_synthetic,
    target_direction,
)


class TrendT1Tests(unittest.TestCase):
    def test_ewma_initialization_and_update(self):
        returns = [0.01] * 20 + [0.02]
        expected = 0.94 * 0.0001 + 0.06 * 0.0004
        self.assertAlmostEqual(ewma_daily_variance(returns), expected)

    def test_score_is_causal_and_positive_for_smooth_rise(self):
        closes = [100 * math.exp(0.01 * index) for index in range(85)]
        score = multihorizon_score(closes)
        self.assertGreater(score, 0.25)
        changed_future = closes + [1.0]
        self.assertEqual(score, multihorizon_score(changed_future[:-1]))

    def test_score_fails_closed_on_bad_or_short_history(self):
        with self.assertRaises(TrendResearchError):
            multihorizon_score([100.0] * 84)
        with self.assertRaises(TrendResearchError):
            multihorizon_score([100.0] * 84 + [0.0])

    def test_thresholds_are_strict(self):
        self.assertEqual(target_direction(0.2500001), 1)
        self.assertEqual(target_direction(0.25), 0)
        self.assertEqual(target_direction(-0.25), 0)
        self.assertEqual(target_direction(-0.2500001), -1)

    def test_risk_fraction_only_scales_down(self):
        self.assertEqual(risk_fraction(0.01), 0.25)
        self.assertLess(risk_fraction(0.20), 0.25)

    def test_funding_signs(self):
        args = (Decimal("1"), Decimal("100"), Decimal("0.001"))
        self.assertEqual(funding_cashflow(1, *args), Decimal("-0.100"))
        self.assertEqual(funding_cashflow(-1, *args), Decimal("0.100"))

    def test_short_adverse_stress_is_up_and_long_is_down(self):
        long_ratio = shocked_margin_ratio(1, Decimal("1"), Decimal("100"), Decimal("100"), Decimal("75"))
        short_ratio = shocked_margin_ratio(-1, Decimal("1"), Decimal("100"), Decimal("100"), Decimal("75"))
        self.assertEqual(long_ratio, Decimal("5"))
        self.assertEqual(short_ratio, Decimal("1.666666666666666666666666667"))

    def test_seeded_control_is_local_and_deterministic(self):
        self.assertEqual(seeded_control_directions(20), seeded_control_directions(20))
        self.assertTrue(set(seeded_control_directions(200)).issubset({-1, 0, 1}))

    def test_reversal_charges_close_and_open_quantity(self):
        bars = [
            SyntheticHour(0, Decimal("100"), Decimal("100"), Decimal("100")),
            SyntheticHour(3_600_000, Decimal("100"), Decimal("100"), Decimal("100")),
        ]
        result = simulate_synthetic(bars, {0: 1, 3_600_000: -1})
        self.assertEqual(len(result["fills"]), 2)
        # Reversal delta is approximately twice one side; equity is marked after entry cost.
        self.assertLess(Decimal(result["fills"][1]["quantity_delta"]), Decimal("-4.99"))
        self.assertEqual(result["actionable_arm_id"], "no_trade")

    def test_gap_forces_severe_flatten(self):
        bars = [
            SyntheticHour(0, Decimal("100"), Decimal("100"), Decimal("100")),
            SyntheticHour(7_200_000, Decimal("100"), Decimal("100"), Decimal("100")),
        ]
        result = simulate_synthetic(bars, {0: 1})
        self.assertEqual(result["fills"][-1]["reason"], "data_gap_neutralization")

    def test_positive_funding_rewards_short_in_ledger(self):
        bars = [SyntheticHour(0, Decimal("100"), Decimal("100"), Decimal("100"), Decimal("0.001"))]
        long = simulate_synthetic(bars, {0: 1})
        short = simulate_synthetic(bars, {0: -1})
        self.assertLess(Decimal(long["funding_cashflow"]), 0)
        self.assertGreater(Decimal(short["funding_cashflow"]), 0)


if __name__ == "__main__":
    unittest.main()
