#!/usr/bin/env python3
"""Segment-aware, mark-to-market BTC 4h SMA trend robustness backtest."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import statistics
from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime, timezone
from pathlib import Path

from trading_platform.execution_model import (
    ExecutionScenario,
    MarketRules,
    OrderIntent,
    OrderKind,
    OrderStatus,
    PortfolioLedger,
    Side,
    load_scenarios,
    simulate_candle_taker,
)

FOUR_HOURS_MS = 14_400_000


@dataclass(frozen=True)
class Bar:
    segment: int
    open_ms: int
    open: float
    high: float
    low: float
    close: float


def load_4h(path: Path) -> tuple[list[Bar], int]:
    source=[]
    with gzip.open(path,"rt",newline="",encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            source.append((int(row["segment_id"]),int(row["open_time_ms"]),float(row["open"]),float(row["high"]),float(row["low"]),float(row["close"])))
    bars=[]; discarded=0; bucket=[]; previous=None
    for item in source:
        segment,open_ms,*_=item
        if previous is None or segment!=previous[0] or open_ms!=previous[1]+300_000 or open_ms%FOUR_HOURS_MS==0:
            if bucket: discarded+=len(bucket); bucket=[]
        bucket.append(item); previous=(segment,open_ms)
        if len(bucket)==48:
            first=bucket[0]; bars.append(Bar(segment,first[1],first[2],max(x[3] for x in bucket),min(x[4] for x in bucket),bucket[-1][5])); bucket=[]
    if bucket: discarded+=len(bucket)
    return bars,discarded


def run(bars: list[Bar], fee_bps: float, slippage_bps: float) -> dict:
    """Legacy full-notional regression path retained to reproduce the earlier report."""
    fee=fee_bps/10_000; slip=slippage_bps/10_000; cash=1.0; units=0.0; desired=False; peak=1.0; max_dd=0.0; equity_series=[]; trades=[]; entry_value=None; entry_index=None; forced_exits=0; exposed=0
    closes=[]
    for i,bar in enumerate(bars):
        new_segment=i==0 or bar.segment!=bars[i-1].segment
        if new_segment:
            desired=False; closes=[]
        if units and not desired:
            fill=bar.open*(1-slip); proceeds=units*fill*(1-fee); trade_return=proceeds/entry_value-1
            cash=proceeds; units=0; trades.append({"return":trade_return,"holding_bars":i-entry_index,"exit_ms":bar.open_ms,"forced_segment_exit":False}); entry_value=None
        if not units and desired and not new_segment:
            entry_value=cash; units=cash*(1-fee)/(bar.open*(1+slip)); cash=0.0; entry_index=i
        closes.append(bar.close)
        equity=cash if not units else units*bar.close
        exposed+=int(bool(units)); peak=max(peak,equity); max_dd=min(max_dd,equity/peak-1); equity_series.append((bar.open_ms,equity))
        if len(closes)>=30:
            fast=sum(closes[-10:])/10; slow=sum(closes[-30:])/30
            if len(closes)==30: desired=fast>slow
            else:
                fast_prev=sum(closes[-11:-1])/10; slow_prev=sum(closes[-31:-1])/30
                if fast_prev<=slow_prev and fast>slow: desired=True
                elif fast_prev>=slow_prev and fast<slow: desired=False
        last_segment_bar=i+1==len(bars) or bars[i+1].segment!=bar.segment
        if units and last_segment_bar:
            proceeds=units*bar.close*(1-slip)*(1-fee); trade_return=proceeds/entry_value-1
            cash=proceeds; units=0; trades.append({"return":trade_return,"holding_bars":i-entry_index+1,"exit_ms":bar.open_ms+FOUR_HOURS_MS,"forced_segment_exit":True}); forced_exits+=1; entry_value=None; desired=False
            equity_series[-1]=(bar.open_ms,cash); max_dd=min(max_dd,cash/peak-1)
    years={}
    grouped={}
    for timestamp,equity in equity_series: grouped.setdefault(datetime.fromtimestamp(timestamp/1000,tz=timezone.utc).year,[]).append(equity)
    prior=1.0
    for year in sorted(grouped):
        end=grouped[year][-1]; years[str(year)]=end/prior-1; prior=end
    elapsed_years=(bars[-1].open_ms-bars[0].open_ms)/(365.2425*86_400_000)
    gains=sum(t["return"] for t in trades if t["return"]>0); losses=-sum(t["return"] for t in trades if t["return"]<0)
    return {"fee_bps_per_side":fee_bps,"slippage_bps_per_side":slippage_bps,"return":cash-1,"cagr":cash**(1/elapsed_years)-1,"max_drawdown":max_dd,"trades":len(trades),"win_rate":sum(t["return"]>0 for t in trades)/len(trades) if trades else None,"profit_factor":gains/losses if losses else None,"exposure":exposed/len(bars),"average_holding_bars":statistics.fmean(t["holding_bars"] for t in trades) if trades else None,"forced_segment_exits":forced_exits,"year_returns":years}


def run_execution_scenario(
    bars: list[Bar],
    scenario: ExecutionScenario,
    position_fraction: Decimal = Decimal("0.25"),
) -> dict:
    """Mandate-bounded benchmark using the shared execution and accounting model."""
    if scenario.mode != "candle_taker":
        raise ValueError("4h benchmark requires a candle_taker scenario")
    if not bars:
        raise ValueError("bars are required")
    rules = MarketRules(
        symbol="BTCUSDT",
        effective_at="research-fixture-v1",
        tick_size=Decimal("0.01"),
        step_size=Decimal("0.00001"),
        min_quantity=Decimal("0.00001"),
        min_notional=Decimal("10"),
        source="research_fixture_not_historical_exchangeInfo",
    )
    ledger = PortfolioLedger(Decimal("1000"))
    desired = False
    closes: list[float] = []
    peak = Decimal("1000")
    max_dd = Decimal("0")
    equity_series: list[tuple[int, Decimal]] = []
    trades: list[dict] = []
    entry_equity: Decimal | None = None
    entry_allocated: Decimal | None = None
    entry_index: int | None = None
    execution_cost = Decimal("0")
    missed_entries = rejected_orders = forced_exits = exposed = 0

    for i, bar in enumerate(bars):
        new_segment = i == 0 or bar.segment != bars[i - 1].segment
        if new_segment:
            desired = False
            closes = []
        decision_price = Decimal(str(bars[i - 1].close if i else bar.open))
        decision_time_ns = bar.open_ms * 1_000_000

        if ledger.base_balance and not desired:
            order = OrderIntent(
                client_order_id=f"{scenario.scenario_id}:exit:{bar.open_ms}",
                side=Side.SELL,
                quantity=ledger.base_balance,
                decision_time_ns=decision_time_ns,
                decision_price=decision_price,
                kind=OrderKind.PROTECTIVE,
                protective=True,
            )
            result = simulate_candle_taker(
                order, Decimal(str(bar.open)), decision_time_ns, scenario, rules,
            )
            if result.status is not OrderStatus.FILLED:
                raise RuntimeError(f"protective exit failed in research simulator: {result.reason}")
            for fill in result.fills:
                ledger.apply_fill(fill)
            execution_cost += result.costs.total_quote
            pnl = ledger.quote_balance - (entry_equity or ledger.quote_balance)
            allocated = entry_allocated or Decimal("1")
            trades.append({
                "return_on_allocated": float(pnl / allocated),
                "pnl_quote": float(pnl),
                "holding_bars": i - (entry_index or i),
                "exit_ms": bar.open_ms,
                "forced_segment_exit": False,
            })
            entry_equity = entry_allocated = None
            entry_index = None

        if not ledger.base_balance and desired and not new_segment:
            equity = ledger.quote_balance
            budget = equity * position_fraction
            adverse_rate = (
                Decimal(str(bar.open))
                * (Decimal("1") + scenario.implicit_cost_bps_per_side / Decimal("10000"))
            )
            fee_factor = Decimal("1") + scenario.taker_fee_bps / Decimal("10000")
            requested_quantity = budget / (adverse_rate * fee_factor)
            order = OrderIntent(
                client_order_id=f"{scenario.scenario_id}:entry:{bar.open_ms}",
                side=Side.BUY,
                quantity=requested_quantity,
                decision_time_ns=decision_time_ns,
                decision_price=decision_price,
            )
            result = simulate_candle_taker(
                order, Decimal(str(bar.open)), decision_time_ns, scenario, rules,
            )
            if result.status is OrderStatus.FILLED:
                entry_equity = ledger.quote_balance
                entry_allocated = sum((fill.notional + fill.commission.quote_value for fill in result.fills), Decimal("0"))
                for fill in result.fills:
                    ledger.apply_fill(fill)
                execution_cost += result.costs.total_quote
                entry_index = i
            elif result.status is OrderStatus.EXPIRED:
                missed_entries += 1
            else:
                rejected_orders += 1

        closes.append(bar.close)
        equity = ledger.quote_balance + ledger.base_balance * Decimal(str(bar.close))
        exposed += int(bool(ledger.base_balance))
        peak = max(peak, equity)
        max_dd = min(max_dd, equity / peak - Decimal("1"))
        equity_series.append((bar.open_ms, equity))

        if len(closes) >= 30:
            fast = sum(closes[-10:]) / 10
            slow = sum(closes[-30:]) / 30
            if len(closes) == 30:
                desired = fast > slow
            else:
                fast_prev = sum(closes[-11:-1]) / 10
                slow_prev = sum(closes[-31:-1]) / 30
                if fast_prev <= slow_prev and fast > slow:
                    desired = True
                elif fast_prev >= slow_prev and fast < slow:
                    desired = False

        last_segment_bar = i + 1 == len(bars) or bars[i + 1].segment != bar.segment
        if ledger.base_balance and last_segment_bar:
            order = OrderIntent(
                client_order_id=f"{scenario.scenario_id}:forced-exit:{bar.open_ms}",
                side=Side.SELL,
                quantity=ledger.base_balance,
                decision_time_ns=(bar.open_ms + FOUR_HOURS_MS) * 1_000_000,
                decision_price=Decimal(str(bar.close)),
                kind=OrderKind.PROTECTIVE,
                protective=True,
            )
            result = simulate_candle_taker(
                order, Decimal(str(bar.close)), order.decision_time_ns, scenario, rules,
            )
            if result.status is not OrderStatus.FILLED:
                raise RuntimeError(f"forced exit failed in research simulator: {result.reason}")
            for fill in result.fills:
                ledger.apply_fill(fill)
            execution_cost += result.costs.total_quote
            pnl = ledger.quote_balance - (entry_equity or ledger.quote_balance)
            allocated = entry_allocated or Decimal("1")
            trades.append({
                "return_on_allocated": float(pnl / allocated),
                "pnl_quote": float(pnl),
                "holding_bars": i - (entry_index or i) + 1,
                "exit_ms": bar.open_ms + FOUR_HOURS_MS,
                "forced_segment_exit": True,
            })
            forced_exits += 1
            desired = False
            entry_equity = entry_allocated = None
            entry_index = None
            equity_series[-1] = (bar.open_ms, ledger.quote_balance)
            max_dd = min(max_dd, ledger.quote_balance / peak - Decimal("1"))

    years: dict[str, float] = {}
    grouped: dict[int, list[Decimal]] = {}
    for timestamp, equity in equity_series:
        grouped.setdefault(datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc).year, []).append(equity)
    prior = Decimal("1000")
    for year in sorted(grouped):
        end = grouped[year][-1]
        years[str(year)] = float(end / prior - Decimal("1"))
        prior = end
    final_equity = ledger.quote_balance
    elapsed_years = (bars[-1].open_ms - bars[0].open_ms) / (365.2425 * 86_400_000)
    trade_returns = [trade["return_on_allocated"] for trade in trades]
    gains = sum(value for value in trade_returns if value > 0)
    losses = -sum(value for value in trade_returns if value < 0)
    return {
        "scenario_id": scenario.scenario_id,
        "scenario_sha256": scenario.checksum,
        "fee_bps_per_side": float(scenario.taker_fee_bps),
        "implicit_cost_bps_per_side": float(scenario.implicit_cost_bps_per_side),
        "round_trip_bps": float(2 * (scenario.taker_fee_bps + scenario.implicit_cost_bps_per_side)),
        "price_protection_bps": float(scenario.price_protection_bps),
        "position_fraction": float(position_fraction),
        "starting_equity": 1000.0,
        "ending_equity": float(final_equity),
        "return": float(final_equity / Decimal("1000") - Decimal("1")),
        "cagr": float((final_equity / Decimal("1000")) ** Decimal(str(1 / elapsed_years)) - Decimal("1")),
        "max_drawdown": float(max_dd),
        "trades": len(trades),
        "win_rate": sum(value > 0 for value in trade_returns) / len(trade_returns) if trades else None,
        "profit_factor": gains / losses if losses else None,
        "exposure": exposed / len(bars),
        "average_holding_bars": statistics.fmean(trade["holding_bars"] for trade in trades) if trades else None,
        "execution_cost_quote": float(execution_cost),
        "missed_entries_price_protection": missed_entries,
        "rejected_orders": rejected_orders,
        "forced_segment_exits": forced_exits,
        "year_returns": years,
        "market_rules_sha256": rules.checksum,
    }


def matched_buy_hold(bars: list[Bar], fee_bps: float, slippage_bps: float) -> dict:
    fee=fee_bps/10_000; slip=slippage_bps/10_000; equity=1.0; peak=1.0; max_dd=0.0; previous_segment=None; units=0.0
    for i,bar in enumerate(bars):
        if bar.segment!=previous_segment:
            if units: equity=units*bar.open*(1-slip)*(1-fee)
            units=equity*(1-fee)/(bar.open*(1+slip)); previous_segment=bar.segment
        mark=units*bar.close; peak=max(peak,mark); max_dd=min(max_dd,mark/peak-1)
        if i+1==len(bars) or bars[i+1].segment!=bar.segment:
            equity=units*bar.close*(1-slip)*(1-fee); units=0
    elapsed_years=(bars[-1].open_ms-bars[0].open_ms)/(365.2425*86_400_000)
    return {"return":equity-1,"cagr":equity**(1/elapsed_years)-1,"max_drawdown":max_dd}


def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument("--data",type=Path,required=True); parser.add_argument("--manifest",type=Path,required=True); parser.add_argument("--hypothesis",type=Path,required=True); parser.add_argument("--output",type=Path,required=True); parser.add_argument("--scenario-config",type=Path,default=Path("config/execution_scenarios.json"))
    args=parser.parse_args(); manifest=json.loads(args.manifest.read_text()); hypothesis=json.loads(args.hypothesis.read_text()); digest=hashlib.sha256(args.data.read_bytes()).hexdigest()
    if manifest.get("partition")!="development-2017-2025" or manifest.get("dataset_sha256")!=digest: parser.error("accepted development dataset required")
    if hypothesis.get("status")!="development_frozen" or hypothesis.get("pattern_id")!="btc-4h-sma-10-30-long-flat-v1": parser.error("frozen development hypothesis required")
    bars,discarded=load_4h(args.data); configured=load_scenarios(args.scenario_config)
    selected=("candle-primary-30bps-rt-v1","candle-stress-40bps-rt-v1","candle-severe-80bps-rt-v1")
    scenarios=[run_execution_scenario(bars,configured[name]) for name in selected]
    primary=scenarios[0]; stress=scenarios[1]; benchmark=matched_buy_hold(bars,10,5)
    gates={"primary_cagr_positive":primary["cagr"]>0,"stress_cagr_positive":stress["cagr"]>0,"primary_profit_factor_above_one":primary["profit_factor"] is not None and primary["profit_factor"]>1,"primary_drawdown_less_severe_than_matched_buy_hold":primary["max_drawdown"]>benchmark["max_drawdown"],"positive_calendar_years_minimum":sum(value>0 for value in primary["year_returns"].values())>=6}
    report={"study":"btc-4h-sma-10-30-long-flat-v1-execution-model-v1","development_dataset_sha256":digest,"bars_4h":len(bars),"discarded_5m_bars_at_segment_or_alignment_boundaries":discarded,"execution":"completed 4h signal; next available 4h-open/5m boundary; shared candle execution model","mandate":"retail-btc-spot-v2","scenarios":scenarios,"matched_buy_hold_primary_cost":benchmark,"development_gates":gates,"accepted_for_holdout":False,"gate_note":"legacy hypothesis had already failed its frozen calendar-consistency gate; execution rerun cannot reopen it","caveat":"development-only benchmark; candle data cannot support sub-second fill or maker claims"}
    args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n"); print(json.dumps(report,indent=2,sort_keys=True))


if __name__=="__main__": main()
