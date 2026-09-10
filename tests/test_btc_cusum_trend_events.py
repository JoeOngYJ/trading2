from __future__ import annotations

import ast
import gzip
import hashlib
import importlib.util
import json
import math
import shutil
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from trading_platform.btc_cusum_trend_events import (
    LABEL_HOURS,
    ONE_HOUR_MS,
    SUPPRESSION_HOURS,
    CusumTrendEventError,
    build_cusum_trigger_catalogue,
    load_cusum_source_candles,
    materialize_cusum_labels,
    page_update,
    trigger_from_record,
)
from trading_platform.research_ledger import FIVE_MINUTES_MS


ROOT = Path(__file__).resolve().parents[1]
DIGEST = "a" * 64
EXPERIMENT = "btc-cusum-trend-onset-v1-tne1"


@dataclass(frozen=True, slots=True)
class Candle:
    segment: int
    open_ms: int
    raw_close_time_ms: int
    open: float
    high: float
    low: float
    close: float
    base_volume: float
    quote_volume: float
    source_row: int
    trade_count: int

    @property
    def close_ms(self) -> int:
        return self.open_ms + FIVE_MINUTES_MS


def prices_with_trigger(hours: int = 330, trigger_z: float = 2.0) -> list[float]:
    returns = [0.01 if index % 2 == 0 else -0.01 for index in range(168)]
    returns.extend([trigger_z * 0.01] * 3)
    returns.extend([0.0] * max(0, hours - 1 - len(returns)))
    prices = [100.0]
    for value in returns[: hours - 1]:
        prices.append(prices[-1] * math.exp(value))
    return prices


def rows_from_prices(
    prices: list[float], *, segment: int = 1, start_ms: int = 0
) -> list[Candle]:
    rows: list[Candle] = []
    for hour, price in enumerate(prices):
        for within in range(12):
            open_ms = start_ms + (hour * 12 + within) * FIVE_MINUTES_MS
            rows.append(
                Candle(
                    segment=segment,
                    open_ms=open_ms,
                    raw_close_time_ms=open_ms + FIVE_MINUTES_MS - 1,
                    open=price,
                    high=price,
                    low=price,
                    close=price,
                    base_volume=1.0,
                    quote_volume=price,
                    source_row=len(rows),
                    trade_count=1,
                )
            )
    return rows


def catalogue(rows):
    return build_cusum_trigger_catalogue(
        rows, source_digest=DIGEST, experiment_id=EXPERIMENT
    )


def load_script(name: str, relative: str):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_source(path: Path, rows: list[Candle]) -> str:
    header = (
        "segment_id,open_time_ms,close_time_ms,open,high,low,close,"
        "base_volume,quote_volume,trade_count\n"
    )
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        handle.write(header)
        for row in rows:
            handle.write(
                f"{row.segment},{row.open_ms},{row.raw_close_time_ms},{row.open},"
                f"{row.high},{row.low},{row.close},{row.base_volume},"
                f"{row.quote_volume},{row.trade_count}\n"
            )
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_page_update_clips_and_triggers_on_exact_threshold_equality():
    state, clipped, contribution = page_update(3.0, 1.75)
    assert clipped == 1.75
    assert contribution == 1.5
    assert state == 4.5
    assert page_update(0.0, 99.0)[1] == 2.0
    assert page_update(0.1, -2.0)[0] == 0.0


def test_trigger_uses_168_strictly_preceding_returns_and_three_contributors():
    result = catalogue(rows_from_prices(prices_with_trigger()))
    assert result.triggers
    trigger = result.triggers[0]
    expected_sigma = math.sqrt((166 * 0.01**2 + 2 * 0.02**2) / 168)
    assert trigger.sigma_hourly == pytest.approx(expected_sigma)
    assert trigger.z_clipped == pytest.approx(0.02 / expected_sigma)
    assert trigger.cusum_before < 3.5
    assert trigger.cusum_after >= 4.5
    assert trigger.active_hours == 3
    assert trigger.positive_contributors == 3
    assert trigger.first_eligible_5m_ms == trigger.trigger_ms
    assert trigger.model_ready
    trigger_index = trigger.trigger_ms // ONE_HOUR_MS - 1
    assert trigger.momentum_24h_log == pytest.approx(
        math.log(trigger.trigger_close / prices_with_trigger()[trigger_index - 24])
    )
    assert trigger.momentum_24h_z == pytest.approx(
        trigger.momentum_24h_log / (trigger.sigma_hourly * math.sqrt(24))
    )
    assert trigger.momentum_72h_z == pytest.approx(
        trigger.momentum_72h_log / (trigger.sigma_hourly * math.sqrt(72))
    )
    assert trigger.sigma24_over_sigma7d == pytest.approx(
        math.sqrt((22 * 0.01**2 + 2 * 0.02**2) / 24)
        / math.sqrt((166 * 0.01**2 + 2 * 0.02**2) / 168)
    )
    assert trigger.hour_of_week_sine**2 + trigger.hour_of_week_cosine**2 == pytest.approx(1.0)
    assert trigger.max_one_hour_positive_contribution_fraction == pytest.approx(
        (2.0 - 0.25) / trigger.cusum_after
    )
    payload = trigger.as_dict()
    assert "target_normalized_72h" not in payload
    assert "diagnostic_first_passage" not in payload


def test_post_trigger_prices_cannot_change_the_first_trigger_record():
    rows = rows_from_prices(prices_with_trigger())
    first = catalogue(rows).triggers[0]
    changed = [
        replace(row, open=row.open * 3, high=row.high * 3, low=row.low * 3, close=row.close * 3)
        if row.open_ms > first.trigger_ms
        else row
        for row in rows
    ]
    replay = catalogue(changed).triggers[0]
    assert replay.as_dict() == first.as_dict()


def test_current_return_is_strictly_excluded_from_its_sigma():
    rows = rows_from_prices(prices_with_trigger())
    first = catalogue(rows).triggers[0]
    trigger_hour_open = first.trigger_ms - ONE_HOUR_MS
    changed = list(rows)
    prior_close = next(
        row.close for row in rows if row.close_ms == trigger_hour_open
    )
    changed_close = prior_close * math.exp(0.04)
    for index, row in enumerate(changed):
        if trigger_hour_open <= row.open_ms < first.trigger_ms:
            changed[index] = replace(
                row,
                open=changed_close,
                high=changed_close,
                low=changed_close,
                close=changed_close,
            )
    replay = catalogue(changed).triggers[0]
    assert replay.trigger_ms == first.trigger_ms
    assert replay.sigma_hourly == first.sigma_hourly
    assert replay.sigma24_over_sigma7d == first.sigma24_over_sigma7d
    assert replay.current_return != first.current_return


def test_gap_and_segment_change_reset_all_history():
    first = rows_from_prices(prices_with_trigger(100), segment=1)
    second_start = first[-1].close_ms + ONE_HOUR_MS
    second = rows_from_prices(prices_with_trigger(100), segment=2, start_ms=second_start)
    combined = first + [replace(row, source_row=len(first) + i) for i, row in enumerate(second)]
    assert catalogue(combined).triggers == ()

    gapped = rows_from_prices(prices_with_trigger(200))
    gapped = gapped[:50] + gapped[51:]
    gapped = [replace(row, source_row=i) for i, row in enumerate(gapped)]
    with pytest.raises(CusumTrendEventError, match="gap inside"):
        catalogue(gapped)


def test_fixed_72h_suppression_skips_updates_then_restarts_empty():
    returns = [0.01 if index % 2 == 0 else -0.01 for index in range(168)]
    returns.extend([0.02] * 3)  # first trigger
    returns.extend([0.02] * 71)  # ignored Page updates inside suppression
    returns.extend([0.04] * 4)  # t+72 is suppressed; t+73 is the first fresh update
    returns.extend([0.0] * 30)
    prices = [100.0]
    for value in returns:
        prices.append(prices[-1] * math.exp(value))
    result = catalogue(rows_from_prices(prices))
    assert len(result.triggers) >= 2
    first, second = result.triggers[:2]
    assert second.run_started_ms == first.suppression_until_ms + ONE_HOUR_MS
    assert second.trigger_ms == first.suppression_until_ms + 3 * ONE_HOUR_MS
    assert second.active_hours == 3


def test_trigger_at_segment_end_is_retained_but_fill_unavailable():
    rows = rows_from_prices(prices_with_trigger(172))
    trigger = catalogue(rows).triggers[0]
    assert trigger.first_eligible_5m_ms is None
    assert not trigger.model_ready
    assert trigger.unavailable_reason == "first_eligible_5m_unavailable"


def test_label_uses_exact_complete_72h_close_and_daily_vol_scale():
    rows = rows_from_prices(prices_with_trigger())
    trigger = catalogue(rows).triggers[0]
    labels = materialize_cusum_labels(
        rows, [trigger], source_digest=DIGEST, experiment_id=EXPERIMENT
    )
    label = labels[0]
    assert label.endpoint_ms == trigger.first_eligible_5m_ms + LABEL_HOURS * ONE_HOUR_MS
    expected_bar = next(
        row for row in rows if row.close_ms == label.endpoint_ms
    )
    expected = math.log(expected_bar.close / trigger.first_eligible_price) / (
        trigger.sigma_hourly * math.sqrt(24)
    )
    assert label.target_normalized_72h == pytest.approx(expected)
    assert not label.censored
    assert label.observed_hours == 72


def test_label_censors_segment_loss_and_first_passage_is_diagnostic_only():
    rows = rows_from_prices(prices_with_trigger())
    trigger = catalogue(rows).triggers[0]
    cutoff = trigger.first_eligible_5m_ms + 20 * ONE_HOUR_MS
    truncated = [row for row in rows if row.close_ms <= cutoff]
    label = materialize_cusum_labels(
        truncated, [trigger], source_digest=DIGEST, experiment_id=EXPERIMENT
    )[0]
    assert label.censored
    assert label.censor_reason == "source_end"
    assert label.target_normalized_72h is None
    assert label.observed_hours == 20


def test_record_and_catalogue_digests_are_deterministic_and_tampering_fails():
    rows = rows_from_prices(prices_with_trigger())
    first = catalogue(rows)
    second = catalogue(rows)
    assert first.catalogue_digest == second.catalogue_digest
    record = first.triggers[0].as_dict()
    assert trigger_from_record(record).record_digest == record["record_digest"]
    record["z_raw"] += 1
    with pytest.raises(CusumTrendEventError, match="digest"):
        trigger_from_record(record)


def test_raw_loader_checks_inclusive_close_checksum_and_identity(tmp_path):
    path = tmp_path / "source.csv.gz"
    digest = write_source(path, rows_from_prices([100.0, 101.0]))
    rows, actual = load_cusum_source_candles(path, digest)
    assert actual == digest and rows[0].raw_close_time_ms == 299_999
    with pytest.raises(CusumTrendEventError, match="checksum"):
        load_cusum_source_candles(path, "0" * 64)

    bad_close = tmp_path / "bad-close.csv.gz"
    bad_rows = rows_from_prices([100.0, 101.0])
    bad_rows[0] = replace(bad_rows[0], raw_close_time_ms=bad_rows[0].close_ms)
    bad_digest = write_source(bad_close, bad_rows)
    with pytest.raises(CusumTrendEventError, match="invalid source candle"):
        load_cusum_source_candles(bad_close, bad_digest)

    bad_activity = tmp_path / "bad-activity.csv.gz"
    bad_rows = rows_from_prices([100.0, 101.0])
    bad_rows[3] = replace(bad_rows[3], trade_count=-1)
    bad_digest = write_source(bad_activity, bad_rows)
    with pytest.raises(CusumTrendEventError, match="invalid source candle"):
        load_cusum_source_candles(bad_activity, bad_digest)

    bad_identity = rows_from_prices(prices_with_trigger())
    bad_identity[10] = replace(bad_identity[10], source_row=99)
    with pytest.raises(CusumTrendEventError, match="invalid source candle"):
        catalogue(bad_identity)


def synthetic_contract(tmp_path: Path, *, minimum: int = 1) -> tuple[Path, str]:
    (tmp_path / "src/trading_platform").mkdir(parents=True)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "tests").mkdir()
    bindings = []
    implementation_bindings = (
        ("src/trading_platform/btc_cusum_trend_events.py", "event_module"),
        ("scripts/run_btc_cusum_trend_catalogue.py", "event_runner"),
        ("scripts/qualify_btc_cusum_design.py", "calibration_script"),
        ("tests/test_btc_cusum_trend_events.py", "event_tests"),
        ("src/trading_platform/btc_cusum_trend_models.py", "model_module"),
        ("scripts/run_btc_cusum_trend_models.py", "model_runner"),
        ("tests/test_btc_cusum_trend_models.py", "model_tests"),
    )
    for relative, role in implementation_bindings:
        source = ROOT / relative
        target = tmp_path / relative
        shutil.copyfile(source, target)
        bindings.append(
            {"path": relative, "role": role, "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}
        )
    for role in (
        "source_manifest",
        "design",
        "research_standard",
        "mandate",
        "cost_model",
        "predecessor_result",
    ):
        relative = f"bound/{role}.txt"
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(role, encoding="utf-8")
        bindings.append(
            {"path": relative, "role": role, "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}
        )
    source_path = tmp_path / "source.csv.gz"
    source_digest = write_source(source_path, rows_from_prices(prices_with_trigger()))
    bindings.append({"path": "source.csv.gz", "role": "source", "sha256": source_digest})
    contract = {
        "action_boundary": {"actionable_arm_id": "no_trade"},
        "bound_inputs": bindings,
        "chronology": {"decision_end_exclusive_ms": 10**15},
        "experiment_id": EXPERIMENT,
        "input_contract": {"expected_rows": len(rows_from_prices(prices_with_trigger()))},
        "outputs": {
            "trigger": {
                "catalogue": "out/trigger/triggers.jsonl.gz",
                "report": "out/trigger/report.json",
                "manifest": "out/trigger/manifest.json",
            },
            "label": {
                "catalogue": "out/label/labels.jsonl.gz",
                "report": "out/label/report.json",
                "manifest": "out/label/manifest.json",
            },
        },
        "rules": {
            "sigma_preceding_1h_returns": 168,
            "z_clip": 2.0,
            "page_drift": 0.25,
            "page_threshold": 4.5,
            "minimum_positive_contributors": 3,
            "minimum_active_hours": 3,
            "suppression_hours": 72,
            "label_hours": 72,
        },
        "status": "frozen_before_historical_trigger_access",
        "trigger_count_gates": {
            "model_ready_minimum": 1,
            "pre_2021_minimum": minimum,
            "evaluation_years": [1970],
            "per_evaluation_year_minimum": 1,
            "distinct_months_minimum": 1,
            "maximum_year_share": 1.0,
            "top_three_month_share": 1.0,
        },
        "label_gates": {
            "minimum_coverage": 0.0,
            "evaluation_years": [1970],
            "complete_per_evaluation_year_minimum": 1,
        },
    }
    path = tmp_path / "contract.json"
    path.write_text(json.dumps(contract), encoding="utf-8")
    return path, source_digest


def test_runner_separates_trigger_and_label_phases_and_refuses_overwrite(tmp_path):
    contract, _ = synthetic_contract(tmp_path)
    runner = load_script("run_btc_cusum", "scripts/run_btc_cusum_trend_catalogue.py")
    trigger = runner.run(contract, EXPERIMENT, tmp_path, "trigger")
    assert trigger["label_phase_allowed"]
    with gzip.open(
        tmp_path / "out/trigger/triggers.jsonl.gz", "rt", encoding="utf-8"
    ) as handle:
        record = json.loads(next(handle))
    assert "target_normalized_72h" not in record
    label = runner.run(contract, EXPERIMENT, tmp_path, "label")
    assert label["label_count"] == trigger["model_ready_trigger_count"]
    assert label["model_phase_allowed"]
    with pytest.raises(CusumTrendEventError, match="refusing to overwrite"):
        runner.run(contract, EXPERIMENT, tmp_path, "trigger")


def test_label_phase_fails_closed_when_trigger_count_gate_fails(tmp_path):
    contract, _ = synthetic_contract(tmp_path, minimum=99)
    runner = load_script("run_btc_cusum_blocked", "scripts/run_btc_cusum_trend_catalogue.py")
    trigger = runner.run(contract, EXPERIMENT, tmp_path, "trigger")
    assert not trigger["label_phase_allowed"]
    with pytest.raises(CusumTrendEventError, match="do not permit"):
        runner.run(contract, EXPERIMENT, tmp_path, "label")


def test_all_frozen_trigger_count_and_concentration_gates():
    runner = load_script("run_btc_cusum_gates", "scripts/run_btc_cusum_trend_catalogue.py")
    base = catalogue(rows_from_prices(prices_with_trigger())).triggers[0]
    triggers = []
    for year in range(2016, 2026):
        for ordinal in range(30):
            month = ordinal % 12 + 1
            day = ordinal // 12 + 1
            timestamp = int(
                datetime(year, month, day, 12, tzinfo=timezone.utc).timestamp() * 1000
            )
            trigger_id = f"gate:{year}:{ordinal}"
            triggers.append(
                replace(
                    base,
                    trigger_id=trigger_id,
                    trigger_ms=timestamp,
                    run_started_ms=timestamp,
                    suppression_until_ms=timestamp + SUPPRESSION_HOURS * ONE_HOUR_MS,
                )
            )
    frozen = {
        "model_ready_minimum": 300,
        "pre_2021_minimum": 150,
        "evaluation_years": [2021, 2022, 2023, 2024, 2025],
        "per_evaluation_year_minimum": 30,
        "distinct_months_minimum": 36,
        "maximum_year_share": 0.30,
        "top_three_month_share": 0.20,
    }
    passed = runner._trigger_gate_report(triggers, frozen)
    assert passed["passed"]
    assert passed["pre_2021_model_ready_count"] == 150
    assert passed["evaluation_year_model_ready_counts"] == {
        str(year): 30 for year in range(2021, 2026)
    }
    assert passed["distinct_model_ready_month_count"] == 120
    assert passed["max_year_share"] == pytest.approx(0.1)
    assert passed["top_three_month_share"] == pytest.approx(0.03)

    failed = runner._trigger_gate_report([triggers[-1]], frozen)
    assert not failed["passed"]
    assert not any(failed["checks"].values())


def test_label_coverage_and_each_evaluation_year_gate():
    runner = load_script("run_btc_cusum_label_gates", "scripts/run_btc_cusum_trend_catalogue.py")
    base = catalogue(rows_from_prices(prices_with_trigger())).triggers[0]
    triggers = []
    labels = []
    for year in range(2021, 2026):
        for ordinal in range(25):
            timestamp = int(
                datetime(year, ordinal % 12 + 1, ordinal // 12 + 1, tzinfo=timezone.utc).timestamp()
                * 1000
            )
            trigger_id = f"label:{year}:{ordinal}"
            triggers.append(replace(base, trigger_id=trigger_id, trigger_ms=timestamp))
            labels.append(SimpleNamespace(trigger_id=trigger_id, censored=False))
    for ordinal in range(13):
        trigger_id = f"censored:{ordinal}"
        triggers.append(replace(base, trigger_id=trigger_id, trigger_ms=ordinal))
        labels.append(SimpleNamespace(trigger_id=trigger_id, censored=True))
    frozen = {
        "minimum_coverage": 0.90,
        "evaluation_years": [2021, 2022, 2023, 2024, 2025],
        "complete_per_evaluation_year_minimum": 25,
    }
    passed = runner._label_gate_report(labels, triggers, frozen)
    assert passed["model_phase_allowed"]
    assert passed["coverage"] == pytest.approx(125 / 138)
    assert passed["complete_evaluation_year_counts"] == {
        str(year): 25 for year in range(2021, 2026)
    }
    labels[0] = SimpleNamespace(trigger_id=labels[0].trigger_id, censored=True)
    failed = runner._label_gate_report(labels, triggers, frozen)
    assert not failed["model_phase_allowed"]
    assert not all(failed["checks"].values())


def test_late_publication_failure_leaves_no_final_phase_artifacts(tmp_path, monkeypatch):
    contract, _ = synthetic_contract(tmp_path)
    runner = load_script("run_btc_cusum_atomic", "scripts/run_btc_cusum_trend_catalogue.py")
    original = runner._write_json
    calls = 0

    def fail_on_manifest(path, value):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("induced late manifest failure")
        return original(path, value)

    monkeypatch.setattr(runner, "_write_json", fail_on_manifest)
    with pytest.raises(RuntimeError, match="induced late"):
        runner.run(contract, EXPERIMENT, tmp_path, "trigger")
    assert not (tmp_path / "out/trigger").exists()
    assert not list((tmp_path / "out").glob(".trigger-*"))


def test_bound_hash_failure_occurs_before_source_deserialization(tmp_path, monkeypatch):
    contract, _ = synthetic_contract(tmp_path)
    runner = load_script("run_btc_cusum_hash", "scripts/run_btc_cusum_trend_catalogue.py")
    (tmp_path / "src/trading_platform/btc_cusum_trend_events.py").write_text(
        "changed", encoding="utf-8"
    )
    called = False

    def forbidden_loader(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("source loader must not run")

    monkeypatch.setattr(runner, "load_cusum_source_candles", forbidden_loader)
    with pytest.raises(CusumTrendEventError, match="checksum"):
        runner.run(contract, EXPERIMENT, tmp_path, "trigger")
    assert not called


def test_monte_carlo_design_reproduces_preregistered_first_passage_values():
    design = load_script("qualify_btc_cusum", "scripts/qualify_btc_cusum_design.py")
    result = design.qualify()
    assert result["passed"]
    assert result["results"]["0.0"]["mean_first_passage_hours"] == pytest.approx(125.1543)
    assert result["results"]["0.0"]["median_first_passage_hours"] == 89.0
    assert result["results"]["0.5"]["mean_first_passage_hours"] == pytest.approx(16.5476)
    assert result["results"]["0.5"]["median_first_passage_hours"] == 14.0


def test_new_modules_are_offline_and_have_no_runtime_or_execution_imports():
    forbidden = {
        "ccxt",
        "httpx",
        "nats",
        "psycopg",
        "requests",
        "trading_platform.execution_model",
    }
    for relative in (
        "src/trading_platform/btc_cusum_trend_events.py",
        "scripts/run_btc_cusum_trend_catalogue.py",
    ):
        tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
        assert not imports.intersection(forbidden)
