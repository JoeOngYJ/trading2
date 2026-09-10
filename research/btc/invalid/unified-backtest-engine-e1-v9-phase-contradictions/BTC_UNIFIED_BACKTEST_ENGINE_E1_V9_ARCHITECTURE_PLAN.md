# BTC unified backtest engine E1-v9 architecture and identity plan

Stage: `E1-v9 preimplementation`
Experiment ID: `btc-unified-backtest-engine-e1-v9`
Actionable arm: `no_trade`

## Purpose and boundary

E1-v9 is a new clean-room implementation identity. It inherits the combined E0-v1 through E0-v4
economics, event order, accounting, failure, pair-close, lineage, and safety semantics without
change. It replaces E1-v8 only because that frozen candidate's self-referential probes did not
exercise the inherited contract. E1-v4 through E1-v8 remain immutable negative evidence and are
not implementation inputs.

This stage is an offline, synthetic, zero-capital accounting kernel only. It may not read historical
market rows or results, sealed 2026 or partial OB0 data, credentials, networks, exchanges,
databases, NATS, Freqtrade, production or soak services. It contains no strategy, performance
metric, router, `SignalPayload`, `OrderIntent`, paper execution, or live execution. The only
actionable arm is `no_trade`.

The blind oracle boundary remains: implementer-readable files identify fixture categories and
inputs but contain no expected numerical terminal outputs. A reviewer independently derives those
values only after the candidate snapshot is immutable.

## Frozen identity and clean room

Implementation may start only after independent preflight PASS, at exactly:

- `src/trading_platform/btc_accounting_state_machine_e1_v9.py`;
- `research/btc/tests/test_btc_accounting_state_machine_e1_v9.py`;
- `research/btc/candidates/unified-backtest-engine-e1-v9/`.

The implementer may read accepted E0-v1–v4, this V9 plan/contract, and exact authorities. The
implementer must not open, search, read, import, execute, copy, diff, summarize, or repair any
invalid/prior E1 artifact, snapshot, result, qualification, or reviewer oracle. Failure or mutation
after freeze requires archiving exact bytes and a new experiment ID.

## Architecture fixed before code

### Authority-verified construction

The sole constructor is an `AuthorityVerifiedFactory`. It consumes role-labelled exact byte
documents and creates an immutable `AccountingStateMachine` only after strict parsing and
internally deriving and matching the manifest-bound hashes for implementation, snapshot,
contract, execution configuration, selected mandate, instrument rules, margin rules, sources, and
semantic run settings. Callers cannot pass, replace, or override any digest, path, scenario fee,
fee asset, margin value, source lineage, or implementation identity. The active and snapshot
module bytes must be identical. Binding attributes and phase are read-only after construction.

The selected execution scenario supplies fee asset, explicit fees, implicit cost, protection, and
severe assumptions. Public order APIs accept quantities and qualified observations, never an
arbitrary fee, tax, implicit rate, or cost. Unsupported tax/base/third-asset treatment fails closed
unless its exact effective authority permits and values it. Each source/rules/margin role is bound
transitively on every applicable row.

### Canonical event state machine

The engine owns a monotone UTC clock, unique IDs, segment, and this exact phase progression:

1. validate expected cadence, boundary, segment and gap;
2. mark the observed open, test immediate liquidation, then allow protective reductions only;
3. process ordinary exits;
4. settle funding from the engine-owned t-minus position snapshot;
5. apply risk permissions;
6. form decisions and submit eligible next-open entries;
7. checkpoint margin/liquidation after every committed fill;
8. observe intrabar adverse risk, preserve close-to-close PnL attribution, and mark the close;
9. reconcile and emit the account row.

Direct public fill/funding/decision calls cannot bypass this progression. Phase zero, duplicate IDs,
duplicate or regressing timestamps, stale marks, caller phase mutation, ordinary phase-2 increases,
and events after terminal/liquidation reject without mutation. Phase 2 owns actual protective gap
reduction. A direct reversal is two engine-owned fills using a current qualified mark.

### Atomic pair operations

`atomic_pair_entry` and `atomic_pair_close` are first-class public operations; generic caller fill
orchestration is prohibited. Each operation owns preflight, leg order, commits, margin checkpoints,
failure recovery, rows, and disposition.

Entry preflight proves every adapter-permitted post-fee spot result and every second-leg result,
including all recovery prices, costs, fee assets, margin, rules, minimums, caps, and balances before
spot leg 1. Spot commits first; the perpetual short commits second. If the second leg rejects or
partials, the engine immediately performs the one preflighted severe spot neutralization at the
same qualified timestamp/price, or schedules the first valid in-bound safety event when the frozen
adapter requires it. The failed intention is sticky `invalid_unknown` even if flat. No naked
exposure is an acceptable completed state.

Close preserves E0-v3 spot-first semantics. Any created naked perpetual short is bought to close;
remaining pair mismatch triggers exactly one immediate, finite, non-recursive severe whole-pair
attempt with a margin/liquidation checkpoint after each commit. Failure records all commits and
becomes sticky invalid/unknown. Delayed safety owns its pending order/output/mismatch/common mark,
cannot cross segment or terminal boundary, and never searches beyond the frozen partition.

### Adapter-owned outcome universe

Candles are all-or-none at the engine-observed same-instrument open. A qualified
`DepthOutcomeUniverse` is derived by the engine from checksummed point-in-time depth rows and
adapter rules. The engine enumerates every intermediate actual post-fee spot result `R` and each
permitted perpetual result `q` for every `R`, with unique canonical set digest, endpoints, VWAP,
explicit and implicit costs, fee mutations, ticks, depth, and severe recovery. Callers provide no
domain, endpoints, recovery booleans, VWAP, cost, delay, mark, or severe-price substitutes. A valid
observed severe price worse than the frozen bound rejects before voluntary leg 1.

### Mandate and risk enforcement

Every operation and order enforces the selected mandate's exact instruments and permissions.
Spot/directional notional is capped at 25% of current eligible equity; each delta-neutral pair leg
is capped at 50%; the pair is approximately delta-neutral at 1x with mismatch inside the frozen
bound. Naked pair legs, unpermitted pyramiding, and 100% exposure reject. Daily loss blocks new
exposure at `<= -1.5%`; drawdown blocks at `<= -10%`; exact UTC reset timing is engine-owned and
protective reductions remain permitted.

### Gap, controls, outputs, and attribution

Gap handling consumes the first valid common in-bound observations, immediately executes and
records forced neutralization, retains the full observed path, marks the interval sticky invalid,
then resets segment and rolling state only after safety completion. No caller boundary boolean or
mark may substitute for evidence.

Flat, true partition-boundary buy-and-hold, and same-timestamp/same-absolute-exposure controls are
actual independent engine runs. They use the same scenario costs, eligibility times, holding and
rebalance schedule, next-open execution, partition boundary, and frozen terminal convention. The
same-exposure control replaces candidate information/direction and never copies the candidate
direction by accident. Every control emits full decision/order/fill/account/episode rows as
applicable.

The literal per-ledger field sets are those in E0-v1: decision, order, fill, funding, account, and
closed episode use the exact E0 names, including `invalidation_reason` (nullable), never a renamed
candidate-local alias. Every event chains sequential before/after state digests. Liquidation rows
bind the actual observed mark, mark source, instrument rule, margin rule, order and emitted fill
digest. Episodes contain local—not lifetime—funding, costs, PnL, MAE/MFE and correct directional or
matched-pair identity. Artifact emission derives counts, costs, summaries and digests from actual
rows; placeholders and hardcoded zeros are forbidden except when the real ledger value is zero.

## Mandatory adversarial gate

All E1-v8 A–K semantics and its 22 named probes remain mandatory, interpreted against exact E0
authorities rather than candidate-local constants. V9 additionally requires executable probes that:

- prove both atomic pair methods exist and directly exercise entry spot-first, second-leg failure,
  forced recovery, committed rows, and sticky `invalid_unknown`;
- reject public phase-zero fill/funding/decision, ordinary phase-2 entry, phase mutation,
  duplicate/regressing ID or time, stale-mark reversal, post-terminal events, and post-liquidation
  funding;
- execute actual phase-3 exits and phase-2 gap protection;
- reject zero or arbitrary scenario costs, unauthorized fee/tax assets, 100% exposure, wrong
  instrument, naked pair legs, non-1x pairing, pyramiding, binding mutation, and unbound
  source/rules/margin lineage;
- reject a caller endpoint-only depth universe, invalid tick/VWAP/implicit/severe economics,
  caller recovery booleans, and an observed severe path worse than its frozen bound;
- perform immediate finite mismatch recovery and verify the full delayed-safety state and boundary;
- flatten an exposed gap with full ledgers, sticky invalidation, and post-safety reset;
- verify flat, buy-and-hold, and same-exposure controls have real fills/accounts, exact scenario
  costs, eligibility schedule, exposure, and next-open/terminal behavior;
- compare every ledger's exact field set to the literal E0 set, verify sequential liquidation
  digest chaining and transitive observed lineage, verify matched-pair direction/episode attribution,
  and derive artifact counts/costs/digests from emitted rows.

Preflight also verifies strict Decimal/canonical JSON, duplicate/nonfinite/key-collision rejection,
all complete negative archive sets, absent V9 implementation/test/snapshot paths, blind-oracle
separation, and `no_trade`. No code begins before independent PASS.
