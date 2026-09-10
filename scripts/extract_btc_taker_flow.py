#!/usr/bin/env python3
"""Build a deterministic BTCUSDT taker-trade-flow dataset from Binance klines."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import os
import tarfile
import tempfile
import zipfile
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from pathlib import Path
from typing import Iterable

SCHEMA_VERSION = "btc-taker-trade-flow-v1"
EXTRACTOR_VERSION = "1"
INTERVAL_MS = 300_000
DERIVED_SCALE = Decimal("0.000000000000000001")
OUTPUT_COLUMNS = (
    "open_time_ms", "close_time_ms", "open", "high", "low", "close",
    "base_volume", "quote_volume", "trade_count", "taker_buy_base_volume",
    "taker_buy_quote_volume", "taker_sell_base_volume", "taker_sell_quote_volume",
    "taker_buy_base_ratio", "taker_buy_quote_ratio", "base_trade_flow_imbalance",
    "quote_trade_flow_imbalance", "average_base_volume_per_trade",
    "average_quote_volume_per_trade",
)


class ValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedRow:
    values: tuple[str, ...]
    open_ms: int
    close_ms: int


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def decimal_value(raw: str, name: str) -> Decimal:
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise ValidationError(f"invalid {name}: {raw!r}") from exc
    if not value.is_finite():
        raise ValidationError(f"non-finite {name}")
    return value


def normalize_timestamp(raw: str, unit: str, name: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValidationError(f"invalid {name}: {raw!r}") from exc
    if value < 0:
        raise ValidationError(f"negative {name}")
    if unit == "milliseconds":
        if len(raw) != 13:
            raise ValidationError(f"mixed timestamp unit for {name}")
        return value
    if unit == "microseconds":
        if len(raw) != 16:
            raise ValidationError(f"mixed timestamp unit for {name}")
        return value // 1000
    raise ValidationError(f"unsupported timestamp unit: {unit}")


def detect_timestamp_unit(raw: str) -> str:
    if len(raw) == 13:
        return "milliseconds"
    if len(raw) == 16:
        return "microseconds"
    raise ValidationError(f"unexpected timestamp width: {raw!r}")


def canonical_source(value: Decimal) -> str:
    return format(value, "f")


def canonical_derived(value: Decimal | None) -> str:
    if value is None:
        return ""
    return format(value.quantize(DERIVED_SCALE, rounding=ROUND_HALF_EVEN), "f")


def parse_row(fields: list[str], unit: str, *, allow_nonzero_ignore: bool = False,
              allow_legacy_close_boundary: bool = False) -> ParsedRow:
    if len(fields) != 12:
        raise ValidationError(f"expected 12 columns, got {len(fields)}")
    open_ms = normalize_timestamp(fields[0], unit, "open timestamp")
    close_ms = normalize_timestamp(fields[6], unit, "close timestamp")
    if unit == "microseconds":
        if int(fields[0]) % 1000 != 0 or int(fields[6]) % 1000 != 999:
            raise ValidationError("microsecond timestamps do not normalize exactly")
    if open_ms % INTERVAL_MS != 0:
        raise ValidationError("open timestamp is not aligned to a 5m boundary")
    if allow_legacy_close_boundary and close_ms == open_ms + INTERVAL_MS:
        close_ms = open_ms + INTERVAL_MS - 1
    elif close_ms != open_ms + INTERVAL_MS - 1:
        raise ValidationError("bar duration is not exactly five minutes")

    open_, high, low, close = (decimal_value(fields[i], n) for i, n in zip(
        (1, 2, 3, 4), ("open", "high", "low", "close")
    ))
    base, quote = decimal_value(fields[5], "base volume"), decimal_value(fields[7], "quote volume")
    buy_base = decimal_value(fields[9], "taker buy base volume")
    buy_quote = decimal_value(fields[10], "taker buy quote volume")
    ignore = decimal_value(fields[11], "ignore field")
    try:
        trades = int(fields[8])
    except ValueError as exc:
        raise ValidationError("trade count is not an integer") from exc
    if fields[8].strip() != str(trades):
        raise ValidationError("trade count is not canonically integral")
    if any(v <= 0 for v in (open_, high, low, close)):
        raise ValidationError("OHLC values must be positive")
    if any(v < 0 for v in (base, quote, buy_base, buy_quote)) or trades < 0:
        raise ValidationError("volume and trade count must be non-negative")
    if low > high or not (low <= open_ <= high) or not (low <= close <= high):
        raise ValidationError("invalid OHLC relationship")
    if buy_base > base or buy_quote > quote:
        raise ValidationError("taker-buy volume exceeds total volume")
    if ignore < 0 or (ignore != 0 and not allow_nonzero_ignore):
        raise ValidationError("Binance ignore field is nonzero")

    sell_base, sell_quote = base - buy_base, quote - buy_quote
    base_ratio = None if base == 0 else buy_base / base
    quote_ratio = None if quote == 0 else buy_quote / quote
    base_imbalance = None if base == 0 else (buy_base - sell_base) / base
    quote_imbalance = None if quote == 0 else (buy_quote - sell_quote) / quote
    avg_base = None if trades == 0 else base / trades
    avg_quote = None if trades == 0 else quote / trades
    for value, label, lower, upper in (
        (base_ratio, "base ratio", Decimal(0), Decimal(1)),
        (quote_ratio, "quote ratio", Decimal(0), Decimal(1)),
        (base_imbalance, "base imbalance", Decimal(-1), Decimal(1)),
        (quote_imbalance, "quote imbalance", Decimal(-1), Decimal(1)),
    ):
        if value is not None and not lower <= value <= upper:
            raise ValidationError(f"{label} outside valid range")

    values = (
        str(open_ms), str(close_ms), canonical_source(open_), canonical_source(high),
        canonical_source(low), canonical_source(close), canonical_source(base),
        canonical_source(quote), str(trades), canonical_source(buy_base),
        canonical_source(buy_quote), canonical_source(sell_base), canonical_source(sell_quote),
        canonical_derived(base_ratio), canonical_derived(quote_ratio),
        canonical_derived(base_imbalance), canonical_derived(quote_imbalance),
        canonical_derived(avg_base), canonical_derived(avg_quote),
    )
    return ParsedRow(values, open_ms, close_ms)


def expected_btc_files(source_manifest: dict) -> list[dict]:
    files = [item for item in source_manifest.get("files", []) if item.get("file", "").startswith("BTCUSDT-5m-")]
    files.sort(key=lambda item: item["file"])
    if len(files) != 24:
        raise ValidationError(f"expected 24 BTC archives, got {len(files)}")
    if len({item["file"] for item in files}) != len(files):
        raise ValidationError("duplicate BTC archive in source manifest")
    return files


def zip_payload(tar: tarfile.TarFile, member: tarfile.TarInfo) -> bytes:
    handle = tar.extractfile(member)
    if handle is None:
        raise ValidationError(f"cannot read {member.name}")
    return handle.read()


def iter_csv_rows(payload: bytes, expected_zip: str) -> Iterable[list[str]]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile as exc:
        raise ValidationError(f"corrupt ZIP: {expected_zip}") from exc
    with archive:
        members = [item for item in archive.infolist() if not item.is_dir()]
        expected_csv = expected_zip.removesuffix(".zip") + ".csv"
        if len(members) != 1 or members[0].filename != expected_csv:
            raise ValidationError(f"unexpected ZIP contents in {expected_zip}")
        with archive.open(members[0], "r") as binary:
            text = io.TextIOWrapper(binary, encoding="utf-8", newline="")
            yield from csv.reader(text)


def build(archive_path: Path, source_manifest_path: Path, output_dir: Path) -> dict:
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    expected = expected_btc_files(source_manifest)
    expected_by_name = {item["file"]: item for item in expected}
    output_dir.mkdir(parents=True, exist_ok=True)
    temp_csv = tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="", dir=output_dir, delete=False)
    temp_csv_path = Path(temp_csv.name)
    months: list[dict] = []
    previous_open: int | None = None
    total_rows = 0
    zero_base = zero_quote = zero_trades = 0
    first_open = last_open = None
    try:
        with tarfile.open(archive_path, "r:gz") as tar, temp_csv:
            candidates = [m for m in tar.getmembers() if m.isfile() and Path(m.name).name.startswith("BTCUSDT-5m-") and m.name.endswith(".zip")]
            found = {Path(m.name).name: m for m in candidates}
            if len(found) != len(candidates):
                raise ValidationError("duplicate BTC archive basename in tar")
            if set(found) != set(expected_by_name):
                raise ValidationError("tar BTC archive set differs from source manifest")
            writer = csv.writer(temp_csv, lineterminator="\n")
            writer.writerow(OUTPUT_COLUMNS)
            for name in sorted(expected_by_name):
                spec = expected_by_name[name]
                payload = zip_payload(tar, found[name])
                digest = hashlib.sha256(payload).hexdigest()
                if digest != spec["sha256"]:
                    raise ValidationError(f"checksum mismatch: {name}")
                rows = iter_csv_rows(payload, name)
                month_count = 0
                month_first = month_last = None
                unit = None
                for fields in rows:
                    if unit is None:
                        unit = detect_timestamp_unit(fields[0])
                        if unit != spec["timestamp_unit"]:
                            raise ValidationError(f"timestamp unit disagrees with manifest: {name}")
                    parsed = parse_row(fields, unit)
                    if previous_open is not None and parsed.open_ms != previous_open + INTERVAL_MS:
                        raise ValidationError(f"gap or duplicate before {parsed.open_ms}")
                    writer.writerow(parsed.values)
                    previous_open = parsed.open_ms
                    month_first = parsed.open_ms if month_first is None else month_first
                    month_last = parsed.open_ms
                    first_open = parsed.open_ms if first_open is None else first_open
                    last_open = parsed.open_ms
                    month_count += 1
                    total_rows += 1
                    zero_base += parsed.values[6] == "0"
                    zero_quote += parsed.values[7] == "0"
                    zero_trades += parsed.values[8] == "0"
                if month_count != spec["rows"] or month_first != spec["first_ms"] or month_last != spec["last_ms"]:
                    raise ValidationError(f"coverage disagrees with manifest: {name}")
                months.append({"file": name, "sha256": digest, "timestamp_unit": unit, "rows": month_count, "first_ms": month_first, "last_ms": month_last, "validation_errors": 0})
        if total_rows != 210_528:
            raise ValidationError(f"expected 210528 rows, got {total_rows}")
        uncompressed_sha = sha256_path(temp_csv_path)
        temp_gzip = tempfile.NamedTemporaryFile("wb", dir=output_dir, delete=False)
        temp_gzip_path = Path(temp_gzip.name)
        try:
            with temp_csv_path.open("rb") as source, temp_gzip:
                with gzip.GzipFile(filename="", mode="wb", compresslevel=9, fileobj=temp_gzip, mtime=0) as target:
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        target.write(chunk)
            compressed_sha = sha256_path(temp_gzip_path)
            dataset_name = f"BTCUSDT-5m-taker-trade-flow-2024-2025-{compressed_sha}.csv.gz"
            dataset_path = output_dir / dataset_name
            if dataset_path.exists():
                if sha256_path(dataset_path) != compressed_sha:
                    raise ValidationError("existing content-addressed dataset checksum mismatch")
                temp_gzip_path.unlink()
            else:
                os.replace(temp_gzip_path, dataset_path)
        finally:
            if temp_gzip_path.exists():
                temp_gzip_path.unlink()
        manifest = {
            "accepted": True, "schema_version": SCHEMA_VERSION, "extractor_version": EXTRACTOR_VERSION,
            "source_archive_sha256": sha256_path(archive_path),
            "source_manifest_sha256": sha256_path(source_manifest_path),
            "symbol": "BTCUSDT", "interval": "5m", "rows": total_rows,
            "first_open_ms": first_open, "last_open_ms": last_open,
            "months": months, "gap_count": 0, "duplicate_count": 0,
            "malformed_count": 0, "invalid_count": 0, "reconciliation_error_count": 0,
            "zero_base_volume_count": zero_base, "zero_quote_volume_count": zero_quote,
            "zero_trade_count": zero_trades, "uncompressed_csv_sha256": uncompressed_sha,
            "dataset_file": dataset_name, "dataset_sha256": compressed_sha,
        }
        manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
        temp_manifest = tempfile.NamedTemporaryFile("wb", dir=output_dir, delete=False)
        temp_manifest_path = Path(temp_manifest.name)
        with temp_manifest:
            temp_manifest.write(manifest_bytes)
        os.replace(temp_manifest_path, output_dir / "btc-taker-trade-flow-manifest.json")
        return manifest
    finally:
        if temp_csv_path.exists():
            temp_csv_path.unlink()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--source-manifest", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = build(args.archive, args.source_manifest, args.output_dir)
    except (ValidationError, OSError, json.JSONDecodeError, tarfile.TarError) as exc:
        parser.exit(2, f"validation failed: {exc}\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
