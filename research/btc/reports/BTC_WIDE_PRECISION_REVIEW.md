# Independent wide-precision successor review

Reviewer: wide_review independent agent. Date: 2026-09-08. Verdict: PASS for
synthetic numeric qualification and the bounded R2-v2 recorded-fill replay.

Scope: reviewed both successor contracts, frozen-input manifest, implementation,
tests and source diffs against `reference_r1.py` and `reconcile_r2.py`. No archived
trade rows or market data were read; `run_archive` was not called. No implementation
files were edited. This review does not accept strategy performance or execution.

The code changes are limited to successor identity/import and numeric bounds:
18 to 32 total digits, 12 to 24 fractional places, and precision 80 to 128.
Source checksums, three cost scenarios, counts, dates and comparison tolerances
are unchanged. Both contract hashes match the frozen-input manifest.

Independent precision argument: each quantity/price is less than 10^32 and has
scale at most 24. With at most 10,000 events inventory is less than 10^36;
summed absolute fill notionals are less than 10^68. Inventory times mark is less
than 10^68; cash plus marked inventory is bounded by 2*10^68. Products and sums
have scale at most 48, requiring at most 69+48=117 significant digits. Precision
128 therefore covers all permitted accounting operations without rounding.
Relative-error reporting can round nonterminating divisions; comparison decisions
use exact Fraction arithmetic and the unchanged frozen tolerance.

Ran `python3 -m unittest research.btc.tests.test_reference_r1_v3 research.btc.tests.test_reconcile_r2_v2`:
9 tests passed. These include eight literal accounting scenarios, exact independent
Fraction reconciliation at the maximum 10,000-event count with mixed scales and
32-digit/24-place inputs, hostile caller Decimal context, invalid inputs, deliberate
cash corruption, checksum/symlink failures, and 12 synthetic float-chain cases.

No blocking finding. Historical execution timing, exchange lot rounding and
strategy economics remain outside this numerical compatibility acceptance.

## Reviewed SHA-256 hashes

| File | SHA-256 |
| --- | --- |
| `research/btc/reference_r1_v3.py` | `b8ce544728204d617a67b1907906d76a3ecd1597d14211bfa72d33e76dc7d648` |
| `research/btc/reconcile_r2_v2.py` | `031e4e7ea561a68ccbbafd33cad0a3e3f6a4d9c7229e9eb12b736a76f2373dab` |
| `research/btc/tests/test_reference_r1_v3.py` | `a74024e92165972cd36b9bda089d744d1b6614afac28c3f97852e164fb77251c` |
| `research/btc/tests/test_reconcile_r2_v2.py` | `b7e64775cb0eb1bacdaeb8aea2fb48d8c977c78188d20188b89b6dea17aac8f9` |
| `research/btc/contracts/btc-reference-fill-accounting-r1-v3.md` | `b9fae5dc9f5b4d059e98855c36e2704452f0aa1d69ce6ce027845c4a0f37bdf5` |
| `research/btc/contracts/btc-archived-breakout-reconciliation-r2-v2.md` | `5e0b48515a63895310fd858bf95f357e50b8d97e2e386ecfb054011cdef44bf2` |
| `research/btc/contracts/btc-wide-precision-successors-inputs.json` | `4f496779b76a939efdbb8bf81e6c61c87b36121a515877eaba60c7b4a99ef0a2` |
