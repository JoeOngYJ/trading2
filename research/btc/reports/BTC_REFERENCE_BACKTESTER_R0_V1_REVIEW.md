# R0-v1 independent implementation review

Reviewer: independent agent `/root/r0_review`.
Verdict: **PASS within the frozen synthetic R0 scope**.

Reviewed against `research/btc/contracts/btc-reference-backtester-r0-v1.md`
and `research/btc/reports/BTC_REFERENCE_BACKTESTER_R0_V1_EXPECTATIONS.md`.

## Reviewed bytes and verification

| File | SHA256 |
|---|---|
| `research/btc/reference_r0.py` | `f1a2ba860f17395fa73442c5e8c7d63bb4d80a70c29f41e4bcd74d66c0a9b11d` |
| `research/btc/tests/test_reference_r0.py` | `0aad4cbd58cfed9bcb301638a96d96860dce4e32703344e57043ef5f974b3833` |

Reproduction command:

```sh
python3 -m unittest research.btc.tests.test_reference_r0 -v
```

Result: four test methods passed, including the 17 literal synthetic cases,
invalid input checks, prefix causality, and quantity/context regressions.
The review inspected implementation semantics alongside test results.

## Initial findings and fixes verified before candidate freeze

1. Division at precision 50 before flooring could round a requested quantity
   just below 2 upward to 2, producing negative unused quantity. The implementation
   now floors an exact integer ratio and constructs the rounded Decimal quantity
   exactly. The regression requests `1.` followed by 54 nines with step `1` and
   verifies a filled quantity of `1`.
2. The local Decimal context inherited caller traps and other context settings.
   A fresh context now supplies precision 50 and ROUND_HALF_EVEN. The caller-context
   regression verifies matching results under precision 6 and an enabled Inexact trap.
3. The required return diagnostic was initially absent. Each row now emits
   `diagnostic_return`, with its equation checked.
4. Literal tests initially checked only cash, inventory and equity through `zip`.
   They now also require three rows, exact timestamps, dispositions, frozen cumulative
   fees and implicit costs, and the terminal expiry payload.

Verified tested behavior includes quote-currency fees, costs counted once,
cash/inventory reconciliation, partial exits, rejection reasons, subsequent-open
execution, delayed availability, equality waiting, terminal marking, and unchanged
prefix emissions when only later valid prices change.

## Acceptance limits

The independent cumulative oracle uses its own arithmetic and imports no engine
arithmetic helpers, but is conditional on engine-emitted signed fills. It reconciles
accounting; it does not independently establish all possible execution schedules or
quantities. The literal fixtures establish those properties for the tested cases.

This accepts a small synthetic reference ledger only. Historical data and execution,
broader numeric extremes, full mandate/risk enforcement, gaps during exposed trading,
terminal liquidation, derivatives and strategy profitability remain unqualified.
No historical inputs, network resources or protected services were accessed.
