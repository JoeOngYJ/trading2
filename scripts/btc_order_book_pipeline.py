#!/usr/bin/env python3
"""Capture and deterministically replay an isolated Binance BTCUSDT spot L2 feed."""
from __future__ import annotations

import argparse
import asyncio
import bisect
import csv
import gzip
import hashlib
import json
import os
import tempfile
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "btc-spot-l2-capture-v1"
REPLAY_VERSION = "1"
DEFAULT_WS_URL = (
    "wss://data-stream.binance.vision/stream?"
    "streams=btcusdt@depth@100ms/btcusdt@aggTrade"
)
DEFAULT_REST_URL = "https://data-api.binance.vision"
FEATURE_COLUMNS = (
    "capture_sequence", "connection_id", "segment_id", "event_time_ms",
    "receipt_time_ns", "first_update_id", "final_update_id", "best_bid",
    "best_ask", "bid_qty_l1", "ask_qty_l1", "spread", "mid_price",
    "microprice", "microprice_minus_mid_spreads", "queue_imbalance_l1",
    "queue_imbalance_l5", "queue_imbalance_l10", "ofi_l1",
    "bid_add_qty", "bid_remove_qty", "ask_add_qty", "ask_remove_qty",
)
TRADE_COLUMNS = (
    "capture_sequence", "connection_id", "event_time_ms", "trade_time_ms", "receipt_time_ns",
    "aggregate_trade_id", "first_trade_id", "last_trade_id", "price",
    "quantity", "quote_quantity", "aggressor_side", "signed_base_quantity",
    "signed_quote_quantity",
)


class ValidationError(ValueError):
    """Raised when captured data cannot be accepted without silent repair."""


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utc_iso_from_ns(timestamp_ns: int) -> str:
    return datetime.fromtimestamp(timestamp_ns / 1_000_000_000, timezone.utc).isoformat()


def decimal_value(raw: Any, label: str, *, allow_zero: bool = False) -> Decimal:
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, ValueError) as exc:
        raise ValidationError(f"invalid {label}: {raw!r}") from exc
    if not value.is_finite() or value < 0 or (not allow_zero and value == 0):
        raise ValidationError(f"invalid {label}: {raw!r}")
    return value


def decimal_text(value: Decimal) -> str:
    return format(value, "f")


def ratio_text(numerator: Decimal, denominator: Decimal) -> str:
    if denominator == 0:
        return ""
    return format(numerator / denominator, ".18f")


def deterministic_gzip(source: Path, target: Path) -> None:
    temp = tempfile.NamedTemporaryFile("wb", dir=target.parent, delete=False)
    temp_path = Path(temp.name)
    try:
        with source.open("rb") as input_handle, temp:
            with gzip.GzipFile(filename="", mode="wb", compresslevel=9,
                               fileobj=temp, mtime=0) as output_handle:
                for chunk in iter(lambda: input_handle.read(1024 * 1024), b""):
                    output_handle.write(chunk)
        os.replace(temp_path, target)
    finally:
        temp_path.unlink(missing_ok=True)


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="\n", dir=path.parent, delete=False
    )
    temp_path = Path(temp.name)
    try:
        with temp:
            temp.write(canonical_json(value) + "\n")
            temp.flush()
            os.fsync(temp.fileno())
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


class RawPartitionWriter:
    """Append canonical envelopes and atomically finalize deterministic hourly gzip files."""

    def __init__(self, raw_dir: Path, capture_id: str):
        self.raw_dir = raw_dir
        self.raw_dir.mkdir(parents=True, exist_ok=False)
        self.capture_id = capture_id
        self.sequence = 0
        self._hour: str | None = None
        self._handle: Any = None
        self._part_path: Path | None = None
        self._counts: Counter[str] = Counter()
        self._partition_counts: Counter[str] = Counter()
        self.partitions: list[dict[str, Any]] = []

    def write(self, kind: str, connection_id: int, **fields: Any) -> dict[str, Any]:
        receipt_ns = int(fields.pop("receipt_time_ns", time.time_ns()))
        hour = datetime.fromtimestamp(receipt_ns / 1_000_000_000, timezone.utc).strftime(
            "%Y%m%dT%H"
        )
        if hour != self._hour:
            self._finalize_partition()
            self._hour = hour
            self._part_path = self.raw_dir / f"raw-{hour}.ndjson.part"
            self._handle = self._part_path.open("w", encoding="utf-8", newline="\n")
            self._partition_counts = Counter()
        self.sequence += 1
        record = {
            "schema_version": SCHEMA_VERSION,
            "capture_id": self.capture_id,
            "sequence": self.sequence,
            "kind": kind,
            "connection_id": connection_id,
            "receipt_time_ns": receipt_ns,
            **fields,
        }
        self._handle.write(canonical_json(record) + "\n")
        self._handle.flush()
        self._counts[kind] += 1
        self._partition_counts[kind] += 1
        return record

    def _finalize_partition(self) -> None:
        if self._handle is None or self._part_path is None or self._hour is None:
            return
        self._handle.flush()
        os.fsync(self._handle.fileno())
        self._handle.close()
        target = self.raw_dir / f"raw-{self._hour}.ndjson.gz"
        uncompressed_sha256 = sha256_path(self._part_path)
        uncompressed_bytes = self._part_path.stat().st_size
        deterministic_gzip(self._part_path, target)
        self.partitions.append({
            "file": target.name,
            "sha256": sha256_path(target),
            "bytes": target.stat().st_size,
            "uncompressed_sha256": uncompressed_sha256,
            "uncompressed_bytes": uncompressed_bytes,
            "records": sum(self._partition_counts.values()),
            "kind_counts": dict(sorted(self._partition_counts.items())),
        })
        self._part_path.unlink()
        self._handle = None
        self._part_path = None

    def close(self) -> None:
        self._finalize_partition()

    @property
    def counts(self) -> dict[str, int]:
        return dict(sorted(self._counts.items()))


async def http_text(client: Any, url: str) -> tuple[str, int, int, int]:
    send_ns = time.time_ns()
    response = await client.get(url)
    receive_ns = time.time_ns()
    response.raise_for_status()
    return response.text, response.status_code, send_ns, receive_ns


async def capture(args: argparse.Namespace) -> Path:
    try:
        import httpx
        import websockets
    except ImportError as exc:  # pragma: no cover - environment-dependent message
        raise SystemExit("capture requires httpx and websockets") from exc

    start_ns = time.time_ns()
    capture_id = f"btc-l2-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    capture_dir = args.output_root / capture_id
    capture_dir.mkdir(parents=True, exist_ok=False)
    writer = RawPartitionWriter(capture_dir / "raw", capture_id)
    deadline = time.monotonic() + args.duration_seconds
    connection_id = 0
    reconnects = 0
    error: str | None = None
    next_checkpoint = time.monotonic()

    def checkpoint(status: str, *, ended_ns: int | None = None) -> None:
        finalized_count = sum(item["records"] for item in writer.partitions)
        finalized_kinds: Counter[str] = Counter()
        for item in writer.partitions:
            finalized_kinds.update(item["kind_counts"])
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "pipeline_sha256": sha256_path(Path(__file__).resolve()),
            "capture_id": capture_id,
            "symbol": "BTCUSDT",
            "venue": "binance",
            "market": "spot",
            "ws_url": args.ws_url,
            "rest_url": args.rest_url,
            "requested_duration_seconds": args.duration_seconds,
            "started_at": utc_iso_from_ns(start_ns),
            "checkpointed_at": utc_iso_from_ns(time.time_ns()),
            "ended_at": None if ended_ns is None else utc_iso_from_ns(ended_ns),
            "status": status,
            "connections": connection_id,
            "reconnects": reconnects,
            "record_count": writer.sequence if ended_ns is not None else finalized_count,
            "active_record_count": writer.sequence,
            "kind_counts": writer.counts if ended_ns is not None else dict(sorted(finalized_kinds.items())),
            "partitions": writer.partitions,
        }
        atomic_write_json(capture_dir / "capture-manifest.json", manifest)

    checkpoint("running")
    try:
        async with httpx.AsyncClient(timeout=args.http_timeout_seconds) as client:
            while time.monotonic() < deadline:
                connection_id += 1
                writer.write("audit", connection_id, event="connect_attempt", ws_url=args.ws_url)
                try:
                    async with websockets.connect(
                        args.ws_url,
                        max_queue=None,
                        ping_interval=20,
                        ping_timeout=20,
                        close_timeout=5,
                    ) as socket:
                        writer.write("audit", connection_id, event="connected")

                        raw_time, status, send_ns, receive_ns = await http_text(
                            client, f"{args.rest_url}/api/v3/time"
                        )
                        server_time = json.loads(raw_time)
                        server_ms = int(server_time["serverTime"])
                        midpoint_ns = (send_ns + receive_ns) // 2
                        writer.write(
                            "clock_sync", connection_id, receipt_time_ns=receive_ns,
                            request_time_ns=send_ns, response_time_ns=receive_ns,
                            round_trip_ns=receive_ns - send_ns, server_time_ms=server_ms,
                            midpoint_offset_ns=server_ms * 1_000_000 - midpoint_ns,
                            http_status=status, raw_json=raw_time,
                        )

                        raw_snapshot, status, send_ns, receive_ns = await http_text(
                            client, f"{args.rest_url}/api/v3/depth?symbol=BTCUSDT&limit=5000"
                        )
                        snapshot = json.loads(raw_snapshot)
                        if not isinstance(snapshot.get("lastUpdateId"), int):
                            raise ValidationError("snapshot lacks integer lastUpdateId")
                        writer.write(
                            "snapshot", connection_id, receipt_time_ns=receive_ns,
                            request_time_ns=send_ns, response_time_ns=receive_ns,
                            http_status=status, last_update_id=snapshot["lastUpdateId"],
                            raw_json=raw_snapshot,
                        )

                        while time.monotonic() < deadline:
                            remaining = deadline - time.monotonic()
                            try:
                                raw_message = await asyncio.wait_for(
                                    socket.recv(), timeout=min(30.0, max(0.001, remaining))
                                )
                            except asyncio.TimeoutError:
                                if time.monotonic() >= deadline:
                                    break
                                writer.write("audit", connection_id, event="receive_timeout")
                                continue
                            receipt_ns = time.time_ns()
                            if isinstance(raw_message, bytes):
                                raw_message = raw_message.decode("utf-8")
                            message = json.loads(raw_message)
                            stream = message.get("stream")
                            if stream not in ("btcusdt@depth@100ms", "btcusdt@aggTrade"):
                                raise ValidationError(f"unexpected stream: {stream!r}")
                            writer.write(
                                "stream", connection_id, receipt_time_ns=receipt_ns,
                                stream=stream, raw_json=raw_message,
                            )
                            if time.monotonic() >= next_checkpoint:
                                checkpoint("running")
                                next_checkpoint = time.monotonic() + 60
                        writer.write("audit", connection_id, event="duration_complete")
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # reconnects are data-quality events
                    reconnects += 1
                    writer.write(
                        "audit", connection_id, event="connection_error",
                        error_type=type(exc).__name__, error=str(exc),
                    )
                    if time.monotonic() < deadline:
                        await asyncio.sleep(min(args.reconnect_max_seconds, 2 ** min(reconnects, 5)))
    except KeyboardInterrupt:
        error = "interrupted"
    except asyncio.CancelledError:
        error = "cancelled"
        raise
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        end_ns = time.time_ns()
        writer.close()
        checkpoint("complete" if error is None else error, ended_ns=end_ns)
    return capture_dir


@dataclass
class LocalBook:
    bids: dict[Decimal, Decimal] = field(default_factory=dict)
    asks: dict[Decimal, Decimal] = field(default_factory=dict)
    bid_prices: list[Decimal] = field(default_factory=list)
    ask_prices: list[Decimal] = field(default_factory=list)
    last_update_id: int = 0

    @classmethod
    def from_snapshot(cls, snapshot: dict[str, Any]) -> "LocalBook":
        try:
            update_id = int(snapshot["lastUpdateId"])
            raw_bids, raw_asks = snapshot["bids"], snapshot["asks"]
        except (KeyError, TypeError, ValueError) as exc:
            raise ValidationError("malformed depth snapshot") from exc
        book = cls(last_update_id=update_id)
        book.bids = book._levels(raw_bids, "snapshot bid")
        book.asks = book._levels(raw_asks, "snapshot ask")
        book.bid_prices = sorted(book.bids)
        book.ask_prices = sorted(book.asks)
        book.validate_uncrossed()
        return book

    @staticmethod
    def _levels(rows: Any, label: str) -> dict[Decimal, Decimal]:
        if not isinstance(rows, list):
            raise ValidationError(f"{label} levels are not a list")
        result: dict[Decimal, Decimal] = {}
        for row in rows:
            if not isinstance(row, list) or len(row) != 2:
                raise ValidationError(f"malformed {label} level")
            price = decimal_value(row[0], f"{label} price")
            quantity = decimal_value(row[1], f"{label} quantity", allow_zero=True)
            if price in result:
                raise ValidationError(f"duplicate {label} price")
            if quantity != 0:
                result[price] = quantity
        if not result:
            raise ValidationError(f"empty {label} book")
        return result

    def validate_uncrossed(self) -> None:
        if not self.bids or not self.asks:
            raise ValidationError("empty side after depth update")
        if self.bid_prices[-1] >= self.ask_prices[0]:
            raise ValidationError("crossed or locked book")

    @staticmethod
    def _apply_side(
        side: dict[Decimal, Decimal], prices: list[Decimal], rows: Any, label: str
    ) -> tuple[Decimal, Decimal]:
        added = Decimal(0)
        removed = Decimal(0)
        if not isinstance(rows, list):
            raise ValidationError(f"{label} updates are not a list")
        seen: set[Decimal] = set()
        parsed: list[tuple[Decimal, Decimal]] = []
        for row in rows:
            if not isinstance(row, list) or len(row) != 2:
                raise ValidationError(f"malformed {label} update")
            price = decimal_value(row[0], f"{label} price")
            quantity = decimal_value(row[1], f"{label} quantity", allow_zero=True)
            if price in seen:
                raise ValidationError(f"duplicate {label} price in update")
            seen.add(price)
            parsed.append((price, quantity))
        for price, quantity in parsed:
            previous = side.get(price, Decimal(0))
            if quantity > previous:
                added += quantity - previous
            elif quantity < previous:
                removed += previous - quantity
            if quantity == 0:
                if price in side:
                    del side[price]
                    index = bisect.bisect_left(prices, price)
                    if index >= len(prices) or prices[index] != price:
                        raise ValidationError(f"{label} price index disagrees with book")
                    prices.pop(index)
            else:
                if price not in side:
                    bisect.insort(prices, price)
                side[price] = quantity
        return added, removed

    def apply(self, data: dict[str, Any]) -> tuple[Decimal, Decimal, Decimal, Decimal]:
        bid_add, bid_remove = self._apply_side(
            self.bids, self.bid_prices, data.get("b"), "bid"
        )
        ask_add, ask_remove = self._apply_side(
            self.asks, self.ask_prices, data.get("a"), "ask"
        )
        self.validate_uncrossed()
        self.last_update_id = int(data["u"])
        return bid_add, bid_remove, ask_add, ask_remove

    def top(self, count: int) -> tuple[list[tuple[Decimal, Decimal]], list[tuple[Decimal, Decimal]]]:
        bids = [(price, self.bids[price]) for price in reversed(self.bid_prices[-count:])]
        asks = [(price, self.asks[price]) for price in self.ask_prices[:count]]
        return bids, asks


def parse_stream(record: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    try:
        message = json.loads(record["raw_json"])
        stream, data = message["stream"], message["data"]
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValidationError("malformed stream envelope") from exc
    if stream != record.get("stream") or not isinstance(data, dict):
        raise ValidationError("stream envelope disagrees with capture metadata")
    return stream, data


def book_feature_row(
    record: dict[str, Any], data: dict[str, Any], book: LocalBook,
    before: tuple[Decimal, Decimal, Decimal, Decimal], segment_id: int,
    deltas: tuple[Decimal, Decimal, Decimal, Decimal],
) -> tuple[str, ...]:
    bids, asks = book.top(10)
    best_bid, bid_qty = bids[0]
    best_ask, ask_qty = asks[0]
    spread = best_ask - best_bid
    mid = (best_bid + best_ask) / 2
    microprice = (best_ask * bid_qty + best_bid * ask_qty) / (bid_qty + ask_qty)
    previous_bid, previous_bid_qty, previous_ask, previous_ask_qty = before
    ofi = (
        (bid_qty if best_bid >= previous_bid else Decimal(0))
        - (previous_bid_qty if best_bid <= previous_bid else Decimal(0))
        - (ask_qty if best_ask <= previous_ask else Decimal(0))
        + (previous_ask_qty if best_ask >= previous_ask else Decimal(0))
    )

    def imbalance(levels: int) -> str:
        bid_depth = sum(quantity for _, quantity in bids[:levels])
        ask_depth = sum(quantity for _, quantity in asks[:levels])
        return ratio_text(bid_depth - ask_depth, bid_depth + ask_depth)

    bid_add, bid_remove, ask_add, ask_remove = deltas
    return (
        str(record["sequence"]), str(record["connection_id"]), str(segment_id),
        str(int(data["E"])), str(record["receipt_time_ns"]), str(int(data["U"])),
        str(int(data["u"])), decimal_text(best_bid), decimal_text(best_ask),
        decimal_text(bid_qty), decimal_text(ask_qty), decimal_text(spread),
        decimal_text(mid), decimal_text(microprice),
        ratio_text(microprice - mid, spread), imbalance(1), imbalance(5), imbalance(10),
        decimal_text(ofi), decimal_text(bid_add), decimal_text(bid_remove),
        decimal_text(ask_add), decimal_text(ask_remove),
    )


def trade_row(record: dict[str, Any], data: dict[str, Any]) -> tuple[str, ...]:
    required = ("E", "T", "a", "f", "l", "p", "q", "m")
    if any(key not in data for key in required) or not isinstance(data["m"], bool):
        raise ValidationError("malformed aggregate trade")
    price = decimal_value(data["p"], "trade price")
    quantity = decimal_value(data["q"], "trade quantity")
    quote = price * quantity
    side = "sell" if data["m"] else "buy"
    sign = Decimal(-1) if side == "sell" else Decimal(1)
    return (
        str(record["sequence"]), str(record["connection_id"]), str(int(data["E"])),
        str(int(data["T"])), str(record["receipt_time_ns"]), str(int(data["a"])), str(int(data["f"])),
        str(int(data["l"])), decimal_text(price), decimal_text(quantity),
        decimal_text(quote), side, decimal_text(sign * quantity),
        decimal_text(sign * quote),
    )


def iter_capture_records(capture_dir: Path) -> Iterable[dict[str, Any]]:
    manifest_path = capture_dir / "capture-manifest.json"
    if not manifest_path.exists():
        raise ValidationError("capture-manifest.json is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = {item["file"]: item for item in manifest.get("partitions", [])}
    actual = sorted((capture_dir / "raw").glob("raw-*.ndjson.gz"))
    if {path.name for path in actual} != set(expected):
        raise ValidationError("raw partition set differs from capture manifest")
    previous_sequence = 0
    for path in actual:
        if sha256_path(path) != expected[path.name]["sha256"]:
            raise ValidationError(f"raw checksum mismatch: {path.name}")
        with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
            for line in handle:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValidationError(f"invalid NDJSON in {path.name}") from exc
                if record.get("schema_version") != SCHEMA_VERSION:
                    raise ValidationError("unknown capture schema")
                sequence = record.get("sequence")
                if not isinstance(sequence, int) or sequence != previous_sequence + 1:
                    raise ValidationError("capture sequence gap or duplicate")
                previous_sequence = sequence
                yield record
    if previous_sequence != manifest.get("record_count"):
        raise ValidationError("capture record count disagrees with manifest")


class DeterministicCsvWriter:
    """Stream rows to disk, then atomically produce reproducible gzip output."""

    def __init__(self, path: Path, columns: tuple[str, ...]):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", newline="", dir=path.parent, delete=False
        )
        self._temp_path = Path(self._handle.name)
        self._writer = csv.writer(self._handle, lineterminator="\n")
        self._writer.writerow(columns)
        self.count = 0

    def write(self, row: tuple[str, ...]) -> None:
        self._writer.writerow(row)
        self.count += 1

    def close(self) -> tuple[int, str]:
        self._handle.flush()
        os.fsync(self._handle.fileno())
        self._handle.close()
        try:
            deterministic_gzip(self._temp_path, self.path)
        finally:
            self._temp_path.unlink(missing_ok=True)
        return self.count, sha256_path(self.path)


def replay_records(records: Iterable[dict[str, Any]], output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    feature_output = DeterministicCsvWriter(
        output_dir / "btc-order-book-features.csv.gz", FEATURE_COLUMNS
    )
    trade_output = DeterministicCsvWriter(
        output_dir / "btc-aggregate-trades.csv.gz", TRADE_COLUMNS
    )
    segments: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    book: LocalBook | None = None
    connection_id: int | None = None
    segment_id = 0
    snapshot_sequence: int | None = None
    segment_start: int | None = None
    segment_end: int | None = None
    accepted_events = stale_events = 0
    last_trade_id: dict[int, int] = {}
    last_raw_trade_id: dict[int, int] = {}
    inactive_depth_events = 0
    inactive_rejection_recorded = False
    hourly: dict[str, dict[str, Any]] = {}
    clock_sync_samples: list[dict[str, int]] = []

    def quality_bucket(record: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
        receipt_ns = int(record["receipt_time_ns"])
        hour = datetime.fromtimestamp(receipt_ns / 1_000_000_000, timezone.utc).strftime(
            "%Y-%m-%dT%H:00:00Z"
        )
        bucket = hourly.setdefault(hour, {
            "stream_records": 0, "accepted_depth_events": 0,
            "stale_depth_events": 0, "inactive_depth_events": 0,
            "aggregate_trades": 0, "first_receipt_time_ns": receipt_ns,
            "last_receipt_time_ns": receipt_ns, "latency_count": 0,
            "latency_sum_ns": 0, "latency_min_ns": None, "latency_max_ns": None,
            "book_samples": 0, "bid_levels_sum": 0, "ask_levels_sum": 0,
            "bid_levels_min": None, "bid_levels_max": None,
            "ask_levels_min": None, "ask_levels_max": None,
        })
        bucket["stream_records"] += 1
        bucket["first_receipt_time_ns"] = min(bucket["first_receipt_time_ns"], receipt_ns)
        bucket["last_receipt_time_ns"] = max(bucket["last_receipt_time_ns"], receipt_ns)
        if isinstance(data.get("E"), int):
            latency = receipt_ns - int(data["E"]) * 1_000_000
            bucket["latency_count"] += 1
            bucket["latency_sum_ns"] += latency
            bucket["latency_min_ns"] = latency if bucket["latency_min_ns"] is None else min(
                bucket["latency_min_ns"], latency
            )
            bucket["latency_max_ns"] = latency if bucket["latency_max_ns"] is None else max(
                bucket["latency_max_ns"], latency
            )
        return bucket

    def add_book_quality(bucket: dict[str, Any], current_book: LocalBook) -> None:
        bid_count, ask_count = len(current_book.bids), len(current_book.asks)
        bucket["book_samples"] += 1
        bucket["bid_levels_sum"] += bid_count
        bucket["ask_levels_sum"] += ask_count
        for side, count in (("bid", bid_count), ("ask", ask_count)):
            minimum, maximum = f"{side}_levels_min", f"{side}_levels_max"
            bucket[minimum] = count if bucket[minimum] is None else min(bucket[minimum], count)
            bucket[maximum] = count if bucket[maximum] is None else max(bucket[maximum], count)

    def finish_segment(reason: str) -> None:
        nonlocal snapshot_sequence, segment_start, segment_end
        if segment_start is not None:
            segments.append({
                "segment_id": segment_id,
                "connection_id": connection_id,
                "status": "accepted",
                "start_sequence": segment_start,
                "end_sequence": segment_end,
                "end_reason": reason,
            })
        elif snapshot_sequence is not None and reason in ("new_snapshot", "end_of_capture"):
            rejected.append({
                "sequence": snapshot_sequence,
                "connection_id": connection_id,
                "reason": "snapshot_without_bridge_event",
            })
        snapshot_sequence = None
        segment_start = segment_end = None

    for record in records:
        kind = record.get("kind")
        if kind == "clock_sync":
            try:
                clock_sync_samples.append({
                    "connection_id": int(record["connection_id"]),
                    "server_time_ms": int(record["server_time_ms"]),
                    "round_trip_ns": int(record["round_trip_ns"]),
                    "midpoint_offset_ns": int(record["midpoint_offset_ns"]),
                })
            except (KeyError, TypeError, ValueError) as exc:
                rejected.append({"sequence": record.get("sequence"), "reason": f"invalid clock sync: {exc}"})
            continue
        if kind == "snapshot":
            finish_segment("new_snapshot")
            try:
                snapshot = json.loads(record["raw_json"])
                if int(snapshot["lastUpdateId"]) != int(record["last_update_id"]):
                    raise ValidationError("snapshot metadata mismatch")
                book = LocalBook.from_snapshot(snapshot)
                connection_id = int(record["connection_id"])
                segment_id += 1
                snapshot_sequence = int(record["sequence"])
                inactive_rejection_recorded = False
            except (KeyError, TypeError, ValueError, json.JSONDecodeError, ValidationError) as exc:
                rejected.append({"sequence": record.get("sequence"), "reason": str(exc)})
                book = None
            continue
        if kind != "stream":
            continue
        try:
            stream, data = parse_stream(record)
            bucket = quality_bucket(record, data)
            if stream == "btcusdt@aggTrade":
                row = trade_row(record, data)
                aggregate_id = int(data["a"])
                trade_connection = int(record["connection_id"])
                previous = last_trade_id.get(trade_connection)
                if previous is not None and aggregate_id != previous + 1:
                    raise ValidationError("aggregate trade ID gap or duplicate")
                first_trade_id, final_trade_id = int(data["f"]), int(data["l"])
                if final_trade_id < first_trade_id:
                    raise ValidationError("invalid underlying trade ID range")
                previous_raw = last_raw_trade_id.get(trade_connection)
                if previous_raw is not None and first_trade_id != previous_raw + 1:
                    raise ValidationError("underlying trade ID gap or duplicate")
                last_trade_id[trade_connection] = aggregate_id
                last_raw_trade_id[trade_connection] = final_trade_id
                trade_output.write(row)
                bucket["aggregate_trades"] += 1
                continue
            if stream != "btcusdt@depth@100ms":
                raise ValidationError(f"unexpected stream: {stream!r}")
            if book is None or int(record["connection_id"]) != connection_id:
                inactive_depth_events += 1
                bucket["inactive_depth_events"] += 1
                if not inactive_rejection_recorded:
                    rejected.append({
                        "sequence": record["sequence"], "reason": "depth_without_snapshot"
                    })
                    inactive_rejection_recorded = True
                continue
            first_id, final_id = int(data["U"]), int(data["u"])
            if first_id <= 0 or final_id < first_id or not isinstance(data.get("E"), int):
                raise ValidationError("invalid depth update IDs or timestamp")
            expected_id = book.last_update_id + 1
            if final_id < expected_id:
                stale_events += 1
                bucket["stale_depth_events"] += 1
                continue
            if not first_id <= expected_id <= final_id:
                finish_segment("update_gap")
                rejected.append({
                    "sequence": record["sequence"], "connection_id": connection_id,
                    "reason": "update_gap", "expected_update_id": expected_id,
                    "first_update_id": first_id, "final_update_id": final_id,
                })
                book = None
                inactive_rejection_recorded = True
                continue
            bids, asks = book.top(1)
            before = (bids[0][0], bids[0][1], asks[0][0], asks[0][1])
            try:
                deltas = book.apply(data)
            except ValidationError as exc:
                finish_segment("invalid_book")
                rejected.append({"sequence": record["sequence"], "reason": str(exc)})
                book = None
                inactive_rejection_recorded = True
                continue
            if segment_start is None:
                segment_start = record["sequence"]
            segment_end = record["sequence"]
            feature_output.write(book_feature_row(record, data, book, before, segment_id, deltas))
            accepted_events += 1
            bucket["accepted_depth_events"] += 1
            add_book_quality(bucket, book)
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            rejected.append({"sequence": record.get("sequence"), "reason": str(exc)})
            if record.get("stream") == "btcusdt@depth@100ms" and book is not None:
                finish_segment("invalid_depth_record")
                book = None
                inactive_rejection_recorded = True
    finish_segment("end_of_capture")

    feature_path = feature_output.path
    trade_path = trade_output.path
    feature_count, feature_sha = feature_output.close()
    trade_count, trade_sha = trade_output.close()
    hourly_quality: list[dict[str, Any]] = []
    for hour, bucket in sorted(hourly.items()):
        coverage_ns = bucket["last_receipt_time_ns"] - bucket["first_receipt_time_ns"]
        latency_count = bucket.pop("latency_count")
        latency_sum = bucket.pop("latency_sum_ns")
        book_samples = bucket.pop("book_samples")
        bid_sum = bucket.pop("bid_levels_sum")
        ask_sum = bucket.pop("ask_levels_sum")
        bucket["hour"] = hour
        bucket["observed_coverage_seconds"] = coverage_ns / 1_000_000_000
        bucket["observed_stream_records_per_second"] = (
            None if coverage_ns <= 0 else bucket["stream_records"] / (coverage_ns / 1_000_000_000)
        )
        bucket["event_receipt_latency_mean_ns"] = (
            None if latency_count == 0 else latency_sum // latency_count
        )
        bucket["bid_levels_mean"] = None if book_samples == 0 else bid_sum / book_samples
        bucket["ask_levels_mean"] = None if book_samples == 0 else ask_sum / book_samples
        hourly_quality.append(bucket)
    manifest = {
        "schema_version": "btc-spot-l2-replay-v1",
        "replay_version": REPLAY_VERSION,
        "pipeline_sha256": sha256_path(Path(__file__).resolve()),
        "feature_file": feature_path.name,
        "feature_sha256": feature_sha,
        "feature_rows": feature_count,
        "trade_file": trade_path.name,
        "trade_sha256": trade_sha,
        "trade_rows": trade_count,
        "accepted_depth_events": accepted_events,
        "stale_depth_events": stale_events,
        "inactive_depth_events": inactive_depth_events,
        "accepted_segments": segments,
        "rejected_intervals": rejected,
        "clock_sync_samples": clock_sync_samples,
        "hourly_quality": hourly_quality,
        "status": "accepted" if feature_count > 0 and not rejected else "accepted_with_rejections" if feature_count > 0 else "rejected",
    }
    manifest_path = output_dir / "replay-manifest.json"
    atomic_write_json(manifest_path, manifest)
    return manifest


def replay(args: argparse.Namespace) -> dict[str, Any]:
    manifest = replay_records(iter_capture_records(args.capture_dir), args.output_dir)
    manifest["capture_manifest_sha256"] = sha256_path(
        args.capture_dir / "capture-manifest.json"
    )
    atomic_write_json(args.output_dir / "replay-manifest.json", manifest)
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    capture_parser = subparsers.add_parser("capture", help="capture the public live feed")
    capture_parser.add_argument("--duration-seconds", type=int, default=300)
    capture_parser.add_argument(
        "--output-root", type=Path,
        default=Path("artifacts/agent-level-experiment/btc-order-book/captures"),
    )
    capture_parser.add_argument("--ws-url", default=DEFAULT_WS_URL)
    capture_parser.add_argument("--rest-url", default=DEFAULT_REST_URL)
    capture_parser.add_argument("--http-timeout-seconds", type=float, default=15.0)
    capture_parser.add_argument("--reconnect-max-seconds", type=float, default=30.0)

    replay_parser = subparsers.add_parser("replay", help="validate and derive features")
    replay_parser.add_argument("--capture-dir", type=Path, required=True)
    replay_parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "capture" and args.duration_seconds <= 0:
        parser.error("--duration-seconds must be positive")
    return args


def main() -> None:
    args = parse_args()
    if args.command == "capture":
        capture_dir = asyncio.run(capture(args))
        print(capture_dir)
    else:
        print(canonical_json(replay(args)))


if __name__ == "__main__":
    main()
