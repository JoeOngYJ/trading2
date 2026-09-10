#!/usr/bin/env python3
"""Contract-bound, offline two-phase runner for BTC CUSUM trend-onset research."""

from __future__ import annotations

import argparse
import gzip
import json
import os
import shutil
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trading_platform.btc_cusum_trend_events import (
    CUSUM_DRIFT,
    CUSUM_THRESHOLD,
    LABEL_HOURS,
    MINIMUM_ACTIVE_HOURS,
    MINIMUM_POSITIVE_CONTRIBUTORS,
    SIGMA_RETURNS,
    SUPPRESSION_HOURS,
    Z_CLIP,
    CusumTrigger,
    CusumTriggerCatalogue,
    CusumTrendEventError,
    build_cusum_trigger_catalogue,
    load_cusum_source_candles,
    materialize_cusum_labels,
    trigger_from_record,
)
from trading_platform.research_ledger import iso_ms, sha256_file, write_jsonl_gzip
from trading_platform.research_routing import canonical_digest


ROOT = Path(__file__).resolve().parents[1]


def _inside_root(root: Path, relative: str, *, must_exist: bool) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise CusumTrendEventError("contract path must be repository-relative")
    resolved_root = root.resolve(strict=True)
    resolved = (resolved_root / candidate).resolve(strict=must_exist)
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise CusumTrendEventError("contract path leaves repository root")
    return resolved


def _load_contract(path: Path, experiment_id: str, root: Path) -> dict[str, Any]:
    resolved_root = root.resolve(strict=True)
    resolved = path.resolve(strict=True)
    if resolved_root not in resolved.parents:
        raise CusumTrendEventError("contract must be inside repository root")
    try:
        contract = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CusumTrendEventError("cannot read TNE1 contract") from exc
    if not isinstance(contract, dict) or contract.get("experiment_id") != experiment_id:
        raise CusumTrendEventError("exact TNE1 experiment ID is required")
    if contract.get("status") != "frozen_before_historical_trigger_access":
        raise CusumTrendEventError("TNE1 contract is not frozen")
    if contract.get("action_boundary", {}).get("actionable_arm_id") != "no_trade":
        raise CusumTrendEventError("TNE1 contract does not fail closed")
    return contract


def _validate_rules(contract: dict[str, Any]) -> None:
    expected = {
        "sigma_preceding_1h_returns": SIGMA_RETURNS,
        "z_clip": Z_CLIP,
        "page_drift": CUSUM_DRIFT,
        "page_threshold": CUSUM_THRESHOLD,
        "minimum_positive_contributors": MINIMUM_POSITIVE_CONTRIBUTORS,
        "minimum_active_hours": MINIMUM_ACTIVE_HOURS,
        "suppression_hours": SUPPRESSION_HOURS,
        "label_hours": LABEL_HOURS,
    }
    rules = contract.get("rules", {})
    for key, value in expected.items():
        if rules.get(key) != value:
            raise CusumTrendEventError(f"contract/code rule mismatch: {key}")


def _validate_bound_inputs(contract: dict[str, Any], root: Path) -> list[dict[str, str]]:
    inputs = contract.get("bound_inputs")
    if not isinstance(inputs, list) or not inputs:
        raise CusumTrendEventError("bound inputs are required")
    checked: list[dict[str, str]] = []
    seen_paths: set[str] = set()
    seen_roles: set[str] = set()
    for item in inputs:
        if not isinstance(item, dict):
            raise CusumTrendEventError("invalid bound input")
        relative, expected, role = item.get("path"), item.get("sha256"), item.get("role")
        if (
            not isinstance(relative, str)
            or not isinstance(expected, str)
            or not isinstance(role, str)
        ):
            raise CusumTrendEventError("bound path/checksum/role are required")
        if relative in seen_paths or role in seen_roles:
            raise CusumTrendEventError("bound input paths and roles must be unique")
        seen_paths.add(relative)
        seen_roles.add(role)
        path = _inside_root(root, relative, must_exist=True)
        actual = sha256_file(path)
        if actual != expected:
            raise CusumTrendEventError(f"bound input checksum mismatch: {relative}")
        checked.append({"path": relative, "role": role, "sha256": actual})
    required_roles = {
        "source",
        "source_manifest",
        "design",
        "research_standard",
        "mandate",
        "cost_model",
        "event_module",
        "event_runner",
        "event_tests",
        "calibration_script",
        "model_module",
        "model_runner",
        "model_tests",
        "predecessor_result",
    }
    if not required_roles.issubset(seen_roles):
        raise CusumTrendEventError("full unified TNE1/TNE2 bindings are required")
    return checked


def _source(contract: dict[str, Any]) -> tuple[str, str]:
    sources = [
        item
        for item in contract.get("bound_inputs", [])
        if isinstance(item, dict) and item.get("role") == "source"
    ]
    if len(sources) != 1:
        raise CusumTrendEventError("exactly one source binding is required")
    path, digest = sources[0].get("path"), sources[0].get("sha256")
    if not isinstance(path, str) or not isinstance(digest, str):
        raise CusumTrendEventError("source binding is invalid")
    return path, digest


def _outputs(contract: dict[str, Any], phase: str, root: Path) -> tuple[dict[str, str], dict[str, Path]]:
    outputs = contract.get("outputs", {}).get(phase)
    required = ("catalogue", "report", "manifest")
    if not isinstance(outputs, dict) or any(not isinstance(outputs.get(key), str) for key in required):
        raise CusumTrendEventError(f"{phase} output paths are required")
    relative = {key: outputs[key] for key in required}
    paths = {
        key: _inside_root(root, value, must_exist=False) for key, value in relative.items()
    }
    if len(set(paths.values())) != len(paths):
        raise CusumTrendEventError("output paths must be distinct")
    parents = {path.parent for path in paths.values()}
    if len(parents) != 1:
        raise CusumTrendEventError("one phase's outputs must share one atomic directory")
    phase_directory = next(iter(parents))
    if phase_directory.exists():
        raise CusumTrendEventError(
            f"refusing to overwrite existing artifact directory: {phase_directory}"
        )
    return relative, paths


def _write_json(path: Path, value: dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, allow_nan=False, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return sha256_file(path)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CusumTrendEventError(f"cannot read prerequisite: {path}") from exc
    if not isinstance(value, dict):
        raise CusumTrendEventError("prerequisite must be a JSON object")
    return value


def _utc_year_month(timestamp_ms: int) -> tuple[int, str]:
    stamp = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
    return stamp.year, f"{stamp.year:04d}-{stamp.month:02d}"


def _trigger_gate_report(
    triggers: list[CusumTrigger], gates: dict[str, Any]
) -> dict[str, Any]:
    """Evaluate every frozen TNE1-A trigger-count/concentration gate."""

    required_integer = {
        "model_ready_minimum",
        "pre_2021_minimum",
        "per_evaluation_year_minimum",
        "distinct_months_minimum",
    }
    required_fraction = {"maximum_year_share", "top_three_month_share"}
    for key in required_integer:
        if not isinstance(gates.get(key), int) or gates[key] < 0:
            raise CusumTrendEventError(f"nonnegative integer trigger gate required: {key}")
    for key in required_fraction:
        value = gates.get(key)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= value <= 1:
            raise CusumTrendEventError(f"unit-interval trigger gate required: {key}")
    evaluation_years = gates.get("evaluation_years")
    if (
        not isinstance(evaluation_years, list)
        or not evaluation_years
        or any(not isinstance(year, int) for year in evaluation_years)
        or len(set(evaluation_years)) != len(evaluation_years)
    ):
        raise CusumTrendEventError("distinct integer evaluation_years are required")

    ready = [trigger for trigger in triggers if trigger.model_ready]
    years: Counter[int] = Counter()
    months: Counter[str] = Counter()
    for trigger in ready:
        year, month = _utc_year_month(trigger.trigger_ms)
        years[year] += 1
        months[month] += 1
    total = len(ready)
    pre_2021 = sum(count for year, count in years.items() if year < 2021)
    evaluation_counts = {str(year): years[year] for year in evaluation_years}
    max_year_share = max(years.values(), default=0) / total if total else None
    top_three_month_share = (
        sum(sorted(months.values(), reverse=True)[:3]) / total if total else None
    )
    checks = {
        "model_ready_minimum": total >= gates["model_ready_minimum"],
        "pre_2021_minimum": pre_2021 >= gates["pre_2021_minimum"],
        "per_evaluation_year_minimum": all(
            years[year] >= gates["per_evaluation_year_minimum"]
            for year in evaluation_years
        ),
        "distinct_months_minimum": len(months) >= gates["distinct_months_minimum"],
        "maximum_year_share": (
            max_year_share is not None and max_year_share <= gates["maximum_year_share"]
        ),
        "top_three_month_share": (
            top_three_month_share is not None
            and top_three_month_share <= gates["top_three_month_share"]
        ),
    }
    return {
        "checks": checks,
        "distinct_model_ready_month_count": len(months),
        "evaluation_year_model_ready_counts": evaluation_counts,
        "gates": {key: gates[key] for key in sorted(required_integer | required_fraction)}
        | {"evaluation_years": evaluation_years},
        "max_year_share": max_year_share,
        "model_ready_month_counts": dict(sorted(months.items())),
        "model_ready_year_counts": {
            str(year): count for year, count in sorted(years.items())
        },
        "passed": all(checks.values()),
        "pre_2021_model_ready_count": pre_2021,
        "top_three_month_share": top_three_month_share,
    }


def _label_gate_report(
    labels: list[Any], triggers: list[CusumTrigger], gates: dict[str, Any]
) -> dict[str, Any]:
    """Evaluate frozen label coverage and per-evaluation-year completeness gates."""

    minimum_coverage = gates.get("minimum_coverage")
    per_year_minimum = gates.get("complete_per_evaluation_year_minimum")
    evaluation_years = gates.get("evaluation_years")
    if (
        not isinstance(minimum_coverage, (int, float))
        or isinstance(minimum_coverage, bool)
        or not 0 <= minimum_coverage <= 1
    ):
        raise CusumTrendEventError("unit-interval minimum_coverage is required")
    if not isinstance(per_year_minimum, int) or per_year_minimum < 0:
        raise CusumTrendEventError("nonnegative complete-per-year label gate is required")
    if (
        not isinstance(evaluation_years, list)
        or not evaluation_years
        or any(not isinstance(year, int) for year in evaluation_years)
        or len(set(evaluation_years)) != len(evaluation_years)
    ):
        raise CusumTrendEventError("distinct integer label evaluation_years are required")
    if len(labels) != len(triggers):
        raise CusumTrendEventError("label/trigger gate lineage count mismatch")

    complete_by_year: Counter[int] = Counter()
    uncensored = 0
    for label, trigger in zip(labels, triggers, strict=True):
        if label.trigger_id != trigger.trigger_id:
            raise CusumTrendEventError("label/trigger gate lineage mismatch")
        if not label.censored:
            uncensored += 1
            year, _ = _utc_year_month(trigger.trigger_ms)
            complete_by_year[year] += 1
    coverage = uncensored / len(labels) if labels else 0.0
    evaluation_counts = {str(year): complete_by_year[year] for year in evaluation_years}
    checks = {
        "minimum_coverage": coverage >= minimum_coverage,
        "complete_per_evaluation_year_minimum": all(
            complete_by_year[year] >= per_year_minimum for year in evaluation_years
        ),
    }
    return {
        "checks": checks,
        "complete_evaluation_year_counts": evaluation_counts,
        "coverage": coverage,
        "gates": {
            "complete_per_evaluation_year_minimum": per_year_minimum,
            "evaluation_years": evaluation_years,
            "minimum_coverage": minimum_coverage,
        },
        "model_phase_allowed": all(checks.values()),
        "uncensored_count": uncensored,
    }


def _trigger_prerequisites(
    contract: dict[str, Any], experiment_id: str, root: Path
) -> tuple[list[Any], dict[str, Any]]:
    configured = contract.get("outputs", {}).get("trigger", {})
    for key in ("catalogue", "report", "manifest"):
        if not isinstance(configured.get(key), str):
            raise CusumTrendEventError("trigger prerequisite paths are missing")
    catalogue_path = _inside_root(root, configured["catalogue"], must_exist=True)
    report_path = _inside_root(root, configured["report"], must_exist=True)
    manifest_path = _inside_root(root, configured["manifest"], must_exist=True)
    report = _read_json(report_path)
    manifest = _read_json(manifest_path)
    if (
        report.get("experiment_id") != experiment_id
        or report.get("phase") != "trigger"
        or not report.get("label_phase_allowed")
    ):
        raise CusumTrendEventError("trigger count gates do not permit label phase")
    current_contract_sha = sha256_file(
        _inside_root(root, str(report.get("contract_path")), must_exist=True)
    )
    if (
        manifest.get("experiment_id") != experiment_id
        or manifest.get("phase") != "trigger"
        or manifest.get("contract_sha256") != current_contract_sha
        or report.get("contract_sha256") != current_contract_sha
        or report.get("effective_contract_digest") != canonical_digest(contract)
    ):
        raise CusumTrendEventError("trigger manifest lineage mismatch")
    artifacts = {
        item.get("path"): item.get("sha256")
        for item in manifest.get("artifacts", [])
        if isinstance(item, dict)
    }
    for relative, path in (
        (configured["catalogue"], catalogue_path),
        (configured["report"], report_path),
    ):
        if artifacts.get(relative) != sha256_file(path):
            raise CusumTrendEventError("trigger prerequisite checksum mismatch")
    triggers = []
    with gzip.open(catalogue_path, "rt", encoding="utf-8") as handle:
        for line in handle:
            raw = json.loads(line)
            trigger = trigger_from_record(raw)
            if trigger.as_dict() != raw:
                raise CusumTrendEventError("trigger prerequisite schema is not canonical")
            triggers.append(trigger)
    if len(triggers) != report.get("total_trigger_count"):
        raise CusumTrendEventError("trigger prerequisite count mismatch")
    ready = [trigger for trigger in triggers if trigger.model_ready]
    if len(ready) != report.get("model_ready_trigger_count"):
        raise CusumTrendEventError("model-ready trigger prerequisite count mismatch")
    source_rows = report.get("source_rows")
    aggregate_rows = report.get("aggregate_rows_1h")
    if not isinstance(source_rows, int) or not isinstance(aggregate_rows, int):
        raise CusumTrendEventError("trigger prerequisite catalogue dimensions are invalid")
    reconstructed = CusumTriggerCatalogue(
        experiment_id=experiment_id,
        source_digest=str(report.get("source_digest")),
        source_rows=source_rows,
        aggregate_rows_1h=aggregate_rows,
        triggers=tuple(triggers),
    )
    if reconstructed.catalogue_digest != report.get("catalogue_digest"):
        raise CusumTrendEventError("trigger prerequisite catalogue digest mismatch")
    return ready, report


def run(contract_path: Path, experiment_id: str, root: Path, phase: str) -> dict[str, Any]:
    if phase not in {"trigger", "label"}:
        raise CusumTrendEventError("phase must be trigger or label")
    root = root.resolve(strict=True)
    contract_path = contract_path.resolve(strict=True)
    contract = _load_contract(contract_path, experiment_id, root)
    _validate_rules(contract)
    relative, output_paths = _outputs(contract, phase, root)
    bound_inputs = _validate_bound_inputs(contract, root)  # before source deserialization
    source_relative, source_digest = _source(contract)

    prerequisite_report: dict[str, Any] | None = None
    triggers: list[Any] | None = None
    if phase == "label":
        triggers, prerequisite_report = _trigger_prerequisites(contract, experiment_id, root)

    rows, actual_digest = load_cusum_source_candles(
        _inside_root(root, source_relative, must_exist=True), source_digest
    )
    expected_rows = contract.get("input_contract", {}).get("expected_rows")
    if not isinstance(expected_rows, int) or len(rows) != expected_rows:
        raise CusumTrendEventError("source row count mismatch")
    boundary = contract.get("chronology", {}).get("decision_end_exclusive_ms")
    if not isinstance(boundary, int) or boundary <= 0:
        raise CusumTrendEventError("integer decision boundary is required")
    if rows[-1].close_ms > boundary:
        raise CusumTrendEventError("source availability exceeds frozen boundary")

    contract_relative = str(contract_path.relative_to(root))
    contract_sha = sha256_file(contract_path)
    if phase == "trigger":
        catalogue = build_cusum_trigger_catalogue(
            rows,
            source_digest=actual_digest,
            experiment_id=experiment_id,
            decision_end_exclusive_ms=boundary,
        )
        model_ready = [trigger for trigger in catalogue.triggers if trigger.model_ready]
        gates = contract.get("trigger_count_gates", {})
        if not isinstance(gates, dict):
            raise CusumTrendEventError("trigger_count_gates must be an object")
        trigger_gate = _trigger_gate_report(list(catalogue.triggers), gates)
        report = {
            "actionable_arm_id": "no_trade",
            "aggregate_rows_1h": catalogue.aggregate_rows_1h,
            "catalogue_digest": catalogue.catalogue_digest,
            "contract_path": contract_relative,
            "contract_sha256": contract_sha,
            "effective_contract_digest": canonical_digest(contract),
            "experiment_id": experiment_id,
            "label_phase_allowed": trigger_gate["passed"],
            "model_ready_trigger_count": len(model_ready),
            "phase": "trigger",
            "source_digest": actual_digest,
            "source_last_close_at": iso_ms(rows[-1].close_ms),
            "source_rows": len(rows),
            "total_trigger_count": len(catalogue.triggers),
            "trigger_count_gate_report": trigger_gate,
        }
        records = (trigger.as_dict() for trigger in catalogue.triggers)
    else:
        assert triggers is not None and prerequisite_report is not None
        labels = list(
            materialize_cusum_labels(
                rows, triggers, source_digest=actual_digest, experiment_id=experiment_id
            )
        )
        diagnostics = Counter(label.diagnostic_first_passage for label in labels)
        label_gates = contract.get("label_gates", {})
        if not isinstance(label_gates, dict):
            raise CusumTrendEventError("label_gates must be an object")
        label_gate = _label_gate_report(labels, triggers, label_gates)
        report = {
            "actionable_arm_id": "no_trade",
            "censored_count": sum(label.censored for label in labels),
            "contract_path": contract_relative,
            "contract_sha256": contract_sha,
            "diagnostic_first_passage_counts": {
                str(key): value for key, value in sorted(diagnostics.items(), key=lambda x: str(x[0]))
            },
            "effective_contract_digest": canonical_digest(contract),
            "experiment_id": experiment_id,
            "label_gate_report": label_gate,
            "label_count": len(labels),
            "model_phase_allowed": label_gate["model_phase_allowed"],
            "phase": "label",
            "source_digest": actual_digest,
            "trigger_report_sha256": sha256_file(
                _inside_root(
                    root, contract["outputs"]["trigger"]["report"], must_exist=True
                )
            ),
            "uncensored_count": sum(not label.censored for label in labels),
        }
        records = (label.as_dict() for label in labels)

    phase_directory = output_paths["catalogue"].parent
    phase_directory.parent.mkdir(parents=True, exist_ok=True)
    temporary_directory = Path(
        tempfile.mkdtemp(prefix=f".{phase_directory.name}-", dir=phase_directory.parent)
    )
    temporary_paths = {
        key: temporary_directory / path.name for key, path in output_paths.items()
    }
    try:
        written = write_jsonl_gzip(temporary_paths["catalogue"], records)
        report.update(
            {
                "output": relative["catalogue"],
                "output_sha256": written["sha256"],
            }
        )
        report_sha = _write_json(temporary_paths["report"], report)
        manifest = {
            "actionable_arm_id": "no_trade",
            "artifacts": [
                {"path": relative["catalogue"], "sha256": written["sha256"]},
                {"path": relative["report"], "sha256": report_sha},
            ],
            "bound_inputs": bound_inputs,
            "contract_path": contract_relative,
            "contract_sha256": contract_sha,
            "experiment_id": experiment_id,
            "phase": phase,
        }
        manifest_sha = _write_json(temporary_paths["manifest"], manifest)
        os.replace(temporary_directory, phase_directory)
    except Exception:
        shutil.rmtree(temporary_directory, ignore_errors=True)
        raise
    return {
        **report,
        "manifest": relative["manifest"],
        "manifest_sha256": manifest_sha,
        "report": relative["report"],
        "report_sha256": report_sha,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--phase", choices=("trigger", "label"), required=True)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    result = run(args.contract, args.experiment_id, args.root, args.phase)
    print(json.dumps(result, allow_nan=False, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
