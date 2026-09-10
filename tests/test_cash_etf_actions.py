from __future__ import annotations

import json
from decimal import Decimal

from trading_platform.cash_etf_actions import compare_distributions


def test_precision_aware_amount_comparison_accepts_half_last_unit() -> None:
    result = compare_distributions(
        [{"action_date": "2023-01-03", "amount_per_share": "0.123"}],
        [{"ex_date": "2023-01-03", "amount_per_share": "0.1235"}],
    )
    assert result["passed"] is True


def test_precision_aware_amount_comparison_rejects_beyond_half_last_unit() -> None:
    result = compare_distributions(
        [{"action_date": "2023-01-03", "amount_per_share": "0.123"}],
        [{"ex_date": "2023-01-03", "amount_per_share": "0.123501"}],
    )
    assert result["passed"] is False
    assert result["amount_mismatches"][0]["tolerance"] == "0.0005"


def test_comparison_fails_closed_on_events_missing_either_way() -> None:
    result = compare_distributions(
        [
            {"action_date": "2023-01-03", "amount_per_share": "1"},
            {"action_date": "2023-02-03", "amount_per_share": "1"},
        ],
        [
            {"ex_date": "2023-01-03", "amount_per_share": "1"},
            {"ex_date": "2023-03-03", "amount_per_share": "1"},
        ],
    )
    assert result["passed"] is False
    assert result["missing_from_official"] == ["2023-02-03"]
    assert result["missing_from_provider"] == ["2023-03-03"]
