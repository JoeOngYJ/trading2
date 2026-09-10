# BTC backtest evidence scorecard result

Experiment ID: `btc-backtest-scorecard-v1`  
Decision: **infrastructure passed; no strategy accepted**  
Actionable arm: `no_trade`

## Result

The canonical offline scorecard and retrospective adapters pass their engineering gates. All three
supplemental audits remain `supplemental_evidence_insufficient`; no historical decision changed
and none is promotion evidence.

| Evidence | Net return | CAGR | Max DD | Conventional Sharpe | Dependence-adjusted Sharpe | 97.5% daily ES | Independent blocks | Trade cohorts |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Fixed 20/10 breakout, 30 bps | 16.94% | 2.26% | 4.83% | 0.884 | 0.739 | 0.410% | 183 | 67 |
| EWMA-scaled breakout, 30 bps | 18.75% | 2.48% | 3.15% | 1.112 | 0.896 | 0.322% | 183 | 67 |
| Positive-funding carry, 30 bps | 5.83% | 2.87% | 0.42% | 5.066 | 1.566 | 0.098% | 9 | 6 |

The carry runner reproduces every legacy headline metric exactly, including its former 5.292
Sharpe. The scorecard's 5.066 conventional value uses the newly frozen common 365.2425-day series
including the first marked day; the primary evidence statistic then falls to 1.566 after accounting
for the 84-day dependence horizon. Neither number repairs the evidence shortage.

## Why the current strategies do not advance

### Positive-funding carry

- Only six independent trades and nine non-overlapping 84-day blocks exist, versus minimums of 30
  and 24.
- The lower 95% paired mean-return bound versus always-on matched carry is negative.
- The best three trades produce 92.50% of all positive trade PnL.
- The original margin-shock and return-per-exposed-day gates remain failed.
- Historical family-trial completeness cannot be proven, so deflated Sharpe is unavailable and
  fails closed.

Funding itself remains a real positive cashflow in this sample. What failed is evidence that the
60/30-bps timing rule adds enough safe, repeatable value over simpler carry exposure.

### Fixed breakout

The series has enough time blocks and trades, survives severe costs, and its probabilistic Sharpe
versus zero exceeds 95%. It still fails as standalone alpha because its lower paired bound versus
segmented BTC participation is negative, its previously frozen random-timing percentile gate
failed, and the trend-family trial history is incomplete. This remains a development control.

### EWMA overlay

EWMA has the strongest risk-adjusted descriptive result of the three and preserves the frozen S2
risk improvements. It is correctly classified as a mandatory risk control, not an independent
forecast or accepted strategy arm. Its return cannot be counted as new alpha.

## Infrastructure delivered

- One deterministic metric engine with UTC daily sampling, conventional and long-run-variance
  Sharpe, PSR/DSR/MinTRL, drawdown duration/recovery, expected shortfall, rolling losses, trade
  concentration, costs, controls and layered gates.
- One conservative append-only trial registry; all retrospective family-completeness flags remain
  false rather than inferring unrecorded trials away.
- Portable scorecard, report and evidence manifests with strict JSON and SHA-256 digests.
- Legacy breakout/EWMA and carry adapters that reproduce frozen ledgers without changing strategy
  logic or historical artifacts.
- Context validation for scorecard contracts, trial history, outputs, isolation boundaries and
  `no_trade` safety.

No 2026 row, partial OB0 data, network, protected service, credential, order, regime model or
strategy parameter was accessed.

## Next permitted action

Do not tune carry v1 or add a regime filter to rescue it. The scorecard infrastructure is now ready
for future experiments. Any next BTC alpha must receive a new frozen hypothesis/experiment ID,
complete trial-family registration and role-specific controls before outcomes. A directional
perpetual long/short strategy would first require a separate research mandate; otherwise remain
within the existing spot long/flat boundary. EWMA stays mandatory for risk comparison.
