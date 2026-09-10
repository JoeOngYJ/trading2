# BTC-focused research workspace

This is the focused research namespace for the next phase. It is additive: existing `config/`,
`artifacts/`, `docs/`, `src/`, and `tests/` paths remain unchanged because their checksums and
context validators depend on them.

## Scope

- Primary market: BTC/USDT.
- Initial mandate: offline research only; actionable route remains `no_trade`.
- Existing fixed breakout and EWMA-scaled breakout are controls, not automatically accepted arms.
- One new economic mechanism per experiment ID.
- Macro inputs may be tested only as causal, downward-only risk overlays.
- ETH is deferred until a BTC mechanism passes independently.

## Layout

- `contracts/`: new BTC experiment contracts, frozen before results.
- `evaluators/`: isolated offline evaluators with no broker, exchange, database, NATS or soak access.
- `reports/`: BTC-focused result summaries and handoffs.
- `tests/`: focused tests for the new namespace.

Historical BTC contracts and evidence remain under `config/experiments/`, `config/research/`,
`artifacts/agent-level-experiment/` and `docs/` and are referenced by repository status files.

## Current disposition

Earlier BTC breakout/regime work is retained as controls and rejected/development evidence. The
next experiment must freeze a single BTC mechanism, data boundary, costs, controls and gates
before any economic output is read.
