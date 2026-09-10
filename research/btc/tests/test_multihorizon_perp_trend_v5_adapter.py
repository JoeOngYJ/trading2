import importlib.util
import unittest
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location(
    "trend_v5_runner", ROOT / "scripts/run_btc_multihorizon_perp_trend_v5.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class TrendV5AdapterTests(unittest.TestCase):
    def test_metrics_bootstrap_is_deterministic(self):
        day = 24 * MODULE.HOUR_MS
        daily = [(index * day, Decimal(1000 + index)) for index in range(100)]
        first = MODULE._metrics(daily, [Decimal("1"), Decimal("-0.5")], 100.0, Decimal("1000"))
        second = MODULE._metrics(daily, [Decimal("1"), Decimal("-0.5")], 100.0, Decimal("1000"))
        self.assertEqual(first, second)

    def test_signals_need_completed_84_day_history(self):
        class Bar:
            def __init__(self, close):
                self.close = Decimal(str(close))

        bars = {}
        day = 24 * MODULE.HOUR_MS
        for index in range(90):
            bars[index * day + 23 * MODULE.HOUR_MS] = Bar(100 + index)
        signals = MODULE._signals(bars, 0, 89 * day + 23 * MODULE.HOUR_MS)
        first_execution = min(signals["candidate_fixed"])
        self.assertEqual(first_execution, 85 * day + MODULE.HOUR_MS)

    def test_contract_has_adapter_binding_list(self):
        import json
        contract = json.loads(MODULE.CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(contract["status"], "frozen_before_single_historical_run")
        self.assertGreaterEqual(len(contract["bound_inputs"]), 3)


if __name__ == "__main__":
    unittest.main()
