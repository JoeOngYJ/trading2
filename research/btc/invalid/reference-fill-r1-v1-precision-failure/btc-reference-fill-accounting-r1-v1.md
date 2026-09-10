# R1 explicit-fill synthetic accounting contract

Identity: `btc-reference-fill-accounting-r1-v1`. Frozen before implementation. Action `no_trade`.
Initial cash 1000 USDT, inventory zero. Synthetic spot long/flat bookkeeping only; supplied fills
are assumed inputs, never executable orders. No sizing, allocation or fill selection is performed.

Input is a list of 1–10000 dictionaries. Every record contains `sequence` (integer, not bool,
exactly 1..N), `timestamp` (real UTC YYYY-MM-DDTHH:MM:SSZ), `kind` and `mark_price`.
Times are nondecreasing; same-time records execute in supplied sequence. Gaps are permitted
because these are events, not a claimed continuous market feed. No causal availability is inferred.
`kind=mark` has no other fields. `kind=fill` additionally requires `side` buy/sell, `quantity`,
`fill_price`, `quote_fee`. Reject missing/extra fields and all other kinds/sides.

Amounts are unsigned ordinary decimal strings with at most 18 digits total and at most 12
fractional digits; no exponent, float, sign, whitespace, NaN or Infinity. Mark, quantity and fill
price must be positive; fee may be zero. Restricting the numeric domain is explicit, not silently
rounding source values. Use a fresh Decimal Context(prec=50, ROUND_HALF_EVEN). No rounding or
quantity resizing. Within these input/count bounds additions and products are exact.

Prevalidate syntax and ordering, then account entirely in memory; any invalid event, insufficient
cash or oversell raises ValueError and returns no ledger. Buy: debit q*p+fee and add q inventory.
Sell: credit q*p-fee and subtract q inventory. Fees must not make cash negative on either side.
Buying more while holding and partial exits are allowed for recording externally supplied fills.
No short inventory, margin, funding, interest or deposits. Mark events change no cash/inventory.

Emit one row per event with sequence, timestamp, kind, cash_before, inventory_before, cash,
inventory, equity=cash+inventory*mark_price, cumulative quote fees and signed cumulative fill
notional (buys positive). Economic outputs are Decimal values. Terminal inventory stays marked;
no forced exit, exit cost or return annualization. Combined-cost legacy fill inputs carry zero
quote_fee; never add a second fee. Explicit-fee representations reconcile only when input economics
are actually equivalent; do not assume the shared execution cost model is algebraically identical.

Acceptance: exact literal states below; independent Fraction arithmetic from the INPUT events
(not emitted fills or engine helpers) reconciles every row; deliberate altered output is rejected;
invalid domain/schema/ordering and insufficient cash/inventory fail; caller Decimal context has
no effect; future mark changes preserve prior rows. Independent review required before acceptance.
Freeze code/tests/results in an external evidence manifest after fixes. No document hashes a
downstream document. No archived trade or market rows are authorized by this contract.
