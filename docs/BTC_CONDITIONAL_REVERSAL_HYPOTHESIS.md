# BTC Conditional Taker-Exhaustion Hypothesis

## Decision

**Rejected before holdout.** The pattern is statistically consistent but too small to
meet its predeclared economic hurdle. The sealed 2026 partition was not analyzed.

## Frozen candidate

Using 2017–2022 discovery thresholds, an event required all of:

- positive base taker-flow imbalance at or above discovery q95;
- quote-volume shock at or above discovery q90 relative to the prior 288 bars;
- range expansion at or above discovery q90 relative to the prior 288 bars;
- positive event-bar return.

The target was BTC reversal over the next 12 five-minute bars. Acceptance required at
least 100 events and a negative mean in each of 2023, 2024, and 2025; a pooled day-block
bootstrap upper bound below zero; and at least 12 bps average reversal.

## Development evidence

| Year | Events | Mean next-1h return | Reversal hit rate |
|---|---:|---:|---:|
| 2023 | 152 | -3.08 bps | 60.5% |
| 2024 | 453 | -8.21 bps | 60.9% |
| 2025 | 665 | -3.24 bps | 54.6% |

Pooled mean reversal was 5.00 bps with a 95% UTC-day block-bootstrap interval of
approximately 1.52–8.48 bps. This passed direction, sample-size, and statistical gates,
but failed the 12 bps economic gate. Its hypothesis artifact therefore has
`status: rejected` and cannot unlock the holdout.

The result may eventually be useful as a no-cost entry veto inside a separately validated
long strategy, but that is a different hypothesis and must not be inferred from this test.
