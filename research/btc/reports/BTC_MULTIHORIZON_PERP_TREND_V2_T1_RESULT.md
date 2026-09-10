# BTC multi-horizon perpetual trend v2 — T1 result

Decision: **synthetic implementation passed; one frozen historical run is permitted**  
Historical rows/returns accessed: **zero**  
Actionable arm: `no_trade`

V1 is closed before strategy evaluation because its volatility wording did not uniquely determine
the sampling series, initialization and update. V2 changes no hypothesis or economic parameter;
it binds daily completed closes, 20-return variance initialization, lambda-0.94 recursion,
component normalization, risk scaling, funding sign, sizing/reversal accounting, random control,
margin stress and gap reset exactly.

Fifteen T0/T1 tests pass. The independent synthetic audit confirms the EWMA arithmetic, rising-
price direction, strict +/-0.25 flat boundary, positive-funding long-pay/short-receive convention,
two-sided reversal turnover, deterministic local random control, 50% adverse stress direction,
fail-closed no-trade output and absence of network/database/exchange imports. It accessed no
historical market row and calculated no historical strategy return.

Evidence digests:

- v2 contract: `a648590ee37521a2eb58b1388a22b050cb4a6fcb0e1d317d06e7b35851551837`;
- implementation: `ecc8d2db2ef04a15ae18d49c420daaaeb58f967e0e818021eba4d8994a8afff9`;
- focused tests: `296bd19ed4e88012aee42360da9be4b682ae6b79726868f715af5f816756b3a9`;
- independent audit: `e54d779b34a7340fa29a85a80a3e4ad07f14ee6265947e9593d9ec1474ec7cd1`;
- evidence manifest: `c37a57459579c6bba9e18162ed0d206cdb2ba8c2cee17df150ede6b7fd4aca89`.

## Next permitted action

Implement the historical runner as a thin adapter to the qualified engine, test its source and
partition bindings without opening results, then execute the complete frozen 30/40/80-bps run
once. Publish every control and gate whether favorable or unfavorable. Any formula, threshold,
horizon, weight, cost, partition or gate change requires a new experiment ID.
