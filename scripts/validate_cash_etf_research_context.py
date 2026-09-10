#!/usr/bin/env python3
"""Validate the repository-owned cash-ETF research context."""

from __future__ import annotations

import json
from pathlib import Path

from trading_platform.cash_etf_program import validate_context


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    print(json.dumps(validate_context(root), sort_keys=True))


if __name__ == "__main__":
    main()
