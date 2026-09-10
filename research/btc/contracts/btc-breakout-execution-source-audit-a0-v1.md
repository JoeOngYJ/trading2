# A0-v1 bounded synthetic execution audit

Identity btc-breakout-execution-source-audit-a0-v1. Freeze source-derived assertions before
executing synthetic probes. No historical candles or new strategy performance. Run only after
R2-v2 accounting replay reconciles. Evaluate existing `research_breakout.resolve_exit` unchanged.

Probe A: entry open100; next five-minute open110, low95, close108; a previously scheduled channel
exit is assigned to that next open. Stop96 is not breached at that open. A chronological open
exit would sell110 before a later intrabar touch. Existing source precedence predicts96/stop.
If observed, record chronology defect for this synthetic schedule, not its historical frequency.

Probe B: one supplied segment's last bar opens100, closes105, low99. Existing source predicts
exit at close105 and returns that bar's index; simulate records its open_ms as exit_ms. Distinguish
known terminal close (allowed if predeclared) from an unexpected subsequent data gap (not knowable
before it occurs). A close valuation is unavailable at its bar's open. No historical impact inferred.

Probe C: retain identical first two bars, change only the third bar's segment label. Existing
resolver is expected to switch its exit from a later bar to the preceding segment's final close.
This shows dependence on later segment metadata; assess as a retrospective boundary convention
requiring disclosure/invalidation, not proof of a realizable advance exit.

Outputs: source hashes, inputs, observed resolver tuples and analytical expected chronology.
No patching legacy execution, tuning, recomputing market returns or historical row access.
If discrepancies are confirmed, stop before corrected historical replay and report the precise
execution-policy decisions needed in a separately frozen correction specification. no_trade.
