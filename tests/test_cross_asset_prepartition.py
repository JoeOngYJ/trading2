from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from trading_platform.cross_asset_oanda_hourly import canonical_json
from trading_platform.cross_asset_prepartition import (
    TimestampPrepartitionError,
    build_prepartitions,
    extract_routing_value,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _contract(source: Path, artifact_root: str, field: str = "observed_at") -> dict:
    code = source.parent / "prepartition.py"
    code.write_text("# fixture code binding\n", encoding="utf-8")
    return {
        "code_binding": {"path": code.name, "sha256": _sha(code)},
        "experiment_id": "cross-asset-a3-timestamp-prepartition-v1",
        "inputs": [
            {
                "instrument_id": f"TEST{index}",
                "kind": "market" if field == "observed_at" else "availability",
                "path": source.name,
                "routing_field": field,
                "sha256": _sha(source),
            }
            for index in range(15)
        ],
        "method": "opaque_jsonl_copy_routed_only_by_timestamp_or_local_date",
        "output": {"artifact_root": artifact_root},
        "partitions": [
            {
                "end_exclusive": "2022-01-01T00:00:00Z",
                "partition_id": "development",
                "start_inclusive": "2010-01-01T00:00:00Z",
            },
            {
                "end_exclusive": "2026-01-01T00:00:00Z",
                "partition_id": "validation",
                "start_inclusive": "2022-01-01T00:00:00Z",
            },
        ],
        "prohibitions": {
            "economic_metric_computation_allowed": False,
            "market_value_deserialization_allowed": False,
            "network_or_runtime_access_allowed": False,
            "prospective_price_access_allowed": False,
            "strategy_feature_or_signal_computation_allowed": False,
        },
        "prospective_final": {
            "price_rows_may_be_present": False,
            "start_inclusive": "2026-08-31T00:00:00Z",
        },
        "schema_version": "cross-asset-a3-timestamp-prepartition-contract-v1",
        "status": "frozen",
    }


def test_timestamp_extractor_does_not_require_valid_json_or_price_values():
    line = b'{"observed_at":"2021-01-01T00:00:00Z","price":NOT_JSON}\n'
    assert extract_routing_value(line, "observed_at").year == 2021


def test_prepartition_is_transactional_and_rejects_prospective_rows(tmp_path: Path):
    source = tmp_path / "source.jsonl"
    source.write_bytes(
        b'{"observed_at":"2011-01-01T00:00:00Z","price":NOT_JSON}\n'
        b'{"observed_at":"2023-01-01T00:00:00Z","price":STILL_NOT_JSON}\n'
        b'{"observed_at":"2026-01-01T00:00:00Z","price":SECRET}\n'
    )
    contract = _contract(source, "artifact")
    path = tmp_path / "contract.json"
    path.write_text(canonical_json(contract), encoding="utf-8")
    with pytest.raises(TimestampPrepartitionError, match="prospective-only"):
        build_prepartitions(path, tmp_path)
    assert not (tmp_path / "artifact").exists()


def test_prepartition_rejects_reversed_routing_values(tmp_path: Path):
    source = tmp_path / "source.jsonl"
    source.write_bytes(
        b'{"observed_at":"2023-01-01T00:00:00Z"}\n'
        b'{"observed_at":"2021-01-01T00:00:00Z"}\n'
    )
    contract = _contract(source, "artifact")
    path = tmp_path / "contract.json"
    path.write_text(canonical_json(contract), encoding="utf-8")
    with pytest.raises(TimestampPrepartitionError, match="strictly increasing"):
        build_prepartitions(path, tmp_path)


def test_prepartition_fails_closed_on_changed_source_checksum(tmp_path: Path):
    source = tmp_path / "source.jsonl"
    source.write_bytes(
        b'{"observed_at":"2011-01-01T00:00:00Z"}\n'
        b'{"observed_at":"2023-01-01T00:00:00Z"}\n'
    )
    contract = _contract(source, "artifact")
    contract["inputs"][0]["sha256"] = "0" * 64
    path = tmp_path / "contract.json"
    path.write_text(canonical_json(contract), encoding="utf-8")
    with pytest.raises(TimestampPrepartitionError, match="checksum changed"):
        build_prepartitions(path, tmp_path)
