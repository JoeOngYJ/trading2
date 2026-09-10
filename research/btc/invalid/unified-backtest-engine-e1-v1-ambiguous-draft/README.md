# Invalid E1 v1 implementation draft

Status: **untested, unqualified and prohibited from use**

These files preserve the exact E1 implementation and test drafts that were written against
`btc-unified-backtest-engine-e0-v1` before an independent oracle review identified unresolved
economic semantics. They were removed from active `src/` and `tests/` paths before any test was
run. They are negative process evidence, not reusable implementation.

The eight unresolved v1 ambiguities were:

1. whether partial collateral release divides by pre- or post-reduction quantity;
2. whether isolated initial margin is additive per fill or recomputed for the whole position;
3. whether liquidation charges its special fee instead of, or in addition to, ordinary close cost;
4. the exact exit-cost-reserve rate, formula and refresh timing;
5. whether economic cashflows themselves are quantized or only reconciliation residuals are
   compared to the universal quote quantum;
6. the explicit adverse intrabar mark mapping for long and short perpetual positions;
7. whether an exposure-increasing order may occur at a terminal execution event; and
8. whether atomic-pair neutralization uses actual spot inventory after a base-asset fee and proves
   the neutralization fee can be paid.

Do not import, execute, copy or repair these files. E0 v2 must pass independent review before a
fresh E1 successor is implemented from scratch.

