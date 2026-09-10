from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from trading_platform.cross_asset_a1_completion import A1CompletionError, build_completion_report


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/experiments/cross-asset-a1-completion-review-v1.json"
FACTS = (
    ROOT
    / "artifacts/agent-level-experiment/cross-asset/a1-completion-review-v1/source-facts.json"
)


def test_completion_review_reconciles_samples_but_fails_all_a1_completion_gates():
    report = build_completion_report(ROOT, CONTRACT, FACTS)
    assert report["decision"] == "a1_blocked_completion_gates"
    assert report["a1_stage_passed"] is False
    assert report["accepted_strategy_arms"] == []
    assert report["approved_execution_instruments"] == []
    assert len(report["corporate_action_sample_results"]) == 13
    assert all(item["matched"] for item in report["corporate_action_sample_results"])
    assert not any(item["passed"] for item in report["gate_results"].values())
    assert not any(report["safety"].values())


def test_completion_review_rejects_amount_disagreement(tmp_path: Path):
    facts = json.loads(FACTS.read_text(encoding="utf-8"))
    facts["corporate_action_samples"][0]["issuer_amount"] = "9.999999"
    changed = tmp_path / "facts.json"
    changed.write_text(json.dumps(facts, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(A1CompletionError, match="issuer sample disagrees"):
        build_completion_report(ROOT, CONTRACT, changed)


def test_completion_review_rejects_strategy_or_execution_permission(tmp_path: Path):
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    unsafe = copy.deepcopy(contract)
    unsafe["prohibitions"]["strategy_signals_allowed"] = True
    changed = tmp_path / "contract.json"
    changed.write_text(json.dumps(unsafe, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(A1CompletionError, match="strategy_signals_allowed"):
        build_completion_report(ROOT, changed, FACTS)
