# A1 IBKR Contract-Details Public Review Result

Review: `cross-asset-a1-ibkr-contract-details-public-review-v1`  
Stage: A1 data/access foundation  
Decision: **partially resolved; A1 remains blocked**  
Observed: 2026-08-29 UTC

## Result

Official public material resolves the expected issuer identity and exact London listing for all
four candidates. The London Stock Exchange pages bind each ticker to its expected ISIN, `XLON`
primary MIC, and quote unit: SWDA/GBX, VAGS/GBP, SGLN/GBX and COMM/GBX. Interactive Brokers' UK
commission page groups `LSEETF` with `LSE` and `LSEIOB1` under Stock Exchange, resolving the venue
group used by the authenticated account result.

VAGS is therefore verified as the exact account line for identity purposes: the account result
matches symbol, name, Stock class, `LSEETF`, and `GBP`, while the issuer and LSE sources bind its
ISIN and `XLON` listing.

SWDA, SGLN and COMM remain `conditional_unapproved`. Their LSE pages use the ISO-style minor-unit
code `GBX`, whereas the IBKR account displayed `GBp`. LSE documentation confirms that GBX is a
minor currency corresponding to GBP, but this review found no allowed official source that
defines IBKR's literal `GBp` UI label or explicitly equates it with `GBX`. The frozen contract
forbids filling that gap by inference, even though the intended meaning appears economically
obvious.

This is an identity-only result. It approves no execution instrument, broker, strategy, order,
position, or live allocation. A1 remains blocked by the pending written Twelve Data retention
answer, incomplete full corporate-action reconciliation, absence of qualified same-line history,
and incomplete account-specific cost evidence.

## Official sources

- Interactive Brokers UK commissions: `LSE`, `LSEETF`, and `LSEIOB1` are grouped under Stock
  Exchange.
- London Stock Exchange company pages: exact ticker, ISIN, quote unit, and `XLON` primary MIC for
  SWDA, VAGS, SGLN and COMM.
- iShares product pages: SWDA, SGLN and COMM issuer identity, ISIN, and London ticker.
- Vanguard UK fund directory: VAGS ISIN, GBP listing, London Stock Exchange and exchange ticker.
- London Stock Exchange trade documentation: GBX is a minor currency corresponding to GBP; it
  does not define IBKR's `GBp` label.

No search-result snippet, quote, price, performance value, raw page snapshot, credential, account
identifier, balance, position, history, order preview, or order is retained in the evidence.

## Reproduce

From `/data/Trading`:

```bash
.venv/bin/python scripts/validate_cross_asset_research_context.py
.venv/bin/pytest -q tests/test_cross_asset_program.py
```

Artifacts:

- Contract: `config/experiments/cross-asset-a1-ibkr-contract-details-public-review-v1.json`
- Normalized source facts: `artifacts/agent-level-experiment/cross-asset/a1-ibkr-contract-details-public-review-v1/source-facts.json`
- Audit report: `artifacts/agent-level-experiment/cross-asset/a1-ibkr-contract-details-public-review-v1/audit-report.json`
- Evidence manifest: `artifacts/agent-level-experiment/cross-asset/a1-ibkr-contract-details-public-review-v1/evidence-manifest.json`
