# BTC unified backtest engine E0 plan

Qualification ID: `btc-unified-backtest-engine-e0-v1`

Status: frozen specification; no engine implementation or market evaluation

Actionable arm: `no_trade`

## Purpose

E0 removes accounting ambiguity before another BTC strategy is tested. It defines one offline,
event-driven research ledger for BTC/USDT spot and BTCUSDT USD-M perpetual simulations. The engine
will later be shared by the fixed breakout/EWMA control, the safe carry benchmark and the rejected
multi-horizon trend reconstruction, but E0 does not rerun or change any of them.

The engine is an accounting tool, not an authority layer. Each run must also satisfy its applicable
spot, directional-perpetual or delta-neutral mandate. E0 cannot emit a production signal, order or
position and cannot connect to an exchange, database, message bus or active soak.

## Frozen design

### Time and causality

- All timestamps are timezone-aware UTC; intervals are half-open `[open_time, close_time)`.
- A decision may use only values whose `available_at` is no later than its decision timestamp.
- The canonical candle adapter fills an eligible rebalance at the exact next hourly open after the
  decision; if that boundary is absent or invalid it does not search forward for a better entry.
  More granular adapters may fill only at or after both decision time and simulated arrival time,
  and must freeze that convention in their run contract.
- At each timestamp the engine snapshots incoming positions, marks the opening gap, immediately
  tests observed liquidation at that open, processes a previously caused safety exit, applies
  funding owed by the incoming perpetual position and immediately retests liquidation, handles the
  eligible rebalance, then marks and margin-tests the remaining position through the interval.
- Funding ownership is determined from the position at `t-`; an exit or entry stamped at `t` cannot
  evade or acquire that funding payment.
- Unknown event order, duplicate events, missing mandatory data and cross-segment state fail closed.
  Prices, funding or rules are never interpolated.

### Accounting

State consists of Decimal quote cash, spot BTC inventory, isolated perpetual collateral, signed
perpetual BTC quantity, average entry, realized and unrealized PnL, accrued funding and separately
classified costs. Spot inventory may not be negative. Perpetual quantity is positive for long and
negative for short.

Every event must satisfy both identities, within the frozen Decimal quantum:

```text
NAV = quote cash + spot BTC * spot mark + valued third-fee-asset balances
      + isolated collateral + perpetual unrealized PnL - liabilities
delta NAV = spot price PnL + perpetual price PnL + funding - explicit costs
            - implicit costs + external cashflow
```

Research runs have zero external cashflow after initialization. Fills alter inventory and cash but
not pre-cost NAV. Reductions realize PnL; reversals are a close and a new open with costs and fill
records on both sides. Entry costs belong to the resulting episode so profit factor cannot omit
them. Funding is `-signed_perp_BTC * funding_mark * rate`: positive funding is paid by longs and
received by shorts.

A spot buy debits quote cash by fill notional and adds BTC; a sell performs the inverse. A linear
perpetual fill exchanges no notional: reductions move realized PnL into isolated collateral and
increases update signed quantity and average entry. Collateral allocation is an explicitly logged
internal transfer from quote cash and cannot change NAV. Perpetual fees, funding and realized PnL
are debited or credited to isolated collateral while it remains open. Funding owed by the `t-`
position after a same-timestamp ordinary exit has released collateral settles once to quote cash;
an observed liquidation before funding removes membership at and after that timestamp.

Balance fields and attribution memos are distinct: cumulative realized PnL, funding and costs are
never added to NAV a second time. Base-, quote- and third-asset fees mutate the corresponding
modelled balance exactly once; an unavailable fee balance or point-in-time conversion fails
closed. Missed quantity, opportunity cost and unused rounded notional are diagnostics and never
reduce equity.

### Execution and failure handling

- Every run reports the frozen 30/40/80-bps round-trip scenarios. Candle proxy implicit costs are
  separate debits and are never also embedded in fill price.
- Candle OHLC execution is all-or-none at the exact next open. Partial fills require either a
  synthetic fixture or a separately qualified point-in-time quote/L2 adapter.
- Orders are validated against their effective-dated rules before any state mutation. Rejected,
  expired, rounded, partial and unfilled quantities are retained.
- A two-leg intention is atomic economically. Any leg failure is followed by immediate simulated
  severe-cost neutralization of filled exposure; it is never treated as intended alpha.
- A missing bar forces exposed accounts to the first subsequent valid executable price under
  severe exit costs and then resets the segment. A missing funding event while a perpetual was
  exposed invalidates the affected evaluation; a later exit cannot manufacture the cashflow.
- Margin is tested after funding and fills and at the adverse intrabar extreme before the close.
  Unknown historical brackets cannot be presented as promotion evidence. Liquidation is never a
  stop or a zero-loss outcome.
- An observed opening or intrabar liquidation breach is terminal: close at that adverse observed
  mark, charge the effective liquidation fee, retain any deficit as a liability and invalidate the
  evaluation. A planning-buffer breach that remains above liquidation schedules a severe-cost
  exit at the next valid open.

### Required ledgers

The later engine must emit canonical, checksummed decision, order, fill, funding, hourly account,
closed-episode and run-summary ledgers. Each economic row carries experiment, scenario, timestamp,
source, rules and implementation lineage. Price PnL, funding, commissions/taxes, spread, slippage,
impact, missed quantity and neutralization costs remain separate.

The E2 oracle must consume canonical fixture/event JSON only and share no kernel, ledger,
execution, dataclass or metrics implementation. Static transitive-import checks and row-by-row
before/after state digest reconciliation are required; matching terminal NAV alone is insufficient.

### Controls

Every later strategy adapter must produce flat/no-trade, true partition-boundary buy-and-hold,
same-timestamp/same-exposure and materially simpler controls. Buy-and-hold must start at the first
tradable partition observation, not after the candidate's feature warm-up. Controls use identical
data, valuation, cost and partition conventions; a control may differ only where its definition
explicitly requires it.

## E0 gate

E0 passes only when:

1. the machine-readable contract is canonical JSON and all bound paths and digests verify;
2. every event phase, identity, rounding rule, failure state and output is unambiguous;
3. an independent reviewer can derive synthetic long, short, funding, reversal, partial-fill,
   gap and margin fixtures without adding assumptions;
4. the specification contains no strategy parameter, historical result or live authority; and
5. `no_trade` remains the only actionable arm.

E0 failure requires a new qualification ID if any economic or event-order semantic changes after
E1 implementation starts. Passing E0 permits only E1 synthetic kernel implementation, followed by
an E2 oracle that shares no accounting implementation code with the kernel. It does not
permit historical data access, result reconciliation, a paper observer or a new strategy test.

## Required phase sequence

```text
E0 frozen specification
  -> E1 Decimal accounting kernel on synthetic fixtures
  -> E2 separate oracle and exact reconciliation
  -> E3 shared metrics and controls
  -> E4 preserved historical-result reconciliation
  -> P0 zero-capital forward observers
  -> H1 separately frozen strategy hypothesis
```
