"""Opaque timestamp-only prepartitioning for cross-asset research inputs.

The module never deserializes a market-data row. It extracts only the routing timestamp
or local date from raw JSONL bytes and copies the original bytes into immutable partitions.
It has no network, database, message-bus, signal, order, or position dependency.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from trading_platform.cross_asset_oanda_hourly import (
    OandaHourlyError,
    _load_canonical,
    _repo_file,
    canonical_json,
    sha256_file,
)


CONTRACT_SCHEMA = "cross-asset-a3-timestamp-prepartition-contract-v1"
EXPERIMENT_ID = "cross-asset-a3-timestamp-prepartition-v1"
OBSERVED_AT = re.compile(rb'"observed_at"\s*:\s*"([^"]+)"')
LOCAL_DATE = re.compile(rb'"local_date"\s*:\s*"([^"]+)"')


@dataclass(frozen=True, slots=True)
class Boundary:
    partition_id: str
    start: datetime | date
    end: datetime | date


class TimestampPrepartitionError(OandaHourlyError):
    """Raised when opaque source routing cannot be proved safe."""


def _parse_utc(raw: bytes) -> datetime:
    try:
        text = raw.decode("ascii")
        value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise TimestampPrepartitionError("invalid timestamp-only observed_at") from exc
    if not text.endswith("Z") or value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
        raise TimestampPrepartitionError("timestamp-only observed_at must use explicit UTC Z")
    return value


def _parse_date(raw: bytes) -> date:
    try:
        return date.fromisoformat(raw.decode("ascii"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise TimestampPrepartitionError("invalid timestamp-only local_date") from exc


def extract_routing_value(line: bytes, field: str) -> datetime | date:
    """Extract one routing field without parsing any other JSON value."""

    pattern = OBSERVED_AT if field == "observed_at" else LOCAL_DATE if field == "local_date" else None
    if pattern is None:
        raise TimestampPrepartitionError(f"unsupported routing field: {field}")
    matches = pattern.findall(line)
    if len(matches) != 1:
        raise TimestampPrepartitionError(f"row must contain exactly one {field}")
    return _parse_utc(matches[0]) if field == "observed_at" else _parse_date(matches[0])


def _boundaries(contract: Mapping[str, Any], field: str) -> tuple[Boundary, ...]:
    result = []
    for record in contract["partitions"]:
        if field == "observed_at":
            start = _parse_utc(str(record["start_inclusive"]).encode("ascii"))
            end = _parse_utc(str(record["end_exclusive"]).encode("ascii"))
        else:
            start = _parse_date(str(record["start_inclusive"])[:10].encode("ascii"))
            end = _parse_date(str(record["end_exclusive"])[:10].encode("ascii"))
        if start >= end:
            raise TimestampPrepartitionError("prepartition boundary is reversed")
        result.append(Boundary(str(record["partition_id"]), start, end))
    if tuple(item.partition_id for item in result) != ("development", "validation"):
        raise TimestampPrepartitionError("prepartition IDs must be development then validation")
    if result[0].end != result[1].start:
        raise TimestampPrepartitionError("prepartition boundaries must be contiguous")
    return tuple(result)


def load_contract(path: Path, repo_root: Path) -> dict[str, Any]:
    contract = _load_canonical(path, "A3 timestamp-prepartition contract")
    if (
        contract.get("schema_version"),
        contract.get("experiment_id"),
        contract.get("status"),
    ) != (CONTRACT_SCHEMA, EXPERIMENT_ID, "frozen"):
        raise TimestampPrepartitionError("unexpected or unfrozen A3 prepartition contract")
    if contract.get("method") != "opaque_jsonl_copy_routed_only_by_timestamp_or_local_date":
        raise TimestampPrepartitionError("A3 prepartition method changed")
    if contract.get("prospective_final", {}).get("price_rows_may_be_present") is not False:
        raise TimestampPrepartitionError("prospective A3 prices must be absent")
    if contract.get("prospective_final", {}).get("start_inclusive") != "2026-08-31T00:00:00Z":
        raise TimestampPrepartitionError("A3 prospective boundary changed")
    for key, value in contract.get("prohibitions", {}).items():
        if value is not False:
            raise TimestampPrepartitionError(f"unsafe A3 prepartition permission: {key}")
    code_record = contract.get("code_binding", {})
    code_path = _repo_file(repo_root, code_record.get("path"), "A3 prepartition code")
    if sha256_file(code_path) != code_record.get("sha256"):
        raise TimestampPrepartitionError("A3 prepartition code checksum changed")
    inputs = contract.get("inputs")
    if not isinstance(inputs, list) or len(inputs) != 15:
        raise TimestampPrepartitionError("A3 prepartition must bind exactly fifteen inputs")
    identities = [(item.get("instrument_id"), item.get("kind")) for item in inputs]
    if len(set(identities)) != len(identities):
        raise TimestampPrepartitionError("A3 prepartition repeats an input identity")
    for record in inputs:
        if record.get("routing_field") not in {"observed_at", "local_date"}:
            raise TimestampPrepartitionError("A3 input has an invalid routing field")
        source = _repo_file(repo_root, record.get("path"), "A3 prepartition source")
        if sha256_file(source) != record.get("sha256"):
            raise TimestampPrepartitionError(f"A3 source checksum changed: {record.get('path')}")
        _boundaries(contract, str(record["routing_field"]))
    return contract


def _copy_one(
    source: Path,
    outputs: Mapping[str, Path],
    field: str,
    boundaries: Sequence[Boundary],
) -> dict[str, dict[str, Any]]:
    handles = {key: path.open("wb") for key, path in outputs.items()}
    summaries = {
        key: {"first_routing_value": None, "last_routing_value": None, "rows": 0}
        for key in outputs
    }
    previous: datetime | date | None = None
    try:
        with source.open("rb") as rows:
            for line_number, line in enumerate(rows, start=1):
                if not line.endswith(b"\n"):
                    raise TimestampPrepartitionError(f"source line {line_number} has no newline")
                value = extract_routing_value(line, field)
                if previous is not None and value <= previous:
                    raise TimestampPrepartitionError("A3 source routing values are not strictly increasing")
                previous = value
                selected = next(
                    (item for item in boundaries if item.start <= value < item.end), None
                )
                if selected is None:
                    if value >= boundaries[-1].end:
                        raise TimestampPrepartitionError(
                            "source contains a row at or beyond the prospective-only boundary"
                        )
                    continue
                handles[selected.partition_id].write(line)
                summary = summaries[selected.partition_id]
                rendered = value.isoformat().replace("+00:00", "Z")
                summary["first_routing_value"] = summary["first_routing_value"] or rendered
                summary["last_routing_value"] = rendered
                summary["rows"] += 1
    finally:
        for handle in handles.values():
            handle.close()
    if any(summary["rows"] == 0 for summary in summaries.values()):
        raise TimestampPrepartitionError("every A3 input must populate both research partitions")
    return summaries


def build_prepartitions(contract_path: Path, repo_root: Path) -> dict[str, Any]:
    """Build one immutable data-only artifact root transactionally."""

    root = repo_root.resolve(strict=True)
    contract = load_contract(contract_path, root)
    artifact_root = root / contract["output"]["artifact_root"]
    if artifact_root.exists():
        raise TimestampPrepartitionError("refusing to rewrite immutable A3 prepartition root")
    artifact_root.parent.mkdir(parents=True, exist_ok=True)
    temp_root = Path(tempfile.mkdtemp(prefix=f".{artifact_root.name}-", dir=artifact_root.parent))
    records = []
    try:
        for source_record in contract["inputs"]:
            source = _repo_file(root, source_record["path"], "A3 prepartition source")
            stem = str(source_record["instrument_id"]).casefold()
            suffix = "h1" if source_record["kind"] in {"market", "conversion"} else "availability"
            output_paths = {}
            for partition in ("development", "validation"):
                directory = temp_root / partition
                directory.mkdir(parents=True, exist_ok=True)
                output_paths[partition] = directory / f"{stem}-{suffix}.jsonl"
            summaries = _copy_one(
                source,
                output_paths,
                str(source_record["routing_field"]),
                _boundaries(contract, str(source_record["routing_field"])),
            )
            for partition, output in output_paths.items():
                relative = Path(contract["output"]["artifact_root"]) / output.relative_to(temp_root)
                records.append(
                    {
                        "first_routing_value": summaries[partition]["first_routing_value"],
                        "instrument_id": source_record["instrument_id"],
                        "kind": source_record["kind"],
                        "last_routing_value": summaries[partition]["last_routing_value"],
                        "partition_id": partition,
                        "path": relative.as_posix(),
                        "routing_field": source_record["routing_field"],
                        "rows": summaries[partition]["rows"],
                        "sha256": sha256_file(output),
                        "source_path": source_record["path"],
                        "source_sha256": source_record["sha256"],
                    }
                )
        manifest = {
            "contract_path": str(contract_path.resolve(strict=True).relative_to(root)),
            "contract_sha256": sha256_file(contract_path),
            "economic_metrics_computed": False,
            "experiment_id": EXPERIMENT_ID,
            "partitions": records,
            "price_fields_deserialized": False,
            "prospective_price_rows_present": False,
            "schema_version": "cross-asset-a3-timestamp-prepartition-manifest-v1",
            "strategy_features_or_signals_computed": False,
        }
        (temp_root / "partition-manifest.json").write_text(canonical_json(manifest), encoding="utf-8")
        os.replace(temp_root, artifact_root)
    except Exception:
        shutil.rmtree(temp_root, ignore_errors=True)
        raise
    return manifest


def evidence_manifest(contract_path: Path, repo_root: Path) -> dict[str, Any]:
    root = repo_root.resolve(strict=True)
    contract = load_contract(contract_path, root)
    artifact_root = root / contract["output"]["artifact_root"]
    manifest_path = artifact_root / "partition-manifest.json"
    manifest = _load_canonical(manifest_path, "A3 prepartition manifest")
    if manifest.get("price_fields_deserialized") is not False:
        raise TimestampPrepartitionError("A3 prepartition deserialization claim changed")
    artifacts = [
        {
            "path": str(contract_path.resolve(strict=True).relative_to(root)),
            "sha256": sha256_file(contract_path),
        },
        {
            "path": str(manifest_path.relative_to(root)),
            "sha256": sha256_file(manifest_path),
        },
    ]
    for record in manifest["partitions"]:
        path = _repo_file(root, record["path"], "A3 prepartition output")
        if sha256_file(path) != record["sha256"]:
            raise TimestampPrepartitionError("A3 prepartition output checksum changed")
        artifacts.append({"path": record["path"], "sha256": record["sha256"]})
    return {
        "artifacts": artifacts,
        "decision": "a3_timestamp_prepartition_passed",
        "economic_metrics_computed": False,
        "experiment_id": EXPERIMENT_ID,
        "price_fields_deserialized": False,
        "prospective_price_rows_present": False,
        "schema_version": "cross-asset-a3-timestamp-prepartition-evidence-v1",
        "strategy_features_or_signals_computed": False,
    }
