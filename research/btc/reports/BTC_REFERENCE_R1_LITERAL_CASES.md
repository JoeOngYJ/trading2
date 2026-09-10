# R1 literal expectations frozen before implementation

All prices invented. Each tuple is (cash, BTC, equity, cumulative quote fees). Default event marks
are 100. Events use increasing sequences starting at 1 and UTC timestamps on 2020-01-01.
Buy at 00:00:00; first sell at 00:05:00; subsequent events at 00:10:00 and 00:15:00 unless stated.

1. Mark only at 100: (1000,0,1000,0).
2. Legacy combined costs: buy 2 at 100.15 fee 0 -> (799.7,2,999.7,0);
   sell 2 at 99.85 fee 0 -> (999.4,0,999.4,0).
3. Equivalent explicit fees: buy 2 at 100 fee 0.3 -> (799.7,2,999.7,0.3);
   sell 2 at 100 fee 0.3 -> (999.4,0,999.4,0.6).
   Cases 2/3 have identical cash/inventory but different reported fee attribution.
4. Partial profit: buy 2 at 100 -> (800,2,1000,0); sell 1 at 110, mark 110 ->
   (910,1,1020,0); mark 90 -> (910,1,1000,0); sell 1 at 90 -> (1000,0,1000,0).
5. Multiple trades: buy 2 at 100 -> (800,2,1000,0); sell 2 at 110 mark 110 ->
   (1020,0,1020,0); buy 1 at 100 -> (920,1,1020,0); sell 1 at 90 -> (1010,0,1010,0).
6. Open terminal: buy 2 at 100 -> (800,2,1000,0); mark 110 at 00:05:00 -> (800,2,1020,0).
   The mark is a close-price valuation event with its own explicit time, not a backdated fill.
7. Same-time sequence: buy 1 at 100 then sell 1 at 100 at 00:00:00 ->
   (900,1,1000,0), (1000,0,1000,0).
8. Additional fill while holding: buy 1 at 100 twice -> (900,1,1000,0), (800,2,1000,0).

All unspecified fees are 0. Each row's before-state equals the prior row's after-state, or
(1000,0) initially. Signed fill notional is independently summed from side*q*fill_price.
Negative tests: empty/oversize input, duplicate/nonconsecutive/bool sequence, reversed/invalid
timestamp, bad or extra/missing keys, invalid side/kind, float/exponent/signed/nonfinite amounts,
overlong amounts, zero prices/quantity, buy 11 at 100, sell without inventory, fee-induced negative
cash on a sell, and an invalid last event following valid events. None returns a partial ledger.
Mutate one emitted cash value by 0.01 and require independent reconciliation to fail.
