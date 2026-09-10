# Cash-ETF C2 Proxy Evaluation Result

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
