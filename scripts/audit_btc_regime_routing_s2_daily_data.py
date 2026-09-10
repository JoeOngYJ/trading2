#!/usr/bin/env python3
"""Validate and reconcile the frozen S2 direct-daily data source without model evaluation."""

from __future__ import annotations

import argparse
import csv
import io
import json
import zipfile
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable

from trading_platform.research_ledger import DAY_MS, iter_jsonl_gzip, write_jsonl_gzip
from trading_platform.research_program import canonical_json, sha256_file


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = REPO_ROOT / "config/experiments/btc-regime-routing-s2-daily-data-audit-v1.json"


def load_canonical(path: Path, label: str) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    payload = json.loads(raw)
    if not isinstance(payload, dict) or raw != canonical_json(payload):
        raise ValueError(f"{label} is not canonical JSON")
    return payload


def require_contract(path: Path) -> dict[str, Any]:
    if path.resolve(strict=True) != DEFAULT_CONTRACT.resolve(strict=True):
        raise ValueError("exact frozen daily-data audit contract is required")
    payload = load_canonical(path, "daily-data audit contract")
    if (
        payload.get("schema_version")
        != "btc-regime-routing-s2-daily-data-audit-contract-v1"
        or payload.get("status") != "frozen"
    ):
        raise ValueError("unsupported or unfrozen daily-data audit contract")
    for item in payload["lineage"]:
        source = (REPO_ROOT / item["path"]).resolve(strict=True)
        source.relative_to(REPO_ROOT.resolve(strict=True))
        if sha256_file(source) != item["sha256"]:
            raise ValueError(f"frozen lineage mismatch: {item['path']}")
    return payload


def iso_ms(value: int) -> str:
    from datetime import datetime, timezone

    return datetime.fromtimestamp(value / 1000, tz=timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )


def parse_iso_ms(value: str) -> int:
    from datetime import datetime

    if not value.endswith("Z"):
        raise ValueError(f"timestamp is not canonical UTC: {value}")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return int(parsed.timestamp() * 1000)


def decimal(raw: Any, label: str) -> Decimal:
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"invalid {label}") from exc
    if not value.is_finite():
        raise ValueError(f"non-finite {label}")
    return value


def normalize_timestamp(raw: str, unit: str, *, require_exact_ms: bool) -> int:
    value = int(raw)
    if unit == "milliseconds":
        return value
    if unit != "microseconds":
        raise ValueError(f"unexpected timestamp unit: {unit}")
    if require_exact_ms and value % 1000:
        raise ValueError("daily open timestamp is not exactly millisecond aligned")
    return value // 1000


def archive_rows(
    archive_path: Path, archive_record: dict[str, Any]
) -> Iterable[dict[str, Any]]:
    filename = archive_record["file"]
    if sha256_file(archive_path) != archive_record["official_sha256"]:
        raise ValueError(f"official archive checksum mismatch: {filename}")
    expected_member = filename.removesuffix(".zip") + ".csv"
    with zipfile.ZipFile(archive_path) as archive:
        members = [member for member in archive.infolist() if not member.is_dir()]
        if len(members) != 1 or members[0].filename != expected_member:
            raise ValueError(f"unexpected archive members: {filename}")
        with archive.open(members[0]) as binary:
            reader = csv.reader(io.TextIOWrapper(binary, encoding="utf-8", newline=""))
            for row in reader:
                if len(row) != 12:
                    raise ValueError(f"invalid daily row width: {filename}")
                unit = archive_record["timestamp_unit"]
                open_ms = normalize_timestamp(row[0], unit, require_exact_ms=True)
                close_ms = normalize_timestamp(row[6], unit, require_exact_ms=False)
                if open_ms % DAY_MS or close_ms != open_ms + DAY_MS - 1:
                    raise ValueError(f"invalid UTC daily interval: {filename}")
                open_price = decimal(row[1], "open")
                high = decimal(row[2], "high")
                low = decimal(row[3], "low")
                close = decimal(row[4], "close")
                base_volume = decimal(row[5], "base volume")
                quote_volume = decimal(row[7], "quote volume")
                if (
                    low <= 0
                    or low > min(open_price, close)
                    or high < max(open_price, close)
                    or base_volume < 0
                    or quote_volume < 0
                ):
                    raise ValueError(f"invalid direct daily values: {filename}")
                yield {
                    "available_at": iso_ms(open_ms + DAY_MS),
                    "base_volume": str(base_volume),
                    "close": str(close),
                    "high": str(high),
                    "low": str(low),
                    "open": str(open_price),
                    "open_at": iso_ms(open_ms),
                    "quote_volume": str(quote_volume),
                    "source_archive": filename,
                    "source_archive_sha256": archive_record["official_sha256"],
                    "trade_count": int(row[8]),
                }


def load_direct_rows(root: Path, source_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    previous_ms: int | None = None
    for record in source_manifest["archives"]:
        archive_path = root / "raw" / record["file"]
        observed = list(archive_rows(archive_path, record))
        if len(observed) != record["rows"]:
            raise ValueError(f"source manifest row mismatch: {record['file']}")
        for row in observed:
            current_ms = parse_iso_ms(row["open_at"])
            if previous_ms is not None and current_ms != previous_ms + DAY_MS:
                raise ValueError(
                    f"direct daily source gap: {iso_ms(previous_ms)} -> {row['open_at']}"
                )
            previous_ms = current_ms
            result.append(row)
    return result


def reconcile(
    direct: list[dict[str, Any]], s1_path: Path, volume_tolerance: Decimal
) -> dict[str, Any]:
    direct_by_open = {row["open_at"]: row for row in direct}
    s1_rows = list(iter_jsonl_gzip(s1_path))
    s1_by_open = {row["open_at"]: row for row in s1_rows}
    if len(s1_by_open) != len(s1_rows):
        raise ValueError("S1 daily ledger repeats an open timestamp")
    price_mismatches: list[dict[str, Any]] = []
    maximum_base_volume_difference = Decimal(0)
    maximum_quote_volume_difference = Decimal(0)
    volume_mismatch_count = 0
    for open_at in sorted(set(direct_by_open) & set(s1_by_open)):
        left = direct_by_open[open_at]
        right = s1_by_open[open_at]
        fields = [
            field
            for field in ("open", "high", "low", "close")
            if decimal(left[field], field) != decimal(right[field], field)
        ]
        if fields:
            price_mismatches.append({"fields": fields, "open_at": open_at})
        base_difference = abs(
            decimal(left["base_volume"], "base volume")
            - decimal(right["base_volume"], "base volume")
        )
        quote_difference = abs(
            decimal(left["quote_volume"], "quote volume")
            - decimal(right["quote_volume"], "quote volume")
        )
        maximum_base_volume_difference = max(maximum_base_volume_difference, base_difference)
        maximum_quote_volume_difference = max(maximum_quote_volume_difference, quote_difference)
        if base_difference > volume_tolerance or quote_difference > volume_tolerance:
            volume_mismatch_count += 1
    return {
        "direct_only_open_times": sorted(set(direct_by_open) - set(s1_by_open)),
        "maximum_base_volume_absolute_difference": str(maximum_base_volume_difference),
        "maximum_quote_volume_absolute_difference": str(maximum_quote_volume_difference),
        "ohlc_mismatch_count": len(price_mismatches),
        "ohlc_mismatches": price_mismatches,
        "overlapping_daily_bars": len(set(direct_by_open) & set(s1_by_open)),
        "s1_only_open_times": sorted(set(s1_by_open) - set(direct_by_open)),
        "volume_difference_above_tolerance_count": volume_mismatch_count,
        "volume_tolerance": str(volume_tolerance),
    }


def affected_history(
    direct: list[dict[str, Any]], observation_times: list[str]
) -> list[dict[str, Any]]:
    by_available: dict[str, tuple[dict[str, Any], int]] = {}
    consecutive_returns = 0
    previous_open_ms: int | None = None
    for row in direct:
        open_ms = parse_iso_ms(row["open_at"])
        if previous_open_ms is not None and open_ms == previous_open_ms + DAY_MS:
            consecutive_returns += 1
        else:
            consecutive_returns = 0
        by_available[row["available_at"]] = (row, consecutive_returns)
        previous_open_ms = open_ms
    result: list[dict[str, Any]] = []
    for timestamp in observation_times:
        matched = by_available.get(timestamp)
        if matched is None:
            result.append(
                {
                    "available": False,
                    "consecutive_completed_returns": 0,
                    "observation_at": timestamp,
                }
            )
        else:
            row, count = matched
            result.append(
                {
                    "available": True,
                    "consecutive_completed_returns": count,
                    "daily_bar_open_at": row["open_at"],
                    "observation_at": timestamp,
                    "source_archive": row["source_archive"],
                }
            )
    return result


def write_text_once(path: Path, payload: str) -> None:
    if path.exists():
        raise ValueError(f"refusing to overwrite audit artifact: {path}")
    path.write_text(payload, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    args = parser.parse_args()
    contract = require_contract(args.contract)
    output_root = (REPO_ROOT / contract["output"]["artifact_root"]).resolve(strict=True)
    output_root.relative_to(REPO_ROOT.resolve(strict=True))
    if output_root.is_symlink():
        raise ValueError("symlinked audit root is prohibited")
    source_manifest_path = output_root / "source-manifest.json"
    source_manifest = load_canonical(source_manifest_path, "daily source manifest")
    if (
        source_manifest.get("audit_id") != contract["audit_id"]
        or source_manifest.get("contract_sha256") != sha256_file(DEFAULT_CONTRACT)
        or source_manifest.get("schema_version")
        != "btc-regime-routing-daily-source-manifest-v1"
    ):
        raise ValueError("daily source manifest does not match the frozen audit")
    boundaries = contract["boundaries"]
    if len(source_manifest["archives"]) != boundaries["expected_monthly_archives"]:
        raise ValueError("daily source manifest archive count mismatch")
    direct = load_direct_rows(output_root, source_manifest)
    if len(direct) != boundaries["expected_daily_rows"]:
        raise ValueError(
            f"direct daily row count mismatch: {len(direct)} != {boundaries['expected_daily_rows']}"
        )
    if direct[0]["open_at"] != boundaries["development_start"]:
        raise ValueError("direct daily start does not match frozen boundary")
    if direct[-1]["available_at"] != boundaries["development_end_exclusive"]:
        raise ValueError("direct daily end does not match frozen boundary")
    dataset_path = output_root / "btc-usdt-direct-1d-development-2017-2025.jsonl.gz"
    if dataset_path.exists():
        raise ValueError(f"refusing to overwrite audit artifact: {dataset_path}")
    dataset_metadata = write_jsonl_gzip(dataset_path, direct)
    s1_path = (REPO_ROOT / contract["inputs"]["s1_daily_candles_path"]).resolve(strict=True)
    if sha256_file(s1_path) != contract["inputs"]["s1_daily_candles_sha256"]:
        raise ValueError("S1 daily candle checksum mismatch")
    reconciliation = reconcile(
        direct,
        s1_path,
        decimal(
            contract["reconciliation"]["s1_volume_comparison_absolute_tolerance"],
            "volume tolerance",
        ),
    )
    affected = affected_history(
        direct, contract["decision_rule"]["required_affected_risk_observation_times"]
    )
    minimum = contract["decision_rule"][
        "minimum_consecutive_completed_returns_at_affected_decision"
    ]
    suitable = (
        reconciliation["ohlc_mismatch_count"] == 0
        and not reconciliation["s1_only_open_times"]
        and all(
            item["available"] and item["consecutive_completed_returns"] >= minimum
            for item in affected
        )
    )
    report = {
        "affected_observations": affected,
        "archive_count": len(source_manifest["archives"]),
        "audit_id": contract["audit_id"],
        "contract_sha256": sha256_file(DEFAULT_CONTRACT),
        "decision": (
            "direct_daily_source_suitable_for_frozen_successor_contract"
            if suitable
            else "direct_daily_source_not_suitable"
        ),
        "direct_daily_rows": len(direct),
        "economic_metrics_computed": False,
        "ewma_forecasts_generated": False,
        "holdout_accessed": False,
        "reconciliation": reconciliation,
        "schema_version": "btc-regime-routing-s2-daily-data-audit-report-v1",
        "suitable_for_successor_contract": suitable,
    }
    report_path = output_root / "daily-data-audit-report.json"
    write_text_once(report_path, canonical_json(report))
    manifest = {
        "artifacts": {
            dataset_path.name: dataset_metadata,
            report_path.name: {
                "bytes": report_path.stat().st_size,
                "sha256": sha256_file(report_path),
            },
            source_manifest_path.name: {
                "bytes": source_manifest_path.stat().st_size,
                "sha256": sha256_file(source_manifest_path),
            },
        },
        "audit_id": contract["audit_id"],
        "contract_sha256": sha256_file(DEFAULT_CONTRACT),
        "decision": report["decision"],
        "economic_metrics_computed": False,
        "ewma_forecasts_generated": False,
        "holdout_accessed": False,
        "schema_version": "btc-regime-routing-s2-daily-data-audit-manifest-v1",
    }
    manifest_path = output_root / "manifest.json"
    write_text_once(manifest_path, canonical_json(manifest))
    print(
        canonical_json(
            {
                "decision": report["decision"],
                "direct_daily_rows": len(direct),
                "manifest_sha256": sha256_file(manifest_path),
                "ohlc_mismatch_count": reconciliation["ohlc_mismatch_count"],
                "suitable_for_successor_contract": suitable,
            }
        ),
        end="",
    )


if __name__ == "__main__":
    main()
