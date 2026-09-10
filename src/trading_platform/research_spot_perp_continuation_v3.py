"""Offline endpoint-only successor for BTC spot/perpetual continuation D1-v3."""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import math
import zipfile
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Sequence

from scripts.extract_btc_taker_flow import detect_timestamp_unit, normalize_timestamp, parse_row
from trading_platform.research_spot_perp_continuation import (
    HORIZON_MS,
    YEAR_2026_MS,
    FiveMinuteOpen,
    SpotPerpContinuationError,
    iso_ms,
    parse_utc_z_ms,
    record_digest,
    resolve_effective_contract,
    rounded,
    sha256_file,
)


V2_EXPERIMENT_ID = "btc-spot-perp-continuation-information-d1-v2"
V3_EXPERIMENT_ID = "btc-spot-perp-continuation-information-d1-v3"


def _reject_symlink_tree(path: Path) -> None:
    candidate = path.absolute()
    for item in (candidate, *candidate.parents):
        if item.is_symlink():
            raise SpotPerpContinuationError(f"symlinked frozen path is prohibited: {item}")


def resolve_v3_contract(root: Path, path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    v3 = json.loads(raw)
    if v3.get("status") != "frozen_before_any_D1_v3_endpoint_label_or_model_materialization":
        raise SpotPerpContinuationError("D1-v3 contract is not frozen")
    base_ref = v3.get("base_contract", {})
    base_path = root / str(base_ref.get("path"))
    if not base_path.is_file() or sha256_file(base_path) != base_ref.get("sha256"):
        raise SpotPerpContinuationError("D1-v3 base-contract checksum mismatch")
    effective = resolve_effective_contract(root, base_path)
    if effective.get("experiment_id") != V2_EXPERIMENT_ID:
        raise SpotPerpContinuationError("D1-v3 did not resolve the exact v2 predecessor")
    effective["experiment_id"] = V3_EXPERIMENT_ID
    effective["status"] = v3["status"]
    effective["outputs"] = dict(v3["outputs"])
    effective["target_contract"] = dict(effective["target_contract"])
    effective["target_contract"]["same_five_minute_segment_required"] = False
    effective["target_contract"]["interior_gap_behavior"] = (
        "count_and_report_not_an_endpoint_label_exclusion"
    )
    effective["v3_contract"] = {
        "path": str(path.relative_to(root)),
        "sha256": sha256_file(path),
    }
    effective["v3_spec"] = v3
    return effective


def validate_v3_bound_inputs(root: Path, contract: Mapping[str, Any]) -> None:
    for item in contract["v3_spec"]["bound_inputs"]:
        path = root / item["path"]
        _reject_symlink_tree(path)
        if not path.is_file() or sha256_file(path) != item["sha256"]:
            raise SpotPerpContinuationError(f"missing or changed D1-v3 input: {item['path']}")


@dataclass(frozen=True, slots=True)
class OfficialEndpoint:
    endpoint_ms: int
    open_price: str
    base_volume: str
    quote_volume: str
    archive_path: str
    archive_sha256: str
    s1_segment: str

    def as_record(self, experiment_id: str) -> dict[str, Any]:
        record: dict[str, Any] = {
            "archive_path": self.archive_path,
            "archive_sha256": self.archive_sha256,
            "base_volume": self.base_volume,
            "endpoint_at": iso_ms(self.endpoint_ms),
            "experiment_id": experiment_id,
            "official_open": self.open_price,
            "quote_volume": self.quote_volume,
            "s1_segment": self.s1_segment,
            "source": "official_Binance_BTCUSDT_spot_monthly_5m_kline",
        }
        record["endpoint_digest"] = record_digest(record, "endpoint_digest")
        return record


def requested_endpoint_timestamps(features: Sequence[Mapping[str, Any]]) -> set[int]:
    needed: set[int] = set()
    for feature in features:
        decision = parse_utc_z_ms(feature["decision_at"], "decision_at")
        target = decision + HORIZON_MS
        if target < YEAR_2026_MS:
            needed.update((decision, target))
    return needed


def _selected_archives(source_manifest: Mapping[str, Any], spec: Mapping[str, Any]) -> list[dict[str, Any]]:
    start = spec["archive_start_period_inclusive"]
    end = spec["archive_end_period_inclusive"]
    selected = []
    for item in source_manifest.get("files", []):
        name = str(item.get("file", ""))
        prefix = "BTCUSDT-5m-"
        if not name.startswith(prefix) or not name.endswith(".zip"):
            continue
        period = name[len(prefix) : -4]
        if start <= period <= end:
            selected.append(dict(item))
    selected.sort(key=lambda item: item["file"])
    if len(selected) != spec["expected_archive_count"] or len({x["file"] for x in selected}) != len(selected):
        raise SpotPerpContinuationError("official endpoint archive inventory changed")
    return selected


def load_official_endpoints(
    root: Path,
    contract: Mapping[str, Any],
    needed_ms: set[int],
    s1_opens: Mapping[int, FiveMinuteOpen],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    v3 = contract["v3_spec"]
    spec = v3["endpoint_audit_contract"]
    source_item = next(
        item
        for item in v3["bound_inputs"]
        if item["path"].endswith("raw/btc-history-source-manifest.json")
    )
    source_path = root / source_item["path"]
    source_manifest = json.loads(source_path.read_text(encoding="utf-8"))
    if (
        source_manifest.get("accepted") is not True
        or source_manifest.get("dataset") != "binance-spot-klines"
    ):
        raise SpotPerpContinuationError("official endpoint source manifest is not accepted")
    if len(needed_ms) != spec["expected_unique_endpoint_timestamps"]:
        raise SpotPerpContinuationError("requested endpoint count changed")
    if any(value >= YEAR_2026_MS for value in needed_ms):
        raise SpotPerpContinuationError("D1-v3 requested a 2026 endpoint")

    archive_records = _selected_archives(source_manifest, spec)
    raw_directory = source_path.parent
    found: dict[int, OfficialEndpoint] = {}
    archive_summaries: list[dict[str, Any]] = []
    for archive_record in archive_records:
        name = archive_record["file"]
        if (
            archive_record.get("origin") not in {"downloaded", "reused_verified_archive"}
            or archive_record.get("source_url")
            != f"https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/5m/{name}"
            or archive_record.get("checksum_url")
            != f"https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/5m/{name}.CHECKSUM"
        ):
            raise SpotPerpContinuationError(f"non-official endpoint archive lineage: {name}")
        archive_path = raw_directory / name
        _reject_symlink_tree(archive_path)
        if not archive_path.is_file():
            raise SpotPerpContinuationError(f"missing official endpoint archive: {name}")
        archive_sha = sha256_file(archive_path)
        if archive_sha != archive_record.get("official_sha256"):
            raise SpotPerpContinuationError(f"official endpoint archive checksum mismatch: {name}")
        row_count = 0
        first_ms: int | None = None
        last_ms: int | None = None
        previous_ms = -1
        relevant_rows = 0
        with zipfile.ZipFile(archive_path) as archive:
            members = [item for item in archive.infolist() if not item.is_dir()]
            expected_member = name.removesuffix(".zip") + ".csv"
            if len(members) != 1 or members[0].filename != expected_member:
                raise SpotPerpContinuationError(f"unexpected official archive contents: {name}")
            with archive.open(members[0]) as binary:
                reader = csv.reader(io.TextIOWrapper(binary, encoding="utf-8", newline=""))
                unit: str | None = None
                for fields in reader:
                    row_count += 1
                    if unit is None:
                        unit = detect_timestamp_unit(fields[0])
                        if unit != archive_record.get("timestamp_unit"):
                            raise SpotPerpContinuationError(f"timestamp unit changed: {name}")
                    opened = normalize_timestamp(fields[0], unit, "open timestamp")
                    if opened <= previous_ms:
                        raise SpotPerpContinuationError(f"non-increasing raw archive timestamps: {name}")
                    first_ms = opened if first_ms is None else first_ms
                    last_ms = opened
                    previous_ms = opened
                    if opened not in needed_ms:
                        continue
                    relevant_rows += 1
                    if opened in found:
                        raise SpotPerpContinuationError(f"duplicate official endpoint: {iso_ms(opened)}")
                    parsed = parse_row(
                        fields,
                        unit,
                        allow_nonzero_ignore=True,
                        allow_legacy_close_boundary=True,
                    )
                    opening = Decimal(parsed.values[2])
                    base_volume = Decimal(parsed.values[6])
                    quote_volume = Decimal(parsed.values[7])
                    if opening <= 0 or base_volume <= 0 or quote_volume <= 0:
                        raise SpotPerpContinuationError(f"non-positive official endpoint row: {iso_ms(opened)}")
                    s1 = s1_opens.get(opened)
                    if s1 is None or Decimal(str(s1.open_price)) != opening:
                        raise SpotPerpContinuationError(f"official/S1 endpoint mismatch: {iso_ms(opened)}")
                    found[opened] = OfficialEndpoint(
                        endpoint_ms=opened,
                        open_price=parsed.values[2],
                        base_volume=parsed.values[6],
                        quote_volume=parsed.values[7],
                        archive_path=str(archive_path.relative_to(root)),
                        archive_sha256=archive_sha,
                        s1_segment=s1.segment,
                    )
        if (
            row_count != archive_record.get("rows")
            or first_ms != archive_record.get("first_ms")
            or last_ms != archive_record.get("last_ms")
        ):
            raise SpotPerpContinuationError(f"official archive inventory mismatch: {name}")
        archive_summaries.append(
            {
                "archive_path": str(archive_path.relative_to(root)),
                "archive_sha256": archive_sha,
                "first_open_at": iso_ms(first_ms),
                "last_open_at": iso_ms(last_ms),
                "relevant_endpoint_rows": relevant_rows,
                "row_count": row_count,
            }
        )
    missing = sorted(needed_ms - set(found))
    records = [found[value].as_record(contract["experiment_id"]) for value in sorted(found)]
    diagnostics = {
        "archive_count": len(archive_records),
        "archive_summaries": archive_summaries,
        "endpoint_count": len(records),
        "missing_endpoint_count": len(missing),
        "missing_endpoints": [iso_ms(value) for value in missing],
        "requested_endpoint_count": len(needed_ms),
    }
    return records, diagnostics


def endpoint_gate_report(diagnostics: Mapping[str, Any], contract: Mapping[str, Any]) -> dict[str, Any]:
    spec = contract["v3_spec"]["endpoint_audit_contract"]
    gates = {
        "all_official_archive_hashes_and_inventory_pass": diagnostics["archive_count"]
        == spec["expected_archive_count"],
        "all_requested_endpoints_present": diagnostics["missing_endpoint_count"] == 0,
        "endpoint_count_exact": diagnostics["endpoint_count"]
        == spec["expected_unique_endpoint_timestamps"],
        "no_2026_or_target_return_materialized": True,
        "official_and_S1_exact_open_match": True,
        "positive_volume_and_open": True,
    }
    return {
        "actionable_arm_id": "no_trade",
        "archive_count": diagnostics["archive_count"],
        "archive_summaries": diagnostics["archive_summaries"],
        "decision": "D1_v3_endpoints_passed_labels_may_materialize"
        if all(gates.values())
        else "D1_v3_endpoints_rejected_stop_before_labels",
        "endpoint_count": diagnostics["endpoint_count"],
        "endpoint_gate_passed": all(gates.values()),
        "experiment_id": contract["experiment_id"],
        "gate_results": gates,
        "missing_endpoint_count": diagnostics["missing_endpoint_count"],
        "requested_endpoint_count": diagnostics["requested_endpoint_count"],
        "target_return_model_strategy_or_pnl_created": False,
    }


def load_endpoint_rows(path: Path, expected_sha256: str, experiment_id: str) -> list[dict[str, Any]]:
    if sha256_file(path) != expected_sha256:
        raise SpotPerpContinuationError("D1-v3 endpoint-ledger checksum mismatch")
    rows: list[dict[str, Any]] = []
    previous = -1
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            row = json.loads(raw)
            if row.get("experiment_id") != experiment_id:
                raise SpotPerpContinuationError("D1-v3 endpoint experiment mismatch")
            if row.get("endpoint_digest") != record_digest(row, "endpoint_digest"):
                raise SpotPerpContinuationError("D1-v3 endpoint digest mismatch")
            timestamp = parse_utc_z_ms(row["endpoint_at"], "endpoint_at")
            if timestamp <= previous or timestamp >= YEAR_2026_MS:
                raise SpotPerpContinuationError("D1-v3 endpoint chronology changed")
            if Decimal(row["official_open"]) <= 0 or Decimal(row["base_volume"]) <= 0 or Decimal(row["quote_volume"]) <= 0:
                raise SpotPerpContinuationError("D1-v3 endpoint numeric validity changed")
            previous = timestamp
            rows.append(row)
    return rows


def relevant_gap_diagnostics(
    features: Sequence[Mapping[str, Any]], validated_manifest: Mapping[str, Any]
) -> tuple[dict[int, list[dict[str, int]]], dict[str, Any]]:
    gaps = [dict(item) for item in validated_manifest.get("gaps", [])]
    by_decision: dict[int, list[dict[str, int]]] = {}
    counts_by_year: Counter[str] = Counter()
    total_minutes_by_year: Counter[str] = Counter()
    for feature in features:
        decision = parse_utc_z_ms(feature["decision_at"], "decision_at")
        target = decision + HORIZON_MS
        if target >= YEAR_2026_MS:
            continue
        crossed = [
            gap
            for gap in gaps
            if decision <= int(gap["after_open_ms"])
            and int(gap["before_open_ms"]) <= target
        ]
        if not crossed:
            continue
        by_decision[decision] = crossed
        year = str(feature["decision_at"])[:4]
        counts_by_year[year] += 1
        total_minutes_by_year[year] += sum(int(gap["missing_bars"]) * 5 for gap in crossed)
    return by_decision, {
        "candidates_crossing_interior_gaps": len(by_decision),
        "crossing_candidates_by_year": dict(sorted(counts_by_year.items())),
        "summed_missing_minutes_by_candidate_year": dict(sorted(total_minutes_by_year.items())),
    }


def build_endpoint_label_rows(
    features: Sequence[Mapping[str, Any]],
    endpoint_rows: Sequence[Mapping[str, Any]],
    gap_map: Mapping[int, Sequence[Mapping[str, int]]],
    contract: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    endpoints = {
        parse_utc_z_ms(row["endpoint_at"], "endpoint_at"): row for row in endpoint_rows
    }
    labels: list[dict[str, Any]] = []
    missing = 0
    outside = 0
    for feature in features:
        decision = parse_utc_z_ms(feature["decision_at"], "decision_at")
        target_at = decision + HORIZON_MS
        if target_at >= YEAR_2026_MS:
            outside += 1
            continue
        entry = endpoints.get(decision)
        exit_ = endpoints.get(target_at)
        if entry is None or exit_ is None:
            missing += 1
            continue
        gaps = gap_map.get(decision, ())
        target = math.log(float(Decimal(exit_["official_open"]) / Decimal(entry["official_open"])))
        record: dict[str, Any] = {
            "decision_at": feature["decision_at"],
            "entry_endpoint_digest": entry["endpoint_digest"],
            "exit_endpoint_digest": exit_["endpoint_digest"],
            "experiment_id": contract["experiment_id"],
            "feature_digest": feature["feature_digest"],
            "interior_gap_count": len(gaps),
            "interior_missing_minutes": sum(int(gap["missing_bars"]) * 5 for gap in gaps),
            "target_available_at": iso_ms(target_at),
            "target_return": rounded(target),
        }
        record["label_digest"] = record_digest(record, "label_digest")
        labels.append(record)
    return labels, {
        "excluded_missing_exact_endpoint_candidates": missing,
        "excluded_target_end_at_or_after_2026": outside,
        "serialized_invalid_labels": 0,
    }
