"""Offline BTC spot/perpetual continuation-information research.

This module contains no strategy, position, execution, cost, exchange, database, message-bus,
credential, or network code.  It implements the frozen D1 feature, label, and forecast contracts
against local checksummed evidence only.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Any, Iterable, Mapping, Sequence

import numpy as np


UTC = timezone.utc
DAY_MS = 86_400_000
FIVE_MINUTES_MS = 300_000
HORIZON_MS = 72 * 60 * 60 * 1000
YEAR_2021_MS = 1_609_459_200_000
YEAR_2026_MS = 1_767_225_600_000
CONTROL_FEATURES = (
    "lagged_72h_spot_return_z",
    "log_spot_rv7_z",
    "spot_turnover_z",
)
CANDIDATE_FEATURES = (
    "basis_impulse_z",
    "spot_minus_perpetual_turnover_z",
)


class SpotPerpContinuationError(ValueError):
    """Raised when a frozen D1 input or causal invariant fails."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(value: object) -> str:
    return json.dumps(
        value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False
    ) + "\n"


def canonical_line(value: object) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def record_digest(value: Mapping[str, Any], digest_key: str) -> str:
    payload = {key: item for key, item in value.items() if key != digest_key}
    return hashlib.sha256(canonical_line(payload).encode()).hexdigest()


def rounded(value: float, places: int = 12) -> float:
    if not math.isfinite(value):
        raise SpotPerpContinuationError("non-finite numeric result")
    result = round(float(value), places)
    return 0.0 if result == 0.0 else result


def iso_ms(value: int) -> str:
    if value % 1000:
        raise SpotPerpContinuationError("timestamp is not whole-second milliseconds")
    return datetime.fromtimestamp(value / 1000, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_utc_z_ms(value: object, label: str) -> int:
    if not isinstance(value, str) or not value.endswith("Z") or "." in value:
        raise SpotPerpContinuationError(f"{label} must be canonical whole-second UTC Z")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as exc:
        raise SpotPerpContinuationError(f"invalid {label}") from exc
    return int(parsed.timestamp() * 1000)


def _reject_symlink_tree(path: Path) -> None:
    candidate = path.absolute()
    for item in (candidate, *candidate.parents):
        if item.is_symlink():
            raise SpotPerpContinuationError(f"symlinked frozen path is prohibited: {item}")


def write_jsonl_gzip(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    if path.exists():
        raise SpotPerpContinuationError(f"refusing to overwrite evidence: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=9, mtime=0) as zipped:
            for row in rows:
                zipped.write((canonical_line(row) + "\n").encode())


def read_jsonl_gzip(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            try:
                value = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise SpotPerpContinuationError(
                    f"invalid JSON line {line_number}: {path}"
                ) from exc
            if not isinstance(value, dict) or raw != canonical_line(value) + "\n":
                raise SpotPerpContinuationError(f"non-canonical JSON line {line_number}: {path}")
            rows.append(value)
    return rows


def resolve_effective_contract(root: Path, v2_path: Path) -> dict[str, Any]:
    v2 = json.loads(v2_path.read_text(encoding="utf-8"))
    if v2.get("status") != "frozen_before_any_D1_v2_historical_feature_label_or_model_access":
        raise SpotPerpContinuationError("D1 v2 contract is not frozen")
    base_ref = v2["base_contract"]
    base_path = root / base_ref["path"]
    if sha256_file(base_path) != base_ref["sha256"]:
        raise SpotPerpContinuationError("D1 v1 base-contract checksum mismatch")
    if sha256_file(root / v2["predecessor"]["result_path"]) != v2["predecessor"]["result_sha256"]:
        raise SpotPerpContinuationError("D1 v1 preflight-result checksum mismatch")
    if sha256_file(root / v2["v2_plan_addendum"]["path"]) != v2["v2_plan_addendum"]["sha256"]:
        raise SpotPerpContinuationError("D1 v2 plan-addendum checksum mismatch")
    effective = json.loads(base_path.read_text(encoding="utf-8"))
    effective["experiment_id"] = v2["experiment_id"]
    effective["status"] = v2["status"]
    old_root = "artifacts/agent-level-experiment/btc-focused/spot-perp-continuation-d1-v1"
    new_root = v2["outputs_root"]
    effective["outputs"] = {
        key: value.replace(old_root, new_root) for key, value in effective["outputs"].items()
    }
    removed = v2["label_gate_override"]["remove"]
    for key, expected in removed.items():
        if effective["label_gates"].pop(key, None) != expected:
            raise SpotPerpContinuationError("D1 v2 label-gate removal does not match base")
    effective["label_gates"].update(v2["label_gate_override"]["set"])
    effective["v2_contract"] = {
        "path": str(v2_path.relative_to(root)),
        "sha256": sha256_file(v2_path),
    }
    return effective


def validate_bound_inputs(root: Path, contract: Mapping[str, Any]) -> None:
    for item in contract["bound_inputs"]:
        path = root / item["path"]
        _reject_symlink_tree(path)
        if not path.is_file() or sha256_file(path) != item["sha256"]:
            raise SpotPerpContinuationError(f"missing or changed bound input: {item['path']}")


@dataclass(frozen=True, slots=True)
class DailyPair:
    open_ms: int
    spot_close: float
    spot_quote_volume: float
    perpetual_close: float
    perpetual_quote_volume: float


def load_daily_pairs(root: Path, contract: Mapping[str, Any]) -> list[DailyPair]:
    """Load D0 sources using its checksum-bound parser, without any target source."""

    from scripts.audit_btc_spot_perp_continuation_data_v3 import (  # local, offline
        load_monthly,
        load_rest,
    )

    manifest_item = next(
        item
        for item in contract["bound_inputs"]
        if item["path"].endswith("spot-perp-continuation-d0-v3/source-manifest.json")
    )
    manifest_path = root / manifest_item["path"]
    if sha256_file(manifest_path) != manifest_item["sha256"]:
        raise SpotPerpContinuationError("D0 source-manifest checksum mismatch")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        manifest.get("credentials_used") is not False
        or manifest.get("archive_failures") != 0
        or len(manifest.get("archive_records", [])) != 148
    ):
        raise SpotPerpContinuationError("D0 source manifest is not accepted input evidence")
    spot, spot_summary = load_monthly(manifest, "spot")
    perpetual_monthly, perpetual_summary = load_monthly(manifest, "perpetual")
    rest = load_rest(manifest)
    perpetual = {timestamp: row for timestamp, row in rest.items() if timestamp < 1_577_836_800_000}
    perpetual.update(perpetual_monthly)
    common = sorted(set(spot).intersection(perpetual))
    if (
        spot_summary["gap_count"] != 0
        or perpetual_summary["gap_count"] != 0
        or not common
        or common[-1] >= YEAR_2026_MS
    ):
        raise SpotPerpContinuationError("daily source continuity or boundary changed")
    output: list[DailyPair] = []
    for opened in common:
        spot_row = spot[opened]
        perp_row = perpetual[opened]
        values = [float(spot_row[4]), float(spot_row[7]), float(perp_row[4]), float(perp_row[7])]
        if not all(math.isfinite(value) and value > 0 for value in values):
            raise SpotPerpContinuationError("invalid daily close or quote turnover")
        output.append(DailyPair(opened, *values))
    return output


def robust_z(
    values: Sequence[float | None], index: int, window: int, clip: float
) -> float | None:
    if index < window or values[index] is None:
        return None
    prior = values[index - window : index]
    if len(prior) != window or any(value is None or not math.isfinite(value) for value in prior):
        return None
    observations = [float(value) for value in prior if value is not None]
    center = median(observations)
    mad = median(abs(value - center) for value in observations)
    scale = 1.4826 * mad
    if not math.isfinite(scale) or scale <= 0:
        return None
    result = (float(values[index]) - center) / scale
    return max(-clip, min(clip, result))


def build_feature_rows(
    pairs: Sequence[DailyPair], contract: Mapping[str, Any], source_sha256: str
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    if not pairs:
        raise SpotPerpContinuationError("daily pair input is empty")
    window = int(contract["feature_contract"]["robust_window_days"])
    clip = float(contract["feature_contract"]["clip_absolute_z"])
    features: list[dict[str, Any]] = []
    unknown_after_minimum = 0
    segment_start = 0
    segment_id = 0
    while segment_start < len(pairs):
        segment_end = segment_start + 1
        while (
            segment_end < len(pairs)
            and pairs[segment_end].open_ms == pairs[segment_end - 1].open_ms + DAY_MS
        ):
            segment_end += 1
        segment = pairs[segment_start:segment_end]
        count = len(segment)
        returns: list[float | None] = [None] * count
        r72: list[float | None] = [None] * count
        log_rv7: list[float | None] = [None] * count
        basis_impulse: list[float | None] = [None] * count
        log_spot_turnover: list[float | None] = [None] * count
        log_perp_turnover: list[float | None] = [None] * count
        basis = [math.log(row.perpetual_close / row.spot_close) for row in segment]
        for index, row in enumerate(segment):
            log_spot_turnover[index] = math.log(row.spot_quote_volume)
            log_perp_turnover[index] = math.log(row.perpetual_quote_volume)
            if index >= 1:
                returns[index] = math.log(row.spot_close / segment[index - 1].spot_close)
                basis_impulse[index] = basis[index] - basis[index - 1]
            if index >= 3:
                r72[index] = math.log(row.spot_close / segment[index - 3].spot_close)
            if index >= 7:
                variance = sum(float(returns[offset]) ** 2 for offset in range(index - 6, index + 1))
                if variance > 0:
                    log_rv7[index] = math.log(math.sqrt(variance))
        raw_series = (r72, log_rv7, log_spot_turnover, basis_impulse, log_perp_turnover)
        minimum_index = window + 7
        for index, row in enumerate(segment):
            scores = [robust_z(values, index, window, clip) for values in raw_series]
            if any(value is None for value in scores):
                if index >= minimum_index:
                    unknown_after_minimum += 1
                continue
            r72_z, rv_z, spot_turnover_z, basis_z, perp_turnover_z = [float(value) for value in scores]
            observed_ms = row.open_ms + DAY_MS
            decision_ms = observed_ms + FIVE_MINUTES_MS
            if decision_ms >= YEAR_2026_MS:
                continue
            values = {
                "basis_impulse_z": rounded(basis_z),
                "lagged_72h_spot_return_z": rounded(r72_z),
                "log_spot_rv7_z": rounded(rv_z),
                "spot_minus_perpetual_turnover_z": rounded(spot_turnover_z - perp_turnover_z),
                "spot_turnover_z": rounded(spot_turnover_z),
            }
            record: dict[str, Any] = {
                "available_at": iso_ms(decision_ms),
                "candidate_experiment_id": contract["candidate_experiment_id"],
                "decision_at": iso_ms(decision_ms),
                "experiment_id": contract["experiment_id"],
                "feature_values": values,
                "instrument": "BTC/USDT",
                "interval": "1d",
                "observed_at": iso_ms(observed_ms),
                "segment": f"d0-common-{segment_id}",
                "source_day_open_at": iso_ms(row.open_ms),
                "source_manifest_sha256": source_sha256,
                "source_window_start_at": iso_ms(segment[index - minimum_index].open_ms),
            }
            record["feature_digest"] = record_digest(record, "feature_digest")
            features.append(record)
        segment_start = segment_end
        segment_id += 1
    return features, {
        "daily_segment_count": segment_id,
        "unknown_after_minimum_history": unknown_after_minimum,
    }


def feature_gate_report(
    rows: Sequence[Mapping[str, Any]], diagnostics: Mapping[str, int], contract: Mapping[str, Any]
) -> dict[str, Any]:
    counts: dict[str, int] = {}
    months: set[str] = set()
    segments: set[str] = set()
    for row in rows:
        decision = datetime.fromtimestamp(parse_utc_z_ms(row["decision_at"], "decision_at") / 1000, tz=UTC)
        counts[str(decision.year)] = counts.get(str(decision.year), 0) + 1
        if 2021 <= decision.year <= 2025:
            months.add(decision.strftime("%Y-%m"))
        segments.add(str(row["segment"]))
    expected_evaluation = sum(366 if year == 2024 else 365 for year in range(2021, 2026))
    observed_evaluation = sum(counts.get(str(year), 0) for year in range(2021, 2026))
    expected_months = {f"{year:04d}-{month:02d}" for year in range(2021, 2026) for month in range(1, 13)}
    gates = contract["feature_gates"]
    gate_results = {
        "all_causality_checksum_timestamp_and_segment_checks_pass": True,
        "evaluation_feature_coverage_minimum": observed_evaluation / expected_evaluation >= gates["evaluation_feature_coverage_minimum"],
        "evaluation_feature_rows_each_year_minimum": all(counts.get(str(year), 0) >= gates["evaluation_feature_rows_each_year_minimum"] for year in range(2021, 2026)),
        "evaluation_months_missing_maximum": len(expected_months - months) <= gates["evaluation_months_missing_maximum"],
        "feature_segments_required": len(segments) == gates["feature_segments_required"],
        "invalid_feature_rows_maximum": diagnostics["unknown_after_minimum_history"] <= gates["invalid_feature_rows_maximum"],
        "pre_2021_feature_rows_minimum": sum(value for year, value in counts.items() if int(year) < 2021) >= gates["pre_2021_feature_rows_minimum"],
    }
    return {
        "actionable_arm_id": "no_trade",
        "candidate_experiment_id": contract["candidate_experiment_id"],
        "decision": "D1_features_passed_label_source_may_open" if all(gate_results.values()) else "D1_features_rejected_stop_before_labels",
        "evaluation_coverage": observed_evaluation / expected_evaluation,
        "experiment_id": contract["experiment_id"],
        "feature_count": len(rows),
        "feature_counts_by_year": dict(sorted(counts.items())),
        "feature_gate_passed": all(gate_results.values()),
        "gate_results": gate_results,
        "label_target_forecast_model_strategy_or_pnl_created": False,
        "missing_evaluation_months": sorted(expected_months - months),
        "pre_2021_feature_count": sum(value for year, value in counts.items() if int(year) < 2021),
        "segment_count": len(segments),
        "unknown_after_minimum_history": diagnostics["unknown_after_minimum_history"],
    }


def load_feature_rows(path: Path, expected_sha256: str, experiment_id: str) -> list[dict[str, Any]]:
    if sha256_file(path) != expected_sha256:
        raise SpotPerpContinuationError("feature-ledger checksum mismatch")
    rows = read_jsonl_gzip(path)
    previous = -1
    for row in rows:
        if row.get("experiment_id") != experiment_id:
            raise SpotPerpContinuationError("wrong feature experiment identity")
        if row.get("feature_digest") != record_digest(row, "feature_digest"):
            raise SpotPerpContinuationError("feature digest mismatch")
        if set(row.get("feature_values", {})) != set(CONTROL_FEATURES + CANDIDATE_FEATURES):
            raise SpotPerpContinuationError("feature set changed")
        timestamp = parse_utc_z_ms(row["decision_at"], "decision_at")
        if timestamp <= previous or timestamp >= YEAR_2026_MS or timestamp % DAY_MS != FIVE_MINUTES_MS:
            raise SpotPerpContinuationError("feature chronology changed")
        previous = timestamp
    return rows


@dataclass(frozen=True, slots=True)
class FiveMinuteOpen:
    segment: str
    open_price: float


def load_needed_five_minute_opens(
    path: Path, expected_sha256: str, expected_rows: int, needed_ms: set[int]
) -> dict[int, FiveMinuteOpen]:
    _reject_symlink_tree(path)
    lowered = str(path.resolve(strict=True)).lower()
    if "holdout" in lowered or "2026" in path.name.lower():
        raise SpotPerpContinuationError("prohibited target-source path")
    if sha256_file(path) != expected_sha256:
        raise SpotPerpContinuationError("five-minute target-source checksum mismatch")
    output: dict[int, FiveMinuteOpen] = {}
    previous_ms = -1
    previous_segment: str | None = None
    closed_segments: set[str] = set()
    row_count = 0
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for row_count, raw in enumerate(handle, start=1):
            try:
                row = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise SpotPerpContinuationError(f"invalid five-minute JSON at row {row_count}") from exc
            required = {"instrument", "interval", "open", "open_at", "segment"}
            if not isinstance(row, dict) or not required.issubset(row):
                raise SpotPerpContinuationError(f"missing five-minute fields at row {row_count}")
            if row["instrument"] != "BTC/USDT" or row["interval"] != "5m":
                raise SpotPerpContinuationError(f"wrong five-minute identity at row {row_count}")
            opened = parse_utc_z_ms(row["open_at"], "open_at")
            if opened % FIVE_MINUTES_MS or opened <= previous_ms or opened >= YEAR_2026_MS:
                raise SpotPerpContinuationError(f"invalid five-minute timestamp at row {row_count}")
            segment = str(row["segment"])
            if previous_segment is not None:
                if segment == previous_segment:
                    if opened != previous_ms + FIVE_MINUTES_MS:
                        raise SpotPerpContinuationError(f"gap inside five-minute segment at row {row_count}")
                else:
                    closed_segments.add(previous_segment)
                    if segment in closed_segments:
                        raise SpotPerpContinuationError(f"five-minute segment reappears at row {row_count}")
            try:
                price = float(row["open"])
            except (TypeError, ValueError) as exc:
                raise SpotPerpContinuationError(f"invalid five-minute open at row {row_count}") from exc
            if not math.isfinite(price) or price <= 0:
                raise SpotPerpContinuationError(f"invalid five-minute open at row {row_count}")
            if opened in needed_ms:
                output[opened] = FiveMinuteOpen(segment, price)
            previous_ms = opened
            previous_segment = segment
    if row_count != expected_rows:
        raise SpotPerpContinuationError(
            f"five-minute row count changed: expected {expected_rows}, got {row_count}"
        )
    return output


def build_label_rows(
    features: Sequence[Mapping[str, Any]], opens: Mapping[int, FiveMinuteOpen], contract: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    labels: list[dict[str, Any]] = []
    missing = 0
    crossing = 0
    outside_boundary = 0
    for feature in features:
        decision_ms = parse_utc_z_ms(feature["decision_at"], "decision_at")
        target_ms = decision_ms + HORIZON_MS
        if target_ms >= YEAR_2026_MS:
            outside_boundary += 1
            continue
        entry = opens.get(decision_ms)
        exit_ = opens.get(target_ms)
        if entry is None or exit_ is None:
            missing += 1
            continue
        if entry.segment != exit_.segment:
            crossing += 1
            continue
        target = math.log(exit_.open_price / entry.open_price)
        record: dict[str, Any] = {
            "decision_at": feature["decision_at"],
            "experiment_id": contract["experiment_id"],
            "feature_digest": feature["feature_digest"],
            "five_minute_segment": entry.segment,
            "target_available_at": iso_ms(target_ms),
            "target_return": rounded(target),
        }
        record["label_digest"] = record_digest(record, "label_digest")
        labels.append(record)
    return labels, {
        "excluded_cross_segment_candidates": crossing,
        "excluded_missing_exact_open_candidates": missing,
        "excluded_target_end_at_or_after_2026": outside_boundary,
        "serialized_invalid_labels": 0,
    }


def label_gate_report(
    features: Sequence[Mapping[str, Any]],
    labels: Sequence[Mapping[str, Any]],
    diagnostics: Mapping[str, int],
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    eligible_features: dict[str, int] = {}
    for row in features:
        decision = parse_utc_z_ms(row["decision_at"], "decision_at")
        if decision + HORIZON_MS >= YEAR_2026_MS:
            continue
        year = str(datetime.fromtimestamp(decision / 1000, tz=UTC).year)
        if 2021 <= int(year) <= 2025:
            eligible_features[year] = eligible_features.get(year, 0) + 1
    label_counts: dict[str, int] = {}
    pre_2021 = 0
    for row in labels:
        decision = parse_utc_z_ms(row["decision_at"], "decision_at")
        target = parse_utc_z_ms(row["target_available_at"], "target_available_at")
        if target >= YEAR_2026_MS or target != decision + HORIZON_MS:
            raise SpotPerpContinuationError("serialized label violates target boundary")
        year = datetime.fromtimestamp(decision / 1000, tz=UTC).year
        if year < 2021 and target < YEAR_2021_MS + FIVE_MINUTES_MS:
            pre_2021 += 1
        if 2021 <= year <= 2025:
            label_counts[str(year)] = label_counts.get(str(year), 0) + 1
    evaluation_count = sum(label_counts.values())
    eligible_count = sum(eligible_features.values())
    coverage_by_year = {
        str(year): label_counts.get(str(year), 0) / eligible_features.get(str(year), 1)
        for year in range(2021, 2026)
    }
    gates = contract["label_gates"]
    gate_results = {
        "all_exact_open_checksum_timestamp_segment_and_2026_checks_pass": True,
        "evaluation_label_coverage_minimum": evaluation_count / eligible_count >= gates["evaluation_label_coverage_minimum"],
        "evaluation_label_rows_each_year_minimum": all(label_counts.get(str(year), 0) >= gates["evaluation_label_rows_each_year_minimum"] for year in range(2021, 2026)),
        "evaluation_label_rows_minimum": evaluation_count >= gates["evaluation_label_rows_minimum"],
        "per_year_label_coverage_minimum": all(value >= gates["per_year_label_coverage_minimum"] for value in coverage_by_year.values()),
        "pre_2021_training_labels_minimum": pre_2021 >= gates["pre_2021_training_labels_minimum"],
        "serialized_invalid_labels_maximum": diagnostics["serialized_invalid_labels"] <= gates["serialized_invalid_labels_maximum"],
    }
    return {
        "actionable_arm_id": "no_trade",
        "coverage_by_year": coverage_by_year,
        "decision": "D1_labels_passed_model_may_fit" if all(gate_results.values()) else "D1_labels_rejected_stop_before_model",
        "diagnostics": dict(diagnostics),
        "evaluation_coverage": evaluation_count / eligible_count,
        "evaluation_eligible_feature_count": eligible_count,
        "evaluation_label_count": evaluation_count,
        "experiment_id": contract["experiment_id"],
        "gate_results": gate_results,
        "label_counts_by_year": dict(sorted(label_counts.items())),
        "label_gate_passed": all(gate_results.values()),
        "model_forecast_strategy_or_pnl_created": False,
        "pre_2021_training_label_count": pre_2021,
    }


def load_label_rows(path: Path, expected_sha256: str, experiment_id: str) -> list[dict[str, Any]]:
    if sha256_file(path) != expected_sha256:
        raise SpotPerpContinuationError("label-ledger checksum mismatch")
    rows = read_jsonl_gzip(path)
    previous = -1
    for row in rows:
        if row.get("experiment_id") != experiment_id or row.get("label_digest") != record_digest(row, "label_digest"):
            raise SpotPerpContinuationError("label identity or digest mismatch")
        decision = parse_utc_z_ms(row["decision_at"], "decision_at")
        target = parse_utc_z_ms(row["target_available_at"], "target_available_at")
        if decision <= previous or target != decision + HORIZON_MS or target >= YEAR_2026_MS:
            raise SpotPerpContinuationError("label chronology changed")
        previous = decision
    return rows


def ols(y: np.ndarray, x: np.ndarray) -> np.ndarray:
    if y.ndim != 1 or x.ndim != 2 or len(y) != len(x) or len(y) < x.shape[1] + 2:
        raise SpotPerpContinuationError("invalid or insufficient OLS input")
    design = np.column_stack([np.ones(len(y), dtype=np.float64), x.astype(np.float64)])
    if not np.isfinite(design).all() or not np.isfinite(y).all():
        raise SpotPerpContinuationError("non-finite OLS input")
    coefficients, _, rank, _ = np.linalg.lstsq(design, y.astype(np.float64), rcond=None)
    if rank != design.shape[1]:
        raise SpotPerpContinuationError("rank-deficient OLS input")
    return coefficients


def _average_ranks(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values), dtype=np.float64)
    start = 0
    while start < len(values):
        end = start + 1
        while end < len(values) and values[order[end]] == values[order[start]]:
            end += 1
        ranks[order[start:end]] = (start + end - 1) / 2.0
        start = end
    return ranks


def spearman(x: np.ndarray, y: np.ndarray) -> float:
    if len(x) < 3 or len(x) != len(y) or not np.isfinite(x).all() or not np.isfinite(y).all():
        raise SpotPerpContinuationError("invalid rank-correlation input")
    xr = _average_ranks(x)
    yr = _average_ranks(y)
    if xr.std() <= 0 or yr.std() <= 0:
        raise SpotPerpContinuationError("constant rank-correlation input")
    return float(np.corrcoef(xr, yr)[0, 1])


def _month_cutoff(decision_ms: int) -> int:
    value = datetime.fromtimestamp(decision_ms / 1000, tz=UTC)
    return int(datetime(value.year, value.month, 1, 0, 5, tzinfo=UTC).timestamp() * 1000)


def walk_forward(
    features: Sequence[Mapping[str, Any]], labels: Sequence[Mapping[str, Any]], contract: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    feature_by_digest = {row["feature_digest"]: row for row in features}
    joined = []
    for label in labels:
        feature = feature_by_digest.get(label["feature_digest"])
        if feature is None or feature["decision_at"] != label["decision_at"]:
            raise SpotPerpContinuationError("label cannot join exact feature")
        joined.append((feature, label))
    joined.sort(key=lambda item: item[0]["decision_at"])
    minimum = int(contract["chronology"]["minimum_training_rows"])
    eval_start = parse_utc_z_ms(contract["chronology"]["evaluation_start_inclusive"], "evaluation_start")
    evaluation = [item for item in joined if parse_utc_z_ms(item[0]["decision_at"], "decision_at") >= eval_start]
    cache: dict[int, tuple[float, np.ndarray, np.ndarray, list[float], int]] = {}
    forecasts: list[dict[str, Any]] = []
    snapshots: list[dict[str, Any]] = []
    names0 = CONTROL_FEATURES
    names1 = CONTROL_FEATURES + CANDIDATE_FEATURES
    for feature, label in evaluation:
        decision_ms = parse_utc_z_ms(feature["decision_at"], "decision_at")
        cutoff = _month_cutoff(decision_ms)
        if cutoff not in cache:
            training = [
                item
                for item in joined
                if parse_utc_z_ms(item[1]["target_available_at"], "target_available_at") < cutoff
            ]
            if len(training) < minimum:
                raise SpotPerpContinuationError(f"insufficient training rows at {iso_ms(cutoff)}")
            y = np.asarray([item[1]["target_return"] for item in training], dtype=np.float64)
            x0 = np.asarray([[item[0]["feature_values"][name] for name in names0] for item in training], dtype=np.float64)
            x1 = np.asarray([[item[0]["feature_values"][name] for name in names1] for item in training], dtype=np.float64)
            b0 = float(y.mean())
            coefficients0 = ols(y, x0)
            coefficients1 = ols(y, x1)
            pred0_train = np.column_stack([np.ones(len(x0)), x0]) @ coefficients0
            pred1_train = np.column_stack([np.ones(len(x1)), x1]) @ coefficients1
            thresholds = [float(value) for value in np.quantile(pred1_train - pred0_train, [0.2, 0.4, 0.6, 0.8])]
            cache[cutoff] = (b0, coefficients0, coefficients1, thresholds, len(training))
            snapshot: dict[str, Any] = {
                "B0_mean": rounded(b0),
                "M0_coefficients": [rounded(value) for value in coefficients0],
                "M0_feature_names": ["intercept", *names0],
                "M1_coefficients": [rounded(value) for value in coefficients1],
                "M1_feature_names": ["intercept", *names1],
                "delta_training_quintile_thresholds": [rounded(value) for value in thresholds],
                "experiment_id": contract["experiment_id"],
                "fit_cutoff": iso_ms(cutoff),
                "training_rows": len(training),
            }
            snapshot["snapshot_digest"] = record_digest(snapshot, "snapshot_digest")
            snapshots.append(snapshot)
        b0, coefficients0, coefficients1, thresholds, training_count = cache[cutoff]
        values0 = np.asarray([1.0, *[feature["feature_values"][name] for name in names0]], dtype=np.float64)
        values1 = np.asarray([1.0, *[feature["feature_values"][name] for name in names1]], dtype=np.float64)
        prediction0 = float(values0 @ coefficients0)
        prediction1 = float(values1 @ coefficients1)
        delta = prediction1 - prediction0
        bucket = 1 + sum(delta > threshold for threshold in thresholds)
        forecast: dict[str, Any] = {
            "B0_prediction": rounded(b0),
            "M0_prediction": rounded(prediction0),
            "M1_prediction": rounded(prediction1),
            "actual_target_return": label["target_return"],
            "decision_at": feature["decision_at"],
            "delta_prediction": rounded(delta),
            "delta_training_bucket": bucket,
            "experiment_id": contract["experiment_id"],
            "feature_digest": feature["feature_digest"],
            "fit_cutoff": iso_ms(cutoff),
            "label_digest": label["label_digest"],
            "target_available_at": label["target_available_at"],
            "training_rows": training_count,
        }
        forecast["forecast_digest"] = record_digest(forecast, "forecast_digest")
        forecasts.append(forecast)
    return forecasts, snapshots


def _metric_arrays(rows: Sequence[Mapping[str, Any]], indices: np.ndarray | None = None) -> tuple[np.ndarray, ...]:
    if indices is None:
        indices = np.arange(len(rows))
    y = np.asarray([rows[index]["actual_target_return"] for index in indices], dtype=np.float64)
    b0 = np.asarray([rows[index]["B0_prediction"] for index in indices], dtype=np.float64)
    m0 = np.asarray([rows[index]["M0_prediction"] for index in indices], dtype=np.float64)
    m1 = np.asarray([rows[index]["M1_prediction"] for index in indices], dtype=np.float64)
    delta = np.asarray([rows[index]["delta_prediction"] for index in indices], dtype=np.float64)
    buckets = np.asarray([rows[index]["delta_training_bucket"] for index in indices], dtype=int)
    return y, b0, m0, m1, delta, buckets


def joint_three_month_bootstrap(
    rows: Sequence[Mapping[str, Any]], replications: int, seed: int
) -> dict[str, Any]:
    months: list[str] = []
    groups: dict[str, list[int]] = {}
    for index, row in enumerate(rows):
        month = str(row["decision_at"])[:7]
        if month not in groups:
            months.append(month)
            groups[month] = []
        groups[month].append(index)
    if len(months) < 6:
        raise SpotPerpContinuationError("insufficient calendar months for bootstrap")
    blocks = [months[start : start + 3] for start in range(len(months) - 2)]
    rng = np.random.Generator(np.random.PCG64(seed))
    improvements: list[float] = []
    rank_ics: list[float] = []
    top_bottom: list[float] = []
    for _ in range(replications):
        sampled_months: list[str] = []
        while len(sampled_months) < len(months):
            sampled_months.extend(blocks[int(rng.integers(0, len(blocks)))])
        sampled_months = sampled_months[: len(months)]
        indices = np.asarray([index for month in sampled_months for index in groups[month]], dtype=int)
        y, _, m0, m1, delta, buckets = _metric_arrays(rows, indices)
        improvements.append(float(np.mean((y - m0) ** 2 - (y - m1) ** 2)))
        try:
            rank_ics.append(spearman(delta, y - m0))
        except SpotPerpContinuationError:
            pass
        top = y[buckets == 5] - m0[buckets == 5]
        bottom = y[buckets == 1] - m0[buckets == 1]
        if len(top) and len(bottom):
            top_bottom.append(float(top.mean() - bottom.mean()))
    def summary(values: Sequence[float]) -> dict[str, Any]:
        array = np.asarray(values, dtype=np.float64)
        return {
            "ci95": [rounded(value) for value in np.quantile(array, [0.025, 0.975])],
            "valid_replications": len(array),
        }
    return {
        "block_length_months": 3,
        "incremental_rank_ic": summary(rank_ics),
        "replications": replications,
        "seed": seed,
        "squared_error_improvement": summary(improvements),
        "top_minus_bottom_residual": summary(top_bottom),
    }


def model_report(
    forecasts: Sequence[Mapping[str, Any]], snapshots: Sequence[Mapping[str, Any]], contract: Mapping[str, Any]
) -> dict[str, Any]:
    if not forecasts or not snapshots:
        raise SpotPerpContinuationError("model output is empty")
    y, b0, m0, m1, delta, buckets = _metric_arrays(forecasts)
    mse_b0 = float(np.mean((y - b0) ** 2))
    mse_m0 = float(np.mean((y - m0) ** 2))
    mse_m1 = float(np.mean((y - m1) ** 2))
    mae = {
        "B0": rounded(float(np.mean(np.abs(y - b0)))),
        "M0": rounded(float(np.mean(np.abs(y - m0)))),
        "M1": rounded(float(np.mean(np.abs(y - m1)))),
    }
    relative_improvement = (mse_m0 - mse_m1) / mse_m0
    bootstrap = joint_three_month_bootstrap(
        forecasts,
        int(contract["statistics"]["bootstrap_replications"]),
        int(contract["statistics"]["bootstrap_seed"]),
    )
    annual: dict[str, Any] = {}
    for year in contract["model_gates"]["required_evaluation_years"]:
        indices = np.asarray([index for index, row in enumerate(forecasts) if str(row["decision_at"]).startswith(str(year))], dtype=int)
        yy, _, mm0, mm1, _, _ = _metric_arrays(forecasts, indices)
        mse0 = float(np.mean((yy - mm0) ** 2))
        mse1 = float(np.mean((yy - mm1) ** 2))
        annual[str(year)] = {
            "M0_mse": rounded(mse0),
            "M1_mse": rounded(mse1),
            "count": len(indices),
            "relative_improvement": rounded((mse0 - mse1) / mse0),
        }
    leave_one_year_out: dict[str, float] = {}
    for year in contract["model_gates"]["required_evaluation_years"]:
        indices = np.asarray([index for index, row in enumerate(forecasts) if not str(row["decision_at"]).startswith(str(year))], dtype=int)
        yy, _, mm0, mm1, _, _ = _metric_arrays(forecasts, indices)
        leave_one_year_out[str(year)] = rounded(float(np.mean((yy - mm0) ** 2 - (yy - mm1) ** 2)))
    month_improvements: dict[str, float] = {}
    for month in sorted({str(row["decision_at"])[:7] for row in forecasts}):
        indices = np.asarray([index for index, row in enumerate(forecasts) if str(row["decision_at"]).startswith(month)], dtype=int)
        yy, _, mm0, mm1, _, _ = _metric_arrays(forecasts, indices)
        month_improvements[month] = float(np.mean((yy - mm0) ** 2 - (yy - mm1) ** 2))
    best_three = sorted(month_improvements, key=month_improvements.get, reverse=True)[:3]
    indices_without_best = np.asarray([index for index, row in enumerate(forecasts) if str(row["decision_at"])[:7] not in best_three], dtype=int)
    yy, _, mm0, mm1, _, _ = _metric_arrays(forecasts, indices_without_best)
    excluding_best = float(np.mean((yy - mm0) ** 2 - (yy - mm1) ** 2))
    basis_coefficients = np.asarray([row["M1_coefficients"][4] for row in snapshots], dtype=np.float64)
    relative_coefficients = np.asarray([row["M1_coefficients"][5] for row in snapshots], dtype=np.float64)
    coefficient_stability = {
        "basis_impulse_z": {
            "median": rounded(float(np.median(basis_coefficients))),
            "positive_fraction": rounded(float(np.mean(basis_coefficients > 0))),
        },
        "spot_minus_perpetual_turnover_z": {
            "median": rounded(float(np.median(relative_coefficients))),
            "positive_fraction": rounded(float(np.mean(relative_coefficients > 0))),
        },
    }
    top = y[buckets == 5] - m0[buckets == 5]
    bottom = y[buckets == 1] - m0[buckets == 1]
    gates = contract["model_gates"]
    gate_results = {
        "M1_MSE_strictly_below_B0": mse_m1 < mse_b0,
        "M1_MSE_strictly_below_M0": mse_m1 < mse_m0,
        "M1_relative_MSE_improvement_over_M0_minimum": relative_improvement >= gates["M1_relative_MSE_improvement_over_M0_minimum"],
        "aggregate_improvement_after_excluding_each_year_strictly_positive": all(value > 0 for value in leave_one_year_out.values()),
        "basis_coefficient_median_strictly_positive": coefficient_stability["basis_impulse_z"]["median"] > 0,
        "basis_positive_refit_fraction_minimum": coefficient_stability["basis_impulse_z"]["positive_fraction"] >= gates["basis_positive_refit_fraction_minimum"],
        "best_three_months_excluded_improvement_strictly_positive": excluding_best > 0,
        "bootstrap_incremental_rank_ic_lower_95_strictly_above": bootstrap["incremental_rank_ic"]["ci95"][0] > gates["bootstrap_incremental_rank_ic_lower_95_strictly_above"],
        "bootstrap_squared_error_improvement_lower_95_strictly_above": bootstrap["squared_error_improvement"]["ci95"][0] > gates["bootstrap_squared_error_improvement_lower_95_strictly_above"],
        "evaluation_years_positive_improvement_minimum": sum(value["relative_improvement"] > 0 for value in annual.values()) >= gates["evaluation_years_positive_improvement_minimum"],
        "per_year_relative_MSE_improvement_minimum": all(value["relative_improvement"] >= gates["per_year_relative_MSE_improvement_minimum"] for value in annual.values()),
        "spot_minus_perpetual_turnover_coefficient_median_strictly_positive": coefficient_stability["spot_minus_perpetual_turnover_z"]["median"] > 0,
        "spot_minus_perpetual_turnover_positive_refit_fraction_minimum": coefficient_stability["spot_minus_perpetual_turnover_z"]["positive_fraction"] >= gates["spot_minus_perpetual_turnover_positive_refit_fraction_minimum"],
        "valid_bootstrap_replications_minimum": min(bootstrap[name]["valid_replications"] for name in ("squared_error_improvement", "incremental_rank_ic")) >= gates["valid_bootstrap_replications_minimum"],
    }
    return {
        "actionable_arm_id": "no_trade",
        "annual_results": annual,
        "best_three_months": best_three,
        "best_three_months_excluded_mean_squared_error_improvement": rounded(excluding_best),
        "bootstrap": bootstrap,
        "coefficient_stability": coefficient_stability,
        "decision": "D1_information_passed_D2_may_be_frozen" if all(gate_results.values()) else "D1_information_rejected",
        "diagnostics": {
            "MAE": mae,
            "incremental_rank_ic": rounded(spearman(delta, y - m0)),
            "top_minus_bottom_M0_residual": rounded(float(top.mean() - bottom.mean())),
        },
        "experiment_id": contract["experiment_id"],
        "forecast_count": len(forecasts),
        "gate_results": gate_results,
        "information_gate_passed": all(gate_results.values()),
        "leave_one_year_out_mean_squared_error_improvement": leave_one_year_out,
        "model_metrics": {
            "B0_MSE": rounded(mse_b0),
            "M0_MSE": rounded(mse_m0),
            "M1_MSE": rounded(mse_m1),
            "M1_relative_MSE_improvement_over_M0": rounded(relative_improvement),
        },
        "no_strategy_cost_PnL_position_order_or_2026_created": True,
        "snapshot_count": len(snapshots),
    }
