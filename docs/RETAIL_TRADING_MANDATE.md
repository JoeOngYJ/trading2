# Retail BTC Trading Mandate

Mandate ID: `retail-btc-spot-v2`  
Effective: 2026-08-25  
Status: **frozen for research and dry-run only**  
Machine-readable source: [`../config/retail_mandate.json`](../config/retail_mandate.json)  
Supersedes: `config/mandates/retail-btc-spot-v1.json`

## Authority boundary

This mandate permits research, backtesting, shadow evaluation, and dry-run work. It does
not permit exchange credentials, order submission, or live funds. Maximum live allocation
is therefore **0 USDT**. A later live proposal must name the execution venue, absolute
capital cap, applicable jurisdiction/account, and separately receive written approval.

Binance is frozen as the **research data venue** because the accepted datasets and current
contracts use Binance spot. This does not assume that Binance will be the eventual live
execution venue. Venue eligibility, exact fee tier, and account-specific restrictions are
part of the deferred cost/execution research.

## Frozen scope

| Decision | Mandate |
|---|---|
| Instrument | BTC/USDT only |
| Market | Spot only |
| Direction | Long or flat |
| Research venue | Binance spot |
| Live venue | Not selected or authorized |
| Prohibited | Shorts, borrowing, margin, leverage, derivatives, options and market making |
| Strategy clock | 4h context, 1h decisions, completed candles only |
| Hosting | Local host for research; always-on host required for unattended paper/live |

ETH may remain in infrastructure fixtures and source-contract tests, but it is outside
this mandate and must not become a traded strategy instrument without a new mandate ID.

## Capital and risk limits

The normalized research and dry-run equity is **1,000 USDT**. This is an accounting unit,
not permission to fund an account.

| Limit | Value | Required response |
|---|---:|---|
| Maximum position allocation | 25% of current equity | Reject or resize a larger entry |
| Maximum planned risk per trade | 0.5% of current equity | Reject an entry that cannot fit the stop and size constraint |
| Daily loss stop | 1.5% from UTC-day starting equity | Disable new entries; protective exits stay active |
| Strategy drawdown stop | 10% from high-water equity | Disable new entries and require manual review |
| Concurrent positions | 1 | Reject additional entries |
| Maximum live allocation | 0 USDT | Live trading prohibited |

Daily loss and drawdown include realized and unrealized P&L. A stop breach may never
disable an exit or exchange-side protection.

## Cadence limits

- At most one new entry per UTC day and four new entries in any rolling seven days.
- Decisions occur only after a completed 1h candle. A 4h context value becomes visible
  only after that 4h candle closes.
- A position may remain open for no more than 336 hours (14 days); the eventual strategy
  may impose a shorter time-stop.
- Retries, partial fills, and order replacements belong to one entry decision and may not
  be counted as permission to create additional exposure.

These are upper bounds, not trade targets. No-trade periods are valid and expected.

## Execution safety policy

The research execution policy is frozen in
[`EXECUTION_COST_MODEL.md`](EXECUTION_COST_MODEL.md):

- entries must use price-bounded orders and may not chase an unbounded market price;
- maker execution is allowed only with a defined fill deadline;
- a taker fallback is allowed only if predeclared by the strategy and still inside its
  price-protection bound;
- at the deadline, cancel the unfilled remainder rather than silently increasing exposure;
- protective exits take priority over fee or maker optimization and may cross the spread;
- entry controls, stale signals, daily stops, and kill switches must never block a
  protective exit.

The primary research assumption is a price-protected taker model with a 10 bps entry cap,
10 bps commission per fill, and 30 bps total round-trip primary friction. A 60-second maker
timeout and 100/250/500/1,000 ms L2 latency sensitivities are frozen for secondary tests.
Exact account fees and forward fill calibration remain pending; this research model does
not authorize live execution.

## Change control

Changing the venue, market type, pair universe, long/flat restriction, capital or risk
limits, cadence, or execution policy requires a new mandate ID and a new evaluation. A
configuration file does not override this document merely because it contains broader
defaults.
