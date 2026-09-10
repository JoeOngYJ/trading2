#!/usr/bin/env python3
"""Create immutable pre-2026 Feather inputs for the top-two development experiment."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd


STEMS = ("BTC_USDT", "ETH_USDT", "SOL_USDT", "XRP_USDT", "BNB_USDT", "DOGE_USDT", "ADA_USDT")
END_EXCLUSIVE = pd.Timestamp("2026-01-01T00:00:00Z")


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        parser.error(f"refusing to overwrite non-empty directory: {args.output_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for stem in STEMS:
        source = args.source_dir / f"{stem}-15m.feather"
        target = args.output_dir / source.name
        frame = pd.read_feather(source)
        frame["date"] = pd.to_datetime(frame["date"], utc=True)
        development = frame[frame["date"] < END_EXCLUSIVE].copy()
        if development.empty or development["date"].max() >= END_EXCLUSIVE:
            raise ValueError(f"failed development cutoff for {stem}")
        development.reset_index(drop=True).to_feather(target)
        rows.append(
            {
                "symbol": stem,
                "source_path": str(source),
                "source_sha256": digest(source),
                "source_rows": len(frame),
                "development_path": str(target),
                "development_sha256": digest(target),
                "development_rows": len(development),
                "development_max_timestamp": development["date"].max().isoformat(),
                "excluded_rows_at_or_after_2026": int((frame["date"] >= END_EXCLUSIVE).sum()),
            }
        )
    payload = {
        "schema_version": "multi-asset-top2-development-input-v1",
        "end_exclusive": END_EXCLUSIVE.isoformat(),
        "files": rows,
    }
    (args.output_dir / "input-manifest.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
