# R0-v1 synthetic accounting contract

Identity: `btc-reference-backtester-r0-v1`. Scope: synthetic BTC/USDT spot accounting only.
This specification freezes before implementation. Qualification is pending. Action: `no_trade`.
It does not qualify a full execution model, mandate enforcement or strategy.

## Inputs and clock

Fixtures contain only invented prices. Initial cash is 1000 USDT and inventory zero. Economic
values are finite decimal strings, never floats; prices and quantity steps are strictly positive.
Use a local Decimal context with precision 50 and ROUND_HALF_EVEN; never change global context.
Quantity is rounded down to a multiple of the fixture step. Fees and cash are not quantized.
Reject malformed or nonfinite values, negative requested quantity and fee/slippage outside
0 through 100 bps. Zero rounded quantity rejects the order without changing state.

Times are exact UTC `YYYY-MM-DDTHH:MM:SSZ`. Opens must be strictly increasing and exactly one
hour apart. Decisions are strictly increasing and carry requested base quantity and buy/sell.
Available time must be no earlier than decision time. A decision uses only information available
at its timestamp. Execute at the first scheduled open strictly after both decision and availability
times, provided that open exists. Equality waits until the following open. Do not search past a
missing scheduled open. Decisions outside the supplied boundary reject the input.

Prevalidate the complete synthetic input before accounting. Duplicate/reversed opens, any missing
hour, invalid timestamps and unavailable future input reject the entire fixture with no result
ledger. This intentionally defers E0's exposed-gap recovery behavior. A valid decision whose next
scheduled open is beyond the input boundary expires without a fill. One order per execution open;
colliding orders reject input. No retry, partial fills, borrowing, pyramid entries or short sale.

## Accounting

For open p, slippage s bps and rounded quantity q, buy price is p*(1+s/10000); sell price is
p*(1-s/10000). Fee = q*fill_price*fee_bps/10000, always paid in quote currency.
Buy: cash_after=cash_before-q*fill_price-fee; inventory_after=inventory_before+q.
Sell: cash_after=cash_before+q*fill_price-fee; inventory_after=inventory_before-q.
Reject a buy if inventory already exists, total debit exceeds cash, or fill notional exceeds
25% of prefill equity marked at that open. Check insufficient cash before allocation. Reject a
sell exceeding inventory. Rejections leave state unchanged. Partial exits are permitted.

Each open emits cash, inventory, raw-open marked equity, cumulative fees, cumulative implicit
cost and disposition (hold/filled/rejected/expired). Implicit cost is q*abs(fill_price-p), already
embedded in cash: never debit it again. State also records gross open-price cashflows to support
independent reconciliation. Equity=cash+inventory*p. No deposits, interest or unrealized cash.
Return=(terminal equity/1000)-1, a fixture diagnostic only. Record any expiry at terminal open.
Terminal inventory remains marked at the final supplied open; no forced sale or hypothetical exit
fee. This valuation-only convention is not an accepted historical strategy terminal convention.

## Required checks and limits

Compare every event against literal fixture expectations and an independent cumulative cashflow
oracle using Decimal and its own formulas, without importing engine helpers. Required identities:
inventory=sum signed fills; cash=1000-sum signed fill notionals-sum fees; equity=cash+inventory*p;
unchanged-price round trip loss equals fees plus implicit costs. Check prefix invariance when only
later valid prices change. Fixtures must cover all cases in the paired expectations document.

Covered E0 concepts: Decimal state, quantity rounding down, quote fees, cash/inventory conservation,
costs counted once, subsequent-open causality and explicit invalid inputs. Deferred: E0 gap exits,
terminal flattening, price protection, historical rules, minimum notional/tick rules, stop/cadence
and full risk enforcement, base/third-asset fees, L2, derivatives, funding, margin and routing.
R0 cannot claim compliance with those deferred requirements or accept any historical strategy.

Evidence graph: this contract and literal fixtures -> implementation/tests -> results -> external
manifest. No upstream file references the manifest or a downstream file hash. Freeze their byte
hashes in an external input manifest before implementation. A changed specification or expectation
requires a new identity and preserved prior evidence. Implementation bugs can be fixed before
candidate freeze. Acceptance requires every case and independent review; a test count alone fails.
