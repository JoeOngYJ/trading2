# Point-in-Time Universe and Research-Evidence Contract

**Status:** P1 implementation foundation  
**Effective:** 2026-08-26  
**Scope:** offline universe membership, development/evaluation partitions, holdout locks,
inspection contamination, and prospective evidence

## Purpose

A backtest cannot claim an unseen result merely because a file is named `holdout`, and it
cannot claim cross-sectional selection alpha when the historical eligible set was inferred
from assets that survived into the present. This contract makes both conditions explicit
and machine-verifiable.

```text
checksummed source evidence -> gap-free eligible/ineligible/unknown timeline
                            -> decision-time eligible snapshot

frozen strategy family -> chronological partitions + label embargo
                       -> inspection ledger -> clean/contaminated audit
                       -> locked collection -> explicit analysis unlock
```

Unknown evidence fails closed. It is never converted to `ineligible`, dropped from a
denominator, forward-filled, or inferred from the presence of an OHLCV file.

## Point-in-time universe timeline

The `research-universe-timeline-v1` schema declares:

- one versioned universe, venue and quote asset;
- a frozen inclusion rule and whether that candidate-selection rule is itself
  point-in-time defensible;
- a closed-open UTC coverage interval;
- the complete candidate-pair set;
- checksummed source-evidence records; and
- gap-free, non-overlapping status intervals for every candidate pair.

Each status is one of:

- `eligible`: source evidence establishes that the pair met the frozen inclusion rule;
- `ineligible`: source evidence establishes that it did not; or
- `unknown`: the required evidence is unavailable or ambiguous.

Both `eligible` and `ineligible` require one or more evidence IDs. `unknown` requires an
explicit reason. The loader verifies evidence checksums, rejects evidence observed after
the contract freeze, requires every pair timeline to tile the declared coverage exactly,
and rejects naive/non-UTC timestamps, gaps, overlaps and out-of-bound intervals.

`eligible_pairs(timestamp)` raises an error when any candidate is unknown or when the
candidate-selection rule was post hoc. This is intentional: silently excluding unknown
assets—or proving listing status only for seven survivors chosen later—would recreate
survivorship and listing bias. A diagnostic caller may request an incomplete snapshot
explicitly, but such a result is not eligibility or promotion evidence.

The current top-two declaration is
`config/research/multi-asset-top2-universe-timeline-v1.json`. It records all seven histories
as `unknown` because R0 did not have a frozen historical membership source. Candle presence
is useful price evidence but is not proof of the universe rule or point-in-time venue rules.
The inherited fixed-seven candidate rule is also marked post hoc; historical listing proof
for those seven alone would therefore still be insufficient.

## Research partitions and contamination

The `research-evidence-boundaries-v1` schema declares:

- strategy-family identity and freeze time;
- forecast/label horizon and minimum embargo;
- chronological, non-overlapping partitions;
- role, state and permitted access purpose for each partition; and
- every known inspection of the family, including its time coverage and information scope.

Partition roles are `development`, `evaluation`, `prospective_validation`, or `excluded`.
Access states are `open`, `locked`, `consumed`, or `contaminated`.

A genuinely unseen partition must:

1. have an evaluation or prospective-validation role;
2. remain locked;
3. observe at least the label-horizon embargo after the previous partition; and
4. have no overlapping inspection by the same strategy family or a global inspection.

An inspection is family-wide. Changing an experiment ID, score threshold, repository, or
filename does not erase it. Once results from an interval have influenced the family, that
interval cannot later become its clean holdout.

Locked prospective collection is distinct from analysis. The registry can authorize
sealed collection during the frozen interval without authorizing outcome inspection.
Analysis requires a separately reviewed contract revision that explicitly opens the
partition after its end/minimum-event criteria pass. An open evaluation must carry the
checksum of its prior locked registry, the frozen experiment checksum, unlock time,
observed-event count, and a one-time-analysis declaration. This prevents someone from
creating an already-open “holdout” after seeing the data. Analysis authorization verifies
both referenced files, proves the prior partition was locked and clean, and rejects changes
to its role, dates, minimum event count or lock time. Contaminated partitions have no
permitted purpose in the current top-two registry.

## Current top-two boundary

`config/research/multi-asset-top2-evidence-boundaries-v1.json` records:

- 2021–2025 as consumed development evidence;
- the prior repository's inspection through May 2026;
- the causal reconstruction and R0 inspection of 2021–2025; and
- January–August 2026 as excluded/contaminated for this family.

There is no clean unseen top-two partition today. The code therefore reports
`evidence_not_ready_fail_closed`. This is the expected safe result, not a validator failure.

## Prospective workflow

Before adding a prospective partition:

1. create a new experiment and universe version;
2. replace unknown membership intervals with checksummed evidence-backed status intervals;
3. freeze the strategy, code digest, cost scenarios, universe rule and minimum event count;
4. set the prospective start after at least the 48-hour label embargo;
5. give the locked partition `collection` permission but not analysis access;
6. seal observations and record every inspection attempt; and
7. open it once only after the frozen end/event rule and an explicit review pass.

The R0 minimum of 60 filled events remains a floor for a new top-two validation. At the
historical frequency this could take several years, which is a practical reason not to
represent this strategy as near promotion. A materially redesigned family requires its own
sample-size and forward-evidence plan; it may not borrow the top-two result.

## Reproduction

Validate the current declarations without external services:

```bash
PYTHONPATH=src:. .venv/bin/python scripts/validate_research_evidence_contracts.py \
  --universe config/research/multi-asset-top2-universe-timeline-v1.json \
  --partitions config/research/multi-asset-top2-evidence-boundaries-v1.json \
  --output-dir artifacts/agent-level-experiment/multi-asset-top2/p1-evidence-contract-v1
```

The runner only accepts contracts under `config/research/`, writes beneath the isolated
research artifact root, refuses overwrite of a non-empty output, and uses no network,
database, NATS, Freqtrade, exchange, or L2 service.

Implementation and evidence:

- `src/trading_platform/research_evidence.py`;
- `scripts/validate_research_evidence_contracts.py`;
- `tests/test_research_evidence.py`; and
- `artifacts/agent-level-experiment/multi-asset-top2/p1-evidence-contract-v1/`.

## What this completes—and what it does not

P1 now has reusable enforcement for point-in-time membership, source checksums, coverage
gaps, label embargoes, access state, inspection contamination, and locked prospective
collection. The current data still lacks the evidence needed to pass the contract, and no
clean prospective partition has been frozen or collected. The infrastructure is
implemented; the missing evidence must not be replaced with assumptions.
