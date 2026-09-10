# BTC unified backtest engine E0 v3 — atomic pair-close clarification

Qualification ID: `btc-unified-backtest-engine-e0-v3-pair-close`

Status: frozen specification pending independent review; no kernel implementation

Actionable arm: `no_trade`

## Purpose

E0 v3 resolves only the exit path for an existing matched long-spot/short-perpetual BTC pair. It
inherits all E0-v1 and E0-v2 accounting, safety, lineage, offline and zero-capital requirements.
It adds no strategy, signal, metric, historical input or executable authority.

The close is one economic intention with two ordered fills at one declared arrival timestamp. The
legs use their own point-in-time price, instrument rules and cost treatment; a spot price may not
be substituted for a perpetual price or vice versa.

Every run must bind the exact execution-scenario file and exactly one applicable machine-readable
mandate by path, ID and exact-file SHA-256. The semantic run-settings digest is separate; it may
not stand in for the execution or mandate digest.

## Frozen close sequence

1. Before either fill, validate effective rules and the fee currency/balance for the spot close,
   intended perpetual close and severe residual-perpetual neutralization.
2. Enumerate the Cartesian outcome set before mutation: every adapter-permitted actual spot
   inventory reduction `R`, including its fee mutation, and for each `R` every permitted
   perpetual fill `q` from zero through the rule-quantized target. Use each outcome's own
   depth-dependent price/VWAP and cost. Apply ordinary short realized PnL and costs, the v2
   pre-reduction collateral release, then the worst permitted severe residual price and fee.
   Ordinary and severe perpetual fees debit isolated collateral only. Reject before the spot fill
   unless every `(R, q)` path is fee-funded and residual-rule-valid. A base-denominated spot fee
   must fit inside actual spot inventory. The residual is exactly `r_R_q = R - q`; when it is
   zero, submit no severe order and pass the residual-valid gate. Only a positive residual must
   meet step, quantity, minimum-notional, upper-bound, price and fee requirements.
3. Execute the spot sale first. Its fill and fee mutations commit immediately and cannot be rolled
   back if the perpetual leg later fails.
4. Define `actual spot inventory reduction` as pre-fill BTC inventory minus post-fill BTC inventory.
   It therefore includes a base-asset fee. Submit a perpetual buy-to-close for exactly that BTC
   amount, subject to its own quantity rule.
5. If the perpetual close is absent or partial, the excess short created by the spot reduction is
   an unintended naked residual. Buy it to close immediately under the severe-cost policy at the
   same timestamp; if no valid same-timestamp price exists, use the first subsequent valid price.
6. If that severe residual close is unavailable, mark the account invalid and unknown, disable all
   new exposure and retain the forced buy-to-close as pending. Do not call the remaining state
   delta-neutral or include it as valid performance.
7. Only the residual matched long-spot/short-perpetual pair may persist. Both its BTC-quantity
   mismatch and point-in-time notional mismatch must be within the bound inherited limit, using
   independently sourced common point-in-time marks after the final same-time or delayed fill.
   Otherwise, close the entire remaining pair immediately under the same severe spot-first
   sequence exactly once. Never recurse. If it cannot complete, invalidate and retain only the
   pending safety action.

For any full spot close with a base-fee rate, choose the largest rule-valid gross sale whose gross
quantity plus computed base fee does not exceed inventory. If this leaves dust, a voluntary close
is rejected before its first fill. Unexpected dust after a delayed safety attempt is recorded,
invalidates evaluation and remains eligible only for future protective cleanup.

All submitted, rejected, expired, unfilled and partially filled quantities, their reasons and the
created/neutralized residual must be recorded. No fill is deleted or rewritten.

## Adapter capability

- Candle OHLC: each leg is individually all-or-none. Both intended legs share the exact next-open
  timestamp. A candle adapter may not invent depth or partial fills.
- Separately qualified quote/L2: a leg may fill partially from point-in-time eligible depth. The
  same ordered commitment and severe residual-neutralization rules apply.

An intended close may reduce exposure only; it may never cross through zero or create a new long
perpetual. A failure path is a safety resolution, not a strategy entry.

The planned pair close occurs in phase 6 after phase-4 funding owed by the incoming `t-` short and
its immediate margin test. Margin/liquidation is retested after the committed spot leg, intended
perpetual leg and severe residual leg. An observed breach terminates immediately. A delayed
residual that crosses a segment is invalid/unknown; only its forced severe buy-to-close may cross
at the first valid new-segment price, and no ordinary pair state may persist across the segment.
That search may not read or cross the frozen terminal/partition boundary. If no valid price exists
inside it, stop invalid/unknown with the safety intention pending; do not open later data.

## V3 gate

V3 passes only if an independent reviewer can construct full-fill, spot-partial, perpetual-partial,
perpetual-rejected, base-fee, quote-fee, same-timestamp neutralization and delayed-neutralization
fixtures without making another economic choice. Passing V3 permits only a separately authorized
fresh E1 implementation. A paused, unqualified E1 draft exists at the exact paths bound by the
machine contract; it is non-importable and is not an active or passed kernel. `no_trade` remains
mandatory.
