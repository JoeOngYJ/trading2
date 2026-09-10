#!/usr/bin/env python3
"""Snapshot public Binance spot trading filters into a checksummed research artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from trading_platform.execution_model import MarketRules, canonical_data


DEFAULT_URL = "https://data-api.binance.vision/api/v3/exchangeInfo"


def read_payload(input_path: Path | None, symbol: str, url: str) -> tuple[dict, str]:
    if input_path is not None:
        raw = input_path.read_bytes()
        source = str(input_path)
    else:
        request_url = f"{url}?{urllib.parse.urlencode({'symbol': symbol})}"
        request = urllib.request.Request(request_url, headers={"User-Agent": "retail-execution-research/1"})
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read()
        source = request_url
    payload = json.loads(raw)
    return payload, source


def build_snapshot(payload: dict, symbol: str, observed_at: str, source: str) -> dict:
    raw_sha256 = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    rules = MarketRules.from_binance_exchange_info(payload, symbol, observed_at)
    return {
        "schema_version": "binance-market-rules-snapshot-v1",
        "symbol": symbol,
        "observed_at": observed_at,
        "source": source,
        "raw_canonical_sha256": raw_sha256,
        "normalized_rules": canonical_data(rules),
        "normalized_rules_sha256": rules.checksum,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    observed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    payload, source = read_payload(args.input, args.symbol, args.url)
    snapshot = build_snapshot(payload, args.symbol, observed_at, source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(snapshot, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
