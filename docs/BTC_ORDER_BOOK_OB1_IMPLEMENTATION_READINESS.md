# BTC Order-Book OB1 Implementation Readiness

**Updated:** 2026-08-26  
**Status:** causal data-contract foundation implemented; real-data execution blocked

## Outcome

The frozen OB1 protocol now has a machine-readable experiment specification and tested,
offline dataset-building primitives. This work used synthetic replay frames only. It did
not read the active partial OB0 capture, connect to the soak stack, or run a predictive
model.

Implemented files:

- `config/experiments/btc-order-book-ob1-v1.json`
- `src/trading_platform/research_order_book.py`
- `tests/test_research_order_book.py`

## Enforced conventions

The implementation now enforces:

- one decision per UTC second;
- local receipt time as the only availability timestamp;
- event windows `(decision - 1 second, decision]`;
- latest-book age no greater than 500 ms;
- no feature, return, or label crossing a connection or replay segment;
- L1 queue imbalance, trailing L1 OFI, and normalized microprice displacement;
- signed-trade quote flow, trade count, absolute quote flow, and trailing return controls;
- spread, L1 depth, depth-event rate, book age, and ten-second realized volatility;
- target prices selected backward as of the target timestamp, never from the first future
  event;
- the primary 250 ms latency / 5 second log-mid return plus all frozen horizon and latency
  sensitivities;
- four chronological development folds with the frozen ten-second purge metadata; and
- a locked collection contract containing exactly 60 accepted development days followed
  by a later, contiguous, metadata-only sealed 30-day test.

Synthetic tests prove that changing events after a decision cannot change its predictors,
stale books fail closed, gaps/segment changes invalidate affected labels, connection-local
trade aggregation is preserved, and 59 development days cannot satisfy readiness.

## Remaining implementation boundary

Do not run OB1 merely when the seven-day OB0 pilot ends. OB0 can accept only acquisition
and deterministic replay. OB1 remains blocked until all of the following exist:

1. 60 accepted development calendar days;
2. a later contiguous 30-day test registered by checksum but left unread;
3. a locked collection contract that passes `validate_ob1_collection_contract`;
4. a streaming/day-partition adapter for the large replay files;
5. frozen regularized linear/logistic model and training-only standardization code;
6. day-block bootstrap, per-fold attribution, calibration, and concentration reporting;
7. a deterministic result manifest; and
8. one reviewed authorization to open the sealed test after development code and settings
   are checksummed.

The current pandas builder is deliberately a correctness reference for synthetic and
bounded daily fixtures. Loading a 60-day event-level replay into memory is not approved;
the production adapter must stream or operate on checksummed day partitions while matching
the reference output byte-for-byte on smaller fixtures.

## Next safe implementation

While OB0 runs, implement the streaming/day-partition adapter and compare it against the
reference builder on synthetic and completed smoke fixtures. Do not point it at the active
capture. Model code may then be implemented and tested against synthetic datasets, but it
must refuse real execution until the 60+30-day collection contract passes.
