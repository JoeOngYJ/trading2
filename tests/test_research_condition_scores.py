from __future__ import annotations

import math
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.qualify_btc_market_condition_primitives import DEFAULT_CONTRACT, run
from trading_platform.research_condition_scores import (
    DAYS_PER_YEAR,
    ConditionScoreError,
    MarketConditionScore,
    MarketConditionScorePanel,
    annualized_completed_funding,
    completed_field_values,
    completed_short_perpetual_funding,
    corwin_schultz_high_low_spread_proxy,
    directional_efficiency,
    lag_one_autocovariance,
    mean_amihud_price_impact_proxy,
    overlapping_variance_ratio,
    perpetual_basis_fraction,
    realized_variation_components,
    standardized_displacement,
    volatility_scaled_return,
)
from trading_platform.research_market_conditions import MarketConditionObservation


UTC = timezone.utc
NOW = datetime(2025, 1, 2, 12, tzinfo=UTC)
DIGEST = "a" * 64


def score(**updates: object) -> MarketConditionScore:
    values = {
        "score_id": "synthetic-persistence",
        "score_version": "v1",
        "instrument": "SYNTHETIC",
        "venue": "OFFLINE_FIXTURE",
        "axis": "persistence",
        "score_kind": "continuous",
        "horizon_seconds": 14400,
        "fit_cutoff": NOW - timedelta(days=30),
        "observed_at": NOW - timedelta(hours=1),
        "available_at": NOW - timedelta(hours=1),
        "expires_at": NOW + timedelta(hours=3),
        "units": "dimensionless",
        "point_estimate": 0.2,
        "lower_bound": -0.1,
        "upper_bound": 0.5,
        "confidence": 0.6,
        "evidence_status": "development",
        "lineage_digests": {"synthetic_fixture": DIGEST},
    }
    values.update(updates)
    return MarketConditionScore(**values)  # type: ignore[arg-type]


def observation(index: int, *, available_offset_hours: int = 0, segment: str = "s1") -> MarketConditionObservation:
    observed = NOW - timedelta(hours=3 - index)
    return MarketConditionObservation(
        instrument="SYNTHETIC",
        venue="OFFLINE_FIXTURE",
        axis="persistence",
        interval="1h",
        segment=segment,
        window_started_at=observed - timedelta(hours=1),
        observed_at=observed,
        available_at=observed + timedelta(hours=available_offset_hours),
        field_values={"return": float(index)},
        lineage_digests={"fixture": DIGEST},
    )


def test_score_contract_is_canonical_and_never_promotes_development_evidence():
    first = score(lineage_digests={"synthetic_fixture": DIGEST})
    second = score()
    assert first.as_dict() == second.as_dict()
    assert first.available_for_research(NOW)
    assert not first.eligible_for_conditioning(NOW)
    assert score(evidence_status="accepted").eligible_for_conditioning(NOW)
    assert not score(evidence_status="rejected").eligible_for_conditioning(NOW)


def test_score_rejects_invalid_probability_timestamps_and_unknown_values():
    with pytest.raises(ConditionScoreError, match="probability"):
        score(score_kind="probability", point_estimate=1.1, lower_bound=0.5, upper_bound=1.2)
    with pytest.raises(ConditionScoreError, match="timestamps"):
        score(available_at=NOW + timedelta(hours=4))
    with pytest.raises(ConditionScoreError, match="unknown score"):
        score(unknown_reason="gap")
    unknown = score(
        point_estimate=None,
        lower_bound=None,
        upper_bound=None,
        unknown_reason="insufficient_history",
    )
    assert not unknown.available_for_research(NOW)
    with pytest.raises(ConditionScoreError, match="unsupported score axis"):
        score(axis="universal_regime")


def test_score_panel_rejects_duplicates_and_future_information_without_aggregation():
    current = score()
    panel = MarketConditionScorePanel(decision_at=NOW, scores=(current,))
    assert panel.as_dict()["score_digests"] == [current.digest]
    assert not hasattr(panel, "aggregate_score")
    with pytest.raises(ConditionScoreError, match="duplicate"):
        MarketConditionScorePanel(decision_at=NOW, scores=(current, current))
    future = score(
        observed_at=NOW + timedelta(minutes=1),
        available_at=NOW + timedelta(minutes=1),
        expires_at=NOW + timedelta(hours=4),
    )
    with pytest.raises(ConditionScoreError, match="future-dependent"):
        MarketConditionScorePanel(decision_at=NOW, scores=(future,))


def test_completed_field_extraction_rejects_future_unknown_and_cross_segment_rows():
    rows = (observation(1), observation(2), observation(3))
    assert completed_field_values(rows, field_name="return", decision_at=NOW, minimum=3) == (
        1.0,
        2.0,
        3.0,
    )
    with pytest.raises(ConditionScoreError, match="causally available"):
        completed_field_values(
            (*rows[:2], observation(3, available_offset_hours=2)),
            field_name="return",
            decision_at=NOW,
        )
    with pytest.raises(ConditionScoreError, match="segment"):
        completed_field_values(
            (*rows[:2], observation(3, segment="s2")),
            field_name="return",
            decision_at=NOW,
        )
    unknown = MarketConditionObservation(
        instrument="SYNTHETIC",
        venue="OFFLINE_FIXTURE",
        axis="persistence",
        interval="1h",
        segment="s1",
        window_started_at=NOW - timedelta(hours=1),
        observed_at=NOW,
        available_at=NOW,
        field_values={},
        lineage_digests={"fixture": DIGEST},
        unknown_reason="gap",
    )
    with pytest.raises(ConditionScoreError, match="gap"):
        completed_field_values((unknown,), field_name="return", decision_at=NOW)


def test_persistence_and_reversion_primitives_match_frozen_formulas():
    returns = (0.01, 0.02, -0.01)
    assert volatility_scaled_return(returns) == pytest.approx(0.02 / math.sqrt(0.0006))
    assert directional_efficiency(returns) == pytest.approx(0.5)
    assert lag_one_autocovariance((1.0, 2.0, 4.0)) == pytest.approx(-1 / 18)
    assert overlapping_variance_ratio((1.0, -1.0, 1.0, -1.0, 1.0, -1.0), 2) == 0
    assert standardized_displacement((1.0, 2.0, 3.0), 4.0) == pytest.approx(2.0)


def test_realized_variation_separates_sign_and_nonnegative_jump_component():
    components = realized_variation_components((0.001, 0.001, 0.1))
    expected_bipower = (math.pi / 2) * (3 / 2) * (0.000001 + 0.0001)
    assert components.realized_variance == pytest.approx(0.010002)
    assert components.positive_semivariance == pytest.approx(0.010002)
    assert components.negative_semivariance == 0
    assert components.bipower_variation == pytest.approx(expected_bipower)
    assert components.nonnegative_jump_variation == pytest.approx(0.010002 - expected_bipower)
    assert 0 < components.jump_share < 1
    mixed = realized_variation_components((0.01, -0.02))
    assert mixed.positive_semivariance == pytest.approx(0.0001)
    assert mixed.negative_semivariance == pytest.approx(0.0004)


def test_liquidity_proxies_are_formula_exact_but_not_fill_costs():
    assert mean_amihud_price_impact_proxy((0.01, -0.02), (1000.0, 2000.0)) == pytest.approx(
        0.00001
    )
    spread = corwin_schultz_high_low_spread_proxy(110.0, 100.0, 110.0, 100.0)
    assert spread == pytest.approx(2 * (1.1 - 1) / (1 + 1.1))
    assert corwin_schultz_high_low_spread_proxy(100.0, 100.0, 100.0, 100.0) == 0
    with pytest.raises(ConditionScoreError, match="strictly positive"):
        mean_amihud_price_impact_proxy((0.01,), (0.0,))
    with pytest.raises(ConditionScoreError, match="positive highs"):
        corwin_schultz_high_low_spread_proxy(90, 100, 110, 100)


def test_carry_transforms_preserve_completed_payment_and_basis_semantics():
    rates = (0.0001, 0.0002, -0.0001)
    expected = (sum(rates) / len(rates)) * 3 * DAYS_PER_YEAR
    assert annualized_completed_funding(rates) == pytest.approx(expected)
    assert completed_short_perpetual_funding(rates) == pytest.approx(0.0002)
    assert perpetual_basis_fraction(spot_price=100, perpetual_price=101) == pytest.approx(0.01)
    with pytest.raises(ConditionScoreError, match="strictly positive"):
        perpetual_basis_fraction(spot_price=0, perpetual_price=101)


def test_primitives_fail_closed_on_insufficient_constant_or_invalid_inputs():
    with pytest.raises(ConditionScoreError, match="at least 2"):
        volatility_scaled_return((0.1,))
    with pytest.raises(ConditionScoreError, match="non-zero path"):
        directional_efficiency((0.0, 0.0))
    with pytest.raises(ConditionScoreError, match="non-zero one-period variance"):
        overlapping_variance_ratio((1.0, 1.0, 1.0, 1.0), 2)
    with pytest.raises(ConditionScoreError, match="non-zero reference variance"):
        standardized_displacement((1.0, 1.0), 2.0)
    with pytest.raises(ConditionScoreError, match="finite"):
        realized_variation_components((0.1, float("nan")))


def test_module_imports_no_production_or_external_clients():
    root = Path(__file__).resolve().parents[1]
    source = (root / "src/trading_platform/research_condition_scores.py").read_text().lower()
    for forbidden in (
        "ccxt",
        "freqtrade",
        "nats",
        "psycopg",
        "requests",
        "sqlalchemy",
        "trading_platform.signals",
    ):
        assert forbidden not in source


def test_mcs2_synthetic_qualification_is_deterministic_and_non_executable(tmp_path: Path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    run(DEFAULT_CONTRACT, first)
    run(DEFAULT_CONTRACT, second)
    assert (first / "synthetic-qualification-report.json").read_bytes() == (
        second / "synthetic-qualification-report.json"
    ).read_bytes()
    assert (first / "evidence-manifest.json").read_bytes() == (
        second / "evidence-manifest.json"
    ).read_bytes()
    report = json.loads((first / "synthetic-qualification-report.json").read_text())
    assert report["decision"] == "mcs2_passed_synthetic_infrastructure_only"
    assert report["invariants"]["market_values_deserialized"] is False
    assert report["invariants"]["models_or_scores_fitted"] is False
    assert report["invariants"]["thresholds_selected"] is False
    assert report["accepted_strategy_arms"] == []
    assert report["actionable_arm_id"] == "no_trade"
