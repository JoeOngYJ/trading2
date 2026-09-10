#!/usr/bin/env python3
"""Generate or verify the corrected compact XLON v2 calendar."""

from __future__ import annotations

import argparse
from pathlib import Path

from trading_platform.cross_asset_xlon_calendar import canonical_json
from trading_platform.cross_asset_xlon_calendar_v2 import calendar_payload


REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = REPO_ROOT / "config/research/xlon-calendar-evidence-v1.json"
OUTPUT = REPO_ROOT / "config/research/xlon-calendar-2009-2025-v2.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered = canonical_json(calendar_payload(EVIDENCE, REPO_ROOT))
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text(encoding="utf-8") != rendered:
            raise SystemExit("XLON v2 calendar is missing, stale, or noncanonical")
        print("XLON v2 calendar valid")
        return
    if OUTPUT.exists() and OUTPUT.read_text(encoding="utf-8") != rendered:
        raise SystemExit("existing XLON v2 calendar differs from frozen output")
    if not OUTPUT.exists():
        OUTPUT.write_text(rendered, encoding="utf-8")
    print(f"XLON v2 calendar written: {OUTPUT.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
