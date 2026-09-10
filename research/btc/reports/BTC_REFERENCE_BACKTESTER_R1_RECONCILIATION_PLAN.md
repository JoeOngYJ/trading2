# Existing spot-control reconciliation plan

Status: source review completed; proposed R1 synthetic accounting adapter, no market-data access.
Target: unchanged fixed 20-day/10-day BTC spot breakout at 10% allocation, retained only as a
development control. Do not reopen its rejected family, adjust thresholds or add a regime filter.

## What the source establishes

The legacy source `scripts/backtest_btc_online_regime_breakout.py`, functions `simulate` and
`resolve_exit`, uses 120/60 completed four-hour channels, fills on the adjacent five-minute
open, a 4% stop, a 14-day holding limit and segment-end close liquidation. Entry open may have
the same timestamp as the completed four-hour decision boundary. This differs from R0's rule
that equality waits for the following hourly open.

Legacy sizing spends 10% of cash including the combined entry cost: budget=cash*0.10;
entry_fill=open*(1+side_cost); quantity=budget/entry_fill. Fees and implicit costs are combined
in that fill. No quantity-step rounding is applied there. R0 instead receives a base quantity,
rounds it, and applies fee separately to the slipped notional. These are distinct conventions.

Legacy protective-stop execution uses min(open,stop) if a five-minute low touches the stop.
Segment-end exits use the final close, yet `exit_ms` is the corresponding row's open timestamp.
Thus an archived exit timestamp alone cannot prove availability of that exit reference.
Determining a segment end from the following row also deserves a separate causality audit.
These are source-level concerns, not a measured historical PnL correction.

`scripts/qualify_btc_backtest_core.py` reads the stored breakout and SMA reports and compares
their metric subsets with frozen expected values. It separately runs synthetic core checks.
Consequently its golden-metric match establishes saved-report regression, not independent
historical fill or accounting replay through that core. Preserve the old result with this limit.

## Smallest useful sequence

1. Freeze `btc-reference-fill-accounting-r1-v1` as a synthetic adapter qualification. It consumes
   explicit externally supplied fills (sequence, side, quantity, fill price, quote fee) and explicit
   valuation events. It does not select orders, calculate stops, infer availability or simulate
   fills. Retain R0 unchanged; do not disguise fills as R0 hourly decisions.
2. Hand-calculate entry/exit cases under the legacy combined-cost convention, plus explicit-fee
   equivalents, partial exit, multiple trades, invalid ordering/negative inventory, terminal mark
   and a close-price valuation event whose time differs from the opening time. Compare each cash
   and inventory transition using an independent calculation. Include a deliberate discrepancy
   to prove the reconciliation fails instead of forcing agreement.
3. After synthetic qualification and review, freeze a separate archived-trade replay contract.
   Resolve exact artifact paths and hashes from the S1 manifest before opening any trade rows;
   freeze allowed record fields, ordering, numeric tolerances and output scope. Verify whether
   archived values are sufficient; if not, stop with a missing-field report. This stage may
   reconcile recorded fill economics but cannot authenticate those fills or their causality.
4. Replay only the unchanged fixed-breakout control, preserving source numeric strings/float
   provenance. Compare per-trade cash-before, cash-after, quantity and PnL before aggregate return.
   Report all discrepancies. Separate float serialization tolerance from changes to economics;
   choose that tolerance from synthetic float/Decimal cases before historical access.
5. Only afterward propose a separately frozen execution audit. That requires exact five-minute
   boundaries, price caps, sizing, stops, cadence, segment/gap handling, valuation timestamps and
   terminal liquidation. It must qualify those features synthetically before market-row access.
   A corrected execution convention requires a new identity and attribution against the legacy
   convention. Do not demand exact old return if fixing a causal or accounting defect changes it.

## Acceptance and boundaries

R1 acceptance means event accounting is correct for supplied synthetic fills; it does not accept
fill generation, timing or any strategy. Archived replay means supplied historical trade arithmetic
reconciles, not that the strategy could have executed. Execution audit is a third distinct claim.
No new model, optimization, historical return calculation or data purchase is needed for step 1.
The 2026 partition, OB0 and protected services stay outside every listed step.

The next permitted action is to freeze the R1 synthetic input/output conventions, hand-calculated
cases and rejection gates, then implement and independently review that adapter. Current action
remains `no_trade`; EWMA remains the mandatory risk benchmark for later strategy comparisons.
