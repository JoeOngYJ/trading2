# BTC unified backtest engine E0 v3 pair-close review

Qualification ID: `btc-unified-backtest-engine-e0-v3-pair-close`  
Disposition: **PASS — E1 synthetic implementation permitted**  
Actionable arm: `no_trade`

The initial v3 draft failed independent review. Successive corrections froze exact machine
authority lineage, isolated-collateral fee funding, Cartesian spot/perpetual partial-fill preflight,
outcome-specific VWAP and costs, committed fills without rollback, residual and whole-pair severe
neutralization, mismatch valuation, funding/margin checkpoints, terminal/segment boundaries and a
finite failure state. A zero residual now submits no severe order; positive residuals alone face
step, minimum-notional, price and fee gates.

The final reviewer verified canonical JSON, all predecessor and authority hashes, paused E1 draft
hashes, the complete Cartesian `R × q` outcome set and every prior blocking condition.

Final reviewed checksums:

- plan: `9454f21e8d1c1005a21c79b5071d76f04ee2ae8306d875cfed37f3eef000eef9`;
- contract: `b0cea8cb6b35df31d51c7745a6b2ec1b3a4a3c6ac99f67c4d5db12a021057df1`.

This pass permits E1 synthetic accounting only. It grants no historical, strategy, paper,
production, credential, external-service or executable authority.
