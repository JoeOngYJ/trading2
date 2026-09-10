# BTC Volatility-Expansion Development Result

Experiment: `btc-volatility-expansion-continuation-v1`  
Decision: **rejected before holdout**  
Evaluated: 2026-08-25  
Frozen hypothesis SHA-256:
`8b501d44a0f4b93baa998e0d41bf16661c6e0e76bbaed269caf60f2346b96f99`  
Development report SHA-256:
`4f119e7c9ca52e3823ba3547edbccd10ef90d57cf9be7df9d1d38f2dec2ac872`

## Outcome

The frozen hypothesis failed nine of ten development gates. It was rejected without
opening the January–July 2026 holdout.

The primary assumption was continuation after a positive 1h price/range/volume/taker-flow
expansion from compressed 4h volatility. The observed confirmation-period direction was
mostly the opposite: across 55 events in 2023–2025, mean raw next-24h log return was
**−31.67 bps**.

| Year | Events | Mean raw next-24h return | Positive fraction |
|---|---:|---:|---:|
| 2023 | 9 | +50.26 bps | 44.4% |
| 2024 | 27 | −19.39 bps | 40.7% |
| 2025 | 19 | −87.94 bps | 31.6% |

The 2023 mean was positive but depended on only nine events and had a negative median.
The sign then reversed in both later confirmation years. This fails the predeclared
sample-size, per-year direction and 45 bps pooled economic gates before considering
execution.

## Executable results

All tests used 1,000 USDT normalized equity, the frozen sizing and stop rules, current
frozen Binance market filters, and the shared candle execution model.

| Cost scenario | Trades | Net return | Mean net trade | Profit factor | Max drawdown |
|---|---:|---:|---:|---:|---:|
| 30 bps primary | 55 | −6.31% | −0.450% | 0.55 | 8.09% |
| 40 bps stress | 55 | −7.53% | −0.549% | 0.49 | 8.92% |
| 80 bps severe | 43 | −9.54% | −0.933% | 0.35 | 10.32% |

The severe scenario stopped taking entries after crossing the frozen 10% strategy
drawdown limit, which is why it executed only 43 trades. In the primary case, 31 trades
hit the protective stop and 24 reached the 24h time exit. No primary entry was missed,
rejected, frequency-blocked or rejected by the stop-distance rule.

The UTC-day block-bootstrap 95% interval for primary mean net trade return was
approximately **−0.924% to +0.111%**, so it did not establish a positive edge. The primary
strategy lost money in all three confirmation years. The only gate that passed was
maximum drawdown at or below 10%.

## Robustness and benchmarks

None of the ten frozen one-at-a-time perturbations had a positive primary-cost mean.
Their net results ranged from approximately −4.25% to −7.12%. This makes the rejection
less likely to be an accident of one exact threshold.

For context, a 25%-allocation buy-and-hold benchmark returned approximately +107.21%
during 2023–2025 but experienced 25.66% maximum drawdown. The strategy therefore reduced
drawdown by staying mostly flat, but did so while losing money; that is not useful risk
control. The existing SMA 10/30 control was already separately rejected for instability
and is not reopened by this comparison.

## Interpretation and boundary

This result rejects only the exact **post-expansion continuation** rule. It does not prove
that compression, taker flow or volatility information is useless. The evidence suggests
that buying after the full positive expansion candle is late: 2024–2025 behaved more like
exhaustion/reversal than continuation.

Do not invert this into a short strategy: shorts are outside the retail mandate, and that
would be a new data-derived hypothesis. A future long/flat candidate could test waiting
for a pullback and causal reclaim after expansion, or use extreme expansion as a no-entry
veto. Either requires a new experiment ID, a newly frozen rule and explicit protection
against tuning to these now-observed development results.

The complete machine report is
[`btc-volatility-expansion-development-report.json`](../artifacts/agent-level-experiment/btc-volatility-expansion/btc-volatility-expansion-development-report.json).
The evaluator is
[`evaluate_btc_volatility_expansion.py`](../scripts/evaluate_btc_volatility_expansion.py).
