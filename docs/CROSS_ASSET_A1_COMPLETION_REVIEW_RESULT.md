# Cross-Asset A1 Completion Review v1 Result

Reviewed: 2026-08-29 22:35 UTC  
Experiment: `cross-asset-a1-completion-review-v1`  
Decision: **A1 remains blocked; A2 is not permitted**

## Result

The frozen review tested the four gates left after the Twelve Data v3 source recovery. It used
current official public documents and the checksummed recovery artifacts only. It computed no
returns, PnL, features, forecasts or strategy signals.

| Gate | Result | Reason |
| --- | --- | --- |
| Archival use | **Failed** | Twelve Data permits personal/internal use during the subscription, but its current Terms sections 12.5 and 16 require all Data to be deleted after termination or expiration. No written retention exception is on file. |
| Corporate actions | **Incomplete** | Thirteen visible issuer distribution samples match provider dates and amounts within frozen precision. EFA is rounded to three decimals. The BIL reverse-split date is independently confirmed, but its ratio and the complete 2008–2025 action histories for all funds remain unreconciled. |
| Executable mapping | **Failed** | The accepted histories are US-listed funds. IBKR states that UK-retail clients cannot purchase US ETFs without an available PRIIPs KID; Trading 212 public catalog pages are not account-specific approval. The London UCITS/ETC candidates are different instruments with no qualified same-line history. |
| Cost model | **Incomplete** | Current public fees were recorded, but no cost model can bind to an unselected execution line. Spread, slippage, rejection and partial-fill evidence is still absent. |

Public fee evidence records Trading 212 Invest/ISA trading and custody commission as zero, an FX
conversion fee of 0.15%, and no stamp duty on ETFs. IBKR UK publishes a 0.05% tiered rate with a
GBP 1 minimum and a 0.05% fixed SmartRouted rate with a GBP 3 minimum for UK stocks/ETFs. These
are planning inputs, not an approved execution model.

The Twelve Data data is technically useful while the subscription remains active, but it does not
meet this program's durable, reproducible archival-data gate under the public agreement. Do not
assume cancellation leaves a right to retain the raw or normalized files.

## Next permitted actions

1. Ask Twelve Data for a written amendment permitting indefinite private retention and use of
   already acquired raw and derived data after cancellation. Their public Terms are not enough.
2. Select the actual UK-retail broker and exact cash trading lines, then run a separately authorized
   read-only account metadata check. Public catalog pages cannot replace this check.
3. Qualify history, corporate actions and effective-dated costs for those exact trading lines.

If Twelve Data does not grant the written retention right, replace it as the durable source. Do not
start A2 using an economic proxy and later pretend it is the executable instrument.

Suggested provider request:

> Please confirm in writing whether an Individual Grow subscriber may indefinitely retain and use,
> solely for private non-commercial research, raw API responses and derived datasets acquired while
> the subscription was active after the subscription ends. If yes, please identify the agreement
> term that overrides sections 12.5 and 16 of the public Terms for this account.

## Evidence

- Contract: `config/experiments/cross-asset-a1-completion-review-v1.json`
- Source facts: `artifacts/agent-level-experiment/cross-asset/a1-completion-review-v1/source-facts.json`
- Audit: `artifacts/agent-level-experiment/cross-asset/a1-completion-review-v1/audit-report.json`
- Manifest: `artifacts/agent-level-experiment/cross-asset/a1-completion-review-v1/evidence-manifest.json`

Official sources include the [Twelve Data Terms](https://twelvedata.com/terms),
[IBKR PRIIPs guidance](https://www.interactivebrokers.com/campus/trading-lessons/trading-overseas-with-ibkr/),
[Trading 212 fees](https://helpcentre.trading212.com/hc/en-us/articles/11471996799517-What-are-the-fees-in-the-Invest-ISAs-and-SIPP),
[Trading 212 FX fees](https://helpcentre.trading212.com/hc/en-us/articles/360018909758-What-is-the-FX-fee-Invest-Stocks-ISA),
and [IBKR UK commissions](https://www.interactivebrokers.co.uk/en/pricing/commissions-stocks.php).
