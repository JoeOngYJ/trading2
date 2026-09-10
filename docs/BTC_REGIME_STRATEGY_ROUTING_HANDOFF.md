# BTC Regime Routing Session Handoff

Updated: 2026-08-29 01:25 UTC  
Program: `btc-regime-strategy-routing-v1`  
Current stage: `S5` — **blocked; zero accepted strategy arms**  
Actionable route: `no_trade` only

## Completed evidence

S0 established immutable offline routing contracts, the initial arm registry, a chained
decision log, deterministic counterfactual ranking, and the fail-closed context validator. S1
then built the shared causal 5m, 4h, and daily ledger on the exact checksummed 2017–2025
development source. It emitted point-in-time feature observations and adapted the unchanged
120-bar entry / 60-bar exit fixed breakout to the generic arm interface.

The S1 runner reproduced all frozen legacy results exactly at 30, 40, and 80 bps round-trip
costs. At the primary 30 bps cost, 67 filled trades returned 16.94% at the frozen 10% allocation,
with 2.26% CAGR, 5.02% maximum drawdown, and 0.450 Calmar. A second isolated run produced
byte-for-byte identical core outputs. This is development reproduction and infrastructure
evidence only; it is not chronological validation or strategy-promotion evidence.

The BTC trend evidence registry records 2017–2025 as consumed development evidence and the
January–July 2026 partition as `sealed_ineligible`. No S1 code read that partition. No risk or
regime model was fitted, no breakout or execution parameter changed, and no partial OB0,
network, database, NATS, Freqtrade, container, production signal, order-intent, or position
interface was accessed.

Latest stable checksums:

- S1 frozen contract: `9a2000c6f2685a9ae878a024fb3105e7dac8ae968a9d1216b66d8cf3b7122f1d`;
- S1 evidence manifest: `5a99488be5dd8fac7b5d1628a3335fc9fb3548745cdb0269604e1d9d860af435`;
- reproduction report: `e4d631998153f2841e54f2d36ee7008a9c5874201f65ad3b8e19bb9bca2a9b61`;
- determinism verification: `c00b01dbd698d752d5dd47c2b04ecd1bf8f459e98c47a783ec36e710969ca162`;
- evidence-boundary registry: `041b1966ede73129e9a33f7469b9e24d441ae39452a4babddb87abc47b56fca8`;
- final S1 decision record: `03bb6e881ae917ee98101bd3b63a605cc2f3084c167e6b74f49737bd870a4232`.

The official S1 artifacts are under
`artifacts/agent-level-experiment/btc-regime-routing/s1-ledger-v1/`. The isolated replay remains
under `artifacts/agent-level-experiment/btc-regime-routing/replays/s1-replay-Ilirmk4u/` because
the environment refused destructive cleanup; it is verification evidence, not a new experiment.

## Completed S2 decision

S2 was frozen and activated before any EWMA or scaled-performance output was computed. Its
contract checksum is
`ee1037b07c3b829a74c36350d2118fd7ec3dd80b9f7f699250bda33b267e339a`.
It may consume only the checksummed S1 daily-feature, five-minute-candle, trade, report and
manifest artifacts. The evidence boundary is versioned rather than rewriting S1; v2 checksum
`f3736036b628c97cc7eb635ec6815f571c49564469c168821d54bc6a02364af1`
retains 2026 as sealed-ineligible.

The primary estimate uses lambda 0.94, 30 consecutive same-segment returns and a 40% annualized
BTC volatility target. It is sampled only at the unchanged breakout decision and fixes quantity
until the existing S1 exit. Unknown risk produces a zero-sized locked cohort. Allocation can
never exceed 10%, and all executable output remains prohibited. Standalone forecast evaluation,
coverage, exposure-matched attribution, path-safe statistics and the predeclared one-at-a-time
sensitivities were mandatory. Results could not select a replacement parameter.

The first frozen gate rejected S2. Only 62 of 67 locked opportunities had a usable estimate
(92.54% versus the 95% requirement); 2019 reached 83.33% and 2021 reached 75%, below the 90%
annual floor. All five exclusions followed same-segment resets and lacked the frozen 30 returns.
The runner stopped before forecast diagnostics, PnL, cost comparisons or sensitivities, so no
economic conclusion was observed. The result is documented in
`docs/BTC_REGIME_ROUTING_S2_RESULT.md`.

Latest S2 checksums:

- evidence manifest: `03613b92340a98c030da01d2935dbd524b94caf35647b509ba135c181aed0c72`;
- coverage report: `632015c6db32728c552faee0952316ab27c0165da3087b1b6474d48048f5c2d4`;
- determinism verification: `a63bb98043f3eb49d86f63efca5cad1a1d7b937b472c8c9b72f491f279a1eb3f`;
- final S2 decision record: `d916ad9ddeb5be0b5781a91eb94abe948e5dd0420ca054355458a915b2662658`.

## Completed S2 daily-data provenance audit

After the S2 coverage rejection, a separately frozen data-only audit acquired the 101 official
Binance BTCUSDT monthly daily archives for August 2017 through December 2025. Every archive
matched its official checksum sidecar, and the resulting 3,059-row UTC daily series is continuous.
No EWMA forecast or strategy return was calculated.

All 3,024 direct daily closes overlapping S1 matched exactly, and the five observations excluded
by S2-v1 had 591, 1,070, 1,477, 1,523 and 2,065 consecutive completed daily returns. The audit's
strict exact-OHLC gate nevertheless rejected the source because three 2017 opens differ between
Binance's official 1d and aggregated official 5m archives. Nineteen volume diagnostics also
differ, confirming that the official interval archives are not exact resamplings of one another.

The audit does not alter or reactivate S2-v1. Latest audit checksums:

- frozen audit contract: `7df2b16ef31384cb1a1294216023e5dc4344264a5845249fd157980e789f3224`;
- source manifest: `a68ebc20c3da63c6ff7b563981fa88c272f50a771714b49b505973b43fa929ea`;
- deterministic direct-daily ledger: `b47b32f0f64371108d947fcb1b0656170dc728d81442accdf52808c2f95fba12`;
- audit report: `695fbecb60978010739f2add729b66dbe57558e357396f90d40e5f1810323e0e`;
- audit manifest: `417ac403fd06d71af9fd9c62e3d677065de8452f254c57cd7bcb9f3f10ea849d`;
- final audit decision record: `a7a80547a6ab417247f90442833bc9f2f852512cfbe6dee3aaf0a7460eec9a40`.

The result is documented in `docs/BTC_REGIME_ROUTING_S2_DAILY_DATA_AUDIT_RESULT.md`.

## Completed S2 successor

The user authorized `btc-regime-routing-s2-ewma-v2` after the audit. Its contract was frozen
before any forecast or PnL output. The only conceptual change from rejected S2-v1 is that causal
close-to-close returns come from the checksummed continuous official daily ledger rather than
being reset at five-minute execution-data segment boundaries. All EWMA parameters,
initialization, allocation mapping, opportunity path, coverage and economic gates, controls,
costs, statistics and safety restrictions are unchanged.

- frozen S2-v2 contract: `11d0d0ba1ccca6460c52c83a287d6b897f4dadb899cf81c8df733d7de6fb5efd`;
- activation decision record: `f46d885d4c85d951026dc6ebf70279563cdbd0556c878018baa57583827dd027`.

S2-v2 reached 67/67 causal opportunity coverage and beat the expanding-variance control on
one-day QLIKE. At 30 bps the scaled breakout returned 18.75% with 3.28% maximum drawdown and
0.758 Calmar, versus 16.94%, 5.02% and 0.450 for fixed 10%. At 80 bps it returned 15.61%, 3.68%
and 0.569, versus 13.01%, 5.62% and 0.314. It also beat the 8.47% capital-time-matched control.
Every predeclared development overlay gate passed, including best-three-month neutralization.

The paired monthly EWMA-minus-fixed return intervals cross zero at both required costs, so the
incremental return remains uncertain and is not promotion evidence. An isolated replay was
byte-identical. Latest S2-v2 checksums:

- evidence manifest: `0b10e3ce5f99bbfac0fa95e305c2f81cecfd0f98556a6e9b17123eaa75a2b4b1`;
- report: `15effc218435e6388edde2b30349a078b942205eabed8ae070a6ffa7ea7ce30e`;
- EWMA observations: `ba313ab08695acc0ca906ce8682fdda85ff3e3f94489335804a027f9bb3d22c5`;
- opportunity allocations: `24445abf6b10ab49e25d94c0e483727554944072f8e8f7fa666e36989d16896b`;
- simulation trades: `ca980bca5247cd854d432e6f6f13c73ff2d53726f39ee79c99e6b8ca9c2decf3`;
- determinism verification: `6aa819163db15514b3aa0712755cf068c4233c4a0496efe386a356d4b45db682`;
- final S2-v2 decision record: `6bb6f27113a702a7468898fa27c625638e5746e46c2009924a1f3387ad03974c`.

The result is documented in `docs/BTC_REGIME_ROUTING_S2_V2_RESULT.md`. It freezes EWMA as the
mandatory simple control; it does not validate or promote the breakout.

## Completed S3 decision

The user separately authorized S3. Before any HMM feature, state, forecast, or PnL output was
read, `btc-regime-routing-s3-student-t-hmm-v1` froze four daily risk-only features, a
two-state diagonal Student-t emission model with five degrees of freedom, monthly expanding
refits, past-only median/MAD scaling, forward-only daily filtering, canonical state labels, and
a continuous multiplier from 50% to 100% of the exact S2 EWMA allocation. Open and volume are
prohibited inputs; the checksummed daily high, low, and close fields are sufficient.

The pre-output implementation review rejected v1 because the downside label and block-bootstrap
construction were not exact enough to execute deterministically. No research output had been
generated. The immutable successor `btc-regime-routing-s3-student-t-hmm-v2` inherits every model,
feature, mapping, control, cost, gate and safety value from v1 and adds only exact calculation
semantics for forward labels, convergence, forward-filter initialization, dwell accounting, and
month-block uncertainty.

Standalone occupancy, transition, dwell, flicker, next-seven-day risk separation, convergence,
label-stability, coverage and causality gates must be evaluated before overlay economics. The
overlay must then beat the frozen EWMA control under the predeclared 30/80 bps gates. S4 is
eligible only if forward-risk separation passes but dwell, flicker, or transition stability
fails. Every actionable route remains `no_trade`.

- frozen S3 base contract: `ed577f204387fff3b2df8d55e91bf74956eb5e9212db36e273d1dd4673941ec4`;
- frozen S3 successor: `032fac4fc2201ba6b30a32c4ebceab74a0ec25bdfc05ede4e1e557bb3ab4afee`;
- active successor decision record: `0cb458d00a83b5515af2d0e5f7da689d2e3a523096e35f7ab38fdd12f1f913a2`.

All 84 monthly refits converged with stable canonical labels. Ordinary/stress occupancy was
57.68%/42.32%; the path had 148 transitions, 12/11-day median dwell, a 6.71% one-day-run
fraction, and fresh causal state coverage for all 67 locked breakout opportunities. Stress minus
ordinary next-seven-day realized variance was `0.0056554`, with a wholly positive 95% month-block
interval `[0.0016699, 0.0103558]`.

The downside-loss difference was positive at `0.0043704`, but its frozen interval
`[-0.0054277, 0.0148960]` crossed zero. The standalone separation gate therefore failed. The
runner stopped before all PnL and cost simulations. An isolated replay reproduced all seven core
files byte-for-byte. S4 is skipped because the HMM passed transition/dwell stability but failed
forward-risk separation; do not tune this model or build the jump model.

- evidence manifest: `26e2d619d65e6e0d76b71a065a926bc702485dac3810e9cde8782523779ede59`;
- report: `fc9d41b0d2f3652d32678194a3079ec57516f92b120a225f73b4fcd71bc2a45b`;
- determinism verification: `25fed6c1a365d0577cc80a7a16b7dc86cf0f864a32ddc48b5a719fa169e637a5`;
- final S3 decision record: `e5c1e545a4e5209a0f4a0718d88cecb5f02dfcecc39dbda129729f418bfc7839`;
- S4 skip decision record: `e1fdd5e1579b60943f852d74dae04c665c7e56f0fd2d87ca75862f1a6ba81e75`.

The result is documented in `docs/BTC_REGIME_ROUTING_S3_RESULT.md`.

## Completed S5 breakout mechanism audit

The user separately authorized S5 and required the economic reason for a strategy to work to
remain explicit. Before any new result, `btc-regime-routing-s5-breakout-mechanism-v1` froze this
claim: persistent directional demand can continue after a completed four-hour close exceeds the
prior 20-day high, while the 10-day low and 4% stop terminate exposure when that persistence
breaks. The expected background is sustained one-way repricing; range-bound and rapidly
reversing markets are the adverse background.

This explanation is falsifiable rather than retrospective. A pre-output review sealed v1
without results because several statistical conventions were underspecified. The clarification-
only successor `btc-regime-routing-s5-breakout-mechanism-v2` inherits the complete hypothesis,
feature identity, strategy, data, costs, controls, gates and safety boundary. It fixes exact
seven-day endpoints, random eligibility, percentile, tercile, bootstrap and concentration
semantics before output. The audit must compare breakout
entries with year-count-matched random seven-day entries and must show that a causal 20-day
directional-efficiency measure improves net trade expectancy. It also freezes cost, calendar
year, exit-reason, trade/month concentration and month-block uncertainty gates. The contract
checksums are `804c5dd2b8a296ed0de1a39976a5980be6135b3f1a81c1169e8835151c16d6b7`
(base) and `227abb65e8f148808c2e3061f377001b5242a4df42937e18dd79812f84d82658`
(successor); the active successor decision digest is
`e038044aa01eb4910aeb4a62f933ae94e739af7ac7a954cebc28313e402be402`.

The audit rejected the complete development mechanism. Conditional efficiency attribution
passed: at 30 bps, 12 high-efficiency trades averaged `+6.9275%` on allocated capital versus
`-1.8539%` for seven low-efficiency trades; the high-minus-low month-block interval was
`[+1.8603%, +15.3525%]`, and high-efficiency expectancy remained positive at 80 bps. Cost,
calendar-year and concentration gates also passed.

The independent entry-timing falsifier failed. Sixty-three filled entries with valid seven-day
returns averaged `+1.0687%` in log terms versus `+0.9456%` for the seeded year-count-matched
random control. The breakout ranked at the `54.31st` percentile of 5,000 replications, far below
the frozen `95th`-percentile minimum. The conditional association is hypothesis-generating only;
do not turn it into a post-result efficiency filter or tune the breakout.

The breakout remains a counterfactual development control. There are no accepted strategy arms,
so S5 is blocked and S6 is not permitted. Every actionable route stays `no_trade`.

## Parallel order-book provider audit

The separately frozen, data-only `btc-order-book-cryptolake-sample-audit-v1` downloaded and
checksummed exactly three explicitly public Binance spot BTC-USDT sample files: book and trades
from 2022-10-01 and `book_delta_v2` from 2024-04-01. The files matched their declared object
metadata, but the audit rejected both adapter-fixture and native-replay acceptance. Their actual
schemas differed from the frozen documented contract, every file declared `contains_gaps=Yes`,
and the delta lacked native `U/u`, snapshot/message typing, incident locations, and a same-period
snapshot/delta/trade bundle.

Do not use these samples for OB0, OB1, features, or strategy evidence, and do not purchase Crypto
Lake history on this evidence. The evidence manifest checksum is
`af711e298fd8972a40b376a0617a7621a49da8ceeb8f573c3419fa3e8649b3b0`; the result is documented
in `docs/BTC_ORDER_BOOK_CRYPTOLAKE_SAMPLE_AUDIT_RESULT.md`. This parallel data-engineering result
does not change the S5 block, open sealed 2026, inspect partial OB0, or authorize S6.

The public CryptoHFTData source was separately frozen and checked on its documented pre-2026
Binance spot example hour. V1 correctly remains rejected under its overly strict exchange-time
partition rule; V2 preserved the same bytes and made receipt time the partition/availability
clock. V2 still rejected the source decisively: all 1,674,190 book rows were updates, zero were
snapshots, and `last_update_id` was null throughout. Although 35,991 update groups and 170,806
trade IDs were contiguous, no absolute book could be initialized. The predeclared gate blocked
the remaining 23 hours, so no full day or 2026 data was downloaded. V2 hour-manifest checksum:
`9011e28da83633fee04384500e0bb9908c12d7c74c725ef6b268e4cdb6b1f25d`. Result:
`docs/BTC_ORDER_BOOK_CRYPTOHFTDATA_AUDIT_RESULT.md`.

The successor provider action is now frozen under `btc-order-book-tardis-raw-pilot-v1`, checksum
`85627eaf8f406ce425cb7d6ec923d0339fdcf691ed6043fc3d82d43ece76c339`. It permits only
exchange-native raw replay for 2019-12-01, 2022-12-01 and 2025-12-01, selected mechanically. The
contract remains blocked pending final OB0 acceptance and provider access. It does not authorize
a download, quote submission, purchase, normalized-CSV substitution, feature computation, or
stage change. See `docs/BTC_ORDER_BOOK_TARDIS_RAW_PILOT_PLAN.md`.

## Reproduce and verify

From `/data/Trading`, with integration connection variables unset:

```bash
.venv/bin/python scripts/download_btc_regime_routing_daily_audit.py
.venv/bin/python scripts/validate_btc_regime_routing_context.py
.venv/bin/python scripts/audit_btc_order_book_cryptolake_sample.py verify
.venv/bin/python scripts/audit_btc_order_book_cryptohftdata.py verify-hour
.venv/bin/python scripts/audit_btc_order_book_cryptohftdata_v2.py verify-hour
.venv/bin/python scripts/validate_btc_order_book_tardis_pilot_contract.py
.venv/bin/pytest -q \
  tests/test_btc_order_book_cryptolake_sample_audit.py \
  tests/test_btc_order_book_cryptohftdata_audit.py \
  tests/test_btc_order_book_cryptohftdata_audit_v2.py \
  tests/test_btc_order_book_tardis_pilot_contract.py \
  tests/test_research_breakout_mechanism.py \
  tests/test_research_hmm.py \
  tests/test_research_daily_data_audit.py \
  tests/test_research_volatility.py \
  tests/test_research_routing.py \
  tests/test_research_program.py \
  tests/test_research_evidence.py \
  tests/test_research_ledger.py \
  tests/test_research_breakout.py
env -u TEST_POSTGRES_URL -u TEST_POSTGRES_CONTAINER \
  -u TEST_NATS_URL -u TEST_NATS_CONTAINER .venv/bin/pytest -q
```

The daily downloader is allowlisted to the frozen public archive URL and checksum sidecars. On
the existing artifact root it verifies and reuses checksum-identical files and refuses a
different manifest. The offline audit output is write-once; verify its complete lineage with
the context validator rather than overwriting it. The final provider/context suite passed 37
tests, and the full isolated suite passed 324 with 29 tests skipped.

The S2-v2 official output is write-once. Reproduce it only in a new empty isolated directory:

```bash
.venv/bin/python scripts/run_btc_regime_routing_s2_ewma_v2.py \
  --output-dir artifacts/agent-level-experiment/btc-regime-routing/replays/<new-empty-directory>
```

The S3 official output is also write-once. A deterministic replay must use a new empty directory:

```bash
.venv/bin/python scripts/run_btc_regime_routing_s3_hmm.py \
  --output-dir artifacts/agent-level-experiment/btc-regime-routing/replays/<new-empty-directory>
```

The S5 official output is write-once. Reproduce the rejected mechanism audit only in a new empty
directory:

```bash
.venv/bin/python scripts/run_btc_regime_routing_s5_breakout_mechanism.py \
  --output-dir artifacts/agent-level-experiment/btc-regime-routing/replays/<new-empty-directory>
```

The S1 artifact builder is intentionally write-once and refuses a non-empty output directory:

```bash
.venv/bin/python scripts/build_btc_regime_research_ledger.py \
  --output-dir artifacts/agent-level-experiment/btc-regime-routing/s1-ledger-v1
```

Use a new empty isolated directory for a deterministic replay; do not overwrite the official
evidence.

## Blockers and next permitted action

S5 is blocked because the breakout mechanism was rejected and there are zero independently
accepted arms. S6 routing is not permitted. A future strategy study requires separate user
authorization, a materially distinct mechanism, a new frozen experiment ID, and genuinely
chronological or prospective evidence; the observed efficiency subset cannot be tuned into a
new filter. S3 remains rejected, the latent-risk branch is closed, and S4 remains skipped. Do
not use sealed-ineligible 2026, inspect partial OB0, use the rejected Crypto Lake or
CryptoHFTData samples, alter prior artifacts, or connect this work to production runtime paths.
The next permitted L2
provider action after final OB0 acceptance is the exact frozen Tardis raw pilot and dated quote;
payment still requires separate approval. Forward collection remains the fallback.
