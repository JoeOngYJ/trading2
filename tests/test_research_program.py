from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from trading_platform.research_program import (
    ProgramContextError,
    canonical_json,
    canonical_json_line,
    record_digest,
    validate_artifact_lineage,
    validate_decision_log,
    validate_program_contract,
    validate_s1_contract,
    validate_s1_determinism,
    validate_s1_evidence_manifest,
    validate_s2_contract,
    validate_s2_v2_contract,
    validate_s2_v2_determinism,
    validate_s2_v2_evidence_manifest,
    validate_s3_contracts,
    validate_s3_determinism,
    validate_s3_evidence_manifest,
    validate_status,
)


ROOT = Path(__file__).resolve().parents[1]


def program_payload() -> dict:
    stages = []
    for index in range(8):
        stages.append(
            {
                "dependencies": [] if index == 0 else [f"S{index - 1}"],
                "next_action": "fixture next action",
                "objective": "fixture objective",
                "pass_gate": "fixture pass gate",
                "stage_id": f"S{index}",
            }
        )
    return {
        "program_id": "fixture-program-v1",
        "required_session_start_paths": [],
        "safety_boundaries": {
            "actionable_arm_id": "no_trade",
            "allowed_inputs": ["synthetic_fixtures", "repository_metadata"],
            "database_access_allowed": False,
            "exchange_access_allowed": False,
            "live_trading_authorized": False,
            "message_bus_access_allowed": False,
            "network_access_allowed": False,
            "order_intent_creation_allowed": False,
            "position_creation_allowed": False,
            "production_signal_creation_allowed": False,
            "running_soak_access_allowed": False,
        },
        "schema_version": "regime-routing-program-v1",
        "stages": stages,
    }


def status_payload(states: list[str], current: str) -> dict:
    return {
        "current_stage": current,
        "program_id": "fixture-program-v1",
        "schema_version": "regime-routing-program-status-v1",
        "stages": [
            {"stage_id": f"S{index}", "state": state} for index, state in enumerate(states)
        ],
    }


def test_program_contract_and_status_reject_skipped_prerequisites_and_multiple_active():
    program_id, graph = validate_program_contract(program_payload())
    with pytest.raises(ProgramContextError, match="unsatisfied prerequisites"):
        validate_status(
            status_payload(["planned", "active", *(["planned"] * 6)], "S1"),
            program_id,
            graph,
        )


def test_conditional_s4_skip_and_s5_progress_accept_terminal_s3_rejection():
    program_id, graph = validate_program_contract(program_payload())
    states = ["passed", "passed", "passed", "rejected", "skipped", "planned", "planned", "planned"]
    current, state, active = validate_status(status_payload(states, "S4"), program_id, graph)
    assert (current, state, active) == ("S4", "skipped", None)
    states[5] = "active"
    current, state, active = validate_status(status_payload(states, "S5"), program_id, graph)
    assert (current, state, active) == ("S5", "active", "S5")
    with pytest.raises(ProgramContextError, match="only one"):
        validate_status(
            status_payload(["active", "active", *(["planned"] * 6)], "S0"),
            program_id,
            graph,
        )
    current, state, active = validate_status(
        status_payload(["passed", "active", *(["planned"] * 6)], "S1"),
        program_id,
        graph,
    )
    assert (current, state, active) == ("S1", "active", "S1")


def test_program_contract_requires_deterministic_safety_boundary():
    unsafe = program_payload()
    unsafe["safety_boundaries"]["network_access_allowed"] = True
    with pytest.raises(ProgramContextError, match="disable runtime access"):
        validate_program_contract(unsafe)


def test_append_only_decision_log_chain_detects_rewrite(tmp_path: Path):
    records = []
    previous = None
    for sequence in (1, 2):
        record = {
            "decision": "fixture",
            "previous_record_digest": previous,
            "reason": f"reason {sequence}",
            "recorded_at": f"2026-08-28T0{sequence}:00:00Z",
            "sequence": sequence,
            "stage_id": "S0",
        }
        record["record_digest"] = record_digest(record)
        previous = record["record_digest"]
        records.append(record)
    path = tmp_path / "decisions.jsonl"
    path.write_text("".join(canonical_json_line(row) + "\n" for row in records), encoding="utf-8")
    assert validate_decision_log(path, ("S0",)) == 2

    changed = copy.deepcopy(records)
    changed[0]["reason"] = "rewritten negative result"
    path.write_text("".join(canonical_json_line(row) + "\n" for row in changed), encoding="utf-8")
    with pytest.raises(ProgramContextError, match="digest mismatch"):
        validate_decision_log(path, ("S0",))


def test_canonical_serialization_and_checksum_are_stable(tmp_path: Path):
    payload = {"z": [2, 1], "a": {"value": True}}
    one = canonical_json(payload)
    two = canonical_json(json.loads(one))
    assert one == two
    path = tmp_path / "canonical.json"
    path.write_text(one, encoding="utf-8")
    assert hashlib.sha256(path.read_bytes()).hexdigest() == hashlib.sha256(two.encode()).hexdigest()


def test_artifact_lineage_detects_changed_content(tmp_path: Path):
    artifact = tmp_path / "evidence.json"
    artifact.write_text('{"state":"frozen"}\n', encoding="utf-8")
    expected = hashlib.sha256(artifact.read_bytes()).hexdigest()
    validate_artifact_lineage(
        tmp_path,
        [{"path": "evidence.json", "sha256": expected}],
    )
    artifact.write_text('{"state":"changed"}\n', encoding="utf-8")
    with pytest.raises(ProgramContextError, match="checksum mismatch"):
        validate_artifact_lineage(
            tmp_path,
            [{"path": "evidence.json", "sha256": expected}],
        )


def test_repository_context_validator_passes():
    # This integration assertion ensures checked-in hashes, stage state, sealed status, and
    # module isolation remain mutually consistent.
    from trading_platform.research_program import validate_program_context

    result = validate_program_context(
        ROOT,
        ROOT / "config/research/btc-regime-routing-program-v1.json",
        ROOT / "config/research/btc-regime-routing-status-v1.json",
        ROOT / "config/experiments/btc-regime-routing-s0-v1.json",
    )
    assert result.current_stage == "S5"
    assert result.current_state == "blocked"
    assert result.active_stage is None
    assert result.decision_records >= 6


def test_repository_s1_contract_evidence_and_determinism_are_valid():
    validate_s1_contract(
        ROOT, ROOT / "config/experiments/btc-regime-routing-s1-ledger-v1.json"
    )
    evidence = (
        ROOT
        / "artifacts/agent-level-experiment/btc-regime-routing/s1-ledger-v1/manifest.json"
    )
    validate_s1_evidence_manifest(ROOT, evidence)
    validate_s1_determinism(evidence.parent / "determinism-verification.json")


def test_repository_s2_contract_is_valid():
    validate_s2_contract(
        ROOT, ROOT / "config/experiments/btc-regime-routing-s2-ewma-v1.json"
    )
    validate_s2_v2_contract(
        ROOT, ROOT / "config/experiments/btc-regime-routing-s2-ewma-v2.json"
    )


def test_repository_s2_evidence_and_determinism_when_terminal():
    status = json.loads(
        (ROOT / "config/research/btc-regime-routing-status-v1.json").read_text(
            encoding="utf-8"
        )
    )
    stage = next(item for item in status["stages"] if item["stage_id"] == "S2")
    if stage["state"] == "active":
        pytest.skip("S2 evidence is not emitted until the active evaluation finishes")
    evidence = ROOT / "artifacts/agent-level-experiment/btc-regime-routing/s2-ewma-v2/manifest.json"
    validate_s2_v2_evidence_manifest(ROOT, evidence)
    validate_s2_v2_determinism(
        ROOT, evidence.parent / "determinism-verification.json"
    )


def test_repository_s3_contract_evidence_and_determinism_are_valid():
    validate_s3_contracts(
        ROOT,
        ROOT / "config/experiments/btc-regime-routing-s3-student-t-hmm-v1.json",
        ROOT / "config/experiments/btc-regime-routing-s3-student-t-hmm-v2.json",
    )
    evidence = (
        ROOT
        / "artifacts/agent-level-experiment/btc-regime-routing/s3-student-t-hmm-v1/manifest.json"
    )
    validate_s3_evidence_manifest(ROOT, evidence)
    validate_s3_determinism(ROOT, evidence.parent / "determinism-verification.json")
