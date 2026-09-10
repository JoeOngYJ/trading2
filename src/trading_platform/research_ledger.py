"""Causal, segment-aware candle and feature ledgers for offline research only."""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

from trading_platform.research_routing import RegimeFeatureObservation


FIVE_MINUTES_MS = 300_000
FOUR_HOURS_MS = 14_400_000
DAY_MS = 86_400_000
UTC = timezone.utc


class ResearchLedgerError(ValueError):
    """Raised when a local candle ledger is invalid, non-causal, or out of scope."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iso_ms(value: int) -> str:
    return datetime.fromtimestamp(value / 1000, tz=UTC).isoformat().replace("+00:00", "Z")


def canonical_json_line(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    )


def reject_symlink_tree(path: Path) -> None:
    candidate = path.absolute()
    for component in (candidate, *candidate.parents):
        if component.is_symlink():
            raise ResearchLedgerError(f"symlinked frozen input is prohibited: {component}")


@dataclass(frozen=True, slots=True)
class SourceCandle:
    segment: int
    open_ms: int
    open: float
    high: float
    low: float
    close: float
    base_volume: float
    quote_volume: float
    source_row: int

    @property
    def close_ms(self) -> int:
        return self.open_ms + FIVE_MINUTES_MS

    def as_dict(self) -> dict[str, Any]:
        return {
            "available_at": iso_ms(self.close_ms),
            "base_volume": self.base_volume,
            "close": self.close,
            "close_at": iso_ms(self.close_ms),
            "high": self.high,
            "instrument": "BTC/USDT",
            "interval": "5m",
            "low": self.low,
            "observed_at": iso_ms(self.close_ms),
            "open": self.open,
            "open_at": iso_ms(self.open_ms),
            "quote_volume": self.quote_volume,
            "segment": str(self.segment),
            "source_row": self.source_row,
        }


@dataclass(frozen=True, slots=True)
class AggregateCandle:
    segment: int
    interval: str
    open_ms: int
    close_ms: int
    open: float
    high: float
    low: float
    close: float
    base_volume: float
    quote_volume: float
    start_row: int
    end_row: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "available_at": iso_ms(self.close_ms),
            "base_volume": self.base_volume,
            "close": self.close,
            "close_at": iso_ms(self.close_ms),
            "end_source_row": self.end_row,
            "high": self.high,
            "instrument": "BTC/USDT",
            "interval": self.interval,
            "low": self.low,
            "observed_at": iso_ms(self.close_ms),
            "open": self.open,
            "open_at": iso_ms(self.open_ms),
            "quote_volume": self.quote_volume,
            "segment": str(self.segment),
            "start_source_row": self.start_row,
        }


def _finite(value: str, label: str, row_number: int) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ResearchLedgerError(f"invalid {label} at source line {row_number}") from exc
    if not math.isfinite(parsed):
        raise ResearchLedgerError(f"non-finite {label} at source line {row_number}")
    return parsed


def load_source_candles(path: Path, expected_sha256: str) -> tuple[list[SourceCandle], str]:
    """Load the one frozen development source and prove order, gaps, and OHLCV validity."""

    reject_symlink_tree(path)
    resolved = path.resolve(strict=True)
    if "holdout" in resolved.name.lower() or "2026-01-07" in resolved.name.lower():
        raise ResearchLedgerError("sealed holdout input is prohibited")
    digest = sha256_file(resolved)
    if digest != expected_sha256:
        raise ResearchLedgerError(
            f"development dataset checksum mismatch: expected {expected_sha256}, got {digest}"
        )
    rows: list[SourceCandle] = []
    previous: SourceCandle | None = None
    closed_segments: set[int] = set()
    with gzip.open(resolved, "rt", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {
            "segment_id",
            "open_time_ms",
            "open",
            "high",
            "low",
            "close",
            "base_volume",
            "quote_volume",
        }
        missing = sorted(required - set(reader.fieldnames or ()))
        if missing:
            raise ResearchLedgerError(f"development dataset lacks columns: {missing}")
        for source_row, source in enumerate(reader):
            line = source_row + 2
            try:
                segment = int(source["segment_id"])
                open_ms = int(source["open_time_ms"])
            except (TypeError, ValueError) as exc:
                raise ResearchLedgerError(f"invalid identity at source line {line}") from exc
            row = SourceCandle(
                segment=segment,
                open_ms=open_ms,
                open=_finite(source["open"], "open", line),
                high=_finite(source["high"], "high", line),
                low=_finite(source["low"], "low", line),
                close=_finite(source["close"], "close", line),
                base_volume=_finite(source["base_volume"], "base_volume", line),
                quote_volume=_finite(source["quote_volume"], "quote_volume", line),
                source_row=source_row,
            )
            if (
                row.segment < 0
                or row.open_ms < 0
                or row.open_ms % FIVE_MINUTES_MS
                or row.open <= 0
                or row.low <= 0
                or row.low > min(row.open, row.close)
                or row.high < max(row.open, row.close)
                or row.base_volume < 0
                or row.quote_volume < 0
            ):
                raise ResearchLedgerError(f"invalid OHLCV at source line {line}")
            if previous is not None:
                if row.open_ms <= previous.open_ms:
                    raise ResearchLedgerError(f"non-increasing timestamp at source line {line}")
                if row.segment == previous.segment:
                    if row.open_ms != previous.open_ms + FIVE_MINUTES_MS:
                        raise ResearchLedgerError(f"gap inside source segment at line {line}")
                else:
                    closed_segments.add(previous.segment)
                    if row.segment in closed_segments:
                        raise ResearchLedgerError(f"source segment reappears at line {line}")
            rows.append(row)
            previous = row
    if not rows:
        raise ResearchLedgerError("development dataset is empty")
    return rows, digest


def aggregate_candles(
    rows: list[SourceCandle], width_ms: int, interval: str
) -> tuple[list[AggregateCandle], int]:
    if width_ms <= FIVE_MINUTES_MS or width_ms % FIVE_MINUTES_MS:
        raise ResearchLedgerError("aggregate width must be a multiple greater than five minutes")
    count = width_ms // FIVE_MINUTES_MS
    bars: list[AggregateCandle] = []
    used = 0
    index = 0
    while index < len(rows):
        first = rows[index]
        if first.open_ms % width_ms:
            index += 1
            continue
        bucket = rows[index : index + count]
        complete = len(bucket) == count and all(
            item.segment == first.segment
            and item.open_ms == first.open_ms + offset * FIVE_MINUTES_MS
            for offset, item in enumerate(bucket)
        )
        if not complete:
            index += 1
            continue
        bars.append(
            AggregateCandle(
                segment=first.segment,
                interval=interval,
                open_ms=first.open_ms,
                close_ms=first.open_ms + width_ms,
                open=first.open,
                high=max(item.high for item in bucket),
                low=min(item.low for item in bucket),
                close=bucket[-1].close,
                base_volume=sum(item.base_volume for item in bucket),
                quote_volume=sum(item.quote_volume for item in bucket),
                start_row=index,
                end_row=index + count - 1,
            )
        )
        used += count
        index += count
    return bars, len(rows) - used


def feature_observations(
    bars: list[AggregateCandle], source_digest: str
) -> list[RegimeFeatureObservation]:
    observations: list[RegimeFeatureObservation] = []
    previous: AggregateCandle | None = None
    for bar in bars:
        values = {
            "high_low_log_range": math.log(bar.high / bar.low),
            "open_to_close_log_return": math.log(bar.close / bar.open),
        }
        if (
            previous is not None
            and previous.segment == bar.segment
            and previous.close_ms == bar.open_ms
        ):
            values["close_to_close_log_return"] = math.log(bar.close / previous.close)
        observed = datetime.fromtimestamp(bar.close_ms / 1000, tz=UTC)
        observations.append(
            RegimeFeatureObservation(
                instrument="BTC/USDT",
                interval=bar.interval,
                segment=str(bar.segment),
                observed_at=observed,
                available_at=observed,
                feature_values=values,
                source_digest=source_digest,
            )
        )
        previous = bar
    return observations


def write_jsonl_gzip(path: Path, rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Write deterministic gzip JSONL with an empty embedded filename and mtime zero."""

    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8", newline="\n") as text:
                for row in rows:
                    text.write(canonical_json_line(row))
                    text.write("\n")
                    count += 1
    return {"bytes": path.stat().st_size, "rows": count, "sha256": sha256_file(path)}


def iter_jsonl_gzip(path: Path) -> Iterator[dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            yield json.loads(line)
