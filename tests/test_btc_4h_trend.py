import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "backtest_btc_4h_trend.py"
SPEC = importlib.util.spec_from_file_location("backtest_btc_4h_trend", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_mark_to_market_drawdown_includes_open_trade():
    bars=[]
    for i in range(40):
        price=100+i if i<32 else 70
        bars.append(MODULE.Bar(0,i*MODULE.FOUR_HOURS_MS,price,price,price,price))
    result=MODULE.run(bars,10,2)
    assert result["trades"] >= 1
    assert result["max_drawdown"] < -0.3


def test_segment_boundary_forces_flat():
    bars=[]
    for i in range(35):
        price=100+i
        bars.append(MODULE.Bar(0,i*MODULE.FOUR_HOURS_MS,price,price,price,price))
    for i in range(35):
        price=200+i
        bars.append(MODULE.Bar(1,(100+i)*MODULE.FOUR_HOURS_MS,price,price,price,price))
    result=MODULE.run(bars,0,0)
    assert result["forced_segment_exits"] >= 1


def test_matched_buy_hold_reports_drawdown():
    prices=[100,120,60,90]
    bars=[MODULE.Bar(0,i*MODULE.FOUR_HOURS_MS,p,p,p,p) for i,p in enumerate(prices)]
    result=MODULE.matched_buy_hold(bars,0,0)
    assert result["max_drawdown"] == -0.5
