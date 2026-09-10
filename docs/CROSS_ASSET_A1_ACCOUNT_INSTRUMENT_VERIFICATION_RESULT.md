# Cross-Asset A1 Account Instrument Verification v1 Result

Reviewed: 2026-08-29 23:15 UTC  
Experiment: `cross-asset-a1-account-instrument-verification-v1`  
Decision: **incomplete; A1 remains blocked and A2 is prohibited**

## Result

The user authorized authenticated, read-only searches in Trading 212 and IBKR for the four frozen
LSE candidates. The review retained only names, symbols, venue labels, displayed currencies,
cash-versus-derivative classifications and the presence of an order-entry control. It did not
retain quotes or prices and did not access balances, holdings, history, order previews or orders.

| Broker | Symbol | Authenticated result | Currency shown | Entry control | Missing frozen identity |
| --- | --- | --- | --- | --- | --- |
| Trading 212 Invest | SWDA | iShares Core MSCI World (Acc), LSE | Not exposed | Buy | ISIN, exact MIC, currency |
| Trading 212 Invest | VAGS | Vanguard Global Aggregate Bond (Acc), LSE | Not exposed | Buy | ISIN, exact MIC, currency |
| Trading 212 Invest | SGLN | iShares Physical Gold, LSE | Not exposed | Buy | ISIN, exact MIC, currency |
| Trading 212 Invest | COMM | No exact result | Not exposed | None | Entire exact line |
| IBKR Client Portal | SWDA | ISHARES CORE MSCI WORLD, LSEETF, Stock | GBp | Trade | ISIN, exact MIC |
| IBKR Client Portal | VAGS | VANG GLBAGG ETF GBP H ACC, LSEETF, Stock | GBP | Trade | ISIN, exact MIC |
| IBKR Client Portal | SGLN | ISHARES PHYSICAL GOLD ETC, LSEETF, Stock | GBp | Trade | ISIN, exact MIC |
| IBKR Client Portal | COMM | ISH DIVERS COMMOD SWAP ETF, LSEETF, Stock | GBp | Trade | ISIN, exact MIC |

Search presence and an entry control are not execution approval under the frozen contract. `GBp`
is also not silently rewritten to ISO `GBX`: that display normalization was not frozen before the
account result. Consequently, no exact trading line passes every required identity field.

IBKR is now the more complete execution candidate because all four frozen symbols appear as
LSEETF Stock results with a Trade control. This is a prioritization for the next metadata check,
not an approved broker or instrument. Trading 212 cannot support the frozen four-line universe
because COMM is absent. Replacing COMM with a different commodity fund would require a new
instrument decision, separately qualified history, actions and costs; it cannot be substituted
after observing this result under the current experiment ID.

The Twelve Data archival-retention request was sent through its signed-in support messenger and is
visible in the conversation. The archival gate remains failed while the response is pending;
silence is not permission.

## Next permitted action

1. Await and preserve Twelve Data's written response. A qualifying permission must explicitly
   survive subscription termination and cover retained raw and derived private-research data.
2. If continuing with IBKR, freeze a separate read-only contract-details check for the four exact
   contracts. It must establish ISIN, exact MIC and authoritative currency without placing or
   previewing an order.
3. Only after exact lines are resolved may A1 qualify same-line history, corporate actions and an
   effective-dated cost model.

Do not start A2, substitute a commodity product, calculate returns, fit a strategy, open sealed
2026 data, inspect partial OB0 or access the protected soak stack.

## Evidence

- Contract: `config/experiments/cross-asset-a1-account-instrument-verification-v1.json`
- Observations: `artifacts/agent-level-experiment/cross-asset/a1-account-instrument-verification-v1/account-observations.json`
- Audit: `artifacts/agent-level-experiment/cross-asset/a1-account-instrument-verification-v1/audit-report.json`
- Manifest: `artifacts/agent-level-experiment/cross-asset/a1-account-instrument-verification-v1/evidence-manifest.json`
- Provider-request progress: `artifacts/agent-level-experiment/cross-asset/a1-account-instrument-verification-v1/progress-record.json`
