# R0-v1 synthetic ledger qualification

Implemented `research/btc/reference_r0.py` against the unchanged frozen specification and
hand-calculated expectations. Four test methods cover all 17 literal scenarios plus validation,
causality, disposition, cost and numeric-boundary checks. Reproduce with:

```sh
python3 -m unittest -v research.btc.tests.test_reference_r0
python3 scripts/validate_btc_focused_context.py
```

Independent reviewer `/root/r0_review` initially required fixes: rounding before flooring could
overfill a near-integer quantity, Decimal settings inherited caller traps, and literal assertions
did not fully check event structure and costs. These implementation defects were corrected before
candidate freeze without changing the specification. The reviewer then passed the synthetic scope.
Its independent review records exact implementation and test hashes.

The ledger prevalidates synthetic inputs, executes at a subsequent scheduled open, records quote
fees and implicit costs exactly once, rounds quantity down using integer ratios, and reports cash,
inventory, equity and diagnostic return at every open. Decimal context is isolated from callers.

Primary/stress/severe unchanged-price round trips produce terminal cash 999.4/999.2/998.4 from
1000. These are fixture arithmetic checks, not BTC market returns. The independent cumulative
cashflow oracle checks accounting conditional on reported fills; literal cases separately check
the tested execution schedule and quantities. No universal execution correctness is claimed.

Decision: accept R0-v1 as a narrow synthetic accounting reference. Full risk/mandate enforcement,
historical rules and price protection, exposed-gap recovery, terminal flattening, derivatives,
funding and real strategy evaluation remain unqualified. No strategy is accepted.

Next permitted action: plan a separately frozen historical reconciliation of one existing BTC
spot control, first mapping its requirements to the reference's deferred features. Resolve any
required feature with synthetic qualification before opening market rows. Do not directly feed
historical prices into R0 or treat prior strategy returns as newly validated. Action: `no_trade`.
