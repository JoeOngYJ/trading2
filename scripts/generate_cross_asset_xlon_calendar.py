#!/usr/bin/env python3
"""Generate or verify the frozen compact XLON calendar artifact."""

from __future__ import annotations

import argparse
from pathlib import Path

from trading_platform.cross_asset_xlon_calendar import calendar_payload, canonical_json


REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = REPO_ROOT / "config/research/xlon-calendar-evidence-v1.json"
OUTPUT = REPO_ROOT / "config/research/xlon-calendar-2009-2025-v1.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered = canonical_json(calendar_payload(EVIDENCE, REPO_ROOT))
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text(encoding="utf-8") != rendered:
            raise SystemExit("XLON calendar is missing, stale, or noncanonical")
        print("XLON calendar valid")
        return
    if OUTPUT.exists() and OUTPUT.read_text(encoding="utf-8") != rendered:
        raise SystemExit("existing XLON calendar differs from frozen output")
    if not OUTPUT.exists():
        OUTPUT.write_text(rendered, encoding="utf-8")
    print(f"XLON calendar written: {OUTPUT.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
