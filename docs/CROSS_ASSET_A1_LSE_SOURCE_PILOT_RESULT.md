# Cross-Asset A1 LSE Source Pilot Result

Pilot ID: `cross-asset-a1-lse-source-pilot-v1`  
Decision: **candidate price source rejected; A1 blocked**  
Strategy evaluation: **not performed**

## Frozen question

Could official issuer identity pages plus four free Stooq daily CSV requests for 2–31 January
2025 qualify exact GBP London Stock Exchange lines for later full-history acquisition, without
computing any return, signal or PnL?

The exact research-mapped set was SWDA (global equity), VAGS (GBP-hedged global aggregate
bonds), SGLN (physical gold) and COMM (broad commodity total-return swap), plus conservative
zero-yield GBP cash. The listed-instrument pilot required exactly 22 expected LSE sessions.

## Result

All four official issuer pages contained the frozen ticker, ISIN, SEDOL and RIC, so exact
instrument identity passed. The official 2025 LSE calendar was also retrieved and checksummed.

The four Stooq URLs returned HTTP-success responses, but every 796-byte body was a JavaScript
proof-of-work browser challenge rather than a CSV. Consequently, zero instruments passed the
technical OHLCV gate. No CAPTCHA, proof-of-work, browser-session or anti-bot bypass was attempted.

Independently, the candidate remained unsuitable because the frozen evidence contained no
documented adjustment policy, corporate-action policy, end-of-day observation/availability
semantics or research-reuse terms. A CSV that happened to parse would not have repaired those
lineage defects.

## Disposition

- Reject `stooq-free-daily-csv-candidate` for the A1 full-history contract.
- Preserve the four exact issuer mappings as research candidates, not approved execution
  instruments.
- Keep A1 blocked with zero accepted market-price sources, zero accepted strategy arms and
  actionable output fixed to `no_trade`.
- Do not retry through a browser challenge, change suffixes, add a fallback vendor or expand the
  date range under this pilot ID.
- A new A1 experiment ID must freeze a source with documented price/corporate-action/timestamp
  semantics and lawful reproducible access. An official or licensed end-of-day source is the
  cleanest next candidate; it may be paid, but purchase is not authorized by this result.

## Reproduction

The original acquisition and audit are write-once and intentionally refuse to overwrite their
artifacts. Validate the preserved evidence and context instead:

```bash
.venv/bin/python scripts/validate_cross_asset_research_context.py
.venv/bin/pytest -q tests/test_cross_asset_program.py tests/test_cross_asset_data_audit.py
```

Evidence root:
`artifacts/agent-level-experiment/cross-asset/a1-lse-source-pilot-v1/`.

Checksums:

- contract: `3a1150fec3ec44cbf3e18706589231890e33892cce9713680410cb297588fd71`;
- source manifest: `1afa9e6f8c271bd37e67e97a9fc2af8e7a532e44222fdb9add62cb792032f1a6`;
- audit report: `5b533c9b0f64a1eee643cfb740679cefcbf84d556d5f4441237327464c8b9692`;
- evidence manifest: `740ef9be6d6208242e9eadb987dcc67363fbc5f8909f23296eb3a82700386b30`.
