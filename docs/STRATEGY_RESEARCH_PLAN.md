# Strategy Research Plan

> **Status: superseded as the active roadmap (2026-08-25).** This file preserves the
> earlier experiment design for reference. Do not launch its multi-strategy matrix now.
> Follow [`RETAIL_TRADER_CHECKLIST.md`](RETAIL_TRADER_CHECKLIST.md): freeze the retail
> mandate and cost model first, then select exactly one slower BTC spot hypothesis.

## Focus workstream: causal BTC prediction -> breakout entries

This is the only strategy family to implement first. It is long/flat initially and uses
completed candles only. The primary signal must not depend on moving averages, RSI, MACD,
ADX, or another lagging indicator. Those indicators may be run as diagnostic controls,
but are not part of the preferred strategy.

### Formal specification

**Context (4h):** calculate on closed 4h bars using causal returns, volatility, range,
volume, BTC/ETH relative movement, and verified event data. The initial candidates are:

1. Positive persistence when recent BTC returns and range expansion are positive.
2. Negative or defensive state when realized volatility expands against BTC.
3. Range/transition state when return persistence and range expansion disagree.

The context is allowed to change only at a 4h close. Between 4h closes, the previous
state is carried forward. No resampling may use future 4h OHLC values.

**Entry (1h):** test one simple rule at a time:

1. SMA(30)/SMA(100) crossover, next 1h open.
2. Breakout above a rolling 20-bar high, next 1h open.
3. Pullback to EMA(20) while the 4h regime is trend-up.

Only one entry family is active per experiment. Exits are tested separately: opposite
signal, ATR stop, trailing stop, and time stop. Position sizing is fixed-risk or fixed
notional during the first comparison so the signal quality is isolated.

### Controlled experiments

| ID | Regime | Entry | Purpose |
|---|---|---|---|
| MTF-01 | None | 1h SMA crossover | Control |
| MTF-02 | 4h trend | 1h SMA crossover | Primary candidate |
| MTF-03 | 4h trend | 1h breakout | Entry robustness |
| MTF-04 | 4h trend | 1h pullback | Lower-turnover alternative |
| MTF-05 | 1d trend | 4h SMA crossover | Slower control |
| MTF-06 | 4h trend | 5m entry | Cost and noise stress test only |

Run BTCUSDT and ETHUSDT separately. Keep the same date splits, fee/slippage assumptions,
execution convention, and initial capital across all IDs. Do not select parameters on the
final test period.

### Required evaluation

Every run must report net return, annualized volatility, Sharpe and Sortino, maximum and
average drawdown, profit factor, win rate, turnover, trade count, average holding period,
cost paid, exposure, and results split by trend-up, trend-down, range/transition, and high
volatility. Include buy-and-hold and flat controls.

Test cost scenarios at minimum: 5/1, 10/2, 20/5, 30/10, and 50/20 basis points for
fee/slippage per side. Later add spread, impact, latency, and partial-fill assumptions.

### Validation gates

1. Timestamp and lookahead tests pass, including 4h boundary cases.
2. Parameters are frozen before the unseen test period.
3. Walk-forward results are positive after costs across both symbols or clearly explain
   why the strategy is symbol-specific.
4. No single month, regime, or small set of trades explains nearly all performance.
5. Perturbing periods and parameters does not destroy the result.
6. The strategy beats its 1h control on the chosen objective, not merely gross return.

## Later strategy families

These are deliberately deferred until the focused workstream is complete:

1. Pure trend following at 4h/1d.
2. Breakout with volatility and volume filters.
3. Mean reversion in a confirmed range regime.
4. Cross-sectional BTC/ETH relative-strength rotation.
5. Volatility-targeted portfolio allocation.
6. News/social overlays as a trade filter, never as an unvalidated primary signal.
7. Agent-assisted ranking after timestamp-safe agent captures exist.

Each family must have its own experiment IDs, controls, costs, and walk-forward report. A
new family cannot be combined with the focused strategy until the individual components
have passed standalone validation; this prevents attribution and overfitting problems.

## Methodology research: entry families

### 1. Moving-average crossover

Test fast/slow pairs such as 10/30, 20/50, and 30/100 on the 1h entry series. A signal
must be generated at the close and executed at the next bar open. Add a confirmation
variant requiring two closes beyond the crossover, and a hysteresis variant that exits
only after a minimum distance or opposite crossover. These reduce whipsaw at the cost of
later entries. Do not test dozens of nearby windows; the 1h standalone control must use
the same small, predeclared set.

Expected strengths: simple, auditable, naturally aligned with a 4h trend regime, and
usually low conceptual complexity. Expected weaknesses: lag, repeated losses in ranges,
and sensitivity to costs when the fast average is short. Crypto studies of moving-average
and breakout rules find results vary materially by asset, timeframe, bubbles, and costs
([technical-rules study](https://www.sciencedirect.com/science/article/pii/S1042443122000816)).

### 2. Breakout

Test a Donchian/channel close above the prior 20, 40, or 60 completed 1h bars. The
breakout level must exclude the current bar. Compare close-confirmed entry with a next-bar
stop order using a conservative fill assumption. Add an ATR buffer (for example 0.1–0.25
ATR) and a volume/relative-volume filter only as separate variants. Exits should include
an opposite channel break and an ATR trailing stop.

Expected strengths: captures persistent crypto expansions and can have positive skew with
few large winners. Expected weaknesses: false breakouts, gap/fast-market slippage, and
high sensitivity to the exact fill model. Published Bitcoin evidence reports that channel
breakout rules can outperform buy-and-hold in strongly trending periods, while explicitly
calling for transaction-cost testing ([Gerritsen et al.](https://dirkgerritsen.nl/uploads/gerritsen_et_al_2020_bitcoin_trading_rules.pdf)).

### 3. Pullback / continuation

Only test pullbacks while the 4h regime is trend-up. Candidate definitions are: price
touches or closes below 1h EMA(20), RSI(2) or RSI(5) is temporarily weak, and price closes
back above the short EMA; or a retracement of 0.5–1.0 ATR followed by a bullish close.
Entry is next 1h open. Test a fixed ATR stop, recent swing-low stop, and a time stop. A
failed pullback that breaks the regime's 4h structure should cancel the setup.

Expected strengths: better entry price, smaller initial stop, and potentially lower
turnover than chasing breakouts. Expected weaknesses: buying temporary weakness during a
real trend failure, many subjective-looking parameters, and poorer performance when trends
accelerate without retracing. Bollinger-band research on BTC/USDT finds breakout versus
mean-reversion interpretations are regime- and volatility-dependent
([SSR​​N study](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5775962)).

### Decision rule for this project

Implement crossover first as the transparent control, breakout second as the asymmetric
trend alternative, and pullback third as the lower-turnover alternative. Promote none on
gross return alone. The winning method must improve the predefined net objective after
costs, reduce or justify drawdown, remain stable across BTC and ETH, and pass walk-forward
and parameter-perturbation tests.

## Immediate implementation order

1. Build a lookahead-safe multi-timeframe feature/label harness.
2. Implement MTF-01 and MTF-02 first.
3. Add MTF-03 and MTF-04 only after the controls run reproducibly.
4. Add full cost scenarios and regime attribution.
5. Run walk-forward and unseen-period validation.
6. Record the decision in `docs/RESEARCH_TRACKER.md` before adding another strategy family.
