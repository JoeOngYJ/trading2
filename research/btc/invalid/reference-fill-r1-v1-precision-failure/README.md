# R1-v1 numeric domain rejection

Reviewer `/root/r1_review` found a four-fill allowed input that lost 1e-24 of equity under
precision 50. Existing three tests passed. Preserved inputs, source and tests here predate the fix.
Reproducer: buy 1 at 1; sell 1 at 999999999999999999; buy 0.000000000001 at
0.000000000001; buy 999999999999999999 at 0.000000000001 and mark at 999999999999999999.
All fees zero. The independent Fraction oracle rejects the final equity. No acceptance artifact.
Successor R1-v2 uses a proven precision-80 bound and adds this and a maximum-count regression.
No market rows or historical trades were accessed; no_trade.
