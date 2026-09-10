# Retail Execution and Cost Model

Reviewed: 2026-08-25  
Implementation: `src/trading_platform/execution_model.py`  
Scenarios: `config/execution_scenarios.json`  
Active mandate: `retail-btc-spot-v2`

## Decision

The authoritative research model is a venue-neutral cash-and-inventory execution engine
with a Binance spot adapter. A price-protected taker order is the primary profitability
benchmark. Maker-then-taker execution is secondary and cannot rescue a strategy until
real queue, non-fill, adverse-selection, and opportunity-cost observations exist.

Freqtrade is retained for parity and dry-run tests, not as the authoritative historical
fill engine. Its candle backtester assumes an order fills at the requested price without
slippage when the price is inside the candle range. This repository therefore evaluates
costs independently and later compares the resulting trade stream with Freqtrade.

Primary references:

- [Binance spot filters](https://developers.binance.com/en/docs/products/spot/filters)
- [Binance spot order API](https://developers.binance.com/en/docs/catalog/core-trading-spot-trading/api/rest-api/trade)
- [Binance commission FAQ](https://developers.binance.com/en/docs/products/spot/faqs/commission_faq)
- [Binance REST failure semantics](https://developers.binance.com/en/docs/products/spot/rest-api)
- [CCXT precision and limits](https://github.com/ccxt/ccxt/wiki/manual)
- [Freqtrade backtesting assumptions](https://docs.freqtrade.io/en/latest/backtesting/)
- [Limit/market order tactics and opportunity cost](https://arxiv.org/abs/1409.1442)
- [Bitcoin market-impact evidence](https://arxiv.org/abs/1412.4503)

## Model layers

### Candle taker

This is the primary long-history model. Strategy decisions use completed 1h candles and
4h context; execution must use the first available underlying 5m observation. The data
cannot distinguish 100 ms from 1,000 ms, so the report must not claim sub-candle latency.

The frozen scenario grid is:

| Scenario | Fee/side | Composite implicit/side | Round trip | Promotion use |
|---|---:|---:|---:|---|
| Fees-only diagnostic | 10 bps | 0 bps | 20 bps | No |
| Primary | 10 bps | 5 bps | 30 bps | Yes |
| Stress | 10 bps | 10 bps | 40 bps | Yes |
| Severe | 20 bps | 20 bps | 80 bps | Yes |

Entries are price-protected. If the first executable price is outside the scenario cap,
the order expires and the missed entry is recorded. Protective exits ignore entry price
caps and remain available. Candle mode never awards a maker fill or maker fee.

### Quote/L2 taker

The simulator selects the first valid book at decision time plus the configured latency,
walks asks for buys or bids for sells, and stops at the protected limit. It reports spread,
depth impact, residual impact, partial quantity, and unfilled quantity separately. The
primary latency is 250 ms; 100, 500, and 1,000 ms are mandatory sensitivities.

Stale, crossed, empty, pre-arrival, wrong-segment, or gap-contaminated books are rejected.
The running OB0 data may be used only after its independent acceptance process completes.

### Maker hybrid

The secondary model places post-only at a declared price. Existing displayed quantity at
that level is queue ahead. Only qualifying opposite-aggressor trades reduce the queue;
cancellations are not assumed to improve our position. It supports partial fills, a
60-second timeout, fills during cancel latency, and a price-protected taker fallback.
Timeout sensitivities are 10, 30, and 120 seconds. Maker results are not promotion evidence
until calibrated against forward observations.

## Cost and accounting contract

Every fill updates a Decimal cash/inventory ledger. Fees are charged for each partial fill
and may be denominated in quote, base, or a third asset. The Binance response parser keeps
standard, special, and tax commissions and applies a BNB-style discount only when both
account and symbol flags permit it.

Every result separates:

- explicit commissions/taxes;
- decision-to-arrival delay;
- spread crossing;
- visible depth impact;
- residual impact/slippage;
- maker adverse selection after a fill;
- opportunity cost for missed quantity;
- rounding and dust.

Scenario, market-rule, input, and result checksums make runs reproducible. Account-specific
fees remain unknown, so the current primary model assumes 10 bps per fill without a BNB
discount. An authenticated commission lookup is allowed only after the security gates and
must not contain credentials in an artifact.

## Exchange and operational cases

The implementation or its test contract covers:

| Case | Required behavior |
|---|---|
| Tick/step or notional failure | Reject before simulated submission |
| Insufficient balance or fee asset | Reject atomically; do not mutate the ledger |
| Price moves beyond entry cap | Expire and count a missed entry |
| Insufficient protected depth | Partial fill and retain unfilled quantity |
| Maker touch without queue consumption | No fill |
| Maker partial then timeout | Protect only filled exposure; cancel remainder |
| Fill during cancel race | Accept fill until cancel acknowledgement |
| Timeout or HTTP 5xx | Mark state unknown and reconcile by client order ID before retry |
| 429/418, maintenance, clock/recvWindow failure | No blind retry; disable new entries and back off |
| Stale/gapped/crossed book | Reject the observation |
| Stop gap | Fill at the worse available opening price plus exit friction |
| Stop and target in one detail candle | Apply the stop first |
| Protective exit | Never blocked by entry caps, stale signals, or strategy kill state |
| Fee promotion/rule change | New effective-dated snapshot and scenario checksum |

## Current real-data evidence

The public, unauthenticated BTCUSDT rules snapshot at
`artifacts/real-data-research/BTCUSDT-market-rules-20260825.json` validates the adapter
against Binance's current response. It records a 0.01 USDT price tick, 0.00001 BTC quantity
step, and 5 USDT minimum notional at the observation time. These current rules must not be
silently projected backward as historical rules.

The development-only SMA benchmark was rerun through the shared candle model and saved as
`artifacts/agent-level-experiment/btc-taker-history/btc-4h-sma-10-30-execution-model-v1-report.json`.
At 25% maximum allocation it returned 114.9%, 97.5%, and 38.7% over the full development
period under 30, 40, and 80 bps round-trip scenarios. Maximum drawdowns were 29.1%, 30.7%,
and 36.6%. Only five of nine calendar slices were positive, so the strategy remains
rejected and the 2026 holdout remains sealed. Cost survival does not repair regime
instability.

## Remaining calibration

Before promotion, capture the exact account commission response, reconcile dry-run order
intentions against contemporaneous public quotes, and later compare approved real fills
against decision and arrival prices. Replace assumptions only with effective-dated evidence;
retain the conservative grid as stress tests.
