import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "analyze_btc_conditional_reversal.py"
SPEC = importlib.util.spec_from_file_location("analyze_btc_conditional_reversal", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_quantile_is_deterministic():
    assert MODULE.quantile([0, 10], 0.9) == 9
    assert MODULE.quantile([4, 1, 3, 2], 0.5) == 2.5


def test_day_bootstrap_is_reproducible():
    events=[(day*86_400_000, -0.001 if day%2 else 0.0002) for day in range(20)]
    assert MODULE.bootstrap_days(events, seed=9, replicates=100) == MODULE.bootstrap_days(events, seed=9, replicates=100)
