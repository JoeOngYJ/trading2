from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from trading_platform.research_risk import (
    DownwardOnlyRiskFusionPolicy,
    ResearchRiskError,
    RiskCap,
    RiskForecast,
    RiskPanel,
)


UTC = timezone.utc
DIGEST = "a" * 64
NOW = datetime(2025, 1, 2, 12, tzinfo=UTC)


def forecast(**updates: object) -> RiskForecast:
    values = {
        "detector_id": "ewma",
        "detector_version": "v2",
        "instrument": "BTCUSDT",
        "axis": "volatility",
        "clock": "daily",
        "horizon_seconds": 86400,
        "observed_at": NOW - timedelta(hours=12),
        "available_at": NOW - timedelta(hours=12),
        "expires_at": NOW + timedelta(hours=12),
        "fit_cutoff": NOW - timedelta(days=30),
        "units": "annualized_volatility_fraction",
        "point_estimate": 0.6,
        "lower_bound": 0.5,
        "upper_bound": 0.7,
        "confidence": 0.8,
        "evidence_status": "benchmark",
        "lineage_digests": {"feature": DIGEST},
    }
    values.update(updates)
    return RiskForecast(**values)  # type: ignore[arg-type]


def cap(axis: str, allocation: float, **updates: object) -> RiskCap:
    values = {
        "detector_id": f"{axis}-detector",
        "detector_version": "v1",
        "axis": axis,
        "clock": "daily" if axis != "jump_change" else "4h",
        "available_at": NOW - timedelta(hours=1),
        "expires_at": NOW + timedelta(hours=1),
        "maximum_allocation_fraction": allocation,
        "evidence_status": "accepted" if axis != "volatility" else "benchmark",
        "lineage_digest": DIGEST,
    }
    values.update(updates)
    return RiskCap(**values)  # type: ignore[arg-type]


def policy() -> DownwardOnlyRiskFusionPolicy:
    return DownwardOnlyRiskFusionPolicy(
        policy_id="btc-risk-fusion",
        policy_version="v1",
        required_axes=("downside_tail", "jump_change", "volatility"),
    )


def test_risk_forecast_serialization_is_deterministic_and_unknown_is_explicit():
    first = forecast()
    second = forecast(lineage_digests={"feature": DIGEST})
    assert first.as_dict() == second.as_dict()
    assert first.usable_at(NOW)
    unknown = forecast(
        point_estimate=None,
        lower_bound=None,
        upper_bound=None,
        unknown_reason="missing_input",
    )
    assert not unknown.usable_at(NOW)
    with pytest.raises(ResearchRiskError):
        forecast(point_estimate=0.8, lower_bound=0.9)


def test_panel_rejects_future_dependent_and_duplicate_forecasts():
    row = forecast()
    with pytest.raises(ResearchRiskError, match="duplicate"):
        RiskPanel(decision_at=NOW, forecasts=(row, row))
    with pytest.raises(ResearchRiskError, match="future-dependent"):
        RiskPanel(
            decision_at=NOW,
            forecasts=(
                forecast(
                    observed_at=NOW + timedelta(minutes=1),
                    available_at=NOW + timedelta(minutes=1),
                    expires_at=NOW + timedelta(hours=2),
                ),
            ),
        )


def test_new_entry_uses_minimum_cap_and_remains_non_executable():
    decision = policy().decide(
        decision_at=NOW,
        requested_allocation_fraction=0.20,
        prior_allocation_fraction=0,
        position_open=False,
        caps=(cap("volatility", 0.12), cap("downside_tail", 0.08), cap("jump_change", 0.10)),
    )
    assert decision.final_allocation_fraction == 0.08
    assert decision.actionable_arm_id == "no_trade"
    assert not decision.order_intent_created


def test_intratrade_derisking_never_releverages():
    reduced = policy().decide(
        decision_at=NOW,
        requested_allocation_fraction=0.20,
        prior_allocation_fraction=0.10,
        position_open=True,
        caps=(cap("volatility", 0.09), cap("downside_tail", 0.07), cap("jump_change", 0.08)),
    )
    assert reduced.final_allocation_fraction == 0.07
    unchanged = policy().decide(
        decision_at=NOW,
        requested_allocation_fraction=0.20,
        prior_allocation_fraction=0.05,
        position_open=True,
        caps=(cap("volatility", 0.12), cap("downside_tail", 0.10), cap("jump_change", 0.08)),
    )
    assert unchanged.final_allocation_fraction == 0.05


def test_missing_stale_unknown_or_development_required_axis_fails_closed():
    base = (cap("volatility", 0.1), cap("jump_change", 0.1))
    for tail in (
        None,
        cap("downside_tail", 0.1, expires_at=NOW),
        cap("downside_tail", 0.1, unknown_reason="missing_input"),
        cap("downside_tail", 0.1, evidence_status="development"),
    ):
        caps = base if tail is None else (*base, tail)
        decision = policy().decide(
            decision_at=NOW,
            requested_allocation_fraction=0.1,
            prior_allocation_fraction=0,
            position_open=False,
            caps=caps,
        )
        assert decision.final_allocation_fraction == 0
        assert "fail_closed" in decision.reasons[0]


def test_timestamps_probabilities_and_open_position_state_are_validated():
    with pytest.raises(ResearchRiskError):
        forecast(available_at=NOW - timedelta(days=31))
    with pytest.raises(ResearchRiskError):
        forecast(confidence=1.1)
    with pytest.raises(ResearchRiskError):
        policy().decide(
            decision_at=NOW,
            requested_allocation_fraction=0.1,
            prior_allocation_fraction=0,
            position_open=True,
            caps=(),
        )
