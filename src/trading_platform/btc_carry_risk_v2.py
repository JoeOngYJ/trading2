"""Offline safe-exposure implementation for the frozen BTC carry-risk v2 experiment."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from trading_platform.btc_carry import (
    BPS,
    DAY_MS,
    HOUR_MS,
    ZERO,
    CarryBacktestError,
    CarryCostScenario,
    CarryParameters,
    FundingEvent,
    HourBar,
    _metrics,
    _monthly_concentration,
    _quantity,
    funding_score_bps,
)


UTC = timezone.utc
SEVERE_EXIT_BPS = Decimal("20")


def _margin_state(
    *,
    active: dict[str, Any],
    mark_price: Decimal,
    params: CarryParameters,
) -> dict[str, Decimal]:
    quantity = active["quantity"]
    observed_equity = (
        active["collateral"]
        + quantity * (active["future_entry_fill"] - mark_price)
        + active["funding"]
        - active["entry_fees"] / 2
    )
    observed_maintenance = quantity * mark_price * params.maintenance_margin_fraction
    shocked_mark = mark_price * (Decimal("1") + params.adverse_mark_shock_fraction)
    shocked_equity = (
        active["collateral"]
        + quantity * (active["future_entry_fill"] - shocked_mark)
        + active["funding"]
        - active["entry_fees"] / 2
    )
    shocked_maintenance = quantity * shocked_mark * params.maintenance_margin_fraction
    return {
        "observed_equity": observed_equity,
        "observed_maintenance": observed_maintenance,
        "observed_ratio": (
            Decimal("Infinity")
            if observed_maintenance == 0
            else observed_equity / observed_maintenance
        ),
        "shocked_equity": shocked_equity,
        "shocked_maintenance": shocked_maintenance,
        "shocked_ratio": (
            Decimal("Infinity")
            if shocked_maintenance == 0
            else shocked_equity / shocked_maintenance
        ),
    }


def run_safe_carry_backtest(
    *,
    spot: dict[int, HourBar],
    future: dict[int, HourBar],
    mark: dict[int, HourBar],
    funding: list[FundingEvent],
    start_ms: int,
    end_ms: int,
    scenario: CarryCostScenario,
    params: CarryParameters,
    minimum_shocked_margin_ratio: Decimal = Decimal("2"),
    starting_equity: Decimal = Decimal("1000"),
    mode: str = "signal",
    include_funding: bool = True,
) -> dict[str, Any]:
    """Run the causal v2 implementation without changing the inherited carry signal."""
    if mode not in {"signal", "always_on"}:
        raise CarryBacktestError("unsupported safe carry mode")
    if params.leg_fraction != Decimal("0.25"):
        raise CarryBacktestError("safe carry v2 requires the frozen 25% leg fraction")
    if minimum_shocked_margin_ratio != Decimal("2"):
        raise CarryBacktestError("safe carry v2 requires the frozen 2.0 shocked margin ratio")
    if start_ms >= end_ms or start_ms % HOUR_MS or end_ms % HOUR_MS:
        raise CarryBacktestError("partition boundaries must be increasing exact hours")

    ordered_funding = sorted(funding, key=lambda event: event.scheduled_ms)
    if len({event.scheduled_ms for event in ordered_funding}) != len(ordered_funding):
        raise CarryBacktestError("duplicate funding schedule")
    hours = list(range(start_ms, end_ms + HOUR_MS, HOUR_MS))
    funding_by_time = {event.scheduled_ms: event for event in ordered_funding}

    equity = starting_equity
    active: dict[str, Any] | None = None
    trades: list[dict[str, Any]] = []
    daily: list[tuple[int, Decimal]] = []
    pending_weekly_action: str | None = None
    pending_risk_exit_signal_ms: int | None = None
    exposure_hours = 0
    margin_breaches = 0
    shock_margin_breaches = 0
    risk_exit_signals = 0
    risk_exits = 0
    entry_shocked_ratio_rejections = 0
    unavailable_hours = 0
    skipped_decisions = 0
    notional_mismatch_rejections = 0
    maximum_entry_notional_mismatch_fraction = ZERO
    minimum_observed_ratio: Decimal | None = None
    minimum_shocked_ratio: Decimal | None = None
    total_funding = ZERO
    total_spot_raw = ZERO
    total_future_raw = ZERO
    total_fees = ZERO
    total_implicit = ZERO
    turnover = ZERO
    last_available_spot_hour: int | None = None

    def close_position(timestamp: int, reason: str, *, severe: bool = False) -> None:
        nonlocal active, equity, total_spot_raw, total_future_raw
        nonlocal total_fees, total_implicit, turnover, risk_exits
        assert active is not None
        spot_bar = spot[timestamp]
        future_bar = future[timestamp]
        exit_fee = SEVERE_EXIT_BPS if severe else scenario.fee_bps_per_fill
        exit_implicit = SEVERE_EXIT_BPS if severe else scenario.implicit_bps_per_fill
        spot_exit_fill = spot_bar.open * (Decimal("1") - exit_implicit / BPS)
        future_exit_fill = future_bar.open * (Decimal("1") + exit_implicit / BPS)
        quantity = active["quantity"]
        spot_raw = quantity * (spot_bar.open - active["spot_entry_raw"])
        future_raw = quantity * (active["future_entry_raw"] - future_bar.open)
        spot_implicit = quantity * (
            (active["spot_entry_fill"] - active["spot_entry_raw"])
            + (spot_bar.open - spot_exit_fill)
        )
        future_implicit = quantity * (
            (active["future_entry_raw"] - active["future_entry_fill"])
            + (future_exit_fill - future_bar.open)
        )
        exit_fees = (
            quantity * spot_exit_fill * exit_fee / BPS
            + quantity * future_exit_fill * exit_fee / BPS
        )
        fees = active["entry_fees"] + exit_fees
        implicit = spot_implicit + future_implicit
        net = spot_raw + future_raw + active["funding"] - fees - implicit
        equity += net
        total_spot_raw += spot_raw
        total_future_raw += future_raw
        total_fees += fees
        total_implicit += implicit
        turnover += quantity * (
            active["spot_entry_fill"]
            + active["future_entry_fill"]
            + spot_exit_fill
            + future_exit_fill
        )
        if reason == "margin_buffer_risk_exit":
            risk_exits += 1
        trades.append(
            {
                "basis_convergence_pnl": str(spot_raw + future_raw),
                "entry_ms": active["entry_ms"],
                "entry_score_bps": str(active["entry_score_bps"]),
                "exit_ms": timestamp,
                "exit_reason": reason,
                "explicit_fees": str(fees),
                "funding_cashflow": str(active["funding"]),
                "future_price_pnl": str(future_raw),
                "holding_hours": (timestamp - active["entry_ms"]) // HOUR_MS,
                "implicit_cost": str(implicit),
                "net_pnl": str(net),
                "quantity_BTC": str(quantity),
                "risk_signal_ms": active.get("risk_signal_ms"),
                "spot_price_pnl": str(spot_raw),
            }
        )
        active = None

    for timestamp in hours:
        spot_bar = spot.get(timestamp)
        future_bar = future.get(timestamp)
        mark_bar = mark.get(timestamp)
        if spot_bar is None or future_bar is None or mark_bar is None:
            unavailable_hours += 1
            continue

        if active is not None and last_available_spot_hour is not None:
            previous = spot[last_available_spot_hour]
            if timestamp != last_available_spot_hour + HOUR_MS or spot_bar.segment != previous.segment:
                close_position(timestamp, "data_gap_neutralization", severe=True)
                pending_weekly_action = None
                pending_risk_exit_signal_ms = None
        last_available_spot_hour = timestamp

        event = funding_by_time.get(timestamp)
        if (
            active is not None
            and event is not None
            and event.observed_ms < timestamp + HOUR_MS
            and timestamp > active["entry_ms"]
        ):
            payment = active["quantity"] * mark_bar.open * event.rate if include_funding else ZERO
            active["funding"] += payment
            total_funding += payment

        if active is not None and pending_risk_exit_signal_ms is not None:
            active["risk_signal_ms"] = pending_risk_exit_signal_ms
            close_position(timestamp, "margin_buffer_risk_exit", severe=True)
            pending_weekly_action = None
            pending_risk_exit_signal_ms = None

        dt = datetime.fromtimestamp(timestamp / 1000, tz=UTC)
        weekday = dt.weekday()
        hour = dt.hour
        if weekday == 0 and hour == 0:
            decision_ms = timestamp + 5 * 60_000
            score = funding_score_bps(ordered_funding, decision_ms, params.lookback_events)
            if score is None:
                skipped_decisions += 1
                pending_weekly_action = None
            elif mode == "always_on":
                pending_weekly_action = "enter" if active is None else None
            elif active is None:
                pending_weekly_action = "enter" if score > params.entry_threshold_bps else None
            elif score <= params.exit_threshold_bps:
                pending_weekly_action = "exit_score"
            elif timestamp + HOUR_MS - active["entry_ms"] >= params.maximum_holding_days * DAY_MS:
                pending_weekly_action = "exit_time"
            else:
                pending_weekly_action = None
            if pending_weekly_action == "enter":
                pending_weekly_action = f"enter:{score}"

        if weekday == 0 and hour == 1 and pending_weekly_action:
            if pending_weekly_action.startswith("exit") and active is not None:
                close_position(
                    timestamp,
                    "score_exit" if pending_weekly_action == "exit_score" else "time_exit",
                )
            elif pending_weekly_action.startswith("enter") and active is None:
                score = Decimal(pending_weekly_action.split(":", 1)[1])
                quantity = _quantity(equity, spot_bar.open, future_bar.open, params)
                mismatch = abs(spot_bar.open - future_bar.open) / max(
                    spot_bar.open, future_bar.open
                )
                maximum_entry_notional_mismatch_fraction = max(
                    maximum_entry_notional_mismatch_fraction, mismatch
                )
                if mismatch > Decimal("0.01"):
                    notional_mismatch_rejections += 1
                elif quantity <= 0:
                    skipped_decisions += 1
                else:
                    spot_fill = spot_bar.open * (
                        Decimal("1") + scenario.implicit_bps_per_fill / BPS
                    )
                    future_fill = future_bar.open * (
                        Decimal("1") - scenario.implicit_bps_per_fill / BPS
                    )
                    entry_fees = (
                        quantity
                        * (spot_fill + future_fill)
                        * scenario.fee_bps_per_fill
                        / BPS
                    )
                    candidate = {
                        "collateral": equity * (Decimal("1") - params.leg_fraction),
                        "entry_equity": equity,
                        "entry_fees": entry_fees,
                        "entry_ms": timestamp,
                        "entry_score_bps": score,
                        "funding": ZERO,
                        "future_entry_fill": future_fill,
                        "future_entry_raw": future_bar.open,
                        "quantity": quantity,
                        "spot_entry_fill": spot_fill,
                        "spot_entry_raw": spot_bar.open,
                    }
                    entry_state = _margin_state(
                        active=candidate,
                        mark_price=mark_bar.open,
                        params=params,
                    )
                    if (
                        entry_state["observed_equity"]
                        <= entry_state["observed_maintenance"]
                        or entry_state["shocked_equity"]
                        <= entry_state["shocked_maintenance"]
                        or entry_state["shocked_ratio"] < minimum_shocked_margin_ratio
                    ):
                        entry_shocked_ratio_rejections += 1
                    else:
                        active = candidate
            pending_weekly_action = None

        if active is not None:
            exposure_hours += 1
            state = _margin_state(active=active, mark_price=mark_bar.close, params=params)
            minimum_observed_ratio = (
                state["observed_ratio"]
                if minimum_observed_ratio is None
                else min(minimum_observed_ratio, state["observed_ratio"])
            )
            minimum_shocked_ratio = (
                state["shocked_ratio"]
                if minimum_shocked_ratio is None
                else min(minimum_shocked_ratio, state["shocked_ratio"])
            )
            if state["observed_equity"] <= state["observed_maintenance"]:
                margin_breaches += 1
                pending_risk_exit_signal_ms = timestamp + HOUR_MS
            elif state["shocked_equity"] <= state["shocked_maintenance"]:
                shock_margin_breaches += 1
                pending_risk_exit_signal_ms = timestamp + HOUR_MS
            elif state["shocked_ratio"] < minimum_shocked_margin_ratio:
                if pending_risk_exit_signal_ms is None:
                    risk_exit_signals += 1
                    pending_risk_exit_signal_ms = timestamp + HOUR_MS

        if hour == 23:
            marked = equity
            if active is not None:
                marked += (
                    active["quantity"] * (spot_bar.close - active["spot_entry_fill"])
                    + active["quantity"]
                    * (active["future_entry_fill"] - future_bar.close)
                    + active["funding"]
                    - active["entry_fees"]
                )
            daily.append((timestamp, marked))

    valid_final_hours = [
        timestamp
        for timestamp in hours
        if timestamp in spot and timestamp in future and timestamp in mark
    ]
    if not valid_final_hours:
        raise CarryBacktestError("safe carry partition has no complete execution hour")
    final_hour = max(valid_final_hours)
    if active is not None:
        close_position(final_hour, "partition_end")
    if not daily or daily[-1][0] != final_hour:
        daily.append((final_hour, equity))
    else:
        daily[-1] = (final_hour, equity)

    metrics = _metrics(daily, trades, starting_equity)
    concentration = _monthly_concentration(daily, trades)
    annual_start: dict[str, Decimal] = {}
    annual_end: dict[str, Decimal] = {}
    for timestamp, value in daily:
        year = str(datetime.fromtimestamp(timestamp / 1000, tz=UTC).year)
        annual_start.setdefault(year, value)
        annual_end[year] = value
    metrics.update(
        {
            "annual_returns": {
                year: float(annual_end[year] / annual_start[year] - Decimal("1"))
                for year in sorted(annual_start)
            },
            "exposure_days": exposure_hours / 24,
            "net_return_per_unit_leg_fraction": metrics["net_return"]
            / float(params.leg_fraction),
            "return_per_exposed_day": (
                None
                if exposure_hours == 0
                else metrics["net_return"] / (exposure_hours / 24)
            ),
            "turnover_quote": str(turnover),
        }
    )
    return {
        "attribution": {
            "basis_convergence_pnl": str(total_spot_raw + total_future_raw),
            "collateral_opportunity_cost": "not_modeled_promotion_blocker",
            "explicit_fees": str(total_fees),
            "funding_cashflow": str(total_funding),
            "future_price_pnl": str(total_future_raw),
            "implicit_cost": str(total_implicit),
            "spot_price_pnl": str(total_spot_raw),
        },
        "concentration": concentration,
        "counts": {
            "entry_shocked_ratio_rejections": entry_shocked_ratio_rejections,
            "margin_breaches": margin_breaches,
            "maximum_entry_notional_mismatch_fraction": float(
                maximum_entry_notional_mismatch_fraction
            ),
            "notional_mismatch_rejections": notional_mismatch_rejections,
            "risk_exit_signals": risk_exit_signals,
            "risk_exits": risk_exits,
            "shock_margin_breaches": shock_margin_breaches,
            "skipped_decisions": skipped_decisions,
            "unavailable_hours": unavailable_hours,
        },
        "margin_diagnostics": {
            "minimum_observed_margin_equity_to_maintenance_ratio": (
                None if minimum_observed_ratio is None else float(minimum_observed_ratio)
            ),
            "minimum_required_shocked_ratio": float(minimum_shocked_margin_ratio),
            "minimum_shocked_margin_equity_to_maintenance_ratio": (
                None if minimum_shocked_ratio is None else float(minimum_shocked_ratio)
            ),
        },
        "metrics": metrics,
        "mode": mode,
        "scenario_id": scenario.scenario_id,
        "trades": trades,
    }
