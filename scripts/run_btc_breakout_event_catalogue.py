#!/usr/bin/env python3
"""Run the frozen offline BTC breakout-event catalogue contract.

The command has no network, database, message-bus, exchange, or production integration.
It refuses to infer an experiment ID or source: both must match the supplied frozen contract.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from trading_platform.btc_breakout_events import (
    COMPRESSION_QUANTILE,
    COMPRESSION_RUN,
    PATH_HORIZONS_HOURS,
    RANGE_BARS_4H,
    REFERENCE_WIDTHS,
    BreakoutEventError,
    build_breakout_event_catalogue,
    load_breakout_source_candles,
)
from trading_platform.research_ledger import iso_ms, sha256_file, write_jsonl_gzip
from trading_platform.research_routing import canonical_digest


ROOT = Path(__file__).resolve().parents[1]
DEVELOPMENT_END_EXCLUSIVE_MS = 1_767_225_600_000


def _read_json(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
        value = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise BreakoutEventError(f"cannot read contract: {path}") from exc
    if not isinstance(value, dict):
        raise BreakoutEventError("contract must be a JSON object")
    return value


def _pointer_parent(value: Any, pointer: str) -> tuple[Any, str]:
    if not pointer.startswith("/"):
        raise BreakoutEventError(f"invalid JSON pointer: {pointer}")
    parts = [part.replace("~1", "/").replace("~0", "~") for part in pointer[1:].split("/")]
    parent = value
    for part in parts[:-1]:
        try:
            parent = parent[int(part)] if isinstance(parent, list) else parent[part]
        except (IndexError, KeyError, TypeError, ValueError) as exc:
            raise BreakoutEventError(f"contract patch path does not exist: {pointer}") from exc
    return parent, parts[-1]


def _apply(value: dict[str, Any], operation: str, pointer: str, replacement: Any = None) -> None:
    parent, key = _pointer_parent(value, pointer)
    if isinstance(parent, list):
        if operation == "add" and key == "-":
            parent.append(copy.deepcopy(replacement))
            return
        try:
            index = int(key)
            if operation == "remove":
                parent.pop(index)
            elif operation == "replace":
                parent[index] = copy.deepcopy(replacement)
            elif operation == "add":
                parent.insert(index, copy.deepcopy(replacement))
            else:
                raise BreakoutEventError(f"unsupported contract patch operation: {operation}")
        except (IndexError, ValueError) as exc:
            raise BreakoutEventError(f"invalid contract list patch: {pointer}") from exc
        return
    if not isinstance(parent, dict):
        raise BreakoutEventError(f"contract patch parent is not a container: {pointer}")
    if operation in {"replace", "remove"} and key not in parent:
        raise BreakoutEventError(f"contract patch path does not exist: {pointer}")
    if operation == "remove":
        del parent[key]
    elif operation in {"replace", "add"}:
        parent[key] = copy.deepcopy(replacement)
    else:
        raise BreakoutEventError(f"unsupported contract patch operation: {operation}")


def _effective_contract(path: Path, root: Path) -> dict[str, Any]:
    wrapper = _read_json(path)
    base_reference = wrapper.get("base_contract")
    if not isinstance(base_reference, dict):
        return wrapper
    relative = base_reference.get("path")
    expected = base_reference.get("sha256")
    if not isinstance(relative, str) or not isinstance(expected, str):
        raise BreakoutEventError("successor contract base path/checksum are required")
    base_path = _inside_root(root, relative, must_exist=True)
    actual = hashlib.sha256(base_path.read_bytes()).hexdigest()
    if actual != expected:
        raise BreakoutEventError("successor contract base checksum mismatch")
    effective = copy.deepcopy(_effective_contract(base_path, root))
    for override in wrapper.get("overrides", []):
        if not isinstance(override, dict):
            raise BreakoutEventError("invalid successor contract override")
        _apply(
            effective,
            "replace",
            str(override.get("json_pointer", "")),
            override.get("replacement"),
        )
    for operation in wrapper.get("patch_operations", []):
        if not isinstance(operation, dict):
            raise BreakoutEventError("invalid successor contract patch")
        _apply(
            effective,
            str(operation.get("op", "")),
            str(operation.get("path", "")),
            operation.get("value"),
        )
    return effective


def _contract(path: Path, experiment_id: str, root: Path) -> dict[str, Any]:
    contract = _effective_contract(path, root)
    if contract.get("experiment_id") != experiment_id:
        raise BreakoutEventError("CLI experiment ID does not exactly match the contract")
    status = contract.get("status")
    if not isinstance(status, str) or not status.endswith("before_historical_event_outcomes"):
        raise BreakoutEventError("contract is not frozen before historical event outcomes")
    if contract.get("action_boundary", {}).get("actionable_arm_id") != "no_trade":
        raise BreakoutEventError("contract does not fail closed to no_trade")
    return contract


def _single_source(contract: dict[str, Any]) -> tuple[str, str]:
    candidates = [
        item
        for item in contract.get("bound_inputs", [])
        if isinstance(item, dict) and str(item.get("path", "")).endswith(".csv.gz")
    ]
    if len(candidates) != 1:
        raise BreakoutEventError("contract must bind exactly one gzip CSV source")
    path = candidates[0].get("path")
    digest = candidates[0].get("sha256")
    if not isinstance(path, str) or not isinstance(digest, str):
        raise BreakoutEventError("contract source path and checksum are required")
    return path, digest


def _validate_rules(contract: dict[str, Any]) -> None:
    rules = contract.get("catalogue_rules", {})
    expected = {
        "activation_expiry_hours": PATH_HORIZONS_HOURS[-1],
        "compression_quantile": COMPRESSION_QUANTILE,
        "compression_reference_widths": REFERENCE_WIDTHS,
        "compression_required_consecutive_bars": COMPRESSION_RUN,
        "range_bars": RANGE_BARS_4H,
    }
    for key, value in expected.items():
        if rules.get(key) != value:
            raise BreakoutEventError(f"contract/code rule mismatch: {key}")
    labels = contract.get("label_rules", {})
    if labels.get("administrative_horizon_hours") != PATH_HORIZONS_HOURS[-1]:
        raise BreakoutEventError("contract/code rule mismatch: administrative_horizon_hours")
    if labels.get("event_tie_precedence") != "range_reentry":
        raise BreakoutEventError("contract/code rule mismatch: event_tie_precedence")


def _validate_bound_inputs(contract: dict[str, Any], root: Path) -> list[dict[str, str]]:
    checked: list[dict[str, str]] = []
    inputs = contract.get("bound_inputs")
    if not isinstance(inputs, list) or not inputs:
        raise BreakoutEventError("contract bound_inputs are required")
    for item in inputs:
        if not isinstance(item, dict):
            raise BreakoutEventError("invalid bound input")
        relative = item.get("path")
        expected = item.get("sha256")
        if not isinstance(relative, str) or not isinstance(expected, str):
            raise BreakoutEventError("bound input path/checksum are required")
        path = _inside_root(root, relative, must_exist=True)
        actual = sha256_file(path)
        if actual != expected:
            raise BreakoutEventError(f"bound input checksum mismatch: {relative}")
        checked.append({"path": relative, "sha256": actual})
    return checked


def _canonical_write(path: Path, value: dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            separators=(",", ": "),
        )
        + "\n",
        encoding="utf-8",
    )
    return sha256_file(path)


def _inside_root(root: Path, relative: str, *, must_exist: bool) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise BreakoutEventError("contract path must be repository-relative")
    resolved_root = root.resolve(strict=True)
    resolved = (resolved_root / candidate).resolve(strict=must_exist)
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise BreakoutEventError("contract path leaves the repository root")
    return resolved


def run(contract_path: Path, experiment_id: str, root: Path) -> dict[str, Any]:
    resolved_root = root.resolve(strict=True)
    resolved_contract = contract_path.resolve(strict=True)
    if resolved_contract != resolved_root and resolved_root not in resolved_contract.parents:
        raise BreakoutEventError("contract path leaves the repository root")
    contract_relative = str(resolved_contract.relative_to(resolved_root))
    contract = _contract(resolved_contract, experiment_id, resolved_root)
    _validate_rules(contract)
    output_relative = contract.get("outputs", {}).get("catalogue")
    if not isinstance(output_relative, str) or not output_relative.endswith(".jsonl.gz"):
        raise BreakoutEventError("contract catalogue output must be a gzip JSONL path")
    report_relative = contract.get("outputs", {}).get("preflight_report")
    manifest_relative = contract.get("outputs", {}).get("evidence_manifest")
    if not isinstance(report_relative, str) or not isinstance(manifest_relative, str):
        raise BreakoutEventError("contract report and evidence-manifest outputs are required")
    output = _inside_root(root, output_relative, must_exist=False)
    report_path = _inside_root(root, report_relative, must_exist=False)
    manifest_path = _inside_root(root, manifest_relative, must_exist=False)
    if len({output, report_path, manifest_path}) != 3:
        raise BreakoutEventError("contract output paths must be distinct")
    for candidate in (output, report_path, manifest_path):
        if candidate.exists():
            raise BreakoutEventError(f"refusing to overwrite existing artifact: {candidate}")
    bound_inputs = _validate_bound_inputs(contract, root)
    source_relative, source_digest = _single_source(contract)
    source_path = _inside_root(root, source_relative, must_exist=True)
    rows, actual_digest = load_breakout_source_candles(source_path, source_digest)
    expected_rows = contract.get("input_contract", {}).get("expected_rows")
    if not isinstance(expected_rows, int) or len(rows) != expected_rows:
        raise BreakoutEventError(
            f"source row count mismatch: expected {expected_rows}, got {len(rows)}"
        )
    if rows[-1].close_ms > DEVELOPMENT_END_EXCLUSIVE_MS:
        raise BreakoutEventError("source causal availability exceeds the frozen development boundary")
    catalogue = build_breakout_event_catalogue(
        rows,
        source_digest=actual_digest,
        experiment_id=experiment_id,
        decision_end_exclusive_ms=DEVELOPMENT_END_EXCLUSIVE_MS,
    )
    written = write_jsonl_gzip(output, (episode.as_dict() for episode in catalogue.episodes))
    contract_sha256 = sha256_file(resolved_contract)
    confirmed = [episode for episode in catalogue.episodes if episode.confirmation_ms is not None]
    competing_counts = Counter(
        episode.competing_outcome for episode in confirmed if episode.competing_outcome is not None
    )
    termination_counts = Counter(episode.termination_reason for episode in catalogue.episodes)
    model_ready = [episode for episode in confirmed if episode.model_ready]
    model_ready_counts = Counter(
        episode.competing_outcome if episode.competing_outcome is not None else "right_censored"
        for episode in model_ready
    )
    model_ready_by_year: dict[str, Counter[str]] = {}
    for episode in model_ready:
        year = iso_ms(episode.confirmation_ms)[:4]
        model_ready_by_year.setdefault(year, Counter())[
            episode.competing_outcome if episode.competing_outcome is not None else "right_censored"
        ] += 1
    report = {
        "actionable_arm_id": "no_trade",
        "aggregate_rows_1h": catalogue.aggregate_rows_1h,
        "aggregate_rows_4h": catalogue.aggregate_rows_4h,
        "catalogue_digest": catalogue.catalogue_digest,
        "confirmed_episode_count": len(confirmed),
        "model_ready_episode_count": sum(episode.model_ready for episode in confirmed),
        "model_ready_competing_counts": dict(sorted(model_ready_counts.items())),
        "model_ready_competing_counts_by_confirmation_year": {
            year: dict(sorted(counts.items())) for year, counts in sorted(model_ready_by_year.items())
        },
        "augmented_diagnostic_ready_episode_count": sum(
            episode.augmented_diagnostic_ready for episode in confirmed
        ),
        "continuation_count": competing_counts["continuation"],
        "range_reentry_count": competing_counts["range_reentry"],
        "right_censored_count": sum(
            episode.competing_outcome is None for episode in confirmed
        ),
        "setup_termination_counts": dict(sorted(termination_counts.items())),
        "contract_path": contract_relative,
        "contract_sha256": contract_sha256,
        "effective_contract_digest": canonical_digest(contract),
        "episode_count": len(catalogue.episodes),
        "experiment_id": experiment_id,
        "output": output_relative,
        "output_sha256": written["sha256"],
        "research_disposition": "development_event_catalogue_only",
        "source_digest": actual_digest,
        "source_last_close_at": iso_ms(rows[-1].close_ms),
        "source_last_close_before_2026": True,
        "source_rows": len(rows),
    }
    report_sha256 = _canonical_write(report_path, report)
    manifest = {
        "actionable_arm_id": "no_trade",
        "artifacts": [
            {"path": output_relative, "sha256": written["sha256"]},
            {"path": report_relative, "sha256": report_sha256},
        ],
        "bound_inputs": bound_inputs,
        "contract_path": contract_relative,
        "contract_sha256": contract_sha256,
        "effective_contract_digest": canonical_digest(contract),
        "experiment_id": experiment_id,
    }
    manifest_sha256 = _canonical_write(manifest_path, manifest)
    return {
        **report,
        "evidence_manifest": manifest_relative,
        "evidence_manifest_sha256": manifest_sha256,
        "preflight_report": report_relative,
        "preflight_report_sha256": report_sha256,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    result = run(args.contract, args.experiment_id, args.root)
    print(json.dumps(result, allow_nan=False, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
