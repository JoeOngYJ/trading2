#!/usr/bin/env python3
"""Write the deterministic 2008-2025 A1 calendar contract."""

from __future__ import annotations

from pathlib import Path

from trading_platform.cross_asset_calendar import calendar_payload, canonical_json


REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT = REPO_ROOT / "config/research/cross-asset-a1-calendars-2008-2025-v1.json"


def main() -> None:
    rendered = canonical_json(calendar_payload())
    if OUTPUT.exists():
        if OUTPUT.read_text(encoding="utf-8") != rendered:
            raise SystemExit("existing calendar differs from frozen deterministic output")
    else:
        OUTPUT.write_text(rendered, encoding="utf-8")
    print(f"calendar written: {OUTPUT.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
