"""Opaque date-only prepartitioning for the cash-ETF proxy source files.

Rows are never JSON-decoded.  Only a single ASCII ``session`` or ``action_date``
field is extracted, after which the original bytes are copied into immutable partitions.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence

from trading_platform.cash_etf_program import canonical_json, sha256_file


CONTRACT_SCHEMA = "cash-etf-c1-prepartition-contract-v1"
EXPERIMENT_ID = "cash-etf-c1-prepartition-v1"
SESSION = re.compile(rb'"session"\s*:\s*"([0-9]{4}-[0-9]{2}-[0-9]{2})"')
ACTION_DATE = re.compile(rb'"action_date"\s*:\s*"([0-9]{4}-[0-9]{2}-[0-9]{2})"')


class CashEtfPrepartitionError(ValueError):
    """Raised when date-only source routing cannot be proved safe."""


@dataclass(frozen=True, slots=True)
class Boundary:
    partition_id: str
    start: date
    end: date


def _load_canonical(path: Path, label: str) -> dict[str, Any]:
    import json

    try:
        raw = path.read_text(encoding="utf-8")
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise CashEtfPrepartitionError(f"cannot read {label}") from exc
    if not isinstance(payload, dict) or raw != canonical_json(payload):
        raise CashEtfPrepartitionError(f"{label} must be canonical JSON")
    return payload


def _repo_file(root: Path, raw: Any, label: str) -> Path:
    if not isinstance(raw, str) or not raw or Path(raw).is_absolute():
        raise CashEtfPrepartitionError(f"{label} must be repository relative")
    boundary = root.resolve(strict=True)
    try:
        path = (boundary / raw).resolve(strict=True)
        path.relative_to(boundary)
    except (OSError, ValueError) as exc:
        raise CashEtfPrepartitionError(f"invalid {label}: {raw}") from exc
    if not path.is_file():
        raise CashEtfPrepartitionError(f"{label} is not a file: {raw}")
    return path


def extract_date(line: bytes, field: str) -> date:
    pattern = SESSION if field == "session" else ACTION_DATE if field == "action_date" else None
    if pattern is None:
        raise CashEtfPrepartitionError(f"unsupported routing field: {field}")
    matches = pattern.findall(line)
    if len(matches) != 1:
        raise CashEtfPrepartitionError(f"row must contain exactly one {field}")
    try:
        return date.fromisoformat(matches[0].decode("ascii"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise CashEtfPrepartitionError(f"invalid {field}") from exc


def _boundaries(contract: Mapping[str, Any]) -> tuple[Boundary, ...]:
    result = tuple(
        Boundary(
            str(row["partition_id"]),
            date.fromisoformat(str(row["start_inclusive"])),
            date.fromisoformat(str(row["end_exclusive"])),
        )
        for row in contract["partitions"]
    )
    if tuple(row.partition_id for row in result) != (
        "development",
        "validation",
        "historical_confirmation",
    ):
        raise CashEtfPrepartitionError("partition order changed")
    for index, row in enumerate(result):
        if row.start >= row.end:
            raise CashEtfPrepartitionError("partition boundary is reversed")
        if index and result[index - 1].end != row.start:
            raise CashEtfPrepartitionError("partitions must be contiguous")
    return result


def load_contract(path: Path, repo_root: Path) -> dict[str, Any]:
    contract = _load_canonical(path, "cash-ETF C1 prepartition contract")
    if (
        contract.get("schema_version"),
        contract.get("experiment_id"),
        contract.get("status"),
    ) != (CONTRACT_SCHEMA, EXPERIMENT_ID, "frozen"):
        raise CashEtfPrepartitionError("unexpected or unfrozen C1 contract")
    if contract.get("method") != "opaque_jsonl_copy_routed_only_by_session_or_action_date":
        raise CashEtfPrepartitionError("C1 prepartition method changed")
    if contract.get("numeric_fields_deserialized") is not False:
        raise CashEtfPrepartitionError("C1 contract permits numeric deserialization")
    if contract.get("excluded_2026_rows_allowed") is not False:
        raise CashEtfPrepartitionError("C1 contract permits 2026 rows")
    inputs = contract.get("inputs")
    if not isinstance(inputs, list) or len(inputs) != 22:
        raise CashEtfPrepartitionError("C1 must bind exactly 22 proxy inputs")
    identities = [(row.get("symbol"), row.get("kind")) for row in inputs]
    if len(identities) != len(set(identities)):
        raise CashEtfPrepartitionError("C1 repeats a source identity")
    for row in inputs:
        if row.get("routing_field") not in {"session", "action_date"}:
            raise CashEtfPrepartitionError("invalid C1 routing field")
        source = _repo_file(repo_root, row.get("path"), "C1 source")
        if sha256_file(source) != row.get("sha256"):
            raise CashEtfPrepartitionError(f"C1 source checksum changed: {row.get('path')}")
    _boundaries(contract)
    return contract


def _copy_one(
    source: Path,
    outputs: Mapping[str, Path],
    field: str,
    boundaries: Sequence[Boundary],
) -> dict[str, dict[str, Any]]:
    handles = {key: path.open("wb") for key, path in outputs.items()}
    summaries = {
        key: {"first_date": None, "last_date": None, "rows": 0} for key in outputs
    }
    previous: date | None = None
    try:
        with source.open("rb") as rows:
            for line_number, line in enumerate(rows, start=1):
                if not line.endswith(b"\n"):
                    raise CashEtfPrepartitionError(f"source line {line_number} lacks newline")
                value = extract_date(line, field)
                if previous is not None and value <= previous:
                    raise CashEtfPrepartitionError("source routing dates are not strictly increasing")
                previous = value
                selected = next((row for row in boundaries if row.start <= value < row.end), None)
                if selected is None:
                    if value >= date(2026, 1, 1):
                        raise CashEtfPrepartitionError("source contains excluded 2026 row")
                    continue
                handles[selected.partition_id].write(line)
                summary = summaries[selected.partition_id]
                summary["first_date"] = summary["first_date"] or value.isoformat()
                summary["last_date"] = value.isoformat()
                summary["rows"] += 1
    finally:
        for handle in handles.values():
            handle.close()
    return summaries


def build_prepartitions(contract_path: Path, repo_root: Path) -> dict[str, Any]:
    root = repo_root.resolve(strict=True)
    contract = load_contract(contract_path, root)
    artifact_root = root / str(contract["output"]["artifact_root"])
    if artifact_root.exists():
        raise CashEtfPrepartitionError("refusing to rewrite immutable C1 artifact root")
    artifact_root.parent.mkdir(parents=True, exist_ok=True)
    temp_root = Path(tempfile.mkdtemp(prefix=f".{artifact_root.name}-", dir=artifact_root.parent))
    records: list[dict[str, Any]] = []
    try:
        boundaries = _boundaries(contract)
        for source_record in contract["inputs"]:
            source = _repo_file(root, source_record["path"], "C1 source")
            outputs: dict[str, Path] = {}
            filename = f"{str(source_record['symbol']).lower().replace('/', '-')}-{source_record['kind']}.jsonl"
            for boundary in boundaries:
                directory = temp_root / boundary.partition_id
                directory.mkdir(parents=True, exist_ok=True)
                outputs[boundary.partition_id] = directory / filename
            summaries = _copy_one(source, outputs, str(source_record["routing_field"]), boundaries)
            for partition_id, output in outputs.items():
                relative = Path(contract["output"]["artifact_root"]) / output.relative_to(temp_root)
                records.append(
                    {
                        "first_date": summaries[partition_id]["first_date"],
                        "kind": source_record["kind"],
                        "last_date": summaries[partition_id]["last_date"],
                        "partition_id": partition_id,
                        "path": relative.as_posix(),
                        "rows": summaries[partition_id]["rows"],
                        "sha256": sha256_file(output),
                        "source_path": source_record["path"],
                        "source_sha256": source_record["sha256"],
                        "symbol": source_record["symbol"],
                    }
                )
        manifest = {
            "contract_path": str(contract_path.resolve(strict=True).relative_to(root)),
            "contract_sha256": sha256_file(contract_path),
            "economic_metrics_computed": False,
            "experiment_id": EXPERIMENT_ID,
            "numeric_fields_deserialized": False,
            "partitions": records,
            "schema_version": "cash-etf-c1-prepartition-manifest-v1",
            "strategy_features_or_signals_computed": False,
        }
        (temp_root / "partition-manifest.json").write_text(canonical_json(manifest), encoding="utf-8")
        os.replace(temp_root, artifact_root)
    except Exception:
        shutil.rmtree(temp_root, ignore_errors=True)
        raise
    return manifest


def write_evidence_manifest(contract_path: Path, repo_root: Path) -> dict[str, Any]:
    root = repo_root.resolve(strict=True)
    contract = load_contract(contract_path, root)
    artifact_root = root / str(contract["output"]["artifact_root"])
    partition_manifest_path = artifact_root / "partition-manifest.json"
    partition_manifest = _load_canonical(partition_manifest_path, "C1 partition manifest")
    artifacts = [
        {
            "path": str(contract_path.resolve(strict=True).relative_to(root)),
            "sha256": sha256_file(contract_path),
        },
        {
            "path": str(partition_manifest_path.relative_to(root)),
            "sha256": sha256_file(partition_manifest_path),
        },
    ]
    for row in partition_manifest["partitions"]:
        path = _repo_file(root, row["path"], "C1 partition output")
        if sha256_file(path) != row["sha256"]:
            raise CashEtfPrepartitionError("C1 partition checksum changed")
        artifacts.append({"path": row["path"], "sha256": row["sha256"]})
    evidence = {
        "artifacts": sorted(artifacts, key=lambda row: row["path"]),
        "decision": "timestamp_prepartition_passed_source_qualification_blocked",
        "economic_metrics_computed": False,
        "experiment_id": EXPERIMENT_ID,
        "numeric_fields_deserialized": False,
        "schema_version": "cash-etf-c1-prepartition-evidence-v1",
        "source_qualification_blocker": "complete_issuer_action_reconciliation_missing",
        "strategy_features_or_signals_computed": False,
    }
    path = artifact_root / "evidence-manifest.json"
    if path.exists():
        raise CashEtfPrepartitionError("refusing to overwrite C1 evidence manifest")
    path.write_text(canonical_json(evidence), encoding="utf-8")
    return evidence
