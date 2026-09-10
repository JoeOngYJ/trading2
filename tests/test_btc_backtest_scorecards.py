import ast
import hashlib
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_btc_backtest_scorecards.py"
OUTPUT = ROOT / "artifacts/agent-level-experiment/btc-focused/backtest-scorecard-v1"


def _load_module():
    spec = importlib.util.spec_from_file_location("build_btc_backtest_scorecards", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_contract_and_trial_registry_fail_closed():
    module = _load_module()
    contract = module.verify_contract()
    rows, summary = module.load_trials()
    assert contract["actionable_arm_id"] == "no_trade"
    assert contract["accepted_strategy_arms"] == []
    assert summary["trials"] == len(rows) == 9
    assert all(not value["complete"] for value in summary["families"].values())


def test_frozen_scorecards_preserve_verdicts_and_expose_insufficient_evidence():
    report = json.loads((OUTPUT / "report.json").read_text())
    assert report["decision"] == "scorecard_infrastructure_passed_no_strategy_accepted"
    assert report["historical_dispositions_changed"] is False
    assert report["promotion_evidence"] is False
    assert report["actionable_arm_id"] == "no_trade"
    assert set(report["scorecard_dispositions"].values()) == {"supplemental_evidence_insufficient"}

    carry = json.loads((OUTPUT / "btc-positive-funding-carry-v1-scorecard.json").read_text())
    assert carry["lineage"]["original_disposition"] == "development_strategy_rejected"
    assert carry["trades"]["trade_count"] == 6
    assert carry["gates"]["universal"]["independent_economic_outcomes"]["status"] == "insufficient"
    assert carry["gates"]["universal"]["independent_blocks"]["status"] == "insufficient"
    assert carry["gates"]["role"]["paired_control_separation"]["status"] == "fail"
    assert carry["gates"]["strategy_specific_preserved"]["no_margin_breach"]["status"] == "fail"
    assert carry["performance"]["autocorrelation_adjusted_sharpe"] < carry["performance"]["conventional_sharpe"]

    breakout = json.loads((OUTPUT / "btc-fixed-20d-10d-breakout-legacy-control-scorecard.json").read_text())
    assert breakout["gates"]["strategy_specific_preserved"]["random_7d_percentile"]["status"] == "fail"
    assert breakout["gates"]["role"]["paired_control_separation"]["status"] == "fail"

    ewma = json.loads((OUTPUT / "btc-regime-routing-s2-ewma-v2-scorecard.json").read_text())
    assert ewma["evaluation_role"] == "risk_overlay"
    assert ewma["gates"]["role"]["not_alpha"]["status"] == "pass"


def test_scorecard_manifest_checksums_and_strict_json():
    manifest = json.loads((OUTPUT / "manifest.json").read_text())
    assert manifest["network_or_protected_service_accessed"] is False
    assert manifest["partial_ob0_accessed"] is False
    assert manifest["year_2026_accessed"] is False
    for item in manifest["files"]:
        path = OUTPUT / item["name"]
        assert path.is_file()
        assert _sha(path) == item["sha256"]
        raw = path.read_text(encoding="utf-8")
        assert "NaN" not in raw and "Infinity" not in raw


def test_scorecard_modules_are_offline_only():
    forbidden_roots = {
        "ccxt",
        "fastapi",
        "httpx",
        "nats",
        "psycopg",
        "requests",
        "websockets",
    }
    for path in (ROOT / "src/trading_platform/research_metrics.py", SCRIPT):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert imported.isdisjoint(forbidden_roots)


def test_scorecard_replay_is_byte_identical(tmp_path):
    module = _load_module()
    replay = tmp_path / "replay"
    module.run(replay)
    expected_files = sorted(path.name for path in OUTPUT.iterdir())
    assert sorted(path.name for path in replay.iterdir()) == expected_files
    for name in expected_files:
        assert (replay / name).read_bytes() == (OUTPUT / name).read_bytes()
