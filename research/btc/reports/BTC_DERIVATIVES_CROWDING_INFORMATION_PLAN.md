# BTC derivatives-crowding information experiment

Experiment ID: `btc-derivatives-crowding-information-v1`  
Status: frozen before forward-outcome evaluation  
Scope: offline information research only; `actionable_arm_id = no_trade`

## Economic mechanism

Leverage can become fragile at either a crowded long or crowded short extreme. This experiment
therefore does not assume that a high funding rate, wide basis, or leveraged-money net short is a
directional BTC signal. It asks the narrower question: do unusually extreme derivatives conditions
forecast more seven-day realized variance and downside path loss than causal price-only risk
information already does?

The single primary feature is the mean absolute, past-only z-score of completed-day Binance
funding, completed-day Binance perpetual basis, and the last conservatively available CME Bitcoin
leveraged-money net share. Funding and basis use trailing 90-observation normalization; CFTC uses
52 reports. Every normalization excludes the current observation.

## Causality and boundary

- Decisions are at 00:00 UTC.
- Funding must contain exactly three regular events in the preceding UTC day.
- A basis row timestamped on day D is delayed to D+1.
- A Tuesday CFTC report is unavailable until Saturday 00:00 UTC.
- BTC daily closes are used only after the following UTC midnight.
- Development is 2020-01-01 through 2023-12-31.
- No 2024–2025 numeric BTC row may be deserialized; 2026 remains excluded.

## Test and disposition

A monthly expanding walk-forward regression compares EWMA variance plus absolute seven-day
momentum with the exact same model plus crowding intensity. Training labels receive a seven-day
embargo. Separately, high- and low-crowding groups use expanding past-only quintiles. Month-block
bootstrap intervals, observation/month coverage, two risk-separation tests, and at least 2% OOS
forecast-error improvement are all mandatory.

Failure preserves a useful negative result and closes this exact mechanism. Passing permits only a
separately frozen strategy or downward-only risk-overlay experiment. It does not approve a signal,
position, strategy arm, leverage, derivatives trading, or use of the locked partitions.
