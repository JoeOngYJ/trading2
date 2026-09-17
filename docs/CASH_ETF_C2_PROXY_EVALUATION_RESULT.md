# Cash-ETF C2 Proxy Evaluation Result

## Current audit disposition — 2026-09-12

**Archived, unqualified development diagnostics; no accepted arm and no rerun authorization.**
The current research authority is [EDGE_RESEARCH_RESET](../research/EDGE_RESEARCH_RESET.md).
The [audit-status metadata](../config/research/cash-etf-evidence-audit-status-20260912-v1.json)
supersedes the operational interpretation of the old `cash-etf-status-v1.json` active label;
that pinned registry remains a historical record.

Later aggregate reports exist through `c2-proxy-evaluation-v8/report.json`, including a third
quarterly defensive-rotation arm. The current evaluator's turn-of-month entry differs from the
frozen contract; its equity and trade accounting disagree, its purported month-block intervals
are trade order statistics, and required matched controls are absent. Exact producer-byte
binding for each old report is UNKNOWN. The numbers below remain preserved observations of
unqualified outputs, not validated results for the frozen hypotheses. The slow-trend profit
factor quoted below appears in v4 and later, while the v3 report retains experiment ID v2 and
reports profit factor zero; the old prose is not an exact report manifest.

The later development-only runs do not restore untouched status to 2019–2023: the earlier C1
pragmatic v2 subledger numerically processed that period. Strategy-outcome exposure there is
not established; independent eligibility remains UNKNOWN. Locked data remain inaccessible.
See the [evidence-integrity investigation](../research/EVIDENCE_INTEGRITY_RESOLUTION.md).

## Historical summary retained from 2026-08-30

Updated: 2026-08-30 23:00 UTC

The corrected development-only evaluator (`cash-etf-c2-proxy-evaluation-v3`) ran on the v5 GBP
ledgers without accessing locked data. It calculated both frozen proxy rules at 10, 25 and 50 bps
round-trip costs. The earlier v2 output is preserved as invalid because of an annualisation and
cost-application defect and must not be used.

At 25 bps, slow trend returned 28.10% cumulative (2.51% annualised), 10.61% maximum drawdown,
0.24 Calmar and 2.69 completed-trade profit factor. Turn-of-month returned -11.45% cumulative
(-1.22% annualised), 22.38% drawdown and 0.87 profit factor. At 50 bps, slow trend remained
positive at 7.66% cumulative; turn-of-month fell to -34.28%.

The corrected successor also reports calendar-year returns and zero-yield-cash controls. These
remain provisional diagnostics, not promotion evidence.

These are development diagnostics only. Validation and historical-confirmation partitions remain
locked, controls and uncertainty gates are not yet complete, and no strategy arm or execution
instrument is accepted. The actionable route remains `no_trade`. C2 stays active pending a full
gate-complete evaluator review.
