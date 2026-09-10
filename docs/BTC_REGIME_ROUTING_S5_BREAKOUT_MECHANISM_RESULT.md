# BTC Regime Routing S5 Breakout Mechanism Result

Decision: **development mechanism rejected; S5 blocked**  
Experiment: `btc-regime-routing-s5-breakout-mechanism-v2`  
Evidence class: consumed 2019–2025 development evidence only  
Actionable arm: `no_trade`

## Why the strategy was expected to work

The frozen mechanism was directional persistence, not a claim that one rule should profit every
year. A completed four-hour close above the prior 20-day high was intended to identify sustained
repricing whose demand continued after entry. The 10-day low exit and 4% stop were intended to
end exposure when persistence failed. This should work best during efficient one-way movement
and should fail in range-bound or rapidly reversing markets. Repeated false breakouts make costs
important; a smaller number of continuation gains must pay for many stop losses.

That explanation was frozen as a falsifiable contract before new output. The audit required both
a conditional-background result and an independent entry-timing result. It could not promote the
arm because all available observations are already consumed development evidence and the 2026
partition is sealed-ineligible.

## Frozen findings

The conditional-background prediction passed. At 30 bps round-trip cost, 12 high-efficiency
entries averaged `+6.9275%` on allocated capital while seven low-efficiency entries averaged
`-1.8539%`. The high-minus-low difference was `+8.7814%`; its frozen month-block 95% interval
was `[+1.8603%, +15.3525%]`. High-efficiency expectancy remained positive at 80 bps.

The independent timing falsifier failed. Sixty-three filled entries had valid fixed seven-day
returns. Their equal-weight mean log return was `+1.0687%`, versus `+0.9456%` across the frozen
year-count-matched random control. The breakout mean ranked at only the `54.31st` percentile of
5,000 seeded random samples, far below the frozen `95th`-percentile requirement. The random
control's 95% interval was `[-1.0788%, +3.0072%]`.

The other gates passed:

- 67 filled trades exceeded the 60-trade floor and four calendar years were positive at 30 bps;
- high-efficiency expectancy was positive at both 30 and 80 bps;
- the top three profitable trades supplied 30.91% of positive trade returns, below the 50% cap;
- the best three profitable months supplied 37.32% of positive monthly PnL, below the 60% cap.

Exit attribution explains the payoff shape but does not rescue the timing claim. At 30 bps, all
20 maximum-holding exits were profitable and averaged `+14.13%`, while all 40 protective-stop
exits lost and averaged `-4.29%`. This is consistent with a positively skewed trend payoff, but
the random test shows that the prior-20-day-high event did not isolate unusually strong generic
seven-day continuation in this development sample.

## Interpretation and boundary

The evidence supports a narrower observation: directional efficiency was associated with the
historical breakout trade outcomes. It does not support the complete frozen mechanism because
the entry event failed its independent timing control. The high-efficiency subset has only 12
trades, the low subset seven, and 29 trades were unknown while the causal cutoff history warmed
up or reset. It is therefore hypothesis-generating, not permission to add an efficiency filter.
Doing so now would be a new strategy created after seeing the result and would require a new
experiment ID plus genuinely chronological or prospective evidence.

The breakout remains a development control, not an accepted strategy. There are zero accepted
arms in the routing registry, so S5 cannot pass and S6 counterfactual-router evaluation is not
permitted. No HMM or jump-model tuning, sealed-2026 access, partial OB0 access, protected-service
access, production signal, order intent, or executable position occurred.

## Reproduction

Official artifacts are under
`artifacts/agent-level-experiment/btc-regime-routing/s5-breakout-mechanism-v1/`.

```bash
.venv/bin/python scripts/run_btc_regime_routing_s5_breakout_mechanism.py \
  --output-dir artifacts/agent-level-experiment/btc-regime-routing/replays/<new-empty-directory>
.venv/bin/pytest -q tests/test_research_breakout_mechanism.py
.venv/bin/python scripts/validate_btc_regime_routing_context.py
```

The isolated replay reproduced all five core artifacts byte-for-byte. Key checksums:

- successor contract: `227abb65e8f148808c2e3061f377001b5242a4df42937e18dd79812f84d82658`;
- report: `a991d3e550aa54e4b200099769216f462b3664d074e819f9b9628fceab762919`;
- evidence manifest: `8f7faacee84fc0260ba4f27a88797eff5cd1977f1badb97ebd969c40702ac8db`;
- determinism verification: `c35bf83218f1dc0d82b015f28300584500983908e63ec62558c5c67da471e0c3`;
- final decision record: `df3d80667ce6fc71e94cc7e58a30798215fe2346f93675f7294d928298acdaeb`.

The final focused research suite passed 67 tests. The complete isolated repository suite passed
281 tests with 33 integration tests skipped because their external-service variables were unset.
