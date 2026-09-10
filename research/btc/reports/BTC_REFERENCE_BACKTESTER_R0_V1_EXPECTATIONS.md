# R0-v1 literal synthetic expectations

These expectations precede engine code. All amounts below are exact decimals in USDT and BTC;
they are not historical observations. Default step is 0.001 BTC, fee/slippage zero. Opens t0/t1/t2
are 2020-01-01 00:00/01:00/02:00 UTC. Default buy decision and availability are t0+30 minutes;
default sell decision and availability are t1+30 minutes. Initial state is cash 1000, BTC 0.
At t0 every valid case emits hold with equity 1000. Each listed state is (cash, BTC, equity).

| Case | Inputs | Expected t1; expected t2 |
|---|---|---|
| Flat | Opens 100,100,110; no orders | (1000,0,1000); (1000,0,1000) |
| Profit | Opens 100,100,110; buy 2, sell 2 | (800,2,1000); (1020,0,1020) |
| Loss | Opens 100,100,90; buy 2, sell 2 | (800,2,1000); (980,0,980) |
| Fees | Opens all 100; buy 2, sell 2; fee 10 bps | (799.8,2,999.8); (999.6,0,999.6); cumulative fee 0.2 then 0.4 |
| Primary costs | Opens all 100; buy 2, sell 2; fee 10, slip 5 bps | (799.6999,2,999.6999); (999.4,0,999.4); fees 0.2001 then 0.4; implicit 0.1 then 0.2 |
| Stress costs | Opens all 100; buy 2, sell 2; fee 10, slip 10 bps | (799.5998,2,999.5998); (999.2,0,999.2); fees 0.2002 then 0.4; implicit 0.2 then 0.4 |
| Severe costs | Opens all 100; buy 2, sell 2; fee 20, slip 20 bps | (799.1992,2,999.1992); (998.4,0,998.4); fees 0.4008 then 0.8; implicit 0.4 then 0.8 |
| Rounding | Opens all 100; requested buy 2.009; step 0.01; no sell | (800,2,1000); (800,2,1000); unused requested quantity 0.009 |
| Insufficient cash | Opens all 100; buy 11; no sell | rejected insufficient_cash (1000,0,1000); hold (1000,0,1000) |
| Allocation | Opens all 100; buy 3; no sell | rejected allocation (1000,0,1000); hold (1000,0,1000) |
| Delayed availability | Opens 100,100,110; buy 2 available t1+1 second; no sell | hold (1000,0,1000); filled (780,2,1000) |
| Equality | Opens 100,100,110; buy 2 decision/availability exactly t1; no sell | hold (1000,0,1000); filled (780,2,1000) |
| Terminal mark | Opens 100,100,110; buy 2; no sell | (800,2,1000); (800,2,1020); no exit fee |
| Expiry | Opens all 100; buy decision/availability t2; no sell | hold (1000,0,1000); expired (1000,0,1000) |
| Oversell | Opens all 100; buy 2, request sell 3 | (800,2,1000); rejected inventory (800,2,1000) |
| Partial exit | Opens 100,100,110; buy 2, sell 1 | (800,2,1000); (910,1,1020) |
| Rounded zero | Opens all 100; buy 0.0001; no sell | rejected zero_quantity (1000,0,1000); hold (1000,0,1000) |

Primary-cost hand calculation: buy fill 100.05, debit 200.1+0.2001=200.3001.
Sell fill 99.95, credit 199.9-0.1999=199.7001. Loss 0.6 equals fee 0.4 plus implicit 0.2.
No costs are deducted twice. Stress/severe losses are respectively 0.8 and 1.6.

Input rejection cases produce no ledger: duplicate t1; reversed t2/t1; missing t1 (both with
and without a requested position); naive/non-UTC/invalid-date timestamp; availability before
decision; decision before t0 or after t2; zero/negative/nonfinite price; numeric float amount;
negative quantity; nonpositive step; fees/slippage outside range; two orders mapping to one open.
Also test a second buy while holding (rejected existing_position, state unchanged).
Changing only t2's price must leave t0/t1 emissions unchanged. Independently check event cash and
inventory identities in all valid cases, including rejected/expired orders.
