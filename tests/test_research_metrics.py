import json
import math

import pytest

from trading_platform.research_metrics import (
    DAY_MS,
    EquityObservation,
    ResearchMetricError,
    TradeObservation,
    build_backtest_scorecard,
    canonical_bytes,
    equity_from_returns,
    validate_equity_path,
    validate_trial_registry,
)


def _returns(count: int, base: float = 0.0004) -> list[tuple[str, float]]:
    start = 1_577_836_800_000
    return [
        (
            __import__("datetime").datetime.fromtimestamp(
                (start + index * DAY_MS) / 1000,
                tz=__import__("datetime").timezone.utc,
            ).strftime("%Y-%m-%d"),
            base + (0.0002 if index % 3 else -0.0001),
        )
        for index in range(count)
    ]


def _trades(count: int) -> list[TradeObservation]:
    start = 1_577_836_800_000
    return [
        TradeObservation(
            trade_id=f"trade-{index:03d}",
            entry_ms=start + index * 15 * DAY_MS,
            exit_ms=start + index * 15 * DAY_MS + 5 * DAY_MS,
            pnl_quote=3.0 if index % 4 else -1.0,
            allocated_quote=100.0,
            cost_quote=0.3,
            turnover_quote=200.0,
        )
        for index in range(count)
    ]


def _scorecard(trade_count: int = 40, trial_history_complete: bool = True):
    returns = _returns(800)
    equity = equity_from_returns(returns)
    flat = equity_from_returns([(day, 0.0) for day, _ in returns])
    return build_backtest_scorecard(
        experiment_id="fixture-alpha-v1",
        strategy_family="fixture-alpha",
        evaluation_role="alpha_strategy",
        evidence_partition="fixture-development",
        source_digest="1" * 64,
        result_digest="2" * 64,
        original_disposition="development_control",
        equity=equity,
        starting_equity=1000.0,
        trades=_trades(trade_count),
        controls={"flat": flat},
        required_control_ids=["flat"],
        dependence_days=5,
        severe_cost_net_return=0.05,
        cost_summary={
            "gross_profit_quote": 120.0,
            "net_profit_quote": 100.0,
            "total_cost_quote": 20.0,
            "turnover_quote": 8000.0,
        },
        trial_history_complete=trial_history_complete,
        annual_trial_sharpes=[0.5, 0.6, 0.7],
        strategy_specific_gates={"maximum_drawdown": True},
        bootstrap_replications=250,
    )


def test_scorecard_is_deterministic_strict_json():
    left = _scorecard()
    right = _scorecard()
    assert left == right
    assert left["scorecard_digest"] == right["scorecard_digest"]
    encoded = canonical_bytes(left)
    assert json.loads(encoded)
    assert b"NaN" not in encoded and b"Infinity" not in encoded
    assert left["actionable_arm_id"] == "no_trade"
    assert left["accepted_strategy_arms"] == []


def test_six_trade_headline_is_insufficient_and_unknown_trials_fail_closed():
    scorecard = _scorecard(trade_count=6, trial_history_complete=False)
    assert scorecard["gates"]["universal"]["independent_economic_outcomes"]["status"] == "insufficient"
    assert scorecard["gates"]["universal"]["trial_history"]["status"] == "insufficient"
    assert scorecard["gates"]["role"]["deflated_sharpe"]["status"] == "insufficient"
    assert scorecard["supplemental_disposition"] == "supplemental_evidence_insufficient"


def test_positive_serial_correlation_reduces_adjusted_sharpe():
    values = []
    state = 0.0
    for index in range(800):
        innovation = 0.0004 if (index // 20) % 2 == 0 else -0.0002
        state = 0.85 * state + innovation
        values.append(state + 0.0002)
    days = _returns(800)
    equity = equity_from_returns([(day, value) for (day, _), value in zip(days, values, strict=True)])
    flat = equity_from_returns([(day, 0.0) for day, _ in days])
    scorecard = build_backtest_scorecard(
        experiment_id="serial-v1",
        strategy_family="serial",
        evaluation_role="control",
        evidence_partition="fixture",
        source_digest="3" * 64,
        result_digest="4" * 64,
        original_disposition="control",
        equity=equity,
        starting_equity=1000.0,
        trades=[],
        controls={"flat": flat},
        required_control_ids=["flat"],
        dependence_days=20,
        severe_cost_net_return=None,
        cost_summary={},
        trial_history_complete=False,
        annual_trial_sharpes=[],
        strategy_specific_gates={},
        continuous_exposure=True,
        bootstrap_replications=100,
    )
    raw = scorecard["performance"]["conventional_sharpe"]
    adjusted = scorecard["performance"]["autocorrelation_adjusted_sharpe"]
    assert math.isfinite(raw) and math.isfinite(adjusted)
    assert adjusted < raw


def test_equity_validation_rejects_gap_duplicate_and_invalid_value():
    with pytest.raises(ResearchMetricError, match="gap"):
        validate_equity_path(
            [EquityObservation(0, 1000), EquityObservation(2 * DAY_MS, 1001)]
        )
    with pytest.raises(ResearchMetricError, match="duplicated"):
        validate_equity_path(
            [EquityObservation(0, 1000), EquityObservation(0, 1001)]
        )
    with pytest.raises(ResearchMetricError, match="finite and positive"):
        EquityObservation(0, float("nan"))


def test_required_control_timeline_and_digest_fail_closed():
    returns = _returns(800)
    equity = equity_from_returns(returns)
    short_flat = equity_from_returns([(day, 0.0) for day, _ in returns[:-1]])
    with pytest.raises(ResearchMetricError, match="control timeline"):
        build_backtest_scorecard(
            experiment_id="bad-control",
            strategy_family="fixture",
            evaluation_role="alpha_strategy",
            evidence_partition="fixture",
            source_digest="1" * 64,
            result_digest="2" * 64,
            original_disposition="rejected",
            equity=equity,
            starting_equity=1000,
            trades=_trades(40),
            controls={"flat": short_flat},
            required_control_ids=["flat"],
            dependence_days=5,
            severe_cost_net_return=0.01,
            cost_summary={},
            trial_history_complete=True,
            annual_trial_sharpes=[0.1],
            strategy_specific_gates={},
            bootstrap_replications=50,
        )


def test_trial_registry_requires_explicit_complete_unique_history():
    result = validate_trial_registry(
        [
            {
                "sequence": 1,
                "experiment_id": "a-v1",
                "strategy_family": "a",
                "outcome_inspected": True,
                "family_history_complete": False,
            },
            {
                "sequence": 2,
                "experiment_id": "b-v1",
                "strategy_family": "b",
                "outcome_inspected": False,
                "family_history_complete": True,
            },
        ]
    )
    assert result["trials"] == 2
    assert result["families"]["a"]["complete"] is False
    with pytest.raises(ResearchMetricError, match="duplicate"):
        validate_trial_registry(
            [
                {
                    "sequence": 1,
                    "experiment_id": "a-v1",
                    "strategy_family": "a",
                    "outcome_inspected": True,
                    "family_history_complete": False,
                },
                {
                    "sequence": 2,
                    "experiment_id": "a-v1",
                    "strategy_family": "a",
                    "outcome_inspected": True,
                    "family_history_complete": False,
                },
            ]
        )
