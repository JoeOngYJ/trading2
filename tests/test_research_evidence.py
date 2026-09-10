from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from trading_platform.research_evidence import (
    EvidenceContractError,
    load_point_in_time_universe,
    load_research_partition_registry,
)


UTC = timezone.utc
REPO_ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def known_universe_payload(evidence_sha256: str) -> dict:
    return {
        "schema_version": "research-universe-timeline-v1",
        "universe_id": "unit-universe-v1",
        "frozen_at": "2026-01-01T00:00:00Z",
        "venue": "unit-spot",
        "quote_asset": "USDT",
        "inclusion_rule": {
            "rule_id": "unit-point-in-time-rule-v1",
            "definition": "All fixture pairs with evidence-backed status at the decision time.",
            "point_in_time_defensible": True,
        },
        "coverage": {
            "start": "2025-01-01T00:00:00Z",
            "end_exclusive": "2025-03-01T00:00:00Z",
        },
        "candidate_pairs": ["BTC/USDT", "NEW/USDT"],
        "evidence": [
            {
                "evidence_id": "venue-history-v1",
                "source_type": "frozen_fixture",
                "observed_at": "2025-12-31T00:00:00Z",
                "sha256": evidence_sha256,
                "local_path": "venue-history.json",
                "description": "Unit-test point-in-time venue history.",
            }
        ],
        "intervals": [
            {
                "pair": "BTC/USDT",
                "start": "2025-01-01T00:00:00Z",
                "end_exclusive": "2025-03-01T00:00:00Z",
                "state": "eligible",
                "evidence_ids": ["venue-history-v1"],
                "reason": "eligible throughout fixture",
            },
            {
                "pair": "NEW/USDT",
                "start": "2025-01-01T00:00:00Z",
                "end_exclusive": "2025-02-01T00:00:00Z",
                "state": "ineligible",
                "evidence_ids": ["venue-history-v1"],
                "reason": "not listed",
            },
            {
                "pair": "NEW/USDT",
                "start": "2025-02-01T00:00:00Z",
                "end_exclusive": "2025-03-01T00:00:00Z",
                "state": "eligible",
                "evidence_ids": ["venue-history-v1"],
                "reason": "listed",
            },
        ],
    }


def make_known_universe(tmp_path: Path) -> tuple[Path, dict]:
    evidence = tmp_path / "venue-history.json"
    evidence.write_text('{"fixture":"point-in-time"}\n', encoding="utf-8")
    digest = hashlib.sha256(evidence.read_bytes()).hexdigest()
    payload = known_universe_payload(digest)
    return write_json(tmp_path / "universe.json", payload), payload


def partition_payload() -> dict:
    return {
        "schema_version": "research-evidence-boundaries-v1",
        "registry_id": "unit-boundaries-v1",
        "strategy_family": "unit-family",
        "frozen_at": "2026-08-26T00:00:00Z",
        "label_horizon_hours": 48,
        "minimum_embargo_hours": 48,
        "partitions": [
            {
                "partition_id": "development",
                "role": "development",
                "start": "2025-01-01T00:00:00Z",
                "end_exclusive": "2025-02-01T00:00:00Z",
                "access_state": "consumed",
                "allowed_purposes": ["development", "reproduction"],
                "minimum_events": None,
                "notes": "inspected development",
            },
            {
                "partition_id": "forward",
                "role": "prospective_validation",
                "start": "2025-02-03T00:00:00Z",
                "end_exclusive": "2025-03-03T00:00:00Z",
                "access_state": "locked",
                "allowed_purposes": ["collection", "analysis"],
                "minimum_events": 5,
                "locked_at": "2025-02-01T00:00:00Z",
                "unlock": None,
                "notes": "sealed forward fixture",
            },
        ],
        "inspections": [
            {
                "inspection_id": "development-review",
                "strategy_family": "unit-family",
                "start": "2025-01-01T00:00:00Z",
                "end_exclusive": "2025-02-01T00:00:00Z",
                "recorded_at": "2026-08-25T00:00:00Z",
                "information_scope": "signals_and_results",
                "notes": "development was inspected",
            }
        ],
    }


def test_point_in_time_universe_distinguishes_known_ineligible_from_unknown(tmp_path: Path):
    path, _ = make_known_universe(tmp_path)
    universe = load_point_in_time_universe(path)
    january = datetime(2025, 1, 15, tzinfo=UTC)
    february = datetime(2025, 2, 15, tzinfo=UTC)
    assert universe.eligible_pairs(january) == ("BTC/USDT",)
    assert universe.eligible_pairs(february) == ("BTC/USDT", "NEW/USDT")
    assert universe.audit(
        datetime(2025, 1, 1, tzinfo=UTC), datetime(2025, 3, 1, tzinfo=UTC)
    ).complete

    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["intervals"][0]["state"] = "unknown"
    payload["intervals"][0]["evidence_ids"] = []
    payload["intervals"][0]["reason"] = "fixture evidence unavailable"
    unknown_path = write_json(tmp_path / "unknown.json", payload)
    unknown = load_point_in_time_universe(unknown_path)
    assert not unknown.audit(
        datetime(2025, 1, 1, tzinfo=UTC), datetime(2025, 3, 1, tzinfo=UTC)
    ).complete
    with pytest.raises(EvidenceContractError, match="membership is unknown"):
        unknown.eligible_pairs(january)


def test_universe_rejects_gaps_and_evidence_checksum_changes(tmp_path: Path):
    path, payload = make_known_universe(tmp_path)
    broken_gap = copy.deepcopy(payload)
    broken_gap["intervals"][2]["start"] = "2025-02-02T00:00:00Z"
    with pytest.raises(EvidenceContractError, match="membership gap"):
        load_point_in_time_universe(write_json(tmp_path / "gap.json", broken_gap))

    (tmp_path / "venue-history.json").write_text("changed\n", encoding="utf-8")
    with pytest.raises(EvidenceContractError, match="checksum mismatch"):
        load_point_in_time_universe(path)


def test_universe_rejects_post_freeze_evidence(tmp_path: Path):
    _, payload = make_known_universe(tmp_path)
    payload["evidence"][0]["observed_at"] = "2026-01-02T00:00:00Z"
    with pytest.raises(EvidenceContractError, match="after the frozen_at"):
        load_point_in_time_universe(write_json(tmp_path / "future-evidence.json", payload))


def test_posthoc_candidate_rule_fails_even_when_membership_intervals_are_known(tmp_path: Path):
    _, payload = make_known_universe(tmp_path)
    payload["inclusion_rule"]["point_in_time_defensible"] = False
    universe = load_point_in_time_universe(write_json(tmp_path / "posthoc-rule.json", payload))
    audit = universe.audit(
        datetime(2025, 1, 1, tzinfo=UTC), datetime(2025, 3, 1, tzinfo=UTC)
    )
    assert not audit.complete
    assert not audit.inclusion_rule_point_in_time_defensible
    with pytest.raises(EvidenceContractError, match="inclusion rule"):
        universe.eligible_pairs(datetime(2025, 2, 15, tzinfo=UTC))


def test_partition_registry_tracks_clean_locked_forward_period_and_access(tmp_path: Path):
    registry = load_research_partition_registry(
        write_json(tmp_path / "partitions.json", partition_payload())
    )
    assert registry.clean_unseen_partition_ids() == ("forward",)
    registry.require_access(
        "forward", "collection", datetime(2025, 2, 10, tzinfo=UTC)
    )
    with pytest.raises(EvidenceContractError, match="explicitly open"):
        registry.require_access(
            "forward", "analysis", datetime(2025, 3, 4, tzinfo=UTC)
        )
    registry.require_access(
        "development", "reproduction", datetime(2026, 8, 26, tzinfo=UTC)
    )


def test_consumed_partition_accepts_explicit_risk_benchmark_purpose(tmp_path: Path):
    payload = partition_payload()
    payload["partitions"][0]["allowed_purposes"] = ["risk_benchmark_development"]
    registry = load_research_partition_registry(
        write_json(tmp_path / "risk-benchmark.json", payload)
    )
    registry.require_access(
        "development",
        "risk_benchmark_development",
        datetime(2026, 8, 26, tzinfo=UTC),
    )


def test_partition_inspection_contaminates_same_family_but_not_unrelated_family(tmp_path: Path):
    payload = partition_payload()
    contamination = {
        "inspection_id": "forward-peek",
        "strategy_family": "unit-family",
        "start": "2025-02-10T00:00:00Z",
        "end_exclusive": "2025-02-11T00:00:00Z",
        "recorded_at": "2026-08-25T00:00:00Z",
        "information_scope": "one_forward_result",
        "notes": "peeked",
    }
    payload["inspections"].append(contamination)
    contaminated = load_research_partition_registry(
        write_json(tmp_path / "contaminated.json", payload)
    )
    audit = contaminated.audit_unseen("forward")
    assert not audit.genuinely_unseen
    assert audit.overlapping_inspection_ids == ("forward-peek",)

    payload["inspections"][-1]["strategy_family"] = "unrelated-family"
    unrelated = load_research_partition_registry(
        write_json(tmp_path / "unrelated.json", payload)
    )
    assert unrelated.audit_unseen("forward").genuinely_unseen


def test_partition_registry_requires_horizon_embargo(tmp_path: Path):
    payload = partition_payload()
    payload["partitions"][1]["start"] = "2025-02-02T00:00:00Z"
    with pytest.raises(EvidenceContractError, match="lacks the 48h embargo"):
        load_research_partition_registry(write_json(tmp_path / "no-embargo.json", payload))


def test_sealed_ineligible_partition_is_excluded_without_claiming_inspection(tmp_path: Path):
    payload = partition_payload()
    payload["partitions"][1] = {
        "partition_id": "sealed-ineligible",
        "role": "excluded",
        "start": "2025-02-01T00:00:00Z",
        "end_exclusive": "2025-03-03T00:00:00Z",
        "access_state": "sealed_ineligible",
        "allowed_purposes": [],
        "minimum_events": None,
        "notes": "Unread but ineligible because the required embargo was absent.",
    }
    registry = load_research_partition_registry(
        write_json(tmp_path / "sealed-ineligible.json", payload)
    )
    audit = registry.audit_unseen("sealed-ineligible")
    assert not audit.genuinely_unseen
    assert audit.overlapping_inspection_ids == ()
    with pytest.raises(EvidenceContractError, match="not allowed"):
        registry.require_access(
            "sealed-ineligible", "analysis", datetime(2025, 3, 2, tzinfo=UTC)
        )


def test_open_evaluation_requires_prior_lock_lineage_and_minimum_events(tmp_path: Path):
    payload = partition_payload()
    prior_path = write_json(tmp_path / "prior-locked.json", payload)
    experiment_path = tmp_path / "frozen-experiment.json"
    experiment_path.write_text('{"status":"frozen"}\n', encoding="utf-8")
    forward = payload["partitions"][1]
    forward["access_state"] = "open"
    payload["frozen_at"] = "2026-08-27T00:00:00Z"
    with pytest.raises(EvidenceContractError, match="lacks unlock lineage"):
        load_research_partition_registry(write_json(tmp_path / "open-without-lineage.json", payload))

    forward["unlock"] = {
        "unlocked_at": "2026-08-27T00:00:00Z",
        "prior_locked_registry_sha256": hashlib.sha256(prior_path.read_bytes()).hexdigest(),
        "frozen_experiment_sha256": hashlib.sha256(experiment_path.read_bytes()).hexdigest(),
        "observed_events": 5,
        "one_time_analysis": True,
    }
    registry = load_research_partition_registry(
        write_json(tmp_path / "open-with-lineage.json", payload)
    )
    with pytest.raises(EvidenceContractError, match="requires the prior locked registry"):
        registry.require_access("forward", "analysis", datetime(2026, 8, 27, tzinfo=UTC))
    registry.require_access(
        "forward",
        "analysis",
        datetime(2026, 8, 27, tzinfo=UTC),
        prior_locked_registry_path=prior_path,
        frozen_experiment_path=experiment_path,
    )

    forward["unlock"]["observed_events"] = 4
    with pytest.raises(EvidenceContractError, match="minimum event count"):
        load_research_partition_registry(write_json(tmp_path / "too-few-events.json", payload))


def test_current_top2_contracts_fail_closed_without_relabelling_2026():
    universe = load_point_in_time_universe(
        REPO_ROOT / "config/research/multi-asset-top2-universe-timeline-v1.json"
    )
    audit = universe.audit(
        datetime(2021, 1, 1, tzinfo=UTC), datetime(2026, 1, 1, tzinfo=UTC)
    )
    assert not audit.complete
    assert set(audit.unknown_pairs) == set(universe.candidate_pairs)

    registry = load_research_partition_registry(
        REPO_ROOT / "config/research/multi-asset-top2-evidence-boundaries-v1.json"
    )
    assert registry.clean_unseen_partition_ids() == ()
    audit_2026 = registry.audit_unseen("historical-2026-known-contaminated")
    assert not audit_2026.genuinely_unseen
    assert "prior-crypto-repository-family-selection" in audit_2026.overlapping_inspection_ids
