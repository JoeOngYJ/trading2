# BTC market-condition scores MCS3-P result

Experiment ID: `btc-market-condition-scores-mcs3-p-v1`  
Decision: **rejected — seven-day signed directional efficiency did not add stable persistence information**  
Strategy, position, cost or PnL evidence: **none**  
Accepted strategy arms: **none**  
Actionable arm: `no_trade`

## Frozen question

Using only completed, same-segment four-hour BTC/USDT candles, does the directional coherence of
the prior 42 returns add information about the next seven-day log return after controlling for the
prior seven-day log return itself?

The candidate was fixed as signed directional efficiency,
`sum(return) / sum(abs(return))`. The benchmark was the same window's cumulative log return. Each
4h, 1d and 7d model was refitted at UTC month boundaries using only targets available strictly
before the cutoff. The 7d target was primary. No threshold, strategy action, trade, cost, position
or PnL was defined.

## Result

The primary seven-day candidate failed seven of the frozen information gates:

- Its walk-forward MSE was `0.0067977803`, 1.19% worse than the benchmark's `0.0067178288`.
- Its incremental OLS coefficient was `0.04530`, but the 42-lag Bartlett/Newey-West 95% interval
  was `[-0.02712, 0.11771]`; zero was not excluded.
- Pooled rank IC was `-0.04414`. The mean monthly rank IC was `-0.27703`, with month-block 95%
  interval `[-0.33944, -0.21258]`.
- The month-block interval for expanded-model squared-error improvement was
  `[-0.0003464, -0.0000027]`, entirely negative.
- Quintile forward-return means were not monotone: `1.43%`, `0.71%`, `0.06%`, `0.05%`, and
  `1.38%` from the lowest through highest causal score buckets.
- The monthly top-minus-bottom estimate was `-5.87%`, with interval
  `[-7.67%, -4.11%]` for months containing both extreme buckets.
- Only four of seven annual incremental coefficients were positive; 2021, 2024 and 2025 were
  negative. Leave-one-year-out pooled coefficients were positive, but this single passed
  stability diagnostic cannot override the failed annual and uncertainty gates.

Overall seven-day coverage was `88.94%`, below the frozen `90%` requirement. Per-year coverage
remained above the frozen `75%` floor, but lookback and forward windows correctly reset at source
segment boundaries. Four-hour and one-day coverage exceeded 93%. This is a real limitation of the
frozen segmented ledger for a 42-return feature plus 42-return target, not permission to bridge
gaps or relax the gate.

The secondary 4h and 1d diagnostics do not rescue the primary hypothesis. Their expanded-model
MSE changes were only -0.010% and -0.043% relative to the benchmark; month-block error-improvement
intervals crossed zero, rank-information intervals were negative, and score buckets were not
monotone. The 1d HAC coefficient barely excluded zero, but the other frozen diagnostics did not
confirm it.

## Interpretation

This rejects this exact signed-efficiency construction, window, benchmark, source and horizons.
It does not prove that BTC never trends. It shows that, in this development ledger, a smoother
completed seven-day path did not provide reliable incremental continuation information beyond the
completed seven-day return. The U-shaped bucket outcomes also warn against treating low
persistence as reversion: both extreme buckets had positive pooled returns while the middle was
near zero.

Do not tune the 42-bar window, horizon, score, buckets or model under this experiment ID, and do
not use a regime label to rescue the rejected breakout or SMA families. The score remains a
rejected control and is ineligible for strategy conditioning.

## Verification

- Seven focused tests pass, including checksum, timestamp, gap, segment, causal-fit, formula, HAC,
  bootstrap and import-isolation checks.
- The isolated replay produced byte-identical `report.json` and `forecasts.jsonl.gz` files.
- A preliminary run that incorrectly offset the single frozen bootstrap seed by horizon/metric is
  preserved under an `invalid-bootstrap-seed-offset` artifact path and is not final evidence. The
  corrected run uses exactly seed `20260831` for every frozen month-block bootstrap; its decision
  is unchanged.
- The report contains 14,394 four-hour, 14,289 one-day and 13,573 seven-day causal forecasts.
- No 2026 row, partial OB0 input, network, database, NATS, Freqtrade, exchange, protected service,
  production signal, order, position, cost or PnL was accessed or created.

## Next permitted action

Freeze MCS3-R under a new experiment ID before reading its outcomes. It must test a separately
defined completed-displacement unwind mechanism with matched controls, non-overlapping horizons
and cost break-even diagnostics. It is not the negative of this rejected persistence score and it
cannot become a strategy until it independently passes its information gates.
