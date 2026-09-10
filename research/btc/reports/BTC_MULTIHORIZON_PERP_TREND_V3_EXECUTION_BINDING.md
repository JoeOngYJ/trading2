# BTC multi-horizon perpetual trend v3 — historical execution binding

Experiment ID: `btc-multihorizon-perp-trend-v3`  
Status: **frozen before historical return access**

V2 passed synthetic T1 but is closed pre-return because its margin language named “current mark”
without binding the qualified historical mark-price ledger. V3 inherits the complete v1 economic
contract and every v2 implementation clarification unchanged. It additionally binds official
Binance USD-M hourly mark-price archives plus the single exact REST recovery already qualified by
`btc-carry-gap-recovery-v1`. No traded close may substitute for mark price.

Within each eligible hour the immutable accounting order is: mark the existing position from the
prior close to the current perpetual open; execute any pending severe gap/risk exit; apply funding
scheduled at this timestamp to the position then held using mark open; execute a scheduled 01:00
rebalance; mark the resulting position from open to close; then evaluate margin using mark close.
At a development/evaluation boundary, flatten at the final development close under the applicable
ordinary cost and restart cash, features and positions for evaluation. Each partition starts at
1,000 USDT. The 2024–2025 partition is consumed stability evidence, never promotion evidence.

The historical adapter may deserialize sources only after validating v3 and all bound checksums.
It must emit all 30/40/80-bps results, fixed-size and downward-only EWMA variants, flat,
buy-and-hold, always-long, simple-28-day-sign and seeded-random controls, full attribution and
every frozen gate. Outputs are immutable and the run occurs once. No post-result change is allowed
under this ID.
