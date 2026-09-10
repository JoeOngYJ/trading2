from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/audit_btc_deribit_dvol_source.py"
SPEC = importlib.util.spec_from_file_location("audit_btc_deribit_dvol_source", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def valid_rows(start: int) -> list[list[float]]:
    return [[start + index * MODULE.DAY_MS, 80.0, 85.0, 75.0, 82.0] for index in range(15)]


def request(start: int) -> dict:
    return {"start_timestamp": start, "end_timestamp": start + 15 * MODULE.DAY_MS - 1}


def test_valid_daily_window_passes_exact_frozen_shape():
    start = 1_616_544_000_000
    audit = MODULE.audit_rows(valid_rows(start), request(start))
    assert audit["rows"] == 15
    assert audit["failures"] == []
    assert audit["duplicate_timestamps"] == 0
    assert audit["non_daily_gap_count"] == 0


def test_gaps_duplicates_bad_ohlc_and_wrong_count_fail_closed():
    start = 1_616_544_000_000
    rows = valid_rows(start)
    rows[2][0] = rows[1][0]
    rows[3][2] = 70.0
    rows.pop()
    audit = MODULE.audit_rows(rows, request(start))
    assert "row_count_not_15" in audit["failures"]
    assert "duplicate_timestamps" in audit["failures"]
    assert "non_daily_timestamp_gap" in audit["failures"]
    assert "row_3_ohlc_order" in audit["failures"]


def test_frozen_v2_contract_is_pre_2026_data_only_and_non_approving():
    path = ROOT / "research/btc/contracts/btc-deribit-dvol-source-pilot-v2.json"
    contract = MODULE.load_contract(path)
    assert contract["action_boundary"]["actionable_arm_id"] == "no_trade"
    assert contract["action_boundary"]["risk_model_input_approval_allowed"] is False
    assert contract["endpoint"]["credentials"] == "forbidden"
    assert len(contract["data_requests"]) == 3
    assert all(item["end_timestamp"] < 1_767_225_600_000 for item in contract["data_requests"])
    assert "2026_data" in contract["prohibited"]


def test_committed_pilot_evidence_matches_raw_checksums():
    output = ROOT / "artifacts/agent-level-experiment/btc-focused/deribit-dvol-source-pilot-v2"
    report = json.loads((output / "audit-report.json").read_text(encoding="utf-8"))
    source = json.loads((output / "source-manifest.json").read_text(encoding="utf-8"))
    evidence = json.loads((output / "evidence-manifest.json").read_text(encoding="utf-8"))
    assert report["decision"] == "technical_pilot_passed_historical_use_blocked"
    assert report["technical_pilot_gate_passed"] is True
    assert report["full_historical_risk_model_input_approved"] is False
    assert len(source["requests"]) == 3
    assert all(item["audit"]["rows"] == 15 for item in source["requests"])
    for item in evidence["files"]:
        path = ROOT / item["path"]
        assert path.is_file()
        assert MODULE.sha256_path(path) == item["sha256"]
