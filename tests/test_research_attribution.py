from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

np = pytest.importorskip("numpy", reason="research attribution tests require requirements-research.txt")
pd = pytest.importorskip("pandas", reason="research attribution tests require requirements-research.txt")

from scripts.backtest_multi_asset_top2 import PAIR_TO_STEM, Signal, run_backtest
from trading_platform.execution_model import ExecutionScenario
from trading_platform.research_attribution import (
    AttributionSignal,
    block_bootstrap_mean_interval,
    friction_adjusted_return,
    matched_gate_distribution,
    ols_alpha_beta,
    random_top2_distribution,
    require_child_path,
    require_output_path,
    selected_pairs,
    validate_attribution_signals,
)


UNIVERSE = tuple(PAIR_TO_STEM)


def scenario(fee: str = "0", implicit: str = "0") -> ExecutionScenario:
    return ExecutionScenario(
        scenario_id="unit-test",
        mode="candle_taker",
        taker_fee_bps=Decimal(fee),
        maker_fee_bps=Decimal("0"),
        implicit_cost_bps_per_side=Decimal(implicit),
        price_protection_bps=Decimal("100"),
    )


def attribution_signal() -> AttributionSignal:
    signal_time = pd.Timestamp("2025-01-01T00:00:00Z")
    return AttributionSignal(
        signal_time=signal_time,
        decision_time=signal_time + pd.Timedelta(minutes=15),
        entry_time=signal_time + pd.Timedelta(minutes=15),
        ranked_pairs=("BTC/USDT", "ETH/USDT"),
        top4_pairs=("BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT"),
    )


def test_signal_validation_enforces_completed_information_and_midnight_cadence():
    signal = attribution_signal()
    validate_attribution_signals(
        [signal], UNIVERSE, pd.Timestamp("2026-01-01T00:00:00Z")
    )
    invalid = AttributionSignal(
        signal_time=signal.signal_time,
        decision_time=signal.signal_time,
        entry_time=signal.signal_time,
        ranked_pairs=signal.ranked_pairs,
        top4_pairs=signal.top4_pairs,
    )
    with pytest.raises(ValueError, match="decision must follow"):
        validate_attribution_signals(
            [invalid], UNIVERSE, pd.Timestamp("2026-01-01T00:00:00Z")
        )


def test_control_selection_is_frozen_and_remainder_excludes_ranked_pairs():
    signal = attribution_signal()
    assert selected_pairs(signal, "ranked_top2", UNIVERSE) == signal.ranked_pairs
    assert selected_pairs(signal, "gate_qualified_top4_equal_weight", UNIVERSE) == signal.top4_pairs
    remainder = selected_pairs(signal, "eligible_remainder_equal_weight", UNIVERSE)
    assert len(remainder) == 5
    assert not set(remainder).intersection(signal.ranked_pairs)


def test_friction_adjusted_return_applies_both_sides_of_cost():
    zero = friction_adjusted_return(100.0, 110.0, scenario())
    costed = friction_adjusted_return(100.0, 110.0, scenario(fee="10", implicit="5"))
    assert zero == pytest.approx(0.10)
    assert costed < zero
    assert costed == pytest.approx((110 * 0.9995 * 0.999) / (100 * 1.0005 * 1.001) - 1)


def test_random_controls_and_bootstrap_are_seed_deterministic():
    matrix = np.arange(35, dtype=float).reshape(5, 7) / 10_000
    first = random_top2_distribution(matrix, simulations=100, seed=11)
    second = random_top2_distribution(matrix, simulations=100, seed=11)
    assert np.array_equal(first, second)

    pools = [np.asarray([0.01, 0.02]), np.asarray([-0.01, 0.03, 0.04])]
    assert np.array_equal(
        matched_gate_distribution(pools, 100, 12),
        matched_gate_distribution(pools, 100, 12),
    )

    values = [0.01, -0.02, 0.03, 0.04]
    blocks = ["2025-01", "2025-01", "2025-02", "2025-03"]
    interval_a = block_bootstrap_mean_interval(values, blocks, 200, 13, 0.95)
    interval_b = block_bootstrap_mean_interval(values, blocks, 200, 13, 0.95)
    assert interval_a == interval_b


def test_ols_recovers_known_alpha_and_beta():
    market = np.asarray([-0.02, -0.01, 0.0, 0.01, 0.02])
    selected = 0.003 + 1.5 * market
    result = ols_alpha_beta(selected, market)
    assert result["alpha_per_event"] == pytest.approx(0.003)
    assert result["beta"] == pytest.approx(1.5)
    assert result["r_squared"] == pytest.approx(1.0)


def test_offline_path_guards_reject_boundary_escape(tmp_path: Path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    inside = allowed / "input"
    inside.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    assert require_child_path(inside, allowed, "fixture") == inside.resolve()
    assert require_output_path(allowed / "new-output", allowed) == (allowed / "new-output").resolve()
    with pytest.raises(ValueError, match="escapes frozen boundary"):
        require_child_path(outside, allowed, "fixture")
    with pytest.raises(ValueError, match="escapes frozen boundary"):
        require_output_path(outside / "new-output", allowed)


def flat_frames() -> dict[str, pd.DataFrame]:
    dates = pd.date_range("2021-01-01T00:00:00Z", periods=194, freq="15min")
    return {
        pair: pd.DataFrame(
            {
                "date": dates,
                "open": 100.0,
                "high": 100.0,
                "low": 100.0,
                "close": 100.0,
                "volume": 1.0,
            }
        )
        for pair in UNIVERSE
    }


@pytest.mark.parametrize(
    ("pairs", "expected_legs"),
    [
        (("BTC/USDT",), 1),
        (("BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT"), 4),
    ],
)
def test_shared_capital_runner_allocates_full_basket_budget_across_any_leg_count(
    pairs: tuple[str, ...], expected_legs: int
):
    signal_time = pd.Timestamp("2021-01-01T00:00:00Z")
    signal = Signal(
        signal_time=signal_time,
        decision_time=signal_time + pd.Timedelta(minutes=15),
        entry_time=signal_time + pd.Timedelta(minutes=15),
        pairs=pairs,
        top4_pairs=("BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT"),
        scores=(1.0, 0.9),
    )
    result, cohorts = run_backtest(flat_frames(), [signal], scenario(), "daily", False)
    assert result["cohorts"] == 1
    assert result["net_return"] == pytest.approx(0.0, abs=1e-8)
    assert cohorts[0]["entry_cost"] == pytest.approx(250.0, abs=1e-5)
    assert len(cohorts[0]["pairs"].split(",")) == expected_legs
