from __future__ import annotations

import math

import pytest

from trading_platform.research_ledger import (
    DAY_MS,
    FIVE_MINUTES_MS,
    sha256_file,
    write_jsonl_gzip,
)
from trading_platform.research_volatility import (
    CandlePoint,
    DailyFeature,
    EWMAConfig,
    Opportunity,
    ResearchVolatilityError,
    RiskLookup,
    allocations_for_opportunities,
    build_ewma_observations,
    check_planned_risk,
    coverage_report,
    load_direct_close_features,
    matched_allocation,
    neutralize_best_relative_months,
    parse_utc_ms,
    realized_variance,
    simulate_locked_cohorts,
)


DIGEST = "a" * 64


def daily_features(returns: list[float], *, segment: str = "0", start: int = 0):
    values = [None, *returns]
    return [
        DailyFeature(
            segment=segment,
            observed_ms=start + index * DAY_MS,
            available_ms=start + index * DAY_MS,
            close_to_close_log_return=value,
            feature_digest=DIGEST,
            source_digest=DIGEST,
        )
        for index, value in enumerate(values)
    ]


def config() -> EWMAConfig:
    return EWMAConfig(
        variant_id="primary",
        decay_lambda=0.94,
        target_annualized_volatility=0.4,
        initialization_returns=30,
    )


def test_ewma_initialization_recursion_and_future_independence():
    baseline = daily_features([0.01] * 30 + [0.02])
    changed = daily_features([0.01] * 30 + [0.50])
    observed = build_ewma_observations(baseline, config())
    changed_observed = build_ewma_observations(changed, config())

    assert all(not item.usable for item in observed[:30])
    assert observed[30].forecast_daily_variance == pytest.approx(0.0001)
    assert observed[30].digest == changed_observed[30].digest
    assert observed[31].forecast_daily_variance == pytest.approx(
        0.94 * 0.0001 + 0.06 * 0.0004
    )
    assert 0 < observed[31].exposure_multiplier <= 1


def test_segment_reset_returns_to_unknown_and_never_bridges_history():
    first = daily_features([0.01] * 30, segment="0")
    second = daily_features([0.01] * 30, segment="1", start=40 * DAY_MS)
    observed = build_ewma_observations([*first, *second], config())
    assert observed[30].usable
    assert not observed[31].usable
    assert observed[31].return_count == 0
    assert observed[-1].usable


def test_direct_close_loader_is_continuous_causal_and_close_only(tmp_path):
    path = tmp_path / "direct-daily.jsonl.gz"
    rows = [
        {
            "available_at": "1970-01-02T00:00:00Z",
            "close": "100",
            "open_at": "1970-01-01T00:00:00Z",
            "source_archive_sha256": DIGEST,
        },
        {
            "available_at": "1970-01-03T00:00:00Z",
            "close": "101",
            "open_at": "1970-01-02T00:00:00Z",
            "source_archive_sha256": DIGEST,
        },
    ]
    write_jsonl_gzip(path, rows)
    features = load_direct_close_features(
        path,
        sha256_file(path),
        2,
        source_segment="independent-daily",
    )
    assert features[0].observed_ms == DAY_MS
    assert features[0].close_to_close_log_return is None
    assert features[1].close_to_close_log_return == pytest.approx(math.log(1.01))
    assert {item.segment for item in features} == {"independent-daily"}


def test_direct_close_loader_fails_closed_on_daily_gap(tmp_path):
    path = tmp_path / "direct-daily-gap.jsonl.gz"
    rows = [
        {
            "available_at": "1970-01-02T00:00:00Z",
            "close": "100",
            "open_at": "1970-01-01T00:00:00Z",
            "source_archive_sha256": DIGEST,
        },
        {
            "available_at": "1970-01-04T00:00:00Z",
            "close": "101",
            "open_at": "1970-01-03T00:00:00Z",
            "source_archive_sha256": DIGEST,
        },
    ]
    write_jsonl_gzip(path, rows)
    with pytest.raises(ResearchVolatilityError, match="gap inside direct daily"):
        load_direct_close_features(
            path,
            sha256_file(path),
            2,
            source_segment="independent-daily",
        )


def test_independent_risk_source_does_not_inherit_execution_segment_identity():
    observed = build_ewma_observations(
        daily_features([0.01] * 30, segment="independent-daily"), config()
    )
    opportunity = Opportunity(
        "op",
        30 * DAY_MS,
        30 * DAY_MS,
        31 * DAY_MS,
        0,
        1,
        "execution-segment-12",
        100,
        101,
        "fixture",
    )
    allocation = allocations_for_opportunities(
        [opportunity],
        observed,
        base_allocation=0.1,
        max_age_ms=DAY_MS,
        independent_risk_source=True,
    )[0]
    assert allocation["unknown_reason"] is None
    assert 0 < allocation["allocation_fraction"] <= 0.1


def test_risk_lookup_rejects_future_stale_and_unknown_observations():
    observed = build_ewma_observations(daily_features([0.01] * 30), config())
    lookup = RiskLookup(observed, max_age_ms=DAY_MS)
    assert lookup.at(-1, "0")[1] == "risk_not_yet_available"
    assert lookup.at(10 * DAY_MS, "0")[1] == "insufficient_same_segment_returns"
    assert lookup.at(30 * DAY_MS, "0")[1] is None
    assert lookup.at(31 * DAY_MS, "0")[1] == "risk_observation_stale"
    assert lookup.at(30 * DAY_MS, "missing")[1] == "segment_has_no_risk_observations"


def test_unknown_risk_zero_sizes_locked_opportunity_without_changing_identity():
    observed = build_ewma_observations(daily_features([0.01] * 30), config())
    opportunities = [
        Opportunity(
            opportunity_id="op-1",
            signal_ms=10 * DAY_MS,
            entry_ms=10 * DAY_MS,
            exit_ms=11 * DAY_MS,
            entry_row=0,
            exit_row=1,
            segment="0",
            entry_reference=100,
            exit_reference=101,
            exit_reason="fixture",
        ),
        Opportunity(
            opportunity_id="op-2",
            signal_ms=30 * DAY_MS,
            entry_ms=30 * DAY_MS,
            exit_ms=31 * DAY_MS,
            entry_row=2,
            exit_row=3,
            segment="0",
            entry_reference=100,
            exit_reference=101,
            exit_reason="fixture",
        ),
    ]
    allocations = allocations_for_opportunities(
        opportunities, observed, base_allocation=0.1, max_age_ms=DAY_MS
    )
    assert [item["opportunity_id"] for item in allocations] == ["op-1", "op-2"]
    assert allocations[0]["allocation_fraction"] == 0
    assert 0 < allocations[1]["allocation_fraction"] <= 0.1
    coverage = coverage_report(opportunities, allocations)
    assert coverage["total"] == 2
    assert coverage["usable"] == 1


def test_realized_variance_requires_contiguous_same_segment_future_rows():
    candles = [
        CandlePoint(
            segment="0",
            open_ms=index * FIVE_MINUTES_MS,
            open=100 + index,
            high=102 + index,
            low=99 + index,
            close=101 + index,
            source_row=index,
        )
        for index in range(290)
    ]
    expected = sum(
        math.log(candles[index].close / candles[index - 1].close) ** 2
        for index in range(1, 289)
    )
    assert realized_variance(candles, FIVE_MINUTES_MS, "0", 1) == pytest.approx(expected)
    contaminated = list(candles)
    contaminated[100] = CandlePoint(
        segment="1",
        open_ms=contaminated[100].open_ms,
        open=200,
        high=201,
        low=199,
        close=200,
        source_row=100,
    )
    assert realized_variance(contaminated, FIVE_MINUTES_MS, "0", 1) is None


def test_capital_time_match_and_planned_risk_are_frozen_and_bounded():
    opportunities = [
        Opportunity("a", 0, 0, DAY_MS, 0, 1, "0", 100, 101, "fixture"),
        Opportunity("b", 2 * DAY_MS, 2 * DAY_MS, 5 * DAY_MS, 2, 5, "0", 100, 101, "fixture"),
    ]
    allocations = [{"allocation_fraction": 0.1}, {"allocation_fraction": 0.05}]
    assert matched_allocation(opportunities, allocations) == pytest.approx(0.0625)
    assert check_planned_risk(0.1, 0.04, 80, 0.005) == pytest.approx(0.0048)
    with pytest.raises(ResearchVolatilityError, match="planned risk"):
        check_planned_risk(0.11, 0.04, 80, 0.005)


def test_locked_simulation_preserves_cohort_and_downward_size():
    candles = [
        CandlePoint("0", index * FIVE_MINUTES_MS, 100, 110, 90, 100 + index, index)
        for index in range(10)
    ]
    opportunity = Opportunity(
        "a",
        FIVE_MINUTES_MS,
        FIVE_MINUTES_MS,
        3 * FIVE_MINUTES_MS,
        1,
        3,
        "0",
        100,
        110,
        "fixture",
    )
    fixed = simulate_locked_cohorts(
        candles,
        [opportunity],
        [0.1],
        side_cost_bps=15,
        evaluation_start_ms=0,
        evaluation_end_ms=10 * FIVE_MINUTES_MS,
    )
    scaled = simulate_locked_cohorts(
        candles,
        [opportunity],
        [0.05],
        side_cost_bps=15,
        evaluation_start_ms=0,
        evaluation_end_ms=10 * FIVE_MINUTES_MS,
    )
    assert fixed["trade_count"] == scaled["trade_count"] == 1
    assert fixed["trades"][0]["opportunity_id"] == scaled["trades"][0]["opportunity_id"]
    assert scaled["trades"][0]["quantity"] < fixed["trades"][0]["quantity"]


def test_best_relative_month_neutralization_uses_same_months_and_timeline():
    fixed = [("2020-01-01", 0.01), ("2020-02-01", 0.01), ("2020-03-01", 0.01)]
    primary = [("2020-01-01", 0.03), ("2020-02-01", 0.02), ("2020-03-01", 0.0)]
    result = neutralize_best_relative_months(primary, fixed, count=1)
    assert result["removed_months"] == ["2020-01"]


def test_timestamp_parser_rejects_naive_and_noncanonical_values():
    assert parse_utc_ms("1970-01-01T00:00:00Z") == 0
    with pytest.raises(ResearchVolatilityError, match="canonical UTC"):
        parse_utc_ms("1970-01-01T00:00:00")
    with pytest.raises(ResearchVolatilityError, match="canonical UTC"):
        parse_utc_ms("1970-01-01T01:00:00+01:00")
