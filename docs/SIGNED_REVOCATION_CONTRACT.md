# Signed Revocation Contract

**Status:** Implemented for policy rejection, caught failures, and expired worker leases.

A revocation is a distinct `signal.revoked` event, never a rewritten `HOLD` decision. It
identifies the exact actionable signal by ID, sequence, and checksum and carries the current
run, evidence, policy digest when available, stable reason code, and a higher stream sequence.

The database permits a revocation only when:

- the target is the latest unexpired non-`HOLD` created signal for the same route;
- the current run owns the exact fenced attempt: a live lease for synchronous failure, or
  an expired lease for the dedicated `worker_lease_expired` recovery reason;
- rejected or sealed evidence supports the reason and policy result;
- every stored column matches the signed envelope;
- the revocation and outbox payload are inserted in the same transaction.

The bridge verifies the signature and routing, sequence-checks both created and revoked events,
and atomically replaces the local signal file with the signed tombstone before recording its
receipt. Freqtrade accepts entries only from `signal.created`; tombstones and malformed files
fail closed. Protective exits are unaffected.

Lease recovery closes partial capture evidence, appends the signed tombstone and outbox row, and
only then abandons the run and releases the job for retry, in one transaction. A crash before
capture begins is anchored to the job's immutable execution snapshot without inventing evidence.

Remaining work: inject hard process death at every state transition and verify competing
recovery workers, redelivery, rollback, and restart behavior under real concurrency.
