from __future__ import annotations

import ast
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from trading_platform.research_routing import (
    ArmForecast,
    CounterfactualRouter,
    RegimeFeatureObservation,
    RegimeState,
    ResearchRoutingError,
    RoutingDecision,
    StrategyArmRegistry,
    StrategyArmSpec,
    validate_feature_sequence,
)


UTC = timezone.utc
T0 = datetime(2025, 12, 31, 23, 59, tzinfo=UTC)
DIGEST_A = "a" * 64
DIGEST_B = "b" * 64
DIGEST_C = "c" * 64
ROOT = Path(__file__).resolve().parents[1]


def registry() -> StrategyArmRegistry:
    return StrategyArmRegistry(
        registry_id="fixture-registry-v1",
        arms=(
            StrategyArmSpec(
                arm_id="no_trade",
                version="1",
                family="flat",
                direction="flat",
                horizon="none",
                maximum_cost_bps=0,
                capacity_fraction=0,
                evidence_status="eligible",
                evidence_digest=DIGEST_A,
            ),
            StrategyArmSpec(
                arm_id="btc_breakout_20d_10d",
                version="1",
                family="btc_directional_trend",
                direction="spot_long_or_flat",
                horizon="14d_maximum",
                maximum_cost_bps=80,
                capacity_fraction=0.10,
                evidence_status="development",
                evidence_digest=DIGEST_B,
            ),
            StrategyArmSpec(
                arm_id="btc_bocpd_gated_breakout",
                version="1",
                family="btc_directional_trend",
                direction="spot_long_or_flat",
                horizon="14d_maximum",
                maximum_cost_bps=80,
                capacity_fraction=0.10,
                evidence_status="rejected",
                evidence_digest=DIGEST_C,
            ),
        ),
    )


def forecast(arm_id: str, score: float, confidence: float = 0.5) -> ArmForecast:
    return ArmForecast(
        arm_id=arm_id,
        arm_version="1",
        decision_at=T0,
        available_at=T0 - timedelta(minutes=1),
        expires_at=T0 + timedelta(hours=1),
        forecast_score=score,
        confidence=confidence,
        horizon="fixture",
        abstention_reason=None,
        lineage_digest=DIGEST_A,
    )


def state(**updates: object) -> RegimeState:
    values = {
        "model_id": "fixture-risk-model",
        "model_version": "1",
        "instrument": "BTC/USDT",
        "interval": "1d",
        "segment": "fixture-segment",
        "observed_at": T0 - timedelta(days=1),
        "available_at": T0 - timedelta(hours=23),
        "fit_cutoff": T0 - timedelta(days=2),
        "probabilities": {"ordinary_risk": 0.7, "stress_risk": 0.3},
        "confidence": 0.7,
        "entropy": 0.61,
        "state_age": 3,
        "transition_probability": 0.1,
        "transition_reason": "forward_filter",
        "cutoffs": {"fit_epoch": 1.0},
    }
    values.update(updates)
    return RegimeState(**values)  # type: ignore[arg-type]


def test_development_arm_can_win_counterfactual_but_never_actionable_route():
    decision = CounterfactualRouter(registry()).route(
        T0,
        [
            forecast("no_trade", 0.0, 1.0),
            forecast("btc_breakout_20d_10d", 0.4, 0.6),
            forecast("btc_bocpd_gated_breakout", 999.0, 1.0),
        ],
    )
    assert decision.counterfactual_arm_id == "btc_breakout_20d_10d"
    assert decision.actionable_arm_id == "no_trade"
    assert decision.disposition == "counterfactual_only"
    assert "btc_bocpd_gated_breakout" not in decision.considered_arm_ids
    assert any(reason.startswith("rejected_arms_excluded") for reason in decision.reasons)


def test_missing_input_and_unknown_state_fail_closed():
    router = CounterfactualRouter(registry())
    missing = router.route(T0, [forecast("no_trade", 0.0)])
    assert missing.counterfactual_arm_id == "no_trade"
    assert missing.considered_arm_ids == ("no_trade",)
    assert "fail_closed" in missing.reasons

    unknown = router.route(
        T0,
        [forecast("no_trade", 0.0), forecast("btc_breakout_20d_10d", 1.0)],
        regime_state=state(unknown_reason="insufficient_history"),
    )
    assert unknown.counterfactual_arm_id == "no_trade"
    assert unknown.actionable_arm_id == "no_trade"
    assert "regime_state_unknown_or_stale" in unknown.reasons

    with pytest.raises(ResearchRoutingError, match="future-dependent"):
        router.route(
            T0,
            [forecast("no_trade", 0.0), forecast("btc_breakout_20d_10d", 1.0)],
            regime_state=state(available_at=T0 + timedelta(seconds=1)),
        )


def test_ranking_tie_break_is_deterministic():
    first = CounterfactualRouter(registry()).route(
        T0,
        [forecast("btc_breakout_20d_10d", 0.0, 1.0), forecast("no_trade", 0.0, 1.0)],
    )
    second = CounterfactualRouter(registry()).route(
        T0,
        [forecast("no_trade", 0.0, 1.0), forecast("btc_breakout_20d_10d", 0.0, 1.0)],
    )
    assert first.counterfactual_arm_id == "btc_breakout_20d_10d"
    assert first.as_dict() == second.as_dict()
    assert first.digest == second.digest


def test_timestamps_probabilities_duplicates_and_staleness_are_rejected():
    with pytest.raises(ResearchRoutingError, match="timezone-aware UTC"):
        replace(forecast("no_trade", 0.0), decision_at=datetime(2025, 1, 1))

    with pytest.raises(ResearchRoutingError, match="stale"):
        ArmForecast(
            arm_id="no_trade",
            arm_version="1",
            decision_at=T0,
            available_at=T0 - timedelta(minutes=1),
            expires_at=T0,
            forecast_score=0,
            confidence=1,
            horizon="none",
            abstention_reason=None,
            lineage_digest=DIGEST_A,
        )
    with pytest.raises(ResearchRoutingError, match="sum to one"):
        state(probabilities={"ordinary_risk": 0.7, "stress_risk": 0.4})
    with pytest.raises(ResearchRoutingError, match="duplicate key"):
        state(probabilities=[("ordinary_risk", 0.5), ("ordinary_risk", 0.5)])
    with pytest.raises(ResearchRoutingError, match="unique"):
        StrategyArmRegistry(
            registry_id="duplicate",
            arms=(registry().arms[0], registry().arms[0]),
        )


def test_feature_observations_are_causal_checksummed_and_segment_bound():
    one = RegimeFeatureObservation(
        instrument="BTC/USDT",
        interval="1d",
        segment="segment-a",
        observed_at=T0 - timedelta(days=2),
        available_at=T0 - timedelta(days=2),
        feature_values={"volatility": 0.1, "jump": 0.2},
        source_digest=DIGEST_A,
    )
    two = RegimeFeatureObservation(
        instrument="BTC/USDT",
        interval="1d",
        segment="segment-a",
        observed_at=T0 - timedelta(days=1),
        available_at=T0 - timedelta(days=1),
        feature_values={"jump": 0.3, "volatility": 0.2},
        source_digest=DIGEST_A,
    )
    assert one.feature_digest == one.feature_digest
    assert len(one.as_dict()["feature_digest"]) == 64
    assert validate_feature_sequence([one, two]) == (one, two)

    crossing = RegimeFeatureObservation(
        instrument="BTC/USDT",
        interval="1d",
        segment="segment-b",
        observed_at=T0,
        available_at=T0,
        feature_values={"jump": 0.4},
        source_digest=DIGEST_A,
    )
    with pytest.raises(ResearchRoutingError, match="crosses a source segment"):
        validate_feature_sequence([one, crossing])
    with pytest.raises(ResearchRoutingError, match="cannot precede"):
        RegimeFeatureObservation(
            instrument="BTC/USDT",
            interval="1d",
            segment="segment-a",
            observed_at=T0,
            available_at=T0 - timedelta(seconds=1),
            feature_values={"jump": 0.1},
            source_digest=DIGEST_A,
        )


def test_routing_decision_constructor_cannot_authorize_an_arm():
    with pytest.raises(ResearchRoutingError, match="fixed to no_trade"):
        RoutingDecision(
            decision_at=T0,
            considered_arm_ids=("btc_breakout_20d_10d",),
            counterfactual_arm_id="btc_breakout_20d_10d",
            actionable_arm_id="btc_breakout_20d_10d",
            disposition="counterfactual_only",
            reasons=("fixture",),
        )


def test_offline_routing_module_has_no_production_or_external_imports():
    path = ROOT / "src/trading_platform/research_routing.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert not any(name.startswith("trading_platform.") for name in imported)
    assert imported.isdisjoint({"ccxt", "httpx", "nats", "psycopg", "requests"})
