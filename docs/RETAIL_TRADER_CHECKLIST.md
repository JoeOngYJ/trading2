# Individual-Trader Delivery Checklist

Last reviewed: 2026-08-25

## Decision

This is the priority checklist for an individual trader. Institutional-scale historical
L2 purchases, many simultaneous strategies, cross-venue HFT, and complex agent models are
not current requirements.

The order book is a background feasibility experiment and, if useful, an execution or
adverse-selection filter. It must not block development of one slower, retail-executable
BTC strategy. It must also not be treated as proven alpha merely because the capture is
technically valid.

## Running in the background — do not disturb

- **24-hour reliability soak:** running under Docker supervision; latest review showed
  23/23 matrices passing and zero failures. Its owning session must perform final
  acceptance.
- **Seven-day BTCUSDT L2 OB0:** replacement capture
  `btc-l2-20260825T194700Z-c924306b` is running as a persistent, sleep-inhibited user
  service with a persistent watcher. It validates data quality only. Do not inspect
  partial predictive relationships.

Neither background process requires a second strategy or a paid dataset now.

## Work now — one active hands-on track

### 1. Freeze the retail trading mandate — complete for research

The research-only mandate is frozen as `retail-btc-spot-v2`; see
[`RETAIL_TRADING_MANDATE.md`](RETAIL_TRADING_MANDATE.md) and
`config/retail_mandate.json`. It authorizes no live funds or credentials. The exact live
venue, account fee response, and forward-fill calibration remain intentionally pending;
the conservative research scenario grid is now frozen.

Frozen values: BTC/USDT spot long/flat, Binance research data, normalized 1,000 USDT
research equity, maximum 25% position allocation, 0.5% risk per trade, 1.5% daily loss
stop, 10% strategy drawdown stop, one position, at most one new entry per day/four per
rolling week, and 4h context with 1h completed-candle decisions. The local workstation is
research-only; unattended paper or live operation requires an always-on host. Live
allocation remains zero.

### 2. Research and implement the realistic retail cost and execution model — v1 complete

The venue-neutral model and Binance adapter are implemented; see
[`EXECUTION_COST_MODEL.md`](EXECUTION_COST_MODEL.md). Account-specific fee and forward-fill
calibration remain pending. The model supports:

- maker/taker fees per side;
- observed or conservative bid/ask spread;
- quantity-dependent slippage/depth walk;
- 100/250/500/1,000 ms latency scenarios;
- maker non-fill, partial fill, timeout, cancel latency, and taker fallback;
- minimum order/notional and price/quantity rounding;
- outages, stale data, rejected orders, and missed entries;
- turnover and total cost attribution.

Keep the frozen 30/40/80 bps round-trip research cases even after the actual fee tier is
known. Gross profitability is never promotion evidence.

### 3. Specify and test exactly one slower BTC strategy — rejected

The candidate was frozen as `btc-volatility-expansion-continuation-v1`; see
[`BTC_VOLATILITY_EXPANSION_HYPOTHESIS.md`](BTC_VOLATILITY_EXPANSION_HYPOTHESIS.md). It is a
4h volatility-compression to positive 1h expansion test. Its development result is now
documented in
[`BTC_VOLATILITY_EXPANSION_DEVELOPMENT_RESULT.md`](BTC_VOLATILITY_EXPANSION_DEVELOPMENT_RESULT.md):
it failed nine of ten gates and is not an approved strategy. Its contract fixed:

- 4h context and 1h decisions;
- completed candles only;
- price structure, volatility state, range expansion/compression, and volume/trade-flow
  measurements may be primary inputs;
- moving averages, RSI, MACD, and ADX are controls only, not required signals;
- L2 may later be compared as an optional entry filter, never made mandatory before OB1;
- deterministic entry, exit, sizing, stop, 24h time-stop, and no-trade semantics;
- 30/40/80 bps execution cases and predeclared development/holdout rejection gates.

Do not run breakout, pullback, mean-reversion, news, ETH, and agent variants together.
Create one experiment ID and one falsifiable hypothesis.

### 4. Run timestamp-safe development and walk-forward evaluation — complete for rejected candidate

- use existing checksummed archives and accepted development segments;
- keep the January–July 2026 holdout sealed until parameters and code are frozen;
- compare against buy-and-hold, flat, and a transparent lagging-indicator control;
- report net return, turnover, exposure, trade count, drawdown, profit factor,
  Sharpe/Sortino, cost paid, and results by UTC period and regime;
- use day/block bootstrap intervals and parameter perturbation;
- reject candidates dependent on one month, regime, or small set of trades.

The frozen candidate was evaluated deterministically on 2023–2025 confirmation data and
rejected. The complete report includes monthly and volatility-regime attribution,
cost-component accounting, a UTC-day bootstrap and all ten frozen perturbations. Because
the development gates failed, the 2026 holdout remains sealed.

### 5. Prove operational use without money

In required order:

1. complete the active 24-hour reliability soak and approve recovery p95/p99;
2. perform an off-host backup and clean-host restore drill—having a runbook is not proof;
3. deploy alert routing and rehearse automatic/manual kill switches;
4. create a read/trade-only exchange key with withdrawals disabled and restricted network
   access where supported, but keep it out of the platform until the preceding gates pass;
5. run a timestamp-safe real-data shadow with all entries disabled;
6. run end-to-end Freqtrade dry-run and reconcile every signal, intent, order, fill, and
   exit;
7. paper trade for at least two weeks through different market conditions;
8. consider tightly limited live capital only after written sign-off.

## Explicitly deferred

- buying Tardis, Kaiko, or another institutional dataset before free OB0 evidence;
- collecting 90 local days while preventing a personal workstation from sleeping;
- additional strategy families or large parameter searches;
- news/sentiment and BTC/ETH cross-impact joins;
- LLM/agent output as a primary trading signal;
- leverage, derivatives, shorts, market making, and sub-second standalone trading;
- live exchange credentials or funds.

## Current gates

| Gate | State | Next evidence |
|---|---|---|
| Reliability 24h soak | Running elsewhere | Completion marker, zero failures, resource growth, recovery p95/p99 |
| BTC L2 OB0 | Running in background | Seven-day checksums, deterministic double replay, coverage decision |
| Retail mandate | **Frozen for research** | `retail-btc-spot-v2`; live allocation remains zero |
| Realistic cost model | **V1 implemented; calibration pending** | Shared candle/L2/maker model, scenario grid and current Binance rules snapshot |
| One slower BTC specification | **Tested and rejected** | −31.67 bps pooled raw 24h mean; −6.31% net at 30 bps; 0/10 positive sensitivities; keep 2026 sealed |
| Clean-host recovery proof | Open | Recorded RPO/RTO drill on an isolated host |
| Real-data shadow | Not started | Timestamp-safe, no-entry evidence lineage |
| Freqtrade dry-run | Not started | Reconciled signal-to-exit trace |
| Paper/live | Not approved | Two-week paper evidence, then separate limited-capital approval |

## Definition of success

For an individual trader, success is not the most sophisticated signal. It is one simple,
reproducible strategy whose modest edge survives actual retail costs and drawdowns, runs
fail-closed, can be restored, and can be stopped immediately without risking withdrawals
or unmanaged positions.
