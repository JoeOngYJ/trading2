# BTC unified backtest engine E0 v2 independent review

Qualification ID: `btc-unified-backtest-engine-e0-v2`  
Disposition: **PASS — fresh E1 synthetic implementation permitted**  
Actionable arm: `no_trade`

An independent closed-form fixture exercise found eight economically material choices left open by
E0-v1 after its document review. Because an untested E1 draft had already been written, v1 was not
silently amended. The exact draft was moved outside importable source/test paths and checksummed
under `research/btc/invalid/unified-backtest-engine-e1-v1-ambiguous-draft/`.

The independent v2 review confirms exact rules for the partial-collateral-release denominator,
additive initial margin, liquidation-only costs, exit-cost-reserve calculation, Decimal
quantization, adverse intrabar marks, terminal-order restrictions and post-fee spot inventory used
by pair neutralization. The predecessor and archived-draft hashes verify, JSON is canonical, and
the active draft paths are absent.

Reviewed checksums:

- v2 plan: `57cfc7fcb4ba0bd2729595234b21a00c4038bf14f87f01d93f03ae54eb3809c8`;
- v2 contract: `201bbaad8f1fb6e00efdc2b3c25d632d0d3da94d8b8521c2f92b37da29cde887`.

This pass permits only a fresh E1 Decimal kernel and synthetic tests derived from the combined v1
and v2 contracts. The archived draft may not be imported, executed, copied or repaired. Historical
market data, strategy returns, metrics, E2 oracle implementation, paper observation, production
integration and executable actions remain prohibited.
