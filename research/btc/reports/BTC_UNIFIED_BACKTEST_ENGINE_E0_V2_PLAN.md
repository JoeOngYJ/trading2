# BTC unified backtest engine E0 v2 clarification plan

Qualification ID: `btc-unified-backtest-engine-e0-v2`

Status: frozen before fresh E1 implementation; independent review required

Actionable arm: `no_trade`

## Why v2 is required

E0 v1 passed its document review, but construction of the independent accounting oracle exposed
eight semantics that an implementer could choose in more than one reasonable way. An E1 draft had
already been written, though no test had run. The exact draft is preserved under
`research/btc/invalid/unified-backtest-engine-e1-v1-ambiguous-draft/` and removed from active source
and test paths. It is unqualified and must never be imported or repaired.

V2 inherits every unchanged E0-v1 safety, event, accounting, output, lineage, offline and
`no_trade` requirement. The following rules replace any broader or ambiguous v1 wording.

## Frozen clarifications

### 1. Partial collateral release

For an incoming absolute perpetual quantity `Q_old` and a reduction of `Q_close`, calculate:

```text
released_initial_margin_memo = old_initial_margin_memo * Q_close / Q_old
```

The denominator is always the pre-reduction quantity. Reduce the memo by that full amount, then
transfer only `min(released_initial_margin_memo, max(post-settlement collateral, 0))` to quote cash.
Losses cannot create cash through collateral release. A full close settles any negative residual
as a liability.

### 2. Initial margin on increases

Initial margin is additive by fill:

```text
increment = abs(filled quantity delta) * accounting fill price / frozen leverage
```

Transfer that increment from quote cash before each increase. Do not reprice the old position or
recompute margin from whole-position notional. Leverage is fixed by the run contract and cannot
change while a position is open.

### 3. Liquidation costs

An observed liquidation charges exactly:

```text
abs(pre-liquidation quantity) * observed adverse mark * liquidation fee rate
```

That liquidation fee replaces ordinary close commission and implicit exit cost. It is charged
once. No additional normal close cost is debited. A future source-supported additive convention
requires another contract version; it cannot be selected by an adapter.

### 4. Exit-cost reserve

Each run binds one nonnegative perpetual exit-cost rate. Except for a fixture explicitly marked
`zero_exit_reserve_fixture`, zero is invalid. The memo is:

```text
abs(current perpetual quantity) * current official mark * bound exit-cost rate
```

It is refreshed after the opening mark, funding, every fill or neutralization, the adverse
intrabar mark and the close mark. It is subtracted in margin-equity tests but is not a cash debit.
An ordinary exit replaces the memo with its realized exit cost; liquidation replaces it with the
single liquidation fee; a flat position has a zero reserve.

### 5. Decimal precision

Economic quantities, prices, fees, funding, collateral and PnL remain exact finite Decimal values.
Only instrument fields are quantized, once, under their effective rule and declared rounding
direction before a transition. Do not round cashflows, NAV or state fields to the universal quote
quantum. After every transition, compare the exact residual with `1e-8` USDT; the comparison never
changes state or silently writes the residual to zero.

### 6. Adverse intrabar mark

The frozen conservative mapping is explicit:

- long perpetual: test the interval low first;
- short perpetual: test the interval high first;
- flat perpetual: neither extreme creates a perpetual margin test.

If the adverse extreme liquidates, terminate there. Do not inspect the favourable extreme or
close to improve the outcome.

### 7. Terminal execution event

The terminal event and its market-on-close or eligible-next-open convention are frozen before the
run. At that event, reject every order that would increase absolute spot or perpetual exposure.
Only reductions, protective exits, forced neutralizations and the predeclared terminal flatten are
permitted. A strategy cannot enter or reverse into new exposure at the boundary.

### 8. Net spot and pair neutralization

For an atomic pair, `net spot quantity` is the actual BTC inventory after all entry fill and
base-asset fee mutations—not requested or gross filled quantity. Size and mismatch the perpetual
leg against that actual inventory.

Before executing the first leg, preflight the severe neutralization path using effective fee and
quantity rules. For a base-fee spot sale, gross sale quantity plus its base fee must be no greater
than actual inventory. The rules must yield a deterministic sale that leaves exactly zero BTC;
otherwise reject the whole pair before any mutation. After a second-leg failure, close any filled
perpetual quantity first, then sell the validated gross spot quantity and debit its reserved base
fee. Do not sell the originally requested spot quantity.

## V2 gate

V2 passes only when an independent reviewer confirms that the combined v1 plus v2 specification
leaves none of these choices to E1. Passing permits a fresh E1 implementation under a new active
module/test identity. It does not rehabilitate the archived draft and permits no historical data,
strategy, metric, oracle reuse, paper observer, production integration or executable action.
