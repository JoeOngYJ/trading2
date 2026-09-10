# Independent A0 synthetic execution review

Reviewer: wide_review independent agent. Date: 2026-09-08.
Verdict: all three source-audit findings independently reproduced. Stop before
corrected historical replay pending a frozen execution correction specification.

Read only the A0 contract, synthetic script and relevant legacy source. Ran
`PYTHONPATH=src python3 research/btc/audit_breakout_execution_a0.py` successfully.
No market candles, archived trade files or replay result data were opened. No
legacy implementation was edited.

1. **Material chronology defect.** The previously scheduled next-open exit at
   110 is displaced by the same candle's low95, producing stop96. Source checks
   the entire candle low before processing scheduled open exits. Under the
   stipulated next-open execution convention, the position already exited before
   a later low. Maximum-holding exits have the same source-order concern, although
   this probe tests the channel exit. A stop breached at the opening price needs
   an explicitly frozen simultaneous-event rule; that is not this example.
2. **Material timestamp mismatch.** The segment-end close105 is returned with its
   candle index and `simulate` writes that candle's opening timestamp as exit_ms.
   In the five-minute fixture the close is available at300000 ms, versus the
   recorded0 ms. This can affect duration and point-in-time attribution. Intrabar
   stop events likewise have only bar-level time resolution; exact touch time
   cannot be inferred from OHLC data.
3. **Material boundary-policy problem.** Changing only the third bar's segment
   label moves the earlier exit from index2/close110 to index1/close105. This is
   retrospective boundary dependence. A predeclared terminal valuation may be
   legitimate, but an unexpected later data gap cannot authorize a realizable
   prior-close sale. Report or censor such boundary-affected paths under an
   explicit policy; do not silently treat the retrospective price as an observed
   executable fill.

These are counterexamples and source findings, not historical frequency or PnL
measurements. Probe A directly exercises the resolver with a supplied planned
exit; it does not claim this whole synthetic sequence satisfies breakout entry
and channel-generation rules. The probes do not establish that the strategy is
profitable or unprofitable. They also do not invalidate an independent arithmetic
reconciliation conditional on already supplied fills. No execution acceptance.

Required correction decisions: explicit ordering of open events versus later
intrabar stops; price/time provenance and uncertainty for each exit type; separate
predeclared terminal valuations from missing-data boundaries; unchanged parameters
and cost scenarios for any eventual historical correction comparison.

## Reviewed SHA-256 hashes

| File | SHA-256 |
| --- | --- |
| `src/trading_platform/research_breakout.py` | `973280749d3316a055be4b5e99d0234a5cd1b1eff39ca61c0bfb2d2b320bbf61` |
| `research/btc/audit_breakout_execution_a0.py` | `8a484eaa180f8045a9aeae0345ea0e977b1a0d7260b7e2c4fb794288afd6aee6` |
| `research/btc/contracts/btc-breakout-execution-source-audit-a0-v1.md` | `1cc9f50278225b2029025516143c495f2cf7624c8a866b34b2549745882a7760` |
