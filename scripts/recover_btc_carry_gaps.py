#!/usr/bin/env python3
"""Recover the exact B2 BTC reference-price gaps from official Binance REST data."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "research/btc/contracts/btc-carry-gap-recovery-v1.json"
DEFAULT_OUTPUT = ROOT / "artifacts/agent-level-experiment/btc-focused/carry-gap-recovery-v1"
B2_SOURCE_MANIFEST = ROOT / "artifacts/agent-level-experiment/btc-focused/carry-data-qualification-v1/source-manifest.json"
B2_AUDIT_REPORT = ROOT / "artifacts/agent-level-experiment/btc-focused/carry-data-qualification-v1/audit-report.json"
HOUR_MS = 3_600_000
UTC = timezone.utc
SERIES = ("markPriceKlines", "indexPriceKlines", "premiumIndexKlines")


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_utc_ms(value: str) -> int:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("timestamp must be explicit UTC with Z suffix")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    if parsed.tzinfo != UTC or parsed.microsecond or parsed.minute or parsed.second:
        raise ValueError("timestamp must be aligned to an exact UTC hour")
    return int(parsed.timestamp() * 1000)


def iso_utc(timestamp_ms: int) -> str:
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC).isoformat().replace("+00:00", "Z")


def expected_times(spec: dict[str, Any]) -> list[int]:
    start = parse_utc_ms(spec["start_open_at"])
    end = parse_utc_ms(spec["end_open_at"])
    if end < start:
        raise ValueError(f"reversed request boundary: {spec['request_id']}")
    values = list(range(start, end + HOUR_MS, HOUR_MS))
    if len(values) != spec["expected_rows"]:
        raise ValueError(f"expected_rows does not match boundary: {spec['request_id']}")
    return values


def request_url(contract: dict[str, Any], spec: dict[str, Any]) -> str:
    endpoint = contract["endpoint_contract"][spec["series"]]
    expected = expected_times(spec)
    query = urllib.parse.urlencode(
        [
            (endpoint["identifier_parameter"], contract["data_boundary"]["symbol_or_pair"]),
            ("interval", contract["http"]["interval"]),
            ("startTime", str(expected[0])),
            ("endTime", str(expected[-1] + HOUR_MS - 1)),
            ("limit", str(spec["expected_rows"])),
        ]
    )
    url = f"https://{contract['allowed_host']}{endpoint['path']}?{query}"
    parsed = urllib.parse.urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != contract["allowed_host"]
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path != endpoint["path"]
    ):
        raise ValueError("generated URL violates the frozen source allowlist")
    return url


def validate_response_rows(payload: bytes, spec: dict[str, Any]) -> list[list[Any]]:
    try:
        rows = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("response is not valid JSON") from exc
    if not isinstance(rows, list):
        raise ValueError("response must be a JSON list")
    expected = expected_times(spec)
    if len(rows) != len(expected):
        raise ValueError(f"expected {len(expected)} rows, received {len(rows)}")
    observed: list[int] = []
    for row in rows:
        if not isinstance(row, list) or len(row) != 12:
            raise ValueError("response row must contain exactly 12 fields")
        if isinstance(row[0], bool) or not isinstance(row[0], int):
            raise ValueError("open time must be an integer millisecond timestamp")
        if isinstance(row[6], bool) or not isinstance(row[6], int):
            raise ValueError("close time must be an integer millisecond timestamp")
        opened = row[0]
        if opened % HOUR_MS or row[6] != opened + HOUR_MS - 1:
            raise ValueError("response row is not an exact one-hour UTC bar")
        try:
            opening, high, low, close = (Decimal(str(row[index])) for index in (1, 2, 3, 4))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError("OHLC field is not numeric") from exc
        values = (opening, high, low, close)
        if not all(value.is_finite() for value in values):
            raise ValueError("OHLC field is not finite")
        if high < max(opening, close) or low > min(opening, close) or high < low:
            raise ValueError("OHLC ordering is invalid")
        if spec["series"] != "premiumIndexKlines" and min(values) <= 0:
            raise ValueError("mark and index prices must be positive")
        observed.append(opened)
    if observed != expected or len(set(observed)) != len(observed):
        raise ValueError("response timestamps do not exactly match the frozen request")
    return rows


def csv_rows(path: Path):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != 1 or not names[0].endswith(".csv"):
            raise ValueError(f"archive must contain exactly one CSV: {path}")
        with archive.open(names[0]) as raw:
            reader = csv.reader(io.TextIOWrapper(raw, encoding="utf-8", newline=""))
            first = next(reader, None)
            if first is None:
                raise ValueError(f"empty CSV: {path}")
            if first[0] != "open_time":
                yield first
            yield from reader


def archive_open_times(records: list[dict[str, Any]], series: str) -> tuple[set[int], int, int]:
    opens: set[int] = set()
    duplicates = 0
    invalid = 0
    for record in records:
        path = ROOT / record["archive_path"]
        for row in csv_rows(path):
            try:
                if len(row) != 12:
                    raise ValueError("unexpected kline width")
                opened = int(row[0])
                if opened >= 100_000_000_000_000:
                    if opened % 1000:
                        raise ValueError("unaligned microsecond timestamp")
                    opened //= 1000
                closed = int(row[6])
                if closed >= 100_000_000_000_000:
                    if closed % 1000:
                        raise ValueError("unaligned microsecond timestamp")
                    closed //= 1000
                values = [float(row[index]) for index in (1, 2, 3, 4)]
                if opened % HOUR_MS or closed != opened + HOUR_MS - 1 or not all(math.isfinite(value) for value in values):
                    raise ValueError("invalid archive row")
                opening, high, low, close = values
                if high < max(opening, close) or low > min(opening, close) or high < low:
                    raise ValueError("invalid archive OHLC")
                if series != "premiumIndexKlines" and min(values) <= 0:
                    raise ValueError("non-positive archive price")
                if opened in opens:
                    duplicates += 1
                opens.add(opened)
            except (ValueError, OverflowError):
                invalid += 1
    return opens, duplicates, invalid


def gap_blocks(open_times: set[int], start: int, end: int) -> list[dict[str, Any]]:
    missing = [timestamp for timestamp in range(start, end + HOUR_MS, HOUR_MS) if timestamp not in open_times]
    blocks: list[dict[str, Any]] = []
    for timestamp in missing:
        if not blocks or timestamp != blocks[-1]["end_ms"] + HOUR_MS:
            blocks.append({"start_ms": timestamp, "end_ms": timestamp, "missing_hours": 1})
        else:
            blocks[-1]["end_ms"] = timestamp
            blocks[-1]["missing_hours"] += 1
    return [
        {
            "first_missing_open_at": iso_utc(item["start_ms"]),
            "last_missing_open_at": iso_utc(item["end_ms"]),
            "missing_hours": item["missing_hours"],
        }
        for item in blocks
    ]


def verify_contract(contract: dict[str, Any]) -> None:
    if contract["status"] != "frozen_before_any_recovery_request" or contract["http"]["credentials"] != "forbidden":
        raise ValueError("recovery contract is not frozen or credential-free")
    for item in contract["bound_inputs"]:
        path = ROOT / item["path"]
        if not path.is_file() or sha256_path(path) != item["sha256"]:
            raise ValueError(f"missing or changed bound input: {item['path']}")
    request_ids = [item["request_id"] for item in contract["frozen_requests"]]
    if len(request_ids) != 18 or len(set(request_ids)) != len(request_ids):
        raise ValueError("contract must contain exactly 18 unique frozen requests")
    audit = json.loads(B2_AUDIT_REPORT.read_text(encoding="utf-8"))
    for series in SERIES:
        frozen = sorted(
            (spec["start_open_at"], spec["end_open_at"], spec["expected_rows"])
            for spec in contract["frozen_requests"]
            if spec["series"] == series
        )
        audited = sorted(
            (item["first_missing_open_at"], item["last_missing_open_at"], item["missing_hours"])
            for item in audit["price_series"][series]["gap_intervals"]
        )
        if frozen != audited:
            raise ValueError(f"frozen requests do not exactly match B2 gaps: {series}")
        for spec in (item for item in contract["frozen_requests"] if item["series"] == series):
            request_url(contract, spec)


def fetch(url: str, timeout: int) -> tuple[int, bytes, str | None]:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "btc-carry-gap-recovery-v1/1.0"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - frozen HTTPS host
            return response.status, response.read(), None
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), f"HTTPError: {exc.reason}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return 0, b"", f"{type(exc).__name__}: {exc}"


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(value))


def run(output: Path) -> dict[str, Any]:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    verify_contract(contract)
    if output.exists():
        raise FileExistsError(f"output already exists; immutable run refused: {output}")
    raw_dir = output / "raw"
    raw_dir.mkdir(parents=True)

    records: list[dict[str, Any]] = []
    valid_rows_by_series: dict[str, list[list[Any]]] = {series: [] for series in SERIES}
    for spec in contract["frozen_requests"]:
        url = request_url(contract, spec)
        status, payload, transport_error = fetch(url, int(contract["http"]["timeout_seconds"]))
        raw_path = raw_dir / f"{spec['request_id']}.json"
        raw_path.write_bytes(payload)
        validation_error = None
        rows: list[list[Any]] = []
        if status == 200 and transport_error is None:
            try:
                rows = validate_response_rows(payload, spec)
            except ValueError as exc:
                validation_error = str(exc)
        else:
            validation_error = transport_error or f"HTTP status {status}"
        if validation_error is None:
            valid_rows_by_series[spec["series"]].extend(rows)
        records.append(
            {
                "bytes": len(payload),
                "expected_rows": spec["expected_rows"],
                "http_status": status,
                "raw_path": str(raw_path.relative_to(ROOT)),
                "raw_sha256": sha256_bytes(payload),
                "request_id": spec["request_id"],
                "response_rows": len(rows),
                "series": spec["series"],
                "source_url": url,
                "status": "valid_exact_response" if validation_error is None else "failed_closed",
                "validation_error": validation_error,
            }
        )

    source_manifest = {
        "audit_id": contract["audit_id"],
        "credentials_used": False,
        "request_count": len(records),
        "requests": records,
        "return_pnl_position_order_or_regime_calculated": False,
        "source": "official_Binance_USD_M_public_REST",
    }
    write_json(output / "source-manifest.json", source_manifest)

    b2_source = json.loads(B2_SOURCE_MANIFEST.read_text(encoding="utf-8"))
    start = parse_utc_ms(contract["data_boundary"]["start_inclusive"])
    end = parse_utc_ms(contract["data_boundary"]["end_inclusive"])
    results: dict[str, Any] = {}
    for series in SERIES:
        archive_records = [
            item for item in b2_source["archive_records"] if item["series"] == series and item["status"] != "failed"
        ]
        archive_times, archive_duplicates, archive_invalid = archive_open_times(archive_records, series)
        recovered_times = [int(row[0]) for row in valid_rows_by_series[series]]
        overlap_count = sum(timestamp in archive_times for timestamp in recovered_times)
        recovered_duplicate_count = len(recovered_times) - len(set(recovered_times))
        combined = archive_times | set(recovered_times)
        gaps = gap_blocks(combined, start, end)
        results[series] = {
            "archive_duplicate_open_times": archive_duplicates,
            "archive_invalid_rows": archive_invalid,
            "archive_row_count": len(archive_times),
            "combined_duplicate_open_times": archive_duplicates + recovered_duplicate_count + overlap_count,
            "combined_gap_blocks": gaps,
            "combined_invalid_rows": archive_invalid,
            "combined_missing_hours": sum(item["missing_hours"] for item in gaps),
            "combined_row_count": len(combined),
            "recovered_archive_overlap_count": overlap_count,
            "recovered_duplicate_open_times": recovered_duplicate_count,
            "recovered_exact_rows": len(recovered_times),
        }
    exact_response_gate = all(item["status"] == "valid_exact_response" for item in records)
    continuity_gate = all(
        item["combined_duplicate_open_times"] == 0
        and item["combined_invalid_rows"] == 0
        and item["combined_missing_hours"] == 0
        and item["combined_row_count"] == contract["data_boundary"]["expected_complete_hour_count"]
        for item in results.values()
    )
    passed = exact_response_gate and continuity_gate
    report = {
        "actionable_arm_id": "no_trade",
        "audit_id": contract["audit_id"],
        "b2_negative_result_preserved": True,
        "combined_continuity_gate_passed": continuity_gate,
        "contract": {
            "path": str(CONTRACT_PATH.relative_to(ROOT)),
            "sha256": sha256_path(CONTRACT_PATH),
        },
        "decision": (
            "reference_price_continuity_recovered_strategy_readiness_still_blocked"
            if passed
            else "official_rest_gap_recovery_rejected"
        ),
        "exact_response_gate_passed": exact_response_gate,
        "no_interpolation_substitution_strategy_or_pnl": True,
        "price_series": results,
        "recovery_passed": passed,
        "strategy_readiness_gate_passed": False,
        "strategy_readiness_remaining_blockers": [
            "effective_dated_historical_fee_evidence",
            "effective_dated_historical_margin_brackets",
            "exact_account_fee_before_promotion",
        ],
    }
    write_json(output / "audit-report.json", report)

    evidence_items = []
    for path in (
        CONTRACT_PATH,
        ROOT / "research/btc/reports/BTC_CARRY_GAP_RECOVERY_PLAN.md",
        ROOT / "scripts/recover_btc_carry_gaps.py",
        ROOT / "research/btc/tests/test_carry_gap_recovery.py",
        output / "source-manifest.json",
        output / "audit-report.json",
    ):
        evidence_items.append({"path": str(path.relative_to(ROOT)), "sha256": sha256_path(path)})
    for record in records:
        evidence_items.append({"path": record["raw_path"], "sha256": record["raw_sha256"]})
    evidence_manifest = {
        "audit_id": contract["audit_id"],
        "items": evidence_items,
        "recovery_passed": passed,
    }
    write_json(output / "evidence-manifest.json", evidence_manifest)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    report = run(output)
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0 if report["recovery_passed"] else 2


if __name__ == "__main__":
    sys.exit(main())
