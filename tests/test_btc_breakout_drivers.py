from __future__ import annotations

import dataclasses
import hashlib
import json
from datetime import datetime, timezone

import pytest

from trading_platform.btc_breakout_drivers import (
    DriverEvent,
    DriverLedger,
    DriverLedgerError,
    EventMatchAnchor,
    NonEventWindowCandidate,
    canonical_json,
    causal_midrank_decile,
    construct_matched_non_event_windows,
    new_york_to_utc,
)


UTC = timezone.utc
CUTOFF = datetime(2025, 12, 31, 23, 59, tzinfo=UTC)
DIGEST = hashlib.sha256(b"archived official source").hexdigest()
STRATA = {
    "past_only_compression_percentile_decile": 2,
    "past_only_sigma24_decile": 4,
}


def utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def event(
    event_id: str,
    *,
    family: str = "macro",
    subtype: str = "cpi",
    actual_at: datetime | None = utc(2024, 6, 12, 12, 30),
    scheduled_at: datetime | None = utc(2024, 6, 12, 12, 30),
    **overrides: object,
) -> DriverEvent:
    anchor = actual_at or scheduled_at
    assert anchor is not None
    values: dict[str, object] = {
        "event_id": event_id,
        "family": family,
        "subtype": subtype,
        "title": f"Fixture {subtype}",
        "observed_at": anchor,
        "available_at": anchor,
        "retrieved_at": utc(2025, 1, 15),
        "ledger_cutoff_at": CUTOFF,
        "source_url": "https://example.gov/archive/release",
        "source_digest": DIGEST,
        "source_authority": "official_primary",
        "availability_quality": "exact_publication_time",
        "vintage_or_revision_id": "fixture-vintage-v1",
        "value_status": "not_applicable",
        "synthetic_fixture": True,
        "scheduled_at": scheduled_at,
        "actual_at": actual_at,
        "eligible_for_timing_test": True,
    }
    values.update(overrides)
    return DriverEvent(**values)  # type: ignore[arg-type]


def candidate(window_id: str, window_at: datetime, **overrides: object) -> NonEventWindowCandidate:
    values: dict[str, object] = {
        "window_id": window_id,
        "window_at": window_at,
        "strata_observed_at": window_at.replace(hour=11, minute=0),
        "strata_available_at": window_at.replace(hour=11, minute=0),
        "pre_event_strata": STRATA,
        "source_digest": DIGEST,
        "retrieved_at": utc(2025, 1, 15),
        "ledger_cutoff_at": CUTOFF,
    }
    values.update(overrides)
    return NonEventWindowCandidate(**values)  # type: ignore[arg-type]


def match_fixture() -> tuple[DriverLedger, EventMatchAnchor]:
    driver = event(
        "cpi-2024-06",
        actual_at=utc(2024, 6, 10, 12, 30),
        scheduled_at=utc(2024, 6, 10, 12, 30),
        eligible_for_association_test=True,
    )
    ledger = DriverLedger((driver,))
    anchor = EventMatchAnchor(
        event_id=driver.event_id,
        event_at=utc(2024, 6, 10, 12, 30),
        strata_observed_at=utc(2024, 6, 10, 11),
        strata_available_at=utc(2024, 6, 10, 11),
        pre_event_strata=STRATA,
        event_digest=driver.digest,
        feature_digest=DIGEST,
    )
    return ledger, anchor


def test_new_york_conversion_rejects_dst_gap_and_requires_fold_for_ambiguity():
    assert new_york_to_utc(datetime(2024, 6, 12, 8, 30)) == utc(2024, 6, 12, 12, 30)
    with pytest.raises(DriverLedgerError, match="DST gap"):
        new_york_to_utc(datetime(2024, 3, 10, 2, 30))
    with pytest.raises(DriverLedgerError, match="DST-ambiguous"):
        new_york_to_utc(datetime(2024, 11, 3, 1, 30))
    assert new_york_to_utc(datetime(2024, 11, 3, 1, 30), fold=0) == utc(2024, 11, 3, 5, 30)
    assert new_york_to_utc(datetime(2024, 11, 3, 1, 30), fold=1) == utc(2024, 11, 3, 6, 30)


def test_causal_midrank_deciles_are_integer_zero_to_nine_with_average_ties():
    assert causal_midrank_decile(-1.0, (0.0, 1.0, 2.0)) == 0
    assert causal_midrank_decile(3.0, (0.0, 1.0, 2.0)) == 9
    assert causal_midrank_decile(1.0, (0.0, 1.0, 1.0, 2.0)) == 5
    with pytest.raises(DriverLedgerError, match="cannot be empty"):
        causal_midrank_decile(1.0, ())


def test_driver_event_preserves_new_york_source_time_and_is_immutable():
    wall = datetime(2024, 6, 12, 8, 30)
    item = event(
        "cpi-2024-06",
        scheduled_time_basis="America/New_York",
        scheduled_local=wall,
        actual_time_basis="America/New_York",
        actual_local=wall,
    )
    assert item.as_dict()["scheduled_local"] == "2024-06-12T08:30:00"
    with pytest.raises(dataclasses.FrozenInstanceError):
        item.title = "changed"  # type: ignore[misc]
    with pytest.raises(DriverLedgerError, match="does not match"):
        event(
            "bad-conversion",
            scheduled_time_basis="America/New_York",
            scheduled_local=datetime(2024, 6, 12, 9, 30),
        )


def test_point_in_time_expectation_directional_eligibility_and_revision_lineage():
    item = event(
        "cpi-valued",
        value_status="revised",
        value_unit="percent_yoy",
        initial_value="3.3",
        previous_value="3.4",
        revised_value="3.2",
        revision_observed_at=utc(2024, 7, 11, 12, 30),
        revision_available_at=utc(2024, 7, 11, 12, 30),
        expectation_value="3.4",
        expectation_observed_at=utc(2024, 6, 11, 15),
        expectation_available_at=utc(2024, 6, 11, 15),
        expectation_source_url="https://example.org/archived-consensus",
        expectation_source_digest=DIGEST,
        surprise_value="-0.1",
        surprise_method="initial_minus_expectation",
        eligible_for_directional_test=True,
    )
    assert (item.initial_value, item.surprise_value) == ("3.3", "-0.1")
    with pytest.raises(DriverLedgerError, match="expectation was not available"):
        event(
            "future-consensus",
            value_status="initial",
            value_unit="percent_yoy",
            initial_value="3.3",
            expectation_value="3.4",
            expectation_observed_at=utc(2024, 6, 13),
            expectation_available_at=utc(2024, 6, 13),
            expectation_source_url="https://example.org/archived-consensus",
            expectation_source_digest=DIGEST,
            surprise_value="-0.1",
            surprise_method="initial_minus_expectation",
        )
    with pytest.raises(DriverLedgerError, match="initial minus expectation"):
        event(
            "wrong-surprise",
            value_status="initial",
            value_unit="percent_yoy",
            initial_value="3.3",
            expectation_value="3.4",
            expectation_observed_at=utc(2024, 6, 11),
            expectation_available_at=utc(2024, 6, 11),
            expectation_source_url="https://example.org/archived-consensus",
            expectation_source_digest=DIGEST,
            surprise_value="0.1",
            surprise_method="initial_minus_expectation",
        )
    with pytest.raises(DriverLedgerError, match="both revision timestamps"):
        event(
            "missing-revision-time",
            value_status="revised",
            value_unit="percent_yoy",
            initial_value="3.3",
            revised_value="3.2",
        )
    with pytest.raises(DriverLedgerError, match="unsupported surprise_method"):
        event(
            "arbitrary-surprise",
            value_status="initial",
            value_unit="percent_yoy",
            initial_value="3.3",
            expectation_value="3.4",
            expectation_observed_at=utc(2024, 6, 11),
            expectation_available_at=utc(2024, 6, 11),
            expectation_source_url="https://example.org/archived-consensus",
            expectation_source_digest=DIGEST,
            surprise_value="-0.1",
            surprise_method="invented_after_results",
        )


@pytest.mark.parametrize(
    ("family", "subtype", "contract_family"),
    [
        ("macro", "fomc_statement", "FOMC_decisions"),
        ("macro", "employment_situation", "US_employment_situation"),
        ("regulatory", "sec_publication", "SEC_BTC_material_actions"),
        ("protocol", "bitcoin_halving", "Bitcoin_protocol_material_events"),
        ("exchange_incident", "official_exchange_notice", "major_exchange_material_events"),
    ],
)
def test_supported_official_event_families(family: str, subtype: str, contract_family: str):
    assert event(f"{family}-{subtype}", family=family, subtype=subtype).as_dict()[
        "event_family"
    ] == contract_family


def test_pce_and_gdp_simultaneous_release_requires_complete_batch():
    members = ("bea-gdp", "bea-pce")
    pce = event("bea-pce", subtype="pce", batch_id="bea-q2", batch_members=members)
    gdp = event("bea-gdp", subtype="gdp", batch_id="bea-q2", batch_members=members)
    assert [row.event_id for row in DriverLedger((pce, gdp)).events] == list(members)
    with pytest.raises(DriverLedgerError, match="one explicit batch"):
        DriverLedger((event("cpi"), event("jobs", subtype="employment_situation")))
    with pytest.raises(DriverLedgerError, match="no independently recorded companion"):
        DriverLedger((pce,))


def test_events_are_association_eligible_but_never_claim_causal_eligibility():
    item = event(
        "confounded-sec",
        family="regulatory",
        subtype="sec_publication",
        confounds=("simultaneous-cpi",),
        eligible_for_association_test=True,
    )
    assert item.eligible_for_association_test is True
    assert not hasattr(item, "eligible_for_causal_test")
    assert item.as_dict()["eligibility"]["association_test"] is True


def test_low_quality_secondary_and_scheduled_records_remain_separate():
    with pytest.raises(DriverLedgerError, match="timestamp quality"):
        event("date-only", availability_quality="date_only", eligible_for_timing_test=True)
    with pytest.raises(DriverLedgerError, match="descriptive only"):
        event("secondary", source_authority="curated_secondary")
    scheduled = event(
        "scheduled-fomc",
        subtype="fomc_minutes",
        actual_at=None,
        scheduled_at=utc(2024, 7, 3, 18),
        availability_quality="scheduled_time_only",
        observed_at=utc(2024, 7, 3, 18),
        available_at=utc(2024, 7, 3, 18),
    )
    assert scheduled.eligible_for_timing_test is True
    assert scheduled.availability_quality == "scheduled_time_only"
    assert scheduled.eligible_for_association_test is False


def test_real_records_require_frozen_official_domains_while_fixtures_are_explicit():
    official = event(
        "official-cpi",
        synthetic_fixture=False,
        source_url="https://www.bls.gov/news.release/cpi.htm",
    )
    assert official.synthetic_fixture is False
    with pytest.raises(DriverLedgerError, match="official-source domain"):
        event(
            "unqualified-real",
            synthetic_fixture=False,
            source_url="https://unqualified.example/repost",
        )


def test_future_and_reversed_timestamps_fail_closed():
    with pytest.raises(DriverLedgerError, match="observed_at <= available_at"):
        event("reversed", observed_at=utc(2024, 6, 13), available_at=utc(2024, 6, 12))
    with pytest.raises(DriverLedgerError, match="future-dated"):
        event("future-event", scheduled_at=utc(2026, 1, 1))
    with pytest.raises(DriverLedgerError, match="<= ledger_cutoff_at"):
        event("future-retrieval", retrieved_at=utc(2026, 1, 1))


def test_canonical_ledger_serialization_and_digest_are_order_independent():
    first = event(
        "jobs",
        subtype="employment_situation",
        actual_at=utc(2024, 6, 7, 12, 30),
        scheduled_at=utc(2024, 6, 7, 12, 30),
    )
    second = event("cpi")
    one, two = DriverLedger((second, first)), DriverLedger((first, second))
    assert one.digest == two.digest
    assert canonical_json(one.as_dict()) == canonical_json(two.as_dict())
    payload = json.loads(canonical_json(one.as_dict()))
    assert payload["events"][0]["source_sha256"] == DIGEST
    assert payload["events"][0]["record_digest"] == one.events[0].digest
    assert payload["events"][0]["release_at"].endswith("Z")


def test_exact_adjacent_week_controls_and_future_placebo_boundary():
    ledger, anchor = match_fixture()
    candidates = (
        candidate("minus-2", utc(2024, 5, 27, 12, 30)),
        candidate("minus-1", utc(2024, 6, 3, 12, 30)),
        candidate("plus-1", utc(2024, 6, 17, 12, 30)),
        candidate("plus-2", utc(2024, 6, 24, 12, 30)),
        candidate("not-frozen-offset", utc(2024, 5, 20, 12, 30)),
    )
    selection = construct_matched_non_event_windows(ledger, (anchor,), candidates)
    assert [match.control_offset_weeks for match in selection.matches] == [-2, -1, 1, 2]
    assert selection.control_offsets_weeks == (-2, -1, 1, 2)
    assert all(match.eligible_for_online_use is False for match in selection.matches)
    assert [match.retrospective_association_only for match in selection.matches] == [
        False,
        False,
        True,
        True,
    ]
    assert selection.reused_candidate_ids == ()


def test_matching_rejects_leaky_strata_bad_bins_event_windows_and_incomplete_offsets():
    with pytest.raises(DriverLedgerError, match="available no later"):
        candidate("leaky", utc(2024, 6, 3, 12, 30), strata_available_at=utc(2024, 6, 3, 13))
    ledger, anchor = match_fixture()
    invalid_bin = candidate(
        "bad-bin",
        utc(2024, 6, 3, 12, 30),
        pre_event_strata={
            "past_only_compression_percentile_decile": 10,
            "past_only_sigma24_decile": 4,
        },
    )
    with pytest.raises(DriverLedgerError, match="outside its frozen bins"):
        construct_matched_non_event_windows(ledger, (anchor,), (invalid_bin,), require_full_match=False)
    known = candidate("known", utc(2024, 6, 3, 12, 30), contains_known_event=True)
    with pytest.raises(DriverLedgerError, match="incomplete frozen control offsets"):
        construct_matched_non_event_windows(ledger, (anchor,), (known,))

    zero_strata = {
        "past_only_compression_percentile_decile": 0,
        "past_only_sigma24_decile": 0,
    }
    zero_anchor = dataclasses.replace(anchor, pre_event_strata=zero_strata)
    zero_control = candidate(
        "zero-deciles", utc(2024, 6, 3, 12, 30), pre_event_strata=zero_strata
    )
    assert construct_matched_non_event_windows(
        ledger, (zero_anchor,), (zero_control,), require_full_match=False
    ).matches[0].pre_event_strata == zero_strata


def test_qualified_event_four_hour_exclusion_and_match_diagnostics():
    target = event(
        "target",
        actual_at=utc(2024, 6, 10, 12, 30),
        scheduled_at=utc(2024, 6, 10, 12, 30),
        eligible_for_association_test=True,
    )
    nearby = event(
        "near-control",
        subtype="employment_situation",
        actual_at=utc(2024, 6, 3, 15, 30),
        scheduled_at=utc(2024, 6, 3, 15, 30),
    )
    ledger = DriverLedger((target, nearby))
    anchor = EventMatchAnchor(
        target.event_id,
        target.actual_at,
        utc(2024, 6, 10, 11),
        utc(2024, 6, 10, 11),
        STRATA,
        target.digest,
        DIGEST,
    )
    controls = (
        candidate("minus-2", utc(2024, 5, 27, 12, 30)),
        candidate("minus-1-excluded", utc(2024, 6, 3, 12, 30)),
        candidate("plus-1", utc(2024, 6, 17, 12, 30)),
        candidate("plus-2", utc(2024, 6, 24, 12, 30)),
    )
    selection = construct_matched_non_event_windows(
        ledger, (anchor,), controls, require_full_match=False
    )
    assert [match.control_offset_weeks for match in selection.matches] == [-2, 1, 2]
    assert selection.unmatched_event_ids == ("target",)
    assert selection.driver_ledger_digest == ledger.digest


def test_matching_binds_ledger_rejects_duplicate_anchors_and_handles_dst_clock():
    ledger, anchor = match_fixture()
    with pytest.raises(DriverLedgerError, match="duplicate event_id"):
        construct_matched_non_event_windows(ledger, (anchor, anchor), (), require_full_match=False)
    wrong = dataclasses.replace(anchor, event_digest="f" * 64)
    with pytest.raises(DriverLedgerError, match="does not match driver ledger"):
        construct_matched_non_event_windows(ledger, (wrong,), (), require_full_match=False)
    timing_only = event(
        "timing-only",
        actual_at=utc(2024, 6, 10, 12, 30),
        scheduled_at=utc(2024, 6, 10, 12, 30),
    )
    timing_anchor = dataclasses.replace(
        anchor, event_id=timing_only.event_id, event_digest=timing_only.digest
    )
    with pytest.raises(DriverLedgerError, match="not association-eligible"):
        construct_matched_non_event_windows(
            DriverLedger((timing_only,)), (timing_anchor,), (), require_full_match=False
        )

    members = ("batch-gdp", "batch-pce")
    batch_gdp = event(
        "batch-gdp",
        subtype="gdp",
        batch_id="batch-release",
        batch_members=members,
        eligible_for_association_test=True,
    )
    batch_pce = event(
        "batch-pce",
        subtype="pce",
        batch_id="batch-release",
        batch_members=members,
        eligible_for_association_test=True,
    )
    batch_anchor = dataclasses.replace(
        anchor,
        event_id=batch_gdp.event_id,
        event_at=batch_gdp.actual_at,
        event_digest=batch_gdp.digest,
    )
    with pytest.raises(DriverLedgerError, match="batch anchor"):
        construct_matched_non_event_windows(
            DriverLedger((batch_gdp, batch_pce)),
            (batch_anchor,),
            (),
            require_full_match=False,
        )

    dst_driver = event(
        "dst-event",
        actual_at=utc(2024, 3, 13, 12, 30),  # 08:30 EDT.
        scheduled_at=utc(2024, 3, 13, 12, 30),
        eligible_for_association_test=True,
    )
    dst_ledger = DriverLedger((dst_driver,))
    dst_anchor = EventMatchAnchor(
        dst_driver.event_id,
        dst_driver.actual_at,
        utc(2024, 3, 13, 11),
        utc(2024, 3, 13, 11),
        STRATA,
        dst_driver.digest,
        DIGEST,
    )
    before_dst = candidate("before-dst", utc(2024, 3, 6, 13, 30))  # 08:30 EST.
    selection = construct_matched_non_event_windows(
        dst_ledger, (dst_anchor,), (before_dst,), require_full_match=False
    )
    assert selection.matches[0].control_offset_weeks == -1
